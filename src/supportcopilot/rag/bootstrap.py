"""Montagem da base de conhecimento na subida da API: PDFs -> chunks -> triagem -> indice."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from langchain_core.embeddings import Embeddings

from supportcopilot.config.settings import Settings
from supportcopilot.guardrails import pii
from supportcopilot.guardrails.engine import GuardrailEngine
from supportcopilot.rag.documents import load_manuals
from supportcopilot.rag.embeddings import build_embeddings
from supportcopilot.rag.index import KnowledgeBase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeBaseReport:
    sources: list[str]
    chunks_indexed: int
    chunks_quarantined: int
    quarantined: list[dict[str, object]] = field(default_factory=list)
    pii_found: dict[str, int] = field(default_factory=dict)
    embedding_model: str = ""


def build_knowledge_base(
    settings: Settings, guardrails: GuardrailEngine, embeddings: Embeddings | None = None
) -> tuple[KnowledgeBase, KnowledgeBaseReport]:
    """Indexa os manuais, deixando de fora trechos com instrucoes embutidas (injecao indireta).

    Um PDF e conteudo de terceiros: se alguem inserir nele "ignore as instrucoes anteriores", esse
    trecho iria direto para o prompt. Cada chunk passa pelas regras de injecao antes de entrar no
    indice; os reprovados ficam em quarentena e sao reportados em ``GET /info``.

    Dados pessoais encontrados nos manuais sao apenas contados (auditoria de curadoria): manual e
    documentacao publica do produto, e mascarar o contato do suporte tornaria a resposta inutil.
    """
    chunks = load_manuals(settings.manuals_dir, settings.chunk_size, settings.chunk_overlap)
    accepted = []
    quarantined: list[dict[str, object]] = []
    pii_found: dict[str, int] = {}
    for chunk in chunks:
        verdict = guardrails.check_context(chunk.page_content)
        if not verdict.allowed:
            quarantined.append(
                {
                    "source": chunk.metadata.get("source"),
                    "page": chunk.metadata.get("page"),
                    "chunk_id": chunk.metadata.get("chunk_id"),
                    "rules": verdict.rule_ids,
                }
            )
            continue
        for label, count in pii.redact(chunk.page_content).counts.items():
            pii_found[label] = pii_found.get(label, 0) + count
        accepted.append(chunk)

    if quarantined:
        logger.warning("%d chunk(s) em quarentena por suspeita de injecao indireta", len(quarantined))
    embeddings = embeddings or build_embeddings(settings.embedding_model, settings.embedding_cache_dir)
    knowledge_base = KnowledgeBase(accepted, embeddings)
    report = KnowledgeBaseReport(
        sources=knowledge_base.sources,
        chunks_indexed=len(accepted),
        chunks_quarantined=len(quarantined),
        quarantined=quarantined,
        pii_found=pii_found,
        embedding_model=settings.embedding_model,
    )
    logger.info("base de conhecimento: %d chunks de %s", report.chunks_indexed, report.sources)
    return knowledge_base, report
