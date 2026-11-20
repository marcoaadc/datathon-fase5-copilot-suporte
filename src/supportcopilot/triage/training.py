"""Treino do modelo de triagem com rastreamento no MLflow.

Protocolo:

1. cada candidato e treinado no treino e avaliado na validacao (um run aninhado por candidato);
2. o vencedor e o de maior F1 macro na validacao (as filas sao desbalanceadas, entao acuracia
   sozinha premiaria quem acerta so as filas grandes);
3. o vencedor e retreinado em treino + validacao e avaliado uma unica vez no teste, que nao
   participou de nenhuma escolha;
4. o artefato, os metadados e o perfil de referencia para drift sao gravados em ``models/triage``
   e o modelo e registrado no Model Registry do MLflow.
"""

from __future__ import annotations

import logging
import platform
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import confusion_matrix

from supportcopilot import __version__
from supportcopilot.config.settings import Settings
from supportcopilot.data.ingest import TARGET, TEXT, load_partition
from supportcopilot.drift.features import build_frame, build_profile
from supportcopilot.observability.tracking import Tracker
from supportcopilot.triage import registry
from supportcopilot.triage.modeling import CANDIDATES, Candidate, build_pipeline, evaluate, scalar_metrics

logger = logging.getLogger(__name__)


def _fit_and_score(
    candidate: Candidate, train: pd.DataFrame, holdout: pd.DataFrame, settings: Settings
) -> tuple[Any, dict[str, Any], float]:
    started = time.perf_counter()
    pipeline = build_pipeline(candidate, settings.seed).fit(train[TEXT], train[TARGET])
    fit_seconds = time.perf_counter() - started
    classes = [str(label) for label in pipeline.classes_]
    metrics = evaluate(
        holdout[TARGET],
        pipeline.predict_proba(holdout[TEXT]),
        classes,
        settings.technical_queues,
        settings.technical_threshold,
    )
    return pipeline, metrics, fit_seconds


def _confusion(y_true, y_pred, classes: list[str]) -> dict[str, Any]:
    matrix = confusion_matrix(y_true, y_pred, labels=classes)
    return {"labels": classes, "matrix": matrix.tolist()}


def majority_baseline(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, float]:
    """Piso de comparacao: prever sempre a fila mais frequente do treino."""
    majority = train[TARGET].mode().iloc[0]
    return {"majority_class_accuracy": float((test[TARGET] == majority).mean())}


def train(settings: Settings, candidates: tuple[Candidate, ...] = CANDIDATES) -> dict[str, Any]:
    train_df = load_partition(settings, "train")
    validation_df = load_partition(settings, "validation")
    test_df = load_partition(settings, "test")
    tracker = Tracker(settings.mlflow_tracking_uri, settings.mlflow_experiment)

    data_params = {
        "dataset": f"{settings.dataset_repo}@{settings.dataset_revision[:12]}",
        "dataset_sha256": settings.dataset_sha256[:16],
        "reference_language": settings.reference_language,
        "n_train": len(train_df),
        "n_validation": len(validation_df),
        "n_test": len(test_df),
        "n_classes": train_df[TARGET].nunique(),
        "max_text_chars": settings.max_text_chars,
        "seed": settings.seed,
        "split": "group_shuffle_near_duplicates",
    }

    with tracker.run("treino-triagem", tags={"stage": "training", "app_version": __version__}) as parent_run:
        tracker.log_params(data_params)

        leaderboard: list[dict[str, Any]] = []
        for candidate in candidates:
            with tracker.run(candidate.name, nested=True, tags={"family": candidate.family}):
                _, metrics, fit_seconds = _fit_and_score(candidate, train_df, validation_df, settings)
                tracker.log_params({"family": candidate.family, **candidate.params})
                tracker.log_metrics({**scalar_metrics(metrics, "val_"), "fit_seconds": fit_seconds})
                leaderboard.append(
                    {
                        "candidate": candidate.name,
                        "family": candidate.family,
                        "params": candidate.params,
                        "val_accuracy": metrics["accuracy"],
                        "val_f1_macro": metrics["f1_macro"],
                        "val_log_loss": metrics["log_loss"],
                        "val_routing_f1": metrics["routing_f1"],
                        "fit_seconds": round(fit_seconds, 2),
                    }
                )
                logger.info(
                    "candidato %s: acc=%.4f f1_macro=%.4f", candidate.name, metrics["accuracy"], metrics["f1_macro"]
                )

        leaderboard.sort(key=lambda row: (row["val_f1_macro"], -row["val_log_loss"]), reverse=True)
        winner = next(c for c in candidates if c.name == leaderboard[0]["candidate"])

        # Retreino final em treino + validacao; o teste e usado uma unica vez.
        development = pd.concat([train_df, validation_df], ignore_index=True)
        pipeline, test_metrics, fit_seconds = _fit_and_score(winner, development, test_df, settings)
        classes = [str(label) for label in pipeline.classes_]
        test_predictions = np.asarray(classes)[pipeline.predict_proba(test_df[TEXT]).argmax(axis=1)]
        baseline = majority_baseline(development, test_df)

        # Perfil de referencia para drift: medido no teste, onde a confianca do modelo e honesta.
        reference_frame = build_frame(pipeline, test_df[TEXT], settings.technical_queues)
        profile = build_profile(reference_frame)

        model_version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        metadata = {
            "model_name": settings.mlflow_registered_model,
            "model_version": model_version,
            "app_version": __version__,
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "candidate": winner.name,
            "family": winner.family,
            "params": winner.params,
            "classes": classes,
            "technical_queues": list(settings.technical_queues),
            "technical_threshold": settings.technical_threshold,
            "data": data_params,
            "metrics": {"test": test_metrics, "baseline": baseline},
            "leaderboard": leaderboard,
            "environment": {
                "python": platform.python_version(),
                "scikit_learn": sklearn.__version__,
                "numpy": np.__version__,
            },
            "mlflow": {"tracking_uri": settings.mlflow_tracking_uri, "run_id": parent_run},
        }
        metadata = registry.save_model(settings.triage_dir, pipeline, metadata, profile)

        tracker.log_params({"winner": winner.name, "winner_family": winner.family})
        tracker.log_metrics({**scalar_metrics(test_metrics, "test_"), **baseline, "final_fit_seconds": fit_seconds})
        tracker.log_dict({"leaderboard": leaderboard}, "selection/leaderboard.json")
        tracker.log_dict(test_metrics["per_class"], "evaluation/per_class.json")
        tracker.log_dict(_confusion(test_df[TARGET], test_predictions, classes), "evaluation/confusion_matrix.json")
        tracker.log_dict(profile, "drift/reference_profile.json")
        tracker.log_artifact(settings.triage_dir / registry.METADATA_FILE, "model_card")
        tracker.log_confusion_matrix(test_df[TARGET], test_predictions, classes, "evaluation/confusion_matrix.png")
        registered = tracker.log_model(
            pipeline,
            input_example=test_df[TEXT].head(3).tolist(),
            registered_name=settings.mlflow_registered_model,
        )
        if registered:
            metadata["mlflow"]["registered_version"] = registered
            registry.write_json(settings.triage_dir / registry.METADATA_FILE, metadata)

    logger.info(
        "modelo %s (%s): teste acc=%.4f f1_macro=%.4f roteamento_f1=%.4f",
        model_version,
        winner.name,
        test_metrics["accuracy"],
        test_metrics["f1_macro"],
        test_metrics["routing_f1"],
    )
    return metadata
