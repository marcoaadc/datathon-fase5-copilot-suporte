"""Base de conhecimento em memoria: FAISS (busca densa) + BM25 (busca lexical).

A busca e hibrida. A densa encontra o trecho pelo *sentido* ("a internet caiu" -> "sem conexao");
a lexical encontra pelo *termo exato* (um codigo de LED, "WPS", "192.168.0.1"), que embeddings
tendem a diluir. As duas listas sao combinadas por Reciprocal Rank Fusion (RRF), que so usa a
posicao de cada trecho em cada lista e por isso dispensa calibrar escalas de score diferentes.

O indice vive na memoria do processo e e reconstruido a partir dos PDFs na subida da API.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import numpy as np
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from rank_bm25 import BM25Okapi

from supportcopilot.guardrails.normalize import strip_accents

logger = logging.getLogger(__name__)

RRF_K = 60
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")
# Palavras vazias em portugues e ingles: fora do BM25 para que ele pese os termos de conteudo.
_STOPWORDS = frozenset({
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no", "na", "nos",
    "nas", "por", "para", "com", "sem", "que", "e", "ou", "se", "como", "meu", "minha", "seu", "sua", "ao",
    "aos", "esta", "este", "isso", "isto", "ser", "estar", "ter", "foi", "sao", "the", "an", "of", "in", "on",
    "to", "for", "with", "and", "or", "is", "are", "my", "your", "how", "what", "can", "does", "i", "it",
    "this", "that", "be", "not",
})  # fmt: skip


def tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN.findall(strip_accents(text.casefold())) if token not in _STOPWORDS]


def indexed_text(chunk: Document) -> str:
    """Texto que representa o chunk no indice: a secao da contexto ao trecho."""
    section = chunk.metadata.get("section")
    return f"{section}\n{chunk.page_content}" if section else chunk.page_content


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    source: str
    page: int
    section: str
    similarity: float  # cosseno entre a pergunta e o trecho (busca densa)
    rrf_score: float
    dense_rank: int | None
    lexical_rank: int | None


class KnowledgeBase:
    def __init__(self, chunks: list[Document], embeddings: Embeddings) -> None:
        if not chunks:
            raise ValueError("a base de conhecimento precisa de ao menos um chunk")
        self._chunks = chunks
        self._embeddings = embeddings
        texts = [indexed_text(chunk) for chunk in chunks]
        ids = [str(position) for position in range(len(chunks))]
        # Vetores normalizados aqui (norma 1) + produto interno = similaridade de cosseno, qualquer
        # que seja o modelo de embeddings (nem todos devolvem vetores unitarios).
        vectors = np.asarray(embeddings.embed_documents(texts), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / np.where(norms == 0, 1.0, norms)
        self._store = FAISS.from_embeddings(
            list(zip(texts, vectors.tolist(), strict=True)),
            embeddings,
            metadatas=[{"position": position} for position in range(len(chunks))],
            ids=ids,
            distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
        )
        self._bm25 = BM25Okapi([tokenize(text) or ["_"] for text in texts])

    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def sources(self) -> list[str]:
        return sorted({str(chunk.metadata.get("source", "")) for chunk in self._chunks})

    def _query_vector(self, query: str) -> np.ndarray:
        vector = np.asarray(self._embeddings.embed_query(query), dtype=np.float32)
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector

    def search(self, query: str, k: int = 4, candidates: int = 12) -> list[RetrievedChunk]:
        """Os ``k`` trechos mais relevantes por RRF entre a busca densa e a lexical."""
        candidates = min(max(candidates, k), len(self._chunks))
        vector = self._query_vector(query)

        scores, positions = self._store.index.search(vector.reshape(1, -1), candidates)
        dense = [
            (int(position), float(score))
            for position, score in zip(positions[0], scores[0], strict=True)
            if position >= 0
        ]
        dense_rank = {position: rank for rank, (position, _) in enumerate(dense, start=1)}
        similarity = dict(dense)

        tokens = tokenize(query)
        lexical_rank: dict[int, int] = {}
        if tokens:
            bm25_scores = self._bm25.get_scores(tokens)
            order = np.argsort(bm25_scores)[::-1][:candidates]
            lexical_rank = {int(p): rank for rank, p in enumerate(order, start=1) if bm25_scores[int(p)] > 0}

        fused: dict[int, float] = {}
        for ranking in (dense_rank, lexical_rank):
            for position, rank in ranking.items():
                fused[position] = fused.get(position, 0.0) + 1.0 / (RRF_K + rank)

        results: list[RetrievedChunk] = []
        for position, score in sorted(fused.items(), key=lambda item: item[1], reverse=True)[:k]:
            if position not in similarity:
                # Trecho que entrou so pela busca lexical: calcula o cosseno a partir do vetor do indice.
                similarity[position] = float(np.dot(self._store.index.reconstruct(position), vector))
            chunk = self._chunks[position]
            results.append(
                RetrievedChunk(
                    chunk_id=str(chunk.metadata.get("chunk_id", position)),
                    text=chunk.page_content,
                    source=str(chunk.metadata.get("source", "")),
                    page=int(chunk.metadata.get("page", 0)),
                    section=str(chunk.metadata.get("section", "")),
                    similarity=similarity[position],
                    rrf_score=score,
                    dense_rank=dense_rank.get(position),
                    lexical_rank=lexical_rank.get(position),
                )
            )
        return results
