"""Candidatos do modelo de triagem e metricas de avaliacao.

Todos os candidatos compartilham a mesma representacao: TF-IDF de palavras (uni e bigramas) unido a
TF-IDF de n-gramas de caracteres, que tolera erros de digitacao e termos que nunca apareceram
inteiros no treino. O que muda e o classificador linear por cima.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, log_loss, precision_recall_fscore_support
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

WORD_STEP = "word"
CHAR_STEP = "char"


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    params: dict[str, Any]


CANDIDATES: tuple[Candidate, ...] = (
    Candidate("nb_alpha0.3", "complement_nb", {"alpha": 0.3}),
    Candidate("logreg_c3", "logistic_regression", {"C": 3.0}),
    Candidate("logreg_c10", "logistic_regression", {"C": 10.0}),
    Candidate("logreg_c30", "logistic_regression", {"C": 30.0}),
    Candidate("svc_c0.3", "linear_svc_calibrated", {"C": 0.3}),
    Candidate("svc_c1", "linear_svc_calibrated", {"C": 1.0}),
)


def build_features() -> FeatureUnion:
    return FeatureUnion(
        [
            (
                WORD_STEP,
                TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2, max_df=0.95, strip_accents="unicode"),
            ),
            (
                CHAR_STEP,
                TfidfVectorizer(
                    analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=3, strip_accents="unicode"
                ),
            ),
        ]
    )


def build_classifier(candidate: Candidate, seed: int):
    if candidate.family == "complement_nb":
        return ComplementNB(**candidate.params)
    if candidate.family == "logistic_regression":
        return LogisticRegression(max_iter=3000, random_state=seed, **candidate.params)
    if candidate.family == "linear_svc_calibrated":
        # LinearSVC nao estima probabilidade; a calibracao sigmoide (Platt) em 3 folds fornece a
        # confianca usada para sinalizar chamados que precisam de revisao humana.
        return CalibratedClassifierCV(LinearSVC(random_state=seed, **candidate.params), method="sigmoid", cv=3)
    raise ValueError(f"familia de modelo desconhecida: {candidate.family}")


def build_pipeline(candidate: Candidate, seed: int) -> Pipeline:
    return Pipeline([("features", build_features()), ("classifier", build_classifier(candidate, seed))])


def expected_calibration_error(confidence: np.ndarray, correct: np.ndarray, bins: int = 10) -> float:
    """ECE: diferenca media, ponderada pelo tamanho da faixa, entre confianca e acerto."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    index = np.clip(np.digitize(confidence, edges[1:-1]), 0, bins - 1)
    error = 0.0
    for bucket in range(bins):
        mask = index == bucket
        if mask.any():
            error += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return float(error)


def technical_probability(probabilities: np.ndarray, classes: list[str], technical: tuple[str, ...]) -> np.ndarray:
    """Probabilidade de o chamado ser tecnico: soma das probabilidades das filas tecnicas."""
    columns = [index for index, label in enumerate(classes) if label in technical]
    return probabilities[:, columns].sum(axis=1)


def evaluate(
    y_true,
    probabilities: np.ndarray,
    classes: list[str],
    technical: tuple[str, ...],
    technical_threshold: float = 0.5,
) -> dict[str, Any]:
    """Metricas da classificacao por fila e da decisao binaria "aciona o RAG ou nao"."""
    y_true = np.asarray(y_true)
    labels = np.asarray(classes)
    y_pred = labels[probabilities.argmax(axis=1)]
    confidence = probabilities.max(axis=1)

    is_technical = np.isin(y_true, technical)
    routed = technical_probability(probabilities, classes, technical) >= technical_threshold
    precision, recall, f1, _ = precision_recall_fscore_support(is_technical, routed, average="binary", zero_division=0)
    per_class = precision_recall_fscore_support(y_true, y_pred, labels=classes, zero_division=0)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", labels=classes, zero_division=0)),
        "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", labels=classes, zero_division=0)),
        "log_loss": float(log_loss(y_true, probabilities, labels=classes)),
        "ece": expected_calibration_error(confidence, y_pred == y_true),
        "mean_confidence": float(confidence.mean()),
        "routing_accuracy": float((is_technical == routed).mean()),
        "routing_precision": float(precision),
        "routing_recall": float(recall),
        "routing_f1": float(f1),
        "per_class": {
            label: {
                "precision": float(per_class[0][i]),
                "recall": float(per_class[1][i]),
                "f1": float(per_class[2][i]),
                "support": int(per_class[3][i]),
            }
            for i, label in enumerate(classes)
        },
    }


def scalar_metrics(metrics: dict[str, Any], prefix: str = "") -> dict[str, float]:
    """Achata as metricas escalares (e o F1 por classe) para o formato do MLflow."""
    flat = {f"{prefix}{key}": value for key, value in metrics.items() if isinstance(value, (int, float))}
    for label, values in metrics.get("per_class", {}).items():
        slug = label.lower().replace(" and ", " ").replace(" ", "_").replace("-", "_")
        flat[f"{prefix}f1__{slug}"] = values["f1"]
    return flat
