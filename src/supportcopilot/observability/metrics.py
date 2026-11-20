"""Metricas Prometheus da API.

Cada aplicacao tem o seu ``CollectorRegistry`` (em vez do registro global): varias instancias
podem coexistir no mesmo processo, o que os testes fazem o tempo todo.

Nenhum rotulo carrega texto do usuario: so rotas, codigos de regra, filas e tipos de dado.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
_DRIFT_LEVEL = {"ok": 0, "insufficient_data": 0, "warning": 1, "critical": 2}


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        registry = self.registry
        self.requests = Counter(
            "copilot_http_requests_total", "Requisicoes HTTP", ["method", "route", "status"], registry=registry
        )
        self.latency = Histogram(
            "copilot_http_request_duration_seconds",
            "Latencia das requisicoes HTTP",
            ["method", "route"],
            buckets=LATENCY_BUCKETS,
            registry=registry,
        )
        self.validation_errors = Counter(
            "copilot_validation_errors_total", "Requisicoes rejeitadas pelo contrato de entrada", ["route"],
            registry=registry,
        )  # fmt: skip
        self.predictions = Counter(
            "copilot_triage_predictions_total", "Chamados triados", ["queue", "technical"], registry=registry
        )
        self.confidence = Histogram(
            "copilot_triage_confidence",
            "Confianca do modelo de triagem",
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            registry=registry,
        )
        self.low_confidence = Counter(
            "copilot_triage_low_confidence_total", "Chamados sinalizados para revisao humana", registry=registry
        )
        self.chat = Counter("copilot_chat_total", "Respostas do /chat", ["status", "mode"], registry=registry)
        self.guardrail_blocks = Counter(
            "copilot_guardrail_violations_total", "Violacoes de guardrail", ["stage", "rule"], registry=registry
        )
        self.pii = Counter(
            "copilot_pii_redactions_total", "Dados pessoais mascarados antes do LLM", ["type"], registry=registry
        )
        self.retrieval_similarity = Histogram(
            "copilot_retrieval_top_similarity",
            "Similaridade do trecho mais relevante recuperado",
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            registry=registry,
        )
        self.llm_latency = Histogram(
            "copilot_llm_request_duration_seconds", "Latencia da chamada ao LLM", ["provider"],
            buckets=LATENCY_BUCKETS, registry=registry,
        )  # fmt: skip
        self.llm_tokens = Counter(
            "copilot_llm_tokens_total", "Tokens consumidos no LLM", ["provider", "kind"], registry=registry
        )
        self.llm_degraded = Counter(
            "copilot_llm_degraded_total", "Respostas degradadas para o modo extrativo", ["reason"], registry=registry
        )
        self.drift_psi = Gauge(
            "copilot_drift_psi", "PSI da janela recente contra a referencia", ["feature"], registry=registry
        )
        self.drift_status = Gauge(
            "copilot_drift_status", "Estado do drift (0 ok, 1 atencao, 2 critico)", registry=registry
        )
        self.drift_window = Gauge(
            "copilot_drift_window_size", "Observacoes na janela do monitor de drift", registry=registry
        )
        self.model_info = Gauge(
            "copilot_model_info", "Versao do modelo de triagem em uso", ["version", "candidate"], registry=registry
        )
        self.knowledge_base_chunks = Gauge(
            "copilot_knowledge_base_chunks", "Chunks indexados na base de conhecimento", registry=registry
        )

    def observe_drift(self, status: dict[str, Any]) -> None:
        self.drift_status.set(_DRIFT_LEVEL.get(str(status.get("status")), 0))
        self.drift_window.set(int(status.get("window_size", 0)))
        for feature, item in status.get("features", {}).items():
            self.drift_psi.labels(feature=feature).set(item["psi"])

    def render(self) -> bytes:
        return generate_latest(self.registry)
