"""API do Copilot de Suporte (FastAPI).

Endpoints de negocio:

* ``POST /triage``   classifica a fila do chamado com o modelo classico;
* ``POST /chat``     responde uma duvida apenas com base no manual em PDF (RAG com guardrails);
* ``POST /tickets``  fluxo completo: tria o chamado e, se for tecnico, aciona o RAG.

Endpoints operacionais: ``/health``, ``/ready``, ``/info``, ``/drift`` e ``/metrics``.

As rotas sao funcoes sincronas: o FastAPI as executa em um pool de threads, entao a chamada
bloqueante ao LLM nao trava o event loop.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from supportcopilot import __version__
from supportcopilot.api import schemas
from supportcopilot.api.container import Container, build_container
from supportcopilot.api.security import API_KEY_HEADER, RateLimiter, api_key_matches
from supportcopilot.config.settings import Settings, get_settings
from supportcopilot.guardrails.engine import OUTPUT_RULES
from supportcopilot.guardrails.rules import BLOCKED_TERMS_RULE_ID, FLOODING_RULE_ID, INPUT_RULES
from supportcopilot.observability.logs import configure_logging, request_id_var
from supportcopilot.rag.service import BLOCKED, ChatResult
from supportcopilot.triage.service import TriagePrediction

logger = logging.getLogger("supportcopilot.api")

MAX_BODY_BYTES = 64 * 1024
OPEN_PATHS = frozenset({"/", "/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json"})
EXCERPT_CHARS = 280
REQUEST_ID_HEADER = "X-Request-ID"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
VALIDATION_MESSAGES = {
    "extra_forbidden": "campo nao permitido pelo contrato",
    "missing": "campo obrigatorio ausente",
    "json_invalid": "o corpo da requisicao nao e um JSON valido",
    "model_attributes_type": "o corpo da requisicao deve ser um objeto JSON",
}
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": schemas.ErrorResponse, "description": "Chave de API ausente ou invalida"},
    413: {"model": schemas.ErrorResponse, "description": "Corpo da requisicao acima do limite"},
    422: {"model": schemas.ErrorResponse, "description": "Entrada reprovada pelo contrato de dados"},
    429: {"model": schemas.ErrorResponse, "description": "Limite de requisicoes excedido"},
    503: {"model": schemas.ErrorResponse, "description": "Componente indisponivel"},
}

DESCRIPTION = """
Motor de um **Copilot de Suporte** hibrido:

1. **Triagem** (`POST /triage`): modelo classico (TF-IDF + regressao logistica) classifica a fila do chamado.
2. **RAG com guardrails** (`POST /chat`): responde duvidas apenas com base no manual em PDF, com
   bloqueio de prompts inseguros e mascaramento de dados pessoais antes do LLM.
3. **Fluxo completo** (`POST /tickets`): tria o chamado e, se for um problema tecnico, aciona o RAG.
4. **Observabilidade**: `GET /drift` (PSI da janela recente contra a referencia) e `GET /metrics` (Prometheus).
"""


def _error(status: int, code: str, message: str, details: list[dict[str, str]] | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details or []}, "request_id": request_id_var.get()}
    return JSONResponse(status_code=status, content=body)


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """Fabrica da aplicacao. ``container`` permite injetar dependencias prontas (testes)."""
    settings = settings or (container.settings if container else get_settings())
    limiter = RateLimiter(settings.rate_limit_per_minute)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level, settings.log_json)
        app.state.container = container or build_container(settings)
        state: Container = app.state.container
        logger.info(
            "api pronta",
            extra={
                "version": __version__,
                "environment": settings.environment,
                "ready": state.ready,
                "llm_provider": state.chat.provider if state.chat else None,
                "startup_errors": sorted(state.startup_errors),
            },
        )
        yield

    app = FastAPI(
        title="Copilot de Suporte",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        license_info={"name": "MIT"},
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", API_KEY_HEADER, REQUEST_ID_HEADER],
        )

    def state_of(request: Request) -> Container:
        return request.app.state.container

    # ------------------------------------------------------------------ middleware
    @app.middleware("http")
    async def request_pipeline(request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if 8 <= len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        state = state_of(request)
        path = request.url.path
        try:
            response = _precheck(request, path)
            if response is None:
                response = await call_next(request)
        except Exception:
            logger.exception("erro nao tratado", extra={"path": path})
            response = _error(500, "internal_error", "Erro interno. Informe o request_id ao suporte.")
        elapsed = time.perf_counter() - started
        route = _route_label(request)
        state.metrics.requests.labels(request.method, route, str(response.status_code)).inc()
        state.metrics.latency.labels(request.method, route).observe(elapsed)
        response.headers[REQUEST_ID_HEADER] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if path not in ("/health", "/ready", "/metrics"):
            logger.info(
                "requisicao",
                extra={
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": round(elapsed * 1000, 1),
                },
            )
        request_id_var.reset(token)
        return response

    def _precheck(request: Request, path: str) -> JSONResponse | None:
        """Controles que rodam antes da rota: tamanho do corpo, autenticacao e limite de taxa."""
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > MAX_BODY_BYTES:
            return _error(413, "payload_too_large", f"O corpo da requisicao excede {MAX_BODY_BYTES} bytes.")
        if path in OPEN_PATHS:
            return None
        if settings.api_key is not None and not api_key_matches(
            request.headers.get(API_KEY_HEADER), settings.api_key.get_secret_value()
        ):
            return _error(401, "unauthorized", f"Informe uma chave valida no cabecalho {API_KEY_HEADER}.")
        client = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.allow(client)
        if not allowed:
            response = _error(429, "rate_limited", "Limite de requisicoes excedido. Tente novamente em instantes.")
            response.headers["Retry-After"] = str(retry_after)
            return response
        return None

    # ------------------------------------------------------------------ erros
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, error: RequestValidationError):
        state_of(request).metrics.validation_errors.labels(_route_label(request)).inc()
        details = []
        for item in error.errors():
            location = [str(part) for part in item.get("loc", ()) if part != "body"]
            message = VALIDATION_MESSAGES.get(
                str(item.get("type")), str(item.get("msg", "valor invalido")).removeprefix("Value error, ")
            )
            # O valor recebido nunca e devolvido nem logado: pode conter dado pessoal.
            details.append({"field": ".".join(location) or "body", "message": message})
        return _error(422, "validation_error", "A requisicao nao atende ao contrato de entrada.", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, error: StarletteHTTPException):
        codes = {404: "not_found", 405: "method_not_allowed", 503: "service_unavailable"}
        return _error(error.status_code, codes.get(error.status_code, "http_error"), str(error.detail))

    # ------------------------------------------------------------------ conversores
    def to_triage_response(prediction: TriagePrediction, model_version: str) -> schemas.TriageResponse:
        return schemas.TriageResponse(
            queue=prediction.queue,
            confidence=round(prediction.confidence, 4),
            is_technical=prediction.is_technical,
            technical_probability=round(prediction.technical_probability, 4),
            needs_human_review=prediction.needs_human_review,
            alternatives=[schemas.QueueProbability(queue=q, probability=round(p, 4)) for q, p in prediction.top],
            model_version=model_version,
            request_id=request_id_var.get(),
        )

    def to_chat_response(result: ChatResult, state: Container) -> schemas.ChatResponse:
        return schemas.ChatResponse(
            status=result.status,
            answer=result.answer,
            mode=result.mode,
            sources=[
                schemas.Source(
                    id=number,
                    source=chunk.source,
                    page=chunk.page,
                    section=chunk.section,
                    similarity=round(chunk.similarity, 4),
                    excerpt=chunk.text[:EXCERPT_CHARS] + ("..." if len(chunk.text) > EXCERPT_CHARS else ""),
                )
                for number, chunk in enumerate(result.sources, start=1)
            ],
            guardrails=schemas.GuardrailReport(
                blocked=result.status == BLOCKED,
                input=[schemas.GuardrailViolation(**v.__dict__) for v in result.input_violations],
                output=[schemas.GuardrailViolation(**v.__dict__) for v in result.output_violations],
            ),
            pii_redacted=result.pii,
            llm=schemas.LLMInfo(
                provider=result.provider or (state.chat.provider if state.chat else "offline"),
                model=result.model or (state.chat.model_name if state.chat else None),
            ),
            degraded_reason=result.degraded_reason,
            request_id=request_id_var.get(),
        )

    # ------------------------------------------------------------------ casos de uso
    def run_triage(state: Container, text: str) -> TriagePrediction:
        if state.triage is None:
            raise HTTPException(503, "Modelo de triagem indisponivel.")
        prediction = state.triage.predict(text)
        metrics = state.metrics
        metrics.predictions.labels(prediction.queue, str(prediction.is_technical).lower()).inc()
        metrics.confidence.observe(prediction.confidence)
        if prediction.needs_human_review:
            metrics.low_confidence.inc()
        state.monitor.observe(prediction.features)
        logger.info(
            "triagem",
            extra={
                "queue": prediction.queue,
                "confidence": round(prediction.confidence, 4),
                "is_technical": prediction.is_technical,
                "n_chars": len(text),
            },
        )
        return prediction

    def run_chat(state: Container, question: str) -> ChatResult:
        if state.chat is None:
            raise HTTPException(503, "Base de conhecimento indisponivel.")
        result = state.chat.answer(question)
        metrics = state.metrics
        metrics.chat.labels(result.status, result.mode).inc()
        for violation in result.input_violations:
            metrics.guardrail_blocks.labels("input", violation.rule_id).inc()
        for violation in result.output_violations:
            metrics.guardrail_blocks.labels("output", violation.rule_id).inc()
        for label, count in result.pii.items():
            metrics.pii.labels(label).inc(count)
        if result.sources:
            metrics.retrieval_similarity.observe(max(chunk.similarity for chunk in result.sources))
        if "llm" in result.timings_ms and result.provider:
            metrics.llm_latency.labels(result.provider).observe(result.timings_ms["llm"] / 1000)
            for kind in ("input_tokens", "output_tokens"):
                if kind in result.usage:
                    metrics.llm_tokens.labels(result.provider, kind).inc(result.usage[kind])
        if result.degraded_reason:
            metrics.llm_degraded.labels(result.degraded_reason).inc()
        logger.info(
            "chat",
            extra={
                "status": result.status,
                "mode": result.mode,
                "input_rules": [v.rule_id for v in result.input_violations],
                "output_rules": [v.rule_id for v in result.output_violations],
                "pii_types": sorted(result.pii),
                "n_sources": len(result.sources),
                "timings_ms": {key: round(value, 1) for key, value in result.timings_ms.items()},
            },
        )
        return result

    # ------------------------------------------------------------------ rotas de negocio
    @app.post("/triage", response_model=schemas.TriageResponse, responses=ERROR_RESPONSES, tags=["Triagem"])
    def triage(payload: schemas.TicketRequest, request: Request) -> schemas.TriageResponse:
        """Classifica a fila de atendimento do chamado com o modelo classico."""
        state = state_of(request)
        prediction = run_triage(state, payload.text)
        return to_triage_response(prediction, state.triage.version)

    @app.post("/chat", response_model=schemas.ChatResponse, responses=ERROR_RESPONSES, tags=["RAG"])
    def chat(payload: schemas.ChatRequest, request: Request) -> schemas.ChatResponse:
        """Responde a duvida apenas com base no manual em PDF, com guardrails de entrada e de saida."""
        state = state_of(request)
        return to_chat_response(run_chat(state, payload.question), state)

    @app.post("/tickets", response_model=schemas.TicketResponse, responses=ERROR_RESPONSES, tags=["Copilot"])
    def tickets(payload: schemas.TicketRequest, request: Request) -> schemas.TicketResponse:
        """Fluxo completo: tria o chamado e, se for um problema tecnico, consulta o manual via RAG."""
        state = state_of(request)
        prediction = run_triage(state, payload.text)
        triage_response = to_triage_response(prediction, state.triage.version)
        if not prediction.is_technical:
            return schemas.TicketResponse(route="human_queue", triage=triage_response, request_id=request_id_var.get())
        chat_response = to_chat_response(run_chat(state, payload.text), state)
        return schemas.TicketResponse(
            route="rag", triage=triage_response, chat=chat_response, request_id=request_id_var.get()
        )

    # ------------------------------------------------------------------ rotas operacionais
    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    @app.get("/health", tags=["Operacao"])
    def health() -> dict[str, str]:
        """Liveness: o processo esta de pe."""
        return {"status": "ok", "version": __version__}

    @app.get("/ready", tags=["Operacao"])
    def ready(request: Request) -> JSONResponse:
        """Readiness: modelo de triagem e base de conhecimento carregados."""
        state = state_of(request)
        body = {
            "ready": state.ready,
            "components": {"triage": state.triage is not None, "chat": state.chat is not None},
            "errors": sorted(state.startup_errors),
        }
        return JSONResponse(status_code=200 if state.ready else 503, content=body)

    @app.get("/info", tags=["Operacao"])
    def info(request: Request) -> dict[str, Any]:
        """Versao do modelo, base de conhecimento indexada, provedor de LLM e catalogo de guardrails."""
        state = state_of(request)
        triage_info = None
        if state.triage is not None:
            metadata = state.triage.metadata
            test = metadata.get("metrics", {}).get("test", {})
            triage_info = {
                "model_version": state.triage.version,
                "candidate": metadata.get("candidate"),
                "trained_at": metadata.get("trained_at"),
                "classes": state.triage.classes,
                "technical_queues": list(settings.technical_queues),
                "test_metrics": {key: value for key, value in test.items() if isinstance(value, float)},
            }
        report = state.knowledge_base_report
        return {
            "version": __version__,
            "environment": settings.environment,
            "triage": triage_info,
            "knowledge_base": report.__dict__ if report else None,
            "llm": {
                "provider": state.chat.provider if state.chat else None,
                "model": state.chat.model_name if state.chat else None,
            },
            "contract": {"max_text_chars": settings.max_text_chars},
            "guardrails": {
                "input": [
                    *(
                        {"rule_id": r.rule_id, "category": r.category, "description": r.description}
                        for r in INPUT_RULES
                    ),
                    {"rule_id": BLOCKED_TERMS_RULE_ID, "category": "blocked_term", "description": "Palavra proibida."},
                    {"rule_id": FLOODING_RULE_ID, "category": "flooding", "description": "Texto repetitivo."},
                ],
                "output": [{"rule_id": rule_id, "description": text} for rule_id, text in OUTPUT_RULES.items()],
            },
        }

    @app.get("/drift", tags=["Operacao"])
    def drift(request: Request) -> dict[str, Any]:
        """PSI das features monitoradas na janela recente de chamados contra a referencia do treino."""
        state = state_of(request)
        status = state.monitor.status()
        state.metrics.observe_drift(status)
        return status

    @app.get("/metrics", include_in_schema=False)
    def metrics(request: Request) -> Response:
        state = state_of(request)
        state.metrics.observe_drift(state.monitor.status())
        return Response(state.metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")

    return app
