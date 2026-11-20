"""Embeddings locais.

Os vetores sao calculados dentro da aplicacao (ONNX, CPU), nao por uma API externa. Tres motivos:

* privacidade: a pergunta do usuario so sai da aplicacao uma vez (para o LLM, ja mascarada), e nao
  duas (embedding + geracao);
* custo e latencia: indexar o manual e buscar nao consomem cota do provedor de LLM;
* reprodutibilidade: a busca funciona, e e testavel, sem nenhuma chave configurada.

O modelo padrao e multilingue (portugues e ingles no mesmo espaco vetorial): uma pergunta em ingles
recupera o trecho certo de um manual em portugues.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from langchain_core.embeddings import Embeddings
from sklearn.feature_extraction.text import HashingVectorizer

logger = logging.getLogger(__name__)

HASHING = "hashing"


class FastEmbedEmbeddings(Embeddings):
    """Adaptador do ``fastembed`` (ONNX Runtime) para a interface ``Embeddings`` do LangChain."""

    def __init__(self, model_name: str, cache_dir: Path | None = None) -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name, cache_dir=str(cache_dir) if cache_dir else None)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class HashingEmbeddings(Embeddings):
    """Embedding lexical deterministico (n-gramas de caracteres com hashing), sem download.

    Nao captura sinonimos nem cruza idiomas. Serve aos testes de unidade e como modo degradado em
    ambiente sem acesso a rede para baixar o modelo (``COPILOT_EMBEDDING_MODEL=hashing``).
    """

    model_name = HASHING

    def __init__(self, dimensions: int = 1024) -> None:
        self._vectorizer = HashingVectorizer(
            n_features=dimensions, analyzer="char_wb", ngram_range=(3, 5), norm="l2", alternate_sign=False,
            strip_accents="unicode", lowercase=True,
        )  # fmt: skip

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return np.asarray(self._vectorizer.transform(texts).todense(), dtype=np.float32).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embeddings(model_name: str, cache_dir: Path | None = None) -> Embeddings:
    if model_name == HASHING:
        return HashingEmbeddings()
    return FastEmbedEmbeddings(model_name, cache_dir)
