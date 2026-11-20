"""Configuracao central (pydantic-settings).

Toda chave pode ser sobrescrita por variavel de ambiente com o prefixo ``COPILOT_`` ou por um
arquivo ``.env``. As chaves de LLM tambem aceitam os nomes convencionais dos provedores
(``OPENAI_API_KEY``, ``GOOGLE_API_KEY``/``GEMINI_API_KEY``) e sao ``SecretStr``: nunca aparecem em
logs nem em ``repr``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Revisao fixa do dataset no Hugging Face: o download e reproduzivel e o hash e conferido.
DATASET_REPO = "Tobi-Bueck/customer-support-tickets"
DATASET_REVISION = "ddf1c81a5475992c4fa6752bf1e8b4e31f07bbeb"
DATASET_FILE = "aa_dataset-tickets-multi-lang-5-2-50-version.csv"
DATASET_SHA256 = "f187c090e59581c2bbf3aa1377c8db4dd647464ecf2ae51bf8966e42e0ed6bc0"

# Filas cujo chamado e um problema tecnico: sao as que acionam o RAG sobre o manual.
TECHNICAL_QUEUES: tuple[str, ...] = (
    "Technical Support",
    "IT Support",
    "Product Support",
    "Service Outages and Maintenance",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COPILOT_", env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    environment: str = "local"
    log_level: str = "INFO"
    log_json: bool = False
    seed: int = 42

    # Diretorios
    data_dir: Path = Path("data")
    models_dir: Path = Path("models")
    reports_dir: Path = Path("reports")

    # Dataset publico de chamados
    dataset_repo: str = DATASET_REPO
    dataset_revision: str = DATASET_REVISION
    dataset_file: str = DATASET_FILE
    dataset_sha256: str = DATASET_SHA256
    reference_language: str = "en"
    drift_language: str = "de"
    validation_fraction: float = Field(0.12, gt=0, lt=0.3)
    test_fraction: float = Field(0.12, gt=0, lt=0.3)
    # Chamados da referencia reservados para simular o fluxo de producao (nunca vistos no treino).
    production_fraction: float = Field(0.12, gt=0, lt=0.3)

    # Contrato de entrada (o mesmo limite vale no treino e na API)
    max_text_chars: int = Field(1000, ge=10)

    # Triagem
    technical_queues: tuple[str, ...] = TECHNICAL_QUEUES
    technical_threshold: float = Field(0.5, gt=0, lt=1)
    low_confidence_threshold: float = Field(0.40, gt=0, lt=1)

    # MLflow (vazio = rastreamento desativado)
    mlflow_tracking_uri: str | None = None
    mlflow_experiment: str = "copilot-triagem"
    mlflow_registered_model: str = "support-ticket-triage"

    # RAG
    chunk_size: int = Field(700, ge=100)
    chunk_overlap: int = Field(120, ge=0)
    retrieval_k: int = Field(4, ge=1, le=10)
    retrieval_candidates: int = Field(12, ge=1, le=50)
    # Escolhido pela varredura de scripts/evaluate_rag.py (reports/rag/retrieval_eval.md).
    min_relevance: float = Field(0.35, ge=0, le=1)
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_cache_dir: Path = Path(".cache/fastembed")

    # LLM. "auto" usa o provedor cuja chave estiver configurada; sem chave, cai no modo extrativo.
    llm_provider: Literal["auto", "openai", "gemini", "offline"] = "auto"
    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("COPILOT_OPENAI_API_KEY", "OPENAI_API_KEY")
    )
    # Nomes de modelo mudam e sao descontinuados pelos provedores: sao configuracao, nao codigo.
    # Confira o que esta disponivel na sua conta com `python -m supportcopilot.pipelines.check_llm`.
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    google_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("COPILOT_GOOGLE_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")
    )
    gemini_model: str = "gemini-3.5-flash"
    llm_temperature: float = Field(0.0, ge=0, le=1)
    llm_max_output_tokens: int = Field(600, ge=50, le=4000)
    llm_timeout_seconds: float = Field(30.0, gt=0)
    llm_max_retries: int = Field(2, ge=0, le=5)

    # Guardrails
    extra_blocked_terms: tuple[str, ...] = ()
    grounding_check: bool = True

    # Monitor de drift em producao (janela deslizante de requisicoes)
    drift_window_size: int = Field(500, ge=50)
    # Em janelas simuladas sem drift, o ruido amostral do PSI da alarme falso em 38% das janelas de
    # 100 chamados e em 0,1% das de 200 (ver docs/drift.md).
    drift_min_samples: int = Field(200, ge=20)
    psi_warning: float = Field(0.10, gt=0)
    psi_critical: float = Field(0.25, gt=0)

    # Seguranca da API (vazio = sem autenticacao, apenas para uso local)
    api_key: SecretStr | None = None
    rate_limit_per_minute: int = Field(120, ge=0)
    cors_origins: tuple[str, ...] = ()

    @field_validator("api_key", "openai_api_key", "google_api_key", mode="before")
    @classmethod
    def _empty_secret_is_unset(cls, value: object) -> object:
        """``COPILOT_API_KEY=`` (vazio) significa "sem chave", e nao "a chave e a string vazia"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    # ------------------------------------------------------------------ caminhos derivados
    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def manuals_dir(self) -> Path:
        return self.data_dir / "manuals"

    @property
    def triage_dir(self) -> Path:
        return self.models_dir / "triage"

    @property
    def drift_reports_dir(self) -> Path:
        return self.reports_dir / "drift"

    @property
    def dataset_url(self) -> str:
        return (
            f"https://huggingface.co/datasets/{self.dataset_repo}/resolve/{self.dataset_revision}/{self.dataset_file}"
        )

    def resolved_llm_provider(self) -> Literal["openai", "gemini", "offline"]:
        """Provedor efetivo: respeita a escolha explicita e, em ``auto``, segue a chave disponivel."""
        if self.llm_provider == "auto":
            if self.openai_api_key is not None and self.openai_api_key.get_secret_value():
                return "openai"
            if self.google_api_key is not None and self.google_api_key.get_secret_value():
                return "gemini"
            return "offline"
        return self.llm_provider


@lru_cache
def get_settings() -> Settings:
    return Settings()
