"""Inferencia do modelo de triagem.

Recebe o texto ja validado pelo contrato da API, aplica a mesma limpeza do treino e devolve a fila
prevista, a confianca e a decisao de roteamento ("e um problema tecnico?").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from supportcopilot.data.text import clean_text, truncate
from supportcopilot.drift.features import describe_text, model_vocabulary
from supportcopilot.triage.registry import LoadedModel, load_model


@dataclass(frozen=True)
class TriagePrediction:
    queue: str
    confidence: float
    is_technical: bool
    technical_probability: float
    needs_human_review: bool
    top: list[tuple[str, float]]
    features: dict[str, Any] = field(repr=False, default_factory=dict)


class TriageService:
    def __init__(
        self,
        loaded: LoadedModel,
        technical_queues: tuple[str, ...],
        technical_threshold: float = 0.5,
        low_confidence_threshold: float = 0.4,
        max_text_chars: int = 1000,
    ) -> None:
        self._pipeline = loaded.pipeline
        self.metadata = loaded.metadata
        self.reference_profile = loaded.reference_profile
        self.classes = [str(label) for label in self._pipeline.classes_]
        self._technical_columns = [i for i, label in enumerate(self.classes) if label in technical_queues]
        self._technical_threshold = technical_threshold
        self._low_confidence = low_confidence_threshold
        self._max_chars = max_text_chars
        self._vocabulary, self._analyzer = model_vocabulary(self._pipeline)

    @classmethod
    def from_directory(cls, directory: Path, **kwargs: Any) -> TriageService:
        return cls(load_model(directory), **kwargs)

    @property
    def version(self) -> str:
        return str(self.metadata.get("model_version", "desconhecida"))

    def predict(self, text: str, top_k: int = 3) -> TriagePrediction:
        prepared = truncate(clean_text(text), self._max_chars)
        probabilities = self._pipeline.predict_proba([prepared])[0]
        order = np.argsort(probabilities)[::-1]
        best = int(order[0])
        confidence = float(probabilities[best])
        technical_probability = float(probabilities[self._technical_columns].sum())
        features = {
            **describe_text(prepared, self._vocabulary, self._analyzer),
            "confidence": confidence,
            "technical_probability": technical_probability,
            "predicted_queue": self.classes[best],
        }
        return TriagePrediction(
            queue=self.classes[best],
            confidence=confidence,
            is_technical=technical_probability >= self._technical_threshold,
            technical_probability=technical_probability,
            needs_human_review=confidence < self._low_confidence,
            top=[(self.classes[int(i)], float(probabilities[int(i)])) for i in order[:top_k]],
            features=features,
        )
