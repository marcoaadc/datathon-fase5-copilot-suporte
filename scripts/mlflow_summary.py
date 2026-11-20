"""Exporta um resumo do que esta registrado no MLflow para ``reports/mlflow/summary.md``.

O banco do MLflow (``mlflow.db``) e os artefatos nao sao versionados. Este resumo, sim: ele deixa no
repositorio a evidencia do rastreamento (experimentos, runs, parametros, metricas, artefatos e
versoes no Model Registry) para quem nao vai subir o servidor.

Uso:  COPILOT_MLFLOW_TRACKING_URI=http://127.0.0.1:5000 python scripts/mlflow_summary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mlflow.tracking import MlflowClient  # noqa: E402

from supportcopilot.config.settings import get_settings  # noqa: E402
from supportcopilot.pipelines.drift_report import DRIFT_EXPERIMENT_SUFFIX  # noqa: E402

TRAIN_METRICS = ("val_accuracy", "val_f1_macro", "val_log_loss", "val_routing_f1", "fit_seconds")
FINAL_METRICS = (
    "test_accuracy", "test_f1_macro", "test_f1_weighted", "test_log_loss", "test_ece", "test_routing_precision",
    "test_routing_recall", "test_routing_f1", "majority_class_accuracy",
)  # fmt: skip
DRIFT_METRICS = (
    "share_drifted",
    "n_drifted",
    "tests_failed",
    "accuracy",
    "f1_macro",
    "mean_confidence",
    "mean_oov_rate",
)


def _artifacts(client: MlflowClient, run_id: str, path: str | None = None) -> list[str]:
    found: list[str] = []
    for item in client.list_artifacts(run_id, path):
        found.extend(_artifacts(client, run_id, item.path) if item.is_dir else [item.path])
    return found


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}".rstrip("0").rstrip(".")


def build() -> str:
    settings = get_settings()
    if not settings.mlflow_tracking_uri:
        raise SystemExit("defina COPILOT_MLFLOW_TRACKING_URI")
    client = MlflowClient(settings.mlflow_tracking_uri)
    lines = [
        "# Resumo do rastreamento no MLflow",
        "",
        f"Extraido do servidor `{settings.mlflow_tracking_uri}` por `scripts/mlflow_summary.py`.",
        "",
    ]

    experiment = client.get_experiment_by_name(settings.mlflow_experiment)
    if experiment is None:
        raise SystemExit(f"experimento {settings.mlflow_experiment} nao encontrado")
    runs = client.search_runs([experiment.experiment_id], order_by=["attributes.start_time ASC"])
    parents = [run for run in runs if "mlflow.parentRunId" not in run.data.tags]
    children = [run for run in runs if "mlflow.parentRunId" in run.data.tags]
    lines += [
        f"## Experimento `{experiment.name}`",
        "",
        f"{len(parents)} run de treino e {len(children)} runs aninhados (um por candidato).",
        "",
        "### Candidatos avaliados na validacao",
        "",
        "| Run | Familia | Parametros | " + " | ".join(TRAIN_METRICS) + " |",
        "|---|---|---|" + "---|" * len(TRAIN_METRICS),
    ]
    for run in sorted(children, key=lambda item: item.data.metrics.get("val_f1_macro", 0), reverse=True):
        params = ", ".join(f"{key}={value}" for key, value in sorted(run.data.params.items()) if key != "family")
        metrics = " | ".join(_fmt(run.data.metrics.get(name)) for name in TRAIN_METRICS)
        lines.append(f"| `{run.info.run_name}` | {run.data.params.get('family', '-')} | {params} | {metrics} |")

    for parent in parents:
        lines += [
            "",
            f"### Run de treino `{parent.info.run_name}` (`{parent.info.run_id}`)",
            "",
            f"Status: {parent.info.status}. Vencedor: `{parent.data.params.get('winner')}`.",
            "",
            "| Parametro | Valor |",
            "|---|---|",
        ]
        lines += [f"| `{key}` | {value} |" for key, value in sorted(parent.data.params.items())]
        lines += ["", "| Metrica (teste) | Valor |", "|---|---|"]
        lines += [f"| `{name}` | {_fmt(parent.data.metrics.get(name))} |" for name in FINAL_METRICS]
        per_class = {k: v for k, v in sorted(parent.data.metrics.items()) if k.startswith("test_f1__")}
        lines += [f"| `{name}` | {_fmt(value)} |" for name, value in per_class.items()]
        lines += ["", "Artefatos:", ""]
        lines += [f"- `{path}`" for path in _artifacts(client, parent.info.run_id)]

    versions = client.search_model_versions(f"name='{settings.mlflow_registered_model}'")
    lines += [
        "",
        f"## Model Registry: `{settings.mlflow_registered_model}`",
        "",
        "| Versao | Run de origem | Status |",
        "|---|---|---|",
    ]
    lines += [f"| {version.version} | `{version.run_id}` | {version.status} |" for version in versions]

    drift = client.get_experiment_by_name(settings.mlflow_experiment + DRIFT_EXPERIMENT_SUFFIX)
    if drift is not None:
        runs = client.search_runs([drift.experiment_id], order_by=["attributes.start_time ASC"])
        lines += [
            "",
            f"## Experimento `{drift.name}`",
            "",
            "Um run por cenario de drift, com o relatorio HTML do Evidently como artefato.",
            "",
            "| Run | " + " | ".join(DRIFT_METRICS) + " | Artefato |",
            "|---|" + "---|" * (len(DRIFT_METRICS) + 1),
        ]
        for run in runs:
            metrics = " | ".join(_fmt(run.data.metrics.get(name)) for name in DRIFT_METRICS)
            artifacts = ", ".join(f"`{path}`" for path in _artifacts(client, run.info.run_id))
            lines.append(f"| `{run.info.run_name}` | {metrics} | {artifacts} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    content = build()
    target = get_settings().reports_dir / "mlflow" / "summary.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    print(f"resumo gravado em {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
