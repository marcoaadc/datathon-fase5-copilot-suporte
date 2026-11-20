"""Relatorio de drift com o Evidently e veredito proprio por PSI.

Para cada cenario, a janela de producao simulada e comparada com a Referencia (particao de teste,
que o modelo nao viu no treino). O relatorio HTML do Evidently traz:

* ``DataDriftPreset`` sobre as features monitoradas: distribuicoes lado a lado, teste por coluna e
  a contagem de colunas com drift (com testes automaticos que ficam vermelhos quando falham);
* ``ClassificationPreset``: a qualidade do modelo na janela, ja que na simulacao o rotulo e
  conhecido. E o que liga "os dados mudaram" a "o modelo piorou".

O veredito do Evidently e resumido em JSON junto com o PSI calculado pelo detector proprio (o mesmo
do monitor da API), para que as duas medidas possam ser confrontadas.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

from supportcopilot.data.ingest import TARGET, TEXT
from supportcopilot.drift.features import CATEGORICAL_FEATURES, NUMERICAL_FEATURES, build_frame, build_profile
from supportcopilot.drift.statistics import profile_psi

PREDICTION = "predicted_queue"
PSI_METHOD = "psi"


def score_window(pipeline: Pipeline, window: pd.DataFrame, technical: tuple[str, ...]) -> pd.DataFrame:
    """Features monitoradas + rotulo real de cada chamado da janela (sem o texto)."""
    frame = build_frame(pipeline, window[TEXT], technical)
    frame[TARGET] = window[TARGET].to_numpy()
    return frame


def quality(frame: pd.DataFrame) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(frame[TARGET], frame[PREDICTION])),
        "f1_macro": float(f1_score(frame[TARGET], frame[PREDICTION], average="macro", zero_division=0)),
        "mean_confidence": float(frame["confidence"].mean()),
        "mean_oov_rate": float(frame["oov_rate"].mean()),
    }


def own_psi(reference: pd.DataFrame, current: pd.DataFrame) -> dict[str, float]:
    """PSI por feature com o detector proprio (faixas por quantis da referencia)."""
    profile = build_profile(reference)["features"]
    return {name: round(profile_psi(profile[name], current[name]), 5) for name in profile}


def run_evidently(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    psi_threshold: float = 0.10,
    drift_share: float = 0.30,
    name: str | None = None,
):
    """Executa o relatorio e devolve o ``Snapshot`` do Evidently."""
    from evidently import DataDefinition, Dataset, MulticlassClassification, Report
    from evidently.presets import ClassificationPreset, DataDriftPreset

    columns = [*NUMERICAL_FEATURES, *CATEGORICAL_FEATURES]
    definition = DataDefinition(
        numerical_columns=list(NUMERICAL_FEATURES),
        categorical_columns=[*CATEGORICAL_FEATURES, TARGET],
        classification=[MulticlassClassification(target=TARGET, prediction_labels=PREDICTION)],
    )
    report = Report(
        [
            DataDriftPreset(columns=columns, method=PSI_METHOD, threshold=psi_threshold, drift_share=drift_share),
            ClassificationPreset(),
        ],
        include_tests=True,
        tags=[name] if name else None,
    )
    keep = [*columns, TARGET]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return report.run(
            Dataset.from_pandas(current[keep], data_definition=definition),
            Dataset.from_pandas(reference[keep], data_definition=definition),
            name=name,
        )


def save_html(snapshot, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.save_html(str(path))
    # O Evidently grava com o fim de linha do sistema; LF mantem o arquivo identico entre SOs.
    content = path.read_bytes().replace(b"\r\n", b"\n")
    path.write_bytes(content)
    return path


def _status(test: dict[str, Any]) -> str:
    status = test.get("status", "")
    return str(getattr(status, "value", status)).upper()


def summarize(snapshot, psi_threshold: float = 0.10) -> dict[str, Any]:
    """Veredito do Evidently: PSI por coluna, colunas com drift e testes que falharam."""
    payload = snapshot.dict()
    psi: dict[str, float] = {}
    share: float | None = None
    for metric in payload.get("metrics", []):
        config = metric.get("config", {})
        kind = str(config.get("type", ""))
        value = metric.get("value")
        if kind.endswith("ValueDrift") and isinstance(value, (int, float)):
            psi[config["column"]] = round(float(value), 5)
        elif kind.endswith("DriftedColumnsCount") and isinstance(value, dict):
            share = float(value.get("share", float("nan")))
    drifted = sorted(column for column, value in psi.items() if value >= psi_threshold)
    tests = payload.get("tests", [])
    failed = [test.get("name", "") for test in tests if _status(test) == "FAIL"]
    return {
        "method": PSI_METHOD,
        "threshold": psi_threshold,
        "n_columns": len(psi),
        "n_drifted": len(drifted),
        "share_drifted": round(share if share is not None else len(drifted) / max(len(psi), 1), 4),
        "drifted_columns": drifted,
        "psi": psi,
        "tests_total": len(tests),
        "tests_failed": len(failed),
        "failed_tests": failed,
    }
