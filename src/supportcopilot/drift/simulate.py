"""Simulacao da degradacao dos dados de producao.

Parte de chamados reais que o modelo nunca viu (particao ``production``) e aplica quatro mecanismos
de drift, cada um representando algo que acontece com um servico de suporte de verdade:

* ``language``  a operacao passa a atender outro pais: parte dos chamados chega em alemao. Sao
                chamados reais do mesmo dataset, nao texto embaralhado: e drift de covariavel
                legitimo, com rotulo conhecido, o que permite medir a queda real do modelo;
* ``prior``     incidente em massa: a mistura de filas muda (explosao de chamados de indisponibilidade
                e de cobranca), sem que o texto de cada fila mude;
* ``noise``     novo canal de entrada (chat no celular): erros de digitacao e texto em maiusculas;
* ``truncate``  integracao que corta a mensagem (widget com limite curto de caracteres).

Os mecanismos sao isolaveis: cada cenario diz quanto de cada um aplicar. Assim da para atribuir a
degradacao observada a uma causa, em vez de so constatar que "algo mudou".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from supportcopilot.data.ingest import LANGUAGE, TARGET, TEXT

MECHANISM = "drift_mechanism"
_KEYBOARD_NEIGHBORS = {
    "a": "qsz", "e": "wrd", "i": "uok", "o": "ipl", "u": "yij", "s": "adw", "t": "ryg", "n": "bmh", "r": "etf",
    "l": "kop", "c": "xvd", "d": "sfe", "m": "nk", "p": "ol", "g": "fht", "h": "gjn",
}  # fmt: skip


@dataclass(frozen=True)
class Scenario:
    name: str
    title: str
    description: str
    language_fraction: float = 0.0
    prior_weights: dict[str, float] = field(default_factory=dict)
    noise_fraction: float = 0.0
    truncate_fraction: float = 0.0
    truncate_chars: int = 70

    @property
    def is_control(self) -> bool:
        return not (self.language_fraction or self.prior_weights or self.noise_fraction or self.truncate_fraction)


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "controle",
        "Controle (sem drift)",
        "Chamados novos, da mesma distribuicao do treino. O relatorio nao deve acusar drift: e a prova de que o "
        "detector nao dispara alarme falso.",
    ),
    Scenario(
        "moderado",
        "Drift moderado",
        "Inicio da degradacao: 15% dos chamados em alemao, incidente dobrando os chamados de indisponibilidade e "
        "10% de texto com erros de digitacao.",
        language_fraction=0.15,
        prior_weights={"Service Outages and Maintenance": 2.0},
        noise_fraction=0.10,
    ),
    Scenario(
        "severo",
        "Drift severo",
        "Degradacao instalada: 45% dos chamados em alemao, incidente em massa (6x indisponibilidade, 2x cobranca), "
        "30% de texto com ruido e 15% de mensagens truncadas.",
        language_fraction=0.45,
        prior_weights={"Service Outages and Maintenance": 6.0, "Billing and Payments": 2.0},
        noise_fraction=0.30,
        truncate_fraction=0.15,
    ),
)


def get_scenario(name: str) -> Scenario:
    for scenario in SCENARIOS:
        if scenario.name == name:
            return scenario
    raise KeyError(f"cenario desconhecido: {name}")


def add_typos(text: str, rng: np.random.Generator, rate: float = 0.06) -> str:
    """Erros de digitacao: troca por tecla vizinha, omissao ou duplicacao de letras."""
    chars = list(text)
    for index, char in enumerate(chars):
        lower = char.lower()
        if not lower.isalpha() or rng.random() >= rate:
            continue
        action = rng.integers(3)
        if action == 0 and lower in _KEYBOARD_NEIGHBORS:
            chars[index] = str(rng.choice(list(_KEYBOARD_NEIGHBORS[lower])))
        elif action == 1:
            chars[index] = ""
        else:
            chars[index] = char * 2
    return "".join(chars)


def apply_noise(text: str, rng: np.random.Generator) -> str:
    noisy = add_typos(text, rng)
    return noisy.upper() if rng.random() < 0.5 else noisy


def _resample_prior(
    frame: pd.DataFrame, weights: dict[str, float], size: int, rng: np.random.Generator
) -> pd.DataFrame:
    row_weights = frame[TARGET].map(lambda queue: weights.get(queue, 1.0)).to_numpy(dtype=float)
    chosen = rng.choice(len(frame), size=size, replace=True, p=row_weights / row_weights.sum())
    return frame.iloc[chosen].reset_index(drop=True)


def simulate(
    production: pd.DataFrame, drift_pool: pd.DataFrame, scenario: Scenario, size: int | None = None, seed: int = 42
) -> pd.DataFrame:
    """Gera uma janela de producao (``size`` chamados) com os mecanismos do cenario aplicados."""
    rng = np.random.default_rng(seed)
    size = size or len(production)
    columns = [TEXT, TARGET, LANGUAGE]

    if scenario.is_control:
        chosen = rng.choice(len(production), size=min(size, len(production)), replace=False)
        window = production.iloc[chosen][columns].reset_index(drop=True)
        window[MECHANISM] = "none"
        return window

    n_foreign = round(size * scenario.language_fraction)
    if n_foreign and drift_pool.empty:
        raise ValueError("cenario com troca de idioma exige o reservatorio de drift")
    weights = scenario.prior_weights
    native = _resample_prior(production[columns], weights, size - n_foreign, rng)
    native[MECHANISM] = "prior" if weights else "none"
    parts = [native]
    if n_foreign:
        foreign = _resample_prior(drift_pool[columns], weights, n_foreign, rng)
        foreign[MECHANISM] = "language"
        parts.append(foreign)
    window = pd.concat(parts, ignore_index=True)

    # Ruido e truncamento atingem qualquer chamado, independentemente do idioma.
    draws = rng.random(len(window))
    noisy = draws < scenario.noise_fraction
    truncated = (draws >= scenario.noise_fraction) & (draws < scenario.noise_fraction + scenario.truncate_fraction)
    window.loc[noisy, TEXT] = [apply_noise(text, rng) for text in window.loc[noisy, TEXT]]
    window.loc[truncated, TEXT] = window.loc[truncated, TEXT].str.slice(0, scenario.truncate_chars).str.strip()
    window.loc[noisy, MECHANISM] = window.loc[noisy, MECHANISM].where(
        window.loc[noisy, MECHANISM] == "language", "noise"
    )
    window.loc[truncated, MECHANISM] = window.loc[truncated, MECHANISM].where(
        window.loc[truncated, MECHANISM] == "language", "truncate"
    )
    return window.sample(frac=1.0, random_state=seed).reset_index(drop=True)
