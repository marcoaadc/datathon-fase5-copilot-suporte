"""PSI (Population Stability Index) e perfis de referencia.

O perfil guarda apenas agregados (limites de faixa e proporcoes): e o suficiente para comparar a
producao com a referencia sem carregar nenhum chamado, e por isso pode ser versionado e embarcado
na imagem da API.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

EPSILON = 1e-4
OTHER = "__other__"


def psi(expected: Sequence[float], actual: Sequence[float], epsilon: float = EPSILON) -> float:
    """PSI entre duas distribuicoes discretas (proporcoes por faixa ou por categoria)."""
    expected_arr = np.clip(np.asarray(expected, dtype=float), epsilon, None)
    actual_arr = np.clip(np.asarray(actual, dtype=float), epsilon, None)
    expected_arr = expected_arr / expected_arr.sum()
    actual_arr = actual_arr / actual_arr.sum()
    return float(np.sum((actual_arr - expected_arr) * np.log(actual_arr / expected_arr)))


def numeric_profile(values: Iterable[float], bins: int = 10) -> dict[str, Any]:
    """Faixas por quantis da referencia e a proporcao esperada em cada uma."""
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        raise ValueError("perfil numerico exige ao menos um valor finito")
    edges = np.unique(np.quantile(array, np.linspace(0, 1, bins + 1)[1:-1]))
    if len(edges) < bins - 1:
        # Feature concentrada em poucos valores (ex.: fracao de caracteres nao ASCII, quase sempre 0):
        # os quantis colapsam. Um limite logo acima de cada valor separa "igual ao valor tipico" de
        # "acima dele"; sem isso, um salto de 0 para 0,05 cairia na mesma faixa e passaria batido.
        edges = np.unique(np.concatenate([edges, np.nextafter(edges, np.inf)]))
    return {
        "kind": "numerical",
        "edges": [float(edge) for edge in edges],
        "expected": bin_proportions(array, edges),
        "mean": float(array.mean()),
        "std": float(array.std()),
    }


def bin_proportions(values: Iterable[float], edges: Sequence[float]) -> list[float]:
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    counts = np.bincount(np.searchsorted(np.asarray(edges, dtype=float), array, side="right"), minlength=len(edges) + 1)
    total = counts.sum()
    return [float(count / total) if total else 0.0 for count in counts]


def categorical_profile(values: Iterable[str]) -> dict[str, Any]:
    counter = Counter(str(value) for value in values)
    total = sum(counter.values())
    if total == 0:
        raise ValueError("perfil categorico exige ao menos um valor")
    categories = sorted(counter)
    return {
        "kind": "categorical",
        "categories": categories,
        "expected": [counter[category] / total for category in categories],
    }


def category_proportions(values: Iterable[str], categories: Sequence[str]) -> list[float]:
    """Proporcoes nas categorias da referencia; o que nao existia la cai em uma faixa extra."""
    counter = Counter(str(value) for value in values)
    total = sum(counter.values())
    known = [counter.get(category, 0) for category in categories]
    other = total - sum(known)
    return [count / total if total else 0.0 for count in [*known, other]]


def profile_psi(profile: dict[str, Any], values: Iterable[Any]) -> float:
    """PSI de uma amostra contra o perfil de referencia da mesma feature."""
    if profile["kind"] == "numerical":
        return psi(profile["expected"], bin_proportions(values, profile["edges"]))
    actual = category_proportions(values, profile["categories"])
    return psi([*profile["expected"], 0.0], actual)
