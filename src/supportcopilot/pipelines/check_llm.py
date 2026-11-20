"""CLI: confere se o provedor de LLM configurado responde (uma chamada minima, sem dados de usuario).

Util logo depois de configurar a chave: nomes de modelo sao descontinuados pelos provedores, e um
nome invalido so apareceria como "modo extrativo" na primeira pergunta ao /chat.

Codigos de saida: 0 = respondeu; 1 = falhou; 2 = nenhum provedor configurado.
"""

from __future__ import annotations

import argparse
import time

from langchain_core.messages import HumanMessage

from supportcopilot.config.settings import get_settings
from supportcopilot.observability.logs import configure_logging
from supportcopilot.rag.llm import build_llm

PROBE = "Responda apenas com a palavra: ok"


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    settings = get_settings()
    configure_logging("WARNING", settings.log_json)
    handle = build_llm(settings)
    if handle is None:
        print("Nenhum provedor configurado (defina OPENAI_API_KEY ou GOOGLE_API_KEY). O /chat usa o modo extrativo.")
        return 2
    started = time.perf_counter()
    try:
        response = handle.client.invoke([HumanMessage(content=PROBE)])
    except Exception as error:
        print(f"FALHA em {handle.provider}/{handle.model_name}: {type(error).__name__}: {str(error)[:400]}")
        print("Verifique a chave e o nome do modelo (COPILOT_OPENAI_MODEL / COPILOT_GEMINI_MODEL).")
        return 1
    elapsed = time.perf_counter() - started
    text = response.content if isinstance(response.content, str) else str(response.content)
    print(f"OK: {handle.provider}/{handle.model_name} respondeu em {elapsed:.1f}s: {text.strip()[:80]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
