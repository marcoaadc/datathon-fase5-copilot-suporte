"""Features monitoradas para drift de um classificador de texto.

Texto livre nao tem "distribuicao" que um teste estatistico compare direto. O que se monitora sao
descritores do texto e a saida do modelo:

* forma do texto: tamanho, numero de palavras, tamanho medio de palavra, fracao de maiusculas,
  de digitos e de caracteres fora do ASCII;
* ``oov_rate``: fracao das palavras do chamado que o vocabulario do modelo nao conhece. E o sinal
  mais direto de que a producao esta falando de algo (ou em um idioma) que o treino nao cobriu;
* saida do modelo: fila prevista, confianca e probabilidade de ser tecnico. Queda de confianca e
  mudanca na mistura de filas sao o efeito do drift sobre a decisao.

Nenhuma dessas features permite reconstruir o texto do chamado.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from supportcopilot.drift.statistics import categorical_profile, numeric_profile
from supportcopilot.triage.modeling import WORD_STEP, technical_probability

TEXT_FEATURES = [
    "n_chars",
    "n_words",
    "mean_word_length",
    "oov_rate",
    "non_ascii_ratio",
    "upper_ratio",
    "digit_ratio",
]
MODEL_FEATURES = ["confidence", "technical_probability"]
NUMERICAL_FEATURES = [*TEXT_FEATURES, *MODEL_FEATURES]
CATEGORICAL_FEATURES = ["predicted_queue"]
MONITORED_FEATURES = [*NUMERICAL_FEATURES, *CATEGORICAL_FEATURES]

_WORD = re.compile(r"\w+", re.UNICODE)


def model_vocabulary(pipeline: Pipeline) -> tuple[frozenset[str], Any]:
    """Vocabulario de unigramas do TF-IDF de palavras e o pre-processador que o gerou."""
    vectorizer = dict(pipeline.named_steps["features"].transformer_list)[WORD_STEP]
    unigrams = frozenset(term for term in vectorizer.vocabulary_ if " " not in term)
    return unigrams, vectorizer.build_analyzer()


def describe_text(text: str, vocabulary: frozenset[str], analyzer) -> dict[str, float]:
    words = _WORD.findall(text)
    n_chars = len(text)
    letters = [char for char in text if char.isalpha()]
    # O analisador devolve uni e bigramas; so os unigramas contam para a taxa fora do vocabulario.
    tokens = [token for token in analyzer(text) if " " not in token]
    return {
        "n_chars": float(n_chars),
        "n_words": float(len(words)),
        "mean_word_length": float(np.mean([len(word) for word in words])) if words else 0.0,
        "oov_rate": sum(token not in vocabulary for token in tokens) / len(tokens) if tokens else 1.0,
        "non_ascii_ratio": sum(ord(char) > 127 for char in text) / n_chars if n_chars else 0.0,
        "upper_ratio": sum(char.isupper() for char in letters) / len(letters) if letters else 0.0,
        "digit_ratio": sum(char.isdigit() for char in text) / n_chars if n_chars else 0.0,
    }


def build_frame(pipeline: Pipeline, texts: pd.Series, technical: tuple[str, ...]) -> pd.DataFrame:
    """Uma linha por chamado com todas as features monitoradas (sem o texto)."""
    vocabulary, analyzer = model_vocabulary(pipeline)
    frame = pd.DataFrame([describe_text(text, vocabulary, analyzer) for text in texts], index=texts.index)
    probabilities = pipeline.predict_proba(texts)
    classes = [str(label) for label in pipeline.classes_]
    frame["confidence"] = probabilities.max(axis=1)
    frame["technical_probability"] = technical_probability(probabilities, classes, technical)
    frame["predicted_queue"] = np.asarray(classes)[probabilities.argmax(axis=1)]
    return frame[MONITORED_FEATURES]


def build_profile(frame: pd.DataFrame, bins: int = 10) -> dict[str, Any]:
    """Perfil de referencia (so agregados) usado pelo monitor de drift da API."""
    features: dict[str, Any] = {name: numeric_profile(frame[name], bins=bins) for name in NUMERICAL_FEATURES}
    features.update({name: categorical_profile(frame[name]) for name in CATEGORICAL_FEATURES})
    return {"n_reference": len(frame), "features": features}
