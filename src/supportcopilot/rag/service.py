"""Servico de chat: guardrails -> mascaramento de PII -> busca -> LLM -> guardrails de saida.

Ordem das etapas e o que cada uma garante:

1. ``check_input``   pergunta insegura e bloqueada antes de qualquer busca ou custo de LLM;
2. ``redact``        dado pessoal e mascarado antes de sair da aplicacao (LGPD);
3. ``search``        trechos do manual; se nenhum e relevante, a resposta e "nao encontrei" *sem*
                     consultar o LLM (pergunta fora do escopo nao da chance a alucinacao);
4. LLM               gera a resposta apenas com os trechos; falha do provedor degrada para o modo
                     extrativo em vez de derrubar a requisicao;
5. ``check_output``  vazamento de prompt bloqueia; resposta sem citacao ou com valor que nao existe
                     no manual e descartada e substituida pelos trechos originais.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from supportcopilot.guardrails import pii
from supportcopilot.guardrails.engine import (
    OUT_PROMPT_LEAK,
    OUT_UNSAFE_CONTENT,
    GuardrailEngine,
    Violation,
)
from supportcopilot.rag import prompts
from supportcopilot.rag.index import KnowledgeBase, RetrievedChunk
from supportcopilot.rag.llm import LLMHandle

logger = logging.getLogger(__name__)

ANSWERED, NOT_FOUND, BLOCKED = "answered", "not_found", "blocked"
MODE_LLM, MODE_EXTRACTIVE, MODE_NONE = "llm", "extractive", "none"

BLOCKED_MESSAGE = (
    "Não posso atender a esta solicitação: ela viola a política de uso do assistente. "
    "Posso ajudar com dúvidas sobre o conteúdo do manual."
)
NOT_FOUND_MESSAGE = (
    "Não encontrei essa informação no manual. Reformule a pergunta ou encaminhe o chamado para um atendente."
)
EXTRACTIVE_HEADER = "Trechos do manual mais relevantes para a sua pergunta:"
EXTRACTIVE_MAX_CHUNKS = 3
_PLACEHOLDER = re.compile(r"\[[A-Z]{2,10}\]")


@dataclass(frozen=True)
class ChatResult:
    status: str
    answer: str
    mode: str
    sources: list[RetrievedChunk] = field(default_factory=list)
    input_violations: list[Violation] = field(default_factory=list)
    output_violations: list[Violation] = field(default_factory=list)
    pii: dict[str, int] = field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    degraded_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    timings_ms: dict[str, float] = field(default_factory=dict)


def _merge_counts(*counts: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for item in counts:
        for key, value in item.items():
            merged[key] = merged.get(key, 0) + value
    return merged


def _text_of(response: Any) -> str:
    """Texto de uma resposta do LangChain (o conteudo pode vir como string ou lista de blocos)."""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts).strip()


class ChatService:
    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        guardrails: GuardrailEngine,
        llm: LLMHandle | None,
        retrieval_k: int = 4,
        retrieval_candidates: int = 12,
        min_relevance: float = 0.3,
        grounding_check: bool = True,
    ) -> None:
        self._kb = knowledge_base
        self._guardrails = guardrails
        self._llm = llm
        self._k = retrieval_k
        self._candidates = retrieval_candidates
        self._min_relevance = min_relevance
        self._grounding_check = grounding_check
        self._canary = prompts.new_canary()

    @property
    def provider(self) -> str:
        return self._llm.provider if self._llm else "offline"

    @property
    def model_name(self) -> str | None:
        return self._llm.model_name if self._llm else None

    def answer(self, question: str) -> ChatResult:
        timings: dict[str, float] = {}

        started = time.perf_counter()
        verdict = self._guardrails.check_input(question)
        timings["guardrails_input"] = (time.perf_counter() - started) * 1000
        if not verdict.allowed:
            return ChatResult(
                BLOCKED, BLOCKED_MESSAGE, MODE_NONE, input_violations=verdict.violations, timings_ms=timings
            )

        redaction = pii.redact(question)
        safe_question = redaction.text

        started = time.perf_counter()
        # Os marcadores ([CPF], [EMAIL]...) nao ajudam a busca: saem da consulta, ficam no prompt.
        query = _PLACEHOLDER.sub(" ", safe_question).strip() or safe_question
        retrieved = self._kb.search(query, k=self._k, candidates=self._candidates)
        timings["retrieval"] = (time.perf_counter() - started) * 1000
        relevant = [chunk for chunk in retrieved if chunk.similarity >= self._min_relevance]
        if not relevant:
            return ChatResult(NOT_FOUND, NOT_FOUND_MESSAGE, MODE_NONE, pii=redaction.counts, timings_ms=timings)

        context = relevant
        base = {"sources": context, "pii": redaction.counts, "timings_ms": timings}

        if self._llm is None:
            return ChatResult(ANSWERED, self._extractive(context), MODE_EXTRACTIVE, **base)

        started = time.perf_counter()
        try:
            response = self._llm.client.invoke(prompts.build_messages(safe_question, context, self._canary))
        except Exception as error:  # falha do provedor nao derruba a requisicao
            timings["llm"] = (time.perf_counter() - started) * 1000
            logger.warning("falha na chamada ao LLM (%s); usando modo extrativo", type(error).__name__)
            return ChatResult(
                ANSWERED,
                self._extractive(context),
                MODE_EXTRACTIVE,
                provider=self._llm.provider,
                model=self._llm.model_name,
                degraded_reason="llm_unavailable",
                **base,
            )
        timings["llm"] = (time.perf_counter() - started) * 1000
        usage = dict(getattr(response, "usage_metadata", None) or {})
        usage = {key: int(value) for key, value in usage.items() if isinstance(value, int)}
        llm_info = {"provider": self._llm.provider, "model": self._llm.model_name, "usage": usage}
        text = _text_of(response)

        if not text or prompts.NOT_FOUND_SENTINEL in text:
            return ChatResult(NOT_FOUND, NOT_FOUND_MESSAGE, MODE_LLM, **base, **llm_info)

        started = time.perf_counter()
        output = self._guardrails.check_output(
            text,
            [chunk.text for chunk in context],
            question=safe_question,
            canary=self._canary,
            protected_text=prompts.system_prompt(self._canary),
            check_grounding=self._grounding_check,
        )
        timings["guardrails_output"] = (time.perf_counter() - started) * 1000

        if not output.allowed:
            if {OUT_PROMPT_LEAK, OUT_UNSAFE_CONTENT} & set(output.rule_ids):
                return ChatResult(
                    BLOCKED,
                    BLOCKED_MESSAGE,
                    MODE_NONE,
                    output_violations=output.violations,
                    pii=redaction.counts,
                    timings_ms=timings,
                    **llm_info,
                )
            # Resposta nao comprovavel pelo manual: descartada; o usuario recebe os trechos originais.
            return ChatResult(
                ANSWERED,
                self._extractive(context),
                MODE_EXTRACTIVE,
                output_violations=output.violations,
                degraded_reason="ungrounded_answer",
                **base,
                **llm_info,
            )

        # A pergunta foi mascarada, entao o LLM nao conhece dados do usuario. Um dado pessoal na
        # resposta que nao venha do manual (ex.: contato do suporte) e inventado ou vazado: mascara.
        answer = pii.redact(text, allowed_in="\n".join(chunk.text for chunk in context))
        return ChatResult(
            ANSWERED,
            answer.text,
            MODE_LLM,
            sources=context,
            pii=_merge_counts(redaction.counts, answer.counts),
            timings_ms=timings,
            **llm_info,
        )

    @staticmethod
    def _extractive(chunks: list[RetrievedChunk]) -> str:
        lines = [EXTRACTIVE_HEADER]
        for number, chunk in enumerate(chunks[:EXTRACTIVE_MAX_CHUNKS], start=1):
            where = f"{chunk.source}, p. {chunk.page}" + (f", seção {chunk.section}" if chunk.section else "")
            lines.append(f"\n[{number}] ({where})\n{chunk.text}")
        return "\n".join(lines)
