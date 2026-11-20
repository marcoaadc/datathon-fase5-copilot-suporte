"""Fachada fina sobre o MLflow.

Com ``tracking_uri`` vazio o rastreamento fica desligado e todas as chamadas viram no-op: o treino
roda igual em um ambiente sem servidor MLflow (testes, CI). O MLflow so e importado quando ligado,
porque ele nao faz parte das dependencias de runtime da API.
"""

from __future__ import annotations

import contextlib
import logging
import math
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Tracker:
    def __init__(self, tracking_uri: str | None, experiment: str) -> None:
        self.enabled = bool(tracking_uri)
        self._mlflow = None
        if self.enabled:
            import mlflow

            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment(experiment)
            self._mlflow = mlflow

    @contextlib.contextmanager
    def run(self, name: str, nested: bool = False, tags: dict[str, str] | None = None) -> Iterator[str | None]:
        if not self.enabled:
            yield None
            return
        with self._mlflow.start_run(run_name=name, nested=nested, tags=tags) as active:
            yield active.info.run_id

    def log_params(self, params: dict[str, Any]) -> None:
        if self.enabled:
            self._mlflow.log_params({key: str(value)[:500] for key, value in params.items()})

    def log_metrics(self, metrics: dict[str, float]) -> None:
        if self.enabled:
            cleaned = {key: float(value) for key, value in metrics.items() if math.isfinite(float(value))}
            self._mlflow.log_metrics(cleaned)

    def log_dict(self, payload: dict[str, Any], artifact_file: str) -> None:
        if self.enabled:
            self._mlflow.log_dict(payload, artifact_file)

    def log_artifact(self, path: Path, artifact_path: str | None = None) -> None:
        if self.enabled:
            self._mlflow.log_artifact(str(path), artifact_path=artifact_path)

    def log_confusion_matrix(self, y_true, y_pred, classes: list[str], artifact_file: str) -> None:
        """Matriz de confusao normalizada por linha, como imagem, para leitura direto na UI."""
        if not self.enabled:
            return
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import ConfusionMatrixDisplay

        figure, axis = plt.subplots(figsize=(9, 8))
        ConfusionMatrixDisplay.from_predictions(
            y_true,
            y_pred,
            labels=classes,
            normalize="true",
            xticks_rotation=60,
            values_format=".2f",
            cmap="Blues",
            colorbar=False,
            ax=axis,
        )
        axis.set_title("Matriz de confusao no teste (normalizada por fila real)")
        figure.tight_layout()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / Path(artifact_file).name
            figure.savefig(target, dpi=120)
            self._mlflow.log_artifact(str(target), artifact_path=str(Path(artifact_file).parent.as_posix()))
        plt.close(figure)

    def log_model(self, pipeline, input_example: list[str], registered_name: str | None = None) -> str | None:
        """Registra o pipeline no MLflow e, se pedido, no Model Registry. Devolve a versao registrada."""
        if not self.enabled:
            return None
        import pandas as pd
        from mlflow.models import infer_signature

        example = pd.DataFrame({"text": input_example})
        signature = infer_signature(example, pipeline.predict(input_example))
        try:
            info = self._mlflow.sklearn.log_model(
                pipeline, name="model", signature=signature, registered_model_name=registered_name
            )
        except Exception:  # o registro do modelo nao pode derrubar um treino ja concluido
            logger.exception("falha ao registrar o modelo no MLflow; o artefato local continua valido")
            return None
        version = getattr(info, "registered_model_version", None)
        return str(version) if version is not None else None
