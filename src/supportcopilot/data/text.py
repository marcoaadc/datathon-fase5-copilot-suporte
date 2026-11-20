"""Normalizacao de texto compartilhada entre o treino e a API.

A mesma funcao limpa o chamado no treino e na inferencia: assim o modelo nunca ve em producao um
formato de texto diferente do que viu ao ser treinado (paridade treino x serving).
"""

from __future__ import annotations

import re
import unicodedata

# Caracteres de controle e de formatacao invisivel (zero-width, bidi), exceto \n e \t.
_INVISIBLE = re.compile(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
_HTML_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_SPACES = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


def clean_text(text: str, unescape: bool = False) -> str:
    """Normaliza Unicode (NFKC), remove caracteres invisiveis e compacta espacos.

    ``unescape`` converte quebras de linha escapadas ("\\n" como dois caracteres), um artefato do
    arquivo do dataset. Fica desligado na API: la uma barra invertida e conteudo do usuario (um
    caminho como ``C:\\network\\temp``), e o JSON ja entrega quebras de linha de verdade.
    """
    text = unicodedata.normalize("NFKC", str(text))
    if unescape:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ")
    text = _HTML_BREAK.sub("\n", text)
    text = _INVISIBLE.sub("", text)
    text = _SPACES.sub(" ", text)
    text = _BLANK_LINES.sub("\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def compose_ticket(subject: str | None, body: str | None) -> str:
    """Junta assunto e corpo do dataset em um unico texto, como o cliente enviaria em um campo so."""
    subject = clean_text(subject or "", unescape=True)
    body = clean_text(body or "", unescape=True)
    if subject and body:
        return f"{subject}\n{body}"
    return subject or body


def truncate(text: str, max_chars: int) -> str:
    """Corta no limite do contrato sem partir a ultima palavra."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    head, _, _ = cut.rpartition(" ")
    return (head or cut).rstrip()


def dedup_key(text: str) -> str:
    """Chave para detectar duplicatas: minusculas, sem pontuacao e sem espacos repetidos."""
    return re.sub(r"\W+", " ", text.casefold()).strip()
