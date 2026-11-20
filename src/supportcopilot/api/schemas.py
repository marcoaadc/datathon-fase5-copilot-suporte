"""Contratos de entrada e saida da API (Pydantic v2).

A validacao estrutural acontece aqui, antes de qualquer modelo ser chamado:

* corpo com campo desconhecido e rejeitado (``extra="forbid"``): erro de integracao aparece cedo;
* o texto nao pode ser vazio, so espacos, so simbolos, nem passar do limite do contrato;
* o limite e medido sobre o texto ja normalizado, o mesmo que o modelo vai receber.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from supportcopilot.config.settings import get_settings
from supportcopilot.data.text import clean_text

MIN_LETTERS = 3
# Teto do texto bruto: evita gastar CPU normalizando um corpo absurdo antes de rejeita-lo.
RAW_LENGTH_FACTOR = 4


def validate_free_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} deve ser um texto")
    max_chars = get_settings().max_text_chars
    if len(value) > max_chars * RAW_LENGTH_FACTOR:
        raise ValueError(f"{field_name} excede o limite de {max_chars} caracteres")
    cleaned = clean_text(value)
    if not cleaned:
        raise ValueError(f"{field_name} nao pode ser vazio")
    if len(cleaned) > max_chars:
        raise ValueError(f"{field_name} excede o limite de {max_chars} caracteres (recebido: {len(cleaned)})")
    if sum(char.isalpha() for char in cleaned) < MIN_LETTERS:
        raise ValueError(f"{field_name} precisa conter texto legivel (ao menos {MIN_LETTERS} letras)")
    return cleaned


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TicketRequest(_StrictModel):
    text: Annotated[
        str,
        Field(
            description="Texto do chamado (assunto e descricao). Obrigatorio, de 1 a 1000 caracteres.",
            examples=[
                "My wireless router keeps dropping the connection every few minutes and the internet LED turns orange."
            ],
        ),
    ]

    @field_validator("text", mode="before")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return validate_free_text(value, "text")


class ChatRequest(_StrictModel):
    question: Annotated[
        str,
        Field(
            description="Duvida do usuario, respondida apenas com base no manual. De 1 a 1000 caracteres.",
            examples=["Como faço a restauração de fábrica do roteador?"],
        ),
    ]

    @field_validator("question", mode="before")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        return validate_free_text(value, "question")


class QueueProbability(BaseModel):
    queue: str
    probability: float


class TriageResponse(BaseModel):
    queue: str = Field(description="Fila de atendimento prevista")
    confidence: float = Field(description="Probabilidade da fila prevista")
    is_technical: bool = Field(description="True quando o chamado e um problema tecnico (aciona o RAG)")
    technical_probability: float = Field(description="Soma das probabilidades das filas tecnicas")
    needs_human_review: bool = Field(description="True quando a confianca esta abaixo do limiar")
    alternatives: list[QueueProbability] = Field(description="As filas mais provaveis, em ordem")
    model_version: str
    request_id: str


class Source(BaseModel):
    id: int = Field(description="Numero usado nas citacoes da resposta, ex.: [1]")
    source: str
    page: int
    section: str
    similarity: float
    excerpt: str


class GuardrailViolation(BaseModel):
    rule_id: str
    category: str
    description: str


class GuardrailReport(BaseModel):
    blocked: bool
    input: list[GuardrailViolation] = Field(default_factory=list)
    output: list[GuardrailViolation] = Field(default_factory=list)


class LLMInfo(BaseModel):
    provider: str
    model: str | None = None


class ChatResponse(BaseModel):
    status: Literal["answered", "not_found", "blocked"]
    answer: str
    mode: Literal["llm", "extractive", "none"] = Field(
        description="llm: resposta gerada; extractive: trechos do manual, sem geracao; none: sem resposta"
    )
    sources: list[Source] = Field(default_factory=list)
    guardrails: GuardrailReport
    pii_redacted: dict[str, int] = Field(
        default_factory=dict, description="Quantidade de dados pessoais mascarados antes do LLM, por tipo"
    )
    llm: LLMInfo
    degraded_reason: str | None = None
    request_id: str


class TicketResponse(BaseModel):
    route: Literal["rag", "human_queue"] = Field(description="rag: respondido pelo copilot; human_queue: fila humana")
    triage: TriageResponse
    chat: ChatResponse | None = None
    request_id: str


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: str
