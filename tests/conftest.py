"""Fixtures compartilhadas.

Os testes nao dependem de rede nem de chave de LLM: o dataset e sintetico, o LLM e um modelo de chat
roteirizado e os embeddings padrao sao lexicais (hashing). O unico arquivo real e o PDF do manual
versionado no repositorio.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from supportcopilot.api.app import create_app
from supportcopilot.api.container import Container, build_container
from supportcopilot.config.settings import Settings, get_settings
from supportcopilot.guardrails.engine import GuardrailEngine
from supportcopilot.rag.bootstrap import build_knowledge_base
from supportcopilot.rag.embeddings import HashingEmbeddings
from supportcopilot.rag.llm import LLMHandle
from supportcopilot.rag.service import ChatService
from supportcopilot.triage import training
from supportcopilot.triage.modeling import Candidate

REPO_ROOT = Path(__file__).resolve().parents[1]
MANUAL_PDF = REPO_ROOT / "data" / "manuals" / "roteador_tucano_ax1800.pdf"
TECHNICAL = ("Technical Support", "IT Support")
FAST_CANDIDATES = (
    Candidate("nb", "complement_nb", {"alpha": 0.5}),
    Candidate("logreg", "logistic_regression", {"C": 10.0}),
)

# Dataset sintetico: cada fila tem um vocabulario proprio; os chamados combinam abertura, problema e
# fecho, de modo que as particoes (separadas por grupos de parafrases) compartilham o vocabulario
# da fila sem repetir a mesma frase.
_OPENERS = ["Hello team,", "Dear support,", "Hi,", "Good morning,", "Urgent:", "Please help,"]
_CLOSERS = ["Thanks in advance.", "Please advise.", "Waiting for your reply.", "This is urgent.", "Best regards."]
_PROBLEMS: dict[str, list[str]] = {
    "Technical Support": [
        "the router keeps dropping the wireless connection",
        "the wifi signal from the router is weak and the connection is slow",
        "the internet connection on the router stopped after the firmware update",
        "my device cannot connect to the wifi network of the router",
        "the router LED is orange and the internet connection is down",
        "the wireless network disappears and the router needs a restart",
    ],
    "IT Support": [
        "the employee account needs a password reset on the corporate domain",
        "the office laptop needs the VPN software installed by the IT team",
        "the shared printer is not visible on the corporate domain for my laptop",
        "the email server rejects the login of my employee account",
        "my corporate laptop cannot open the VPN after the account change",
        "the IT team should install the email software on the office laptop",
    ],
    "Billing and Payments": [
        "I was charged twice on my invoice and need a refund of the payment",
        "the amount on my bill is wrong and I need a corrected invoice",
        "my credit card payment failed but the amount was charged",
        "please send the receipt of the subscription payment and the invoice",
        "the refund of the duplicate payment is missing on my bill",
        "the invoice shows a charge for a payment I already made",
    ],
    "Customer Service": [
        "I would like to update the delivery address of my order",
        "I want to talk to a human agent about my complaint",
        "I want to cancel my subscription plan and close the order",
        "thank you for the help of the agent with my complaint",
        "how do I change the delivery date of my order with an agent",
        "my complaint about the delivery of the order was not answered",
    ],
}
_GERMAN = [
    "Sehr geehrtes Team, die Verbindung bricht alle {n} Minuten ab, bitte um Hilfe",
    "Die Rechnung {n} ist falsch, ich möchte eine Rückerstattung erhalten",
    "Das Passwort für das Konto {n} muss zurückgesetzt werden",
    "Der Drucker {n} funktioniert nach dem Update nicht mehr",
]


def make_tickets(per_queue: int = 60, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for queue, problems in _PROBLEMS.items():
        for index in range(per_queue):
            opener, closer = rng.choice(_OPENERS), rng.choice(_CLOSERS)
            first, second = rng.choice(problems, size=2, replace=False)
            body = f"{opener} {first} and {second}. Ticket reference {index}. {closer}"
            rows.append({"subject": None, "body": body, "queue": queue, "language": "en"})
    queues = list(_PROBLEMS)
    for position, template in enumerate(_GERMAN):
        for index in range(per_queue // 3):
            rows.append(
                {"subject": "Anfrage", "body": template.format(n=index), "queue": queues[position], "language": "de"}
            )
    frame = pd.DataFrame(rows)
    frame["priority"] = "medium"
    frame["type"] = "Incident"
    return frame


@pytest.fixture(autouse=True)
def _clean_settings_cache(monkeypatch: pytest.MonkeyPatch):
    """Isola cada teste de chaves de LLM e de configuracao presentes no ambiente de quem roda."""
    for name in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def build_settings(root: Path, **overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "data_dir": root / "data",
        "models_dir": root / "models",
        "reports_dir": root / "reports",
        "technical_queues": TECHNICAL,
        "embedding_model": "hashing",
        "llm_provider": "offline",
        "rate_limit_per_minute": 0,
        "min_relevance": 0.12,
        "drift_window_size": 60,
        "drift_min_samples": 20,
        "dataset_sha256": "",
    }
    return Settings(_env_file=None, **{**defaults, **overrides})


@pytest.fixture(scope="session")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Diretorio com as particoes sinteticas, o manual e um modelo treinado (uma vez por sessao)."""
    from supportcopilot.data import ingest

    root = tmp_path_factory.mktemp("workspace")
    settings = build_settings(root)
    partitions, _ = ingest.prepare(make_tickets(), settings)
    settings.processed_dir.mkdir(parents=True)
    for name, part in partitions.items():
        part.to_parquet(settings.processed_dir / f"{name}.parquet", index=False)
    settings.manuals_dir.mkdir(parents=True)
    shutil.copy(MANUAL_PDF, settings.manuals_dir / MANUAL_PDF.name)
    training.train(settings, FAST_CANDIDATES)
    return root


@pytest.fixture
def settings(workspace: Path) -> Settings:
    return build_settings(workspace)


class ScriptedChatModel(BaseChatModel):
    """Modelo de chat de teste: a resposta vem de uma funcao que recebe as mensagens do prompt."""

    responder: Callable[[list[BaseMessage]], str]
    calls: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        self.calls.append(messages)
        message = AIMessage(
            content=self.responder(messages),
            usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def scripted_llm(responder: Callable[[list[BaseMessage]], str] | str) -> LLMHandle:
    function = responder if callable(responder) else (lambda _messages: responder)
    return LLMHandle("scripted", "scripted-1", ScriptedChatModel(responder=function, calls=[]))


@pytest.fixture(scope="session")
def knowledge_base(workspace: Path):
    kb, report = build_knowledge_base(build_settings(workspace), GuardrailEngine(), HashingEmbeddings())
    return kb, report


@pytest.fixture
def make_chat(knowledge_base, settings: Settings):
    """Fabrica de ``ChatService`` sobre o manual real, com o LLM que o teste quiser."""

    def factory(llm: LLMHandle | None = None, **overrides: Any) -> ChatService:
        options = {"min_relevance": settings.min_relevance, "retrieval_k": 4, "retrieval_candidates": 12}
        return ChatService(knowledge_base[0], GuardrailEngine(), llm, **{**options, **overrides})

    return factory


@pytest.fixture(scope="session")
def base_container(workspace: Path) -> Container:
    return build_container(build_settings(workspace))


@pytest.fixture
def client(base_container: Container, settings: Settings):
    """Cliente HTTP sobre a aplicacao real (modelo sintetico, manual real, LLM desligado)."""
    container = fresh_container(base_container, settings)
    with TestClient(create_app(container=container)) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        yield test_client


def fresh_container(base: Container, settings: Settings, **overrides: Any) -> Container:
    """Reaproveita modelo e base de conhecimento (caros) com metricas e monitor novos por teste."""
    from supportcopilot.drift.monitor import DriftMonitor
    from supportcopilot.observability.metrics import Metrics

    monitor = DriftMonitor(
        base.triage.reference_profile if base.triage else None,
        window_size=settings.drift_window_size,
        min_samples=settings.drift_min_samples,
    )
    fields: dict[str, Any] = {
        "settings": settings,
        "metrics": Metrics(),
        "guardrails": base.guardrails,
        "monitor": monitor,
        "triage": base.triage,
        "chat": base.chat,
        "knowledge_base_report": base.knowledge_base_report,
    }
    return Container(**{**fields, **overrides})
