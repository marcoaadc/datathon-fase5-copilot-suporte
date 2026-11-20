"""Dependencias da API montadas uma unica vez na subida (modelo, base de conhecimento, guardrails).

Triagem e chat sobem de forma independente: se o modelo de triagem estiver ausente, o /chat
continua de pe (e vice-versa). O que falhou fica registrado e aparece em ``GET /ready``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from supportcopilot.config.settings import Settings
from supportcopilot.drift.monitor import DriftMonitor
from supportcopilot.guardrails.engine import GuardrailEngine
from supportcopilot.observability.metrics import Metrics
from supportcopilot.rag.bootstrap import KnowledgeBaseReport, build_knowledge_base
from supportcopilot.rag.llm import build_llm
from supportcopilot.rag.service import ChatService
from supportcopilot.triage.service import TriageService

logger = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    metrics: Metrics
    guardrails: GuardrailEngine
    monitor: DriftMonitor
    triage: TriageService | None = None
    chat: ChatService | None = None
    knowledge_base_report: KnowledgeBaseReport | None = None
    startup_errors: dict[str, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.triage is not None and self.chat is not None


def build_container(settings: Settings) -> Container:
    metrics = Metrics()
    guardrails = GuardrailEngine(settings.extra_blocked_terms)
    errors: dict[str, str] = {}

    triage: TriageService | None = None
    try:
        triage = TriageService.from_directory(
            settings.triage_dir,
            technical_queues=settings.technical_queues,
            technical_threshold=settings.technical_threshold,
            low_confidence_threshold=settings.low_confidence_threshold,
            max_text_chars=settings.max_text_chars,
        )
        metrics.model_info.labels(version=triage.version, candidate=str(triage.metadata.get("candidate"))).set(1)
    except Exception as error:  # a API sobe degradada e reporta em /ready
        logger.exception("modelo de triagem indisponivel")
        errors["triage"] = f"{type(error).__name__}: {error}"

    chat: ChatService | None = None
    report: KnowledgeBaseReport | None = None
    try:
        knowledge_base, report = build_knowledge_base(settings, guardrails)
        chat = ChatService(
            knowledge_base,
            guardrails,
            build_llm(settings),
            retrieval_k=settings.retrieval_k,
            retrieval_candidates=settings.retrieval_candidates,
            min_relevance=settings.min_relevance,
            grounding_check=settings.grounding_check,
        )
        metrics.knowledge_base_chunks.set(report.chunks_indexed)
    except Exception as error:
        logger.exception("base de conhecimento indisponivel")
        errors["chat"] = f"{type(error).__name__}: {error}"

    monitor = DriftMonitor(
        triage.reference_profile if triage else None,
        window_size=settings.drift_window_size,
        min_samples=settings.drift_min_samples,
        psi_warning=settings.psi_warning,
        psi_critical=settings.psi_critical,
    )
    return Container(
        settings=settings,
        metrics=metrics,
        guardrails=guardrails,
        monitor=monitor,
        triage=triage,
        chat=chat,
        knowledge_base_report=report,
        startup_errors=errors,
    )
