"""Atribuicao causal da degradacao: quanto cada mecanismo de drift responde pela queda do modelo.

O relatorio por cenario mostra que o modelo piorou e quais features mudaram; nao diz *qual* dos
mecanismos (idioma, mistura de filas, ruido, truncamento) causou a queda. Como a simulacao e
controlada, da para intervir: ligar e desligar cada mecanismo e medir.

O efeito de um mecanismo depende dos outros (ruido em cima de texto em alemao nao custa o mesmo
que ruido em texto em ingles), entao medir cada um isolado nao fecha a conta. Os **valores de
Shapley** resolvem isso: para cada mecanismo, a media da sua contribuicao marginal sobre todas as
ordens em que os mecanismos poderiam ser ligados. A soma dos quatro valores e exatamente a
diferenca entre a janela com tudo ligado e a janela de controle (propriedade de eficiencia).

Custo: 2^4 = 16 combinacoes por seed; cada combinacao e uma simulacao + uma passagem do modelo.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from itertools import combinations
from math import factorial
from typing import Any

import pandas as pd
from sklearn.pipeline import Pipeline

from supportcopilot.drift.features import NUMERICAL_FEATURES, build_frame, build_profile
from supportcopilot.drift.report import quality
from supportcopilot.drift.simulate import Scenario, simulate
from supportcopilot.drift.statistics import profile_psi

logger = logging.getLogger(__name__)

MECHANISMS: tuple[str, ...] = ("language", "prior", "noise", "truncate")
MECHANISM_TITLES = {
    "language": "Idioma (chamados em alemao)",
    "prior": "Mistura de filas (incidente)",
    "noise": "Ruido de digitacao e maiusculas",
    "truncate": "Mensagens truncadas",
}
METRICS: tuple[str, ...] = ("accuracy", "f1_macro", "mean_confidence", "mean_oov_rate", "share_drifted")


def scenario_subset(base: Scenario, active: frozenset[str]) -> Scenario:
    """O cenario ``base`` com apenas os mecanismos em ``active`` ligados."""
    return replace(
        base,
        name="+".join(sorted(active)) or "nenhum",
        language_fraction=base.language_fraction if "language" in active else 0.0,
        prior_weights=dict(base.prior_weights) if "prior" in active else {},
        noise_fraction=base.noise_fraction if "noise" in active else 0.0,
        truncate_fraction=base.truncate_fraction if "truncate" in active else 0.0,
    )


def shapley_values(value: dict[frozenset[str], float], players: tuple[str, ...]) -> dict[str, float]:
    """Valores de Shapley de uma funcao caracteristica ``value`` definida em todos os subconjuntos."""
    n = len(players)
    result: dict[str, float] = {}
    for player in players:
        others = [p for p in players if p != player]
        total = 0.0
        for size in range(n):
            weight = factorial(size) * factorial(n - size - 1) / factorial(n)
            for subset in combinations(others, size):
                without = frozenset(subset)
                total += weight * (value[without | {player}] - value[without])
        result[player] = total
    return result


def attribute(
    pipeline: Pipeline,
    reference: pd.DataFrame,
    production: pd.DataFrame,
    drift_pool: pd.DataFrame,
    base: Scenario,
    technical: tuple[str, ...],
    psi_threshold: float,
    seeds: tuple[int, ...] = (42, 43, 44),
    window_size: int | None = None,
) -> dict[str, Any]:
    """Mede todas as combinacoes dos mecanismos do cenario ``base`` e reparte a degradacao por Shapley.

    Cada combinacao e simulada ``len(seeds)`` vezes (seeds diferentes) e as metricas sao a media.
    Devolve, por metrica, o valor em cada combinacao, o valor de Shapley de cada mecanismo, o efeito
    isolado (so aquele mecanismo ligado) e a variacao total (tudo ligado menos controle).
    """
    profile = build_profile(reference)["features"]
    subsets = [frozenset(combo) for size in range(len(MECHANISMS) + 1) for combo in combinations(MECHANISMS, size)]
    values: dict[str, dict[frozenset[str], float]] = {metric: {} for metric in METRICS}
    for active in subsets:
        scenario = scenario_subset(base, active)
        runs: list[dict[str, float]] = []
        for seed in seeds:
            window = simulate(production, drift_pool, scenario, size=window_size, seed=seed)
            frame = build_frame(pipeline, window["text"], technical)
            frame["queue"] = window["queue"].to_numpy()
            metrics = quality(frame)
            drifted = sum(profile_psi(profile[name], frame[name]) >= psi_threshold for name in NUMERICAL_FEATURES)
            metrics["share_drifted"] = drifted / len(NUMERICAL_FEATURES)
            runs.append(metrics)
        for metric in METRICS:
            values[metric][active] = float(sum(run[metric] for run in runs) / len(runs))
        logger.info("atribuicao %-32s acuracia %.3f", scenario.name, values["accuracy"][active])

    everything, nothing = frozenset(MECHANISMS), frozenset()
    report: dict[str, Any] = {
        "base_scenario": base.name,
        "seeds": list(seeds),
        "rows_per_window": window_size or len(production),
        "mechanisms": list(MECHANISMS),
        "metrics": {},
    }
    for metric in METRICS:
        value = values[metric]
        shapley = shapley_values(value, MECHANISMS)
        report["metrics"][metric] = {
            "control": value[nothing],
            "all": value[everything],
            "total_change": value[everything] - value[nothing],
            "shapley": {m: shapley[m] for m in MECHANISMS},
            "isolated": {m: value[frozenset({m})] - value[nothing] for m in MECHANISMS},
            "by_subset": {"+".join(sorted(s)) or "nenhum": v for s, v in value.items()},
        }
    return report


def to_markdown(report: dict[str, Any]) -> str:
    accuracy = report["metrics"]["accuracy"]
    lines = [
        "## Atribuição causal da degradação (valores de Shapley)",
        "",
        f"Cenário `{report['base_scenario']}` decomposto nas 16 combinações dos 4 mecanismos, "
        f"{len(report['seeds'])} seeds por combinação, {report['rows_per_window']} chamados por janela. "
        f"Acurácia: controle {accuracy['control']:.3f}, tudo ligado {accuracy['all']:.3f} "
        f"(variação {accuracy['total_change']:+.3f}).",
        "",
        "| Mecanismo | Shapley (acurácia) | Isolado (acurácia) | Shapley (F1 macro) | Shapley (fora do vocab.) "
        "| Shapley (colunas em drift) |",
        "|---|---|---|---|---|---|",
    ]
    for mechanism in report["mechanisms"]:
        cells = [
            f"{report['metrics']['accuracy']['shapley'][mechanism]:+.3f}",
            f"{report['metrics']['accuracy']['isolated'][mechanism]:+.3f}",
            f"{report['metrics']['f1_macro']['shapley'][mechanism]:+.3f}",
            f"{report['metrics']['mean_oov_rate']['shapley'][mechanism]:+.3f}",
            f"{report['metrics']['share_drifted']['shapley'][mechanism]:+.2f}",
        ]
        lines.append(f"| {MECHANISM_TITLES[mechanism]} | " + " | ".join(cells) + " |")
    total = [
        f"{report['metrics'][m]['total_change']:+.3f}"
        if m != "share_drifted"
        else f"{report['metrics'][m]['total_change']:+.2f}"
        for m in ("accuracy", "accuracy", "f1_macro", "mean_oov_rate", "share_drifted")
    ]
    lines.append("| **Total (tudo ligado − controle)** | **" + "** | **".join(total) + "** |")
    return "\n".join(lines) + "\n"
