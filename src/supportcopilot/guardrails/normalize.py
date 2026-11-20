"""Normalizacao usada so para *detectar* ataques (o texto original nunca e alterado por ela).

Quem tenta burlar um filtro de palavras raramente escreve a frase limpa: troca letras por numeros
("1gn0re"), separa caracteres ("i g n o r e"), usa letras de outros alfabetos ou caracteres
invisiveis. As regras rodam sobre uma copia do texto em que esses disfarces foram desfeitos.
"""

from __future__ import annotations

import re
import unicodedata

_INVISIBLE = re.compile(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})
# Letras cirilicas e gregas visualmente identicas as latinas (ataque de homoglifos).
_HOMOGLYPHS = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i", "ѕ": "s", "ј": "j",
        "α": "a", "ε": "e", "ο": "o", "ρ": "p", "ι": "i", "κ": "k", "ν": "v", "τ": "t",
    }
)  # fmt: skip
# Letras isoladas separadas por espaco ou pontuacao: "i g n o r e", "i.g.n.o.r.e", "i-g-n-o-r-e".
# Um unico separador entre as letras: dois espacos seguidos continuam sendo fronteira de palavra
# ("i g n o r e  p r e v i o u s" vira "ignore previous", e nao uma palavra so).
_SPACED = re.compile(r"(?<![^\W_])(?:[^\W_][ .\-_*|/\\]){3,}[^\W_](?![^\W_])")
_SEPARATORS = re.compile(r"[ .\-_*|/\\]+")
_WHITESPACE = re.compile(r"\s+")


def strip_invisible(text: str) -> str:
    return _INVISIBLE.sub("", text)


def strip_accents(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", text) if not unicodedata.combining(char))


def collapse_spaced_letters(text: str) -> str:
    return _SPACED.sub(lambda match: _SEPARATORS.sub("", match.group(0)), text)


def normalize_for_matching(text: str, leet: bool = False) -> str:
    """Minusculas, sem acento, sem invisiveis, sem letras espacadas; opcionalmente desfaz leetspeak."""
    text = unicodedata.normalize("NFKC", text)
    text = strip_invisible(text).casefold().translate(_HOMOGLYPHS)
    text = strip_accents(text)
    text = collapse_spaced_letters(text)
    if leet:
        text = text.translate(_LEET)
    return _WHITESPACE.sub(" ", text).strip()


def matching_views(text: str) -> tuple[str, ...]:
    """Versoes do texto sobre as quais as regras rodam: normalizada e com leetspeak desfeito."""
    plain = normalize_for_matching(text)
    leet = normalize_for_matching(text, leet=True)
    return (plain,) if leet == plain else (plain, leet)
