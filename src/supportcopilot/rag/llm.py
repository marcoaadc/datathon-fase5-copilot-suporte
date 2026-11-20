"""Fabrica do modelo de chat (OpenAI ou Gemini, via LangChain).

O provedor e escolhido por configuracao. Sem chave, a fabrica devolve ``None`` e o servico de chat
opera em modo extrativo (devolve os trechos do manual, sem geracao): a API continua util e
testavel, e nenhuma chave precisa existir para subir o container.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel

from supportcopilot.config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMHandle:
    provider: str
    model_name: str
    client: BaseChatModel


def build_llm(settings: Settings) -> LLMHandle | None:
    provider = settings.resolved_llm_provider()
    if provider == "offline":
        logger.warning("nenhum provedor de LLM configurado: /chat respondera em modo extrativo")
        return None

    if provider == "openai":
        if settings.openai_api_key is None:
            raise ValueError("COPILOT_LLM_PROVIDER=openai exige OPENAI_API_KEY")
        from langchain_openai import ChatOpenAI

        client: BaseChatModel = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_output_tokens,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        return LLMHandle("openai", settings.openai_model, client)

    if settings.google_api_key is None:
        raise ValueError("COPILOT_LLM_PROVIDER=gemini exige GOOGLE_API_KEY")
    from langchain_google_genai import ChatGoogleGenerativeAI

    client = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    return LLMHandle("gemini", settings.gemini_model, client)
