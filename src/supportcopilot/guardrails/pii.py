"""Deteccao e mascaramento de dados pessoais (Privacy by Design, LGPD).

Tudo o que sai da aplicacao rumo ao LLM passa por aqui antes: a pergunta do usuario, o chamado e os
trechos do manual. O dado pessoal e trocado por um marcador (``[CPF]``, ``[EMAIL]``...), que
preserva o sentido da frase para o modelo sem expor o titular.

Cada tipo tem um padrao e, quando existe, um validador (digitos verificadores de CPF/CNPJ, Luhn
para cartao): validar reduz falso positivo em numeros que apenas se parecem com um documento.
"""

from __future__ import annotations

import ipaddress
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Redaction:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def types(self) -> list[str]:
        return sorted(self.counts)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def valid_cpf(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(digit) * weight for digit, weight in zip(digits[:size], range(size + 1, 1, -1), strict=True))
        if (total * 10 % 11) % 10 != int(digits[size]):
            return False
    return True


def valid_cnpj(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False
    for size in (12, 13):
        weights = [*range(size - 7, 1, -1), *range(9, 1, -1)]
        total = sum(int(digit) * weight for digit, weight in zip(digits[:size], weights, strict=True))
        remainder = total % 11
        if (0 if remainder < 2 else 11 - remainder) != int(digits[size]):
            return False
    return True


def valid_card(value: str) -> bool:
    digits = _digits(value)
    if not 13 <= len(digits) <= 19 or digits == digits[0] * len(digits):
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2 == 1:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


def public_ip(value: str) -> bool:
    """So IP publico identifica um assinante; 192.168.x.x e afins fazem parte do suporte tecnico."""
    if value in PUBLIC_DNS:
        return False
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global


@dataclass(frozen=True)
class _Pattern:
    label: str
    regex: re.Pattern[str]
    validator: Callable[[str], bool] | None = None
    group: int = 0


_CREDENTIAL_PREFIX = (
    r"\b(?:senha|password|passwd|pwd|passphrase|pin|chave(?:\s+de\s+seguran[cç]a)?)"
    r"(?:\s+(?:d[oae]\s+)?(?:wi-?fi|rede|roteador|admin|acesso|network|router))?"
)
# Resolvedores de DNS publicos: aparecem em duvidas de configuracao e nao identificam ninguem.
PUBLIC_DNS = frozenset(
    {"8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9", "149.112.112.112", "208.67.222.222", "208.67.220.220"}
)

# A ordem define a prioridade quando dois padroes casam no mesmo trecho.
_PATTERNS: tuple[_Pattern, ...] = (
    _Pattern("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    _Pattern("CNPJ", re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)"), valid_cnpj),
    _Pattern("CPF", re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"), valid_cpf),
    # IMEI tambem passa no algoritmo de Luhn; quando o texto diz que e um IMEI, nao e cartao.
    _Pattern(
        "CARTAO", re.compile(r"(?<!\d)(?<!imei )(?<!imei: )(?:\d[ -]?){12,18}\d(?!\d)", re.IGNORECASE), valid_card
    ),
    _Pattern("RG", re.compile(r"(?<![\d.])\d{1,2}\.\d{3}\.\d{3}-[\dXx](?![\d-])")),
    _Pattern("MAC", re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")),
    # Quatro numeros separados por ponto tambem sao uma versao de firmware ("versao 2.1.0.5").
    _Pattern(
        "IP",
        re.compile(
            r"(?<![\d.])(?<!firmware )(?<!vers[aã]o )(?<!version )(?<![vV])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])",
            re.IGNORECASE,
        ),
        public_ip,
    ),
    # Telefone so com evidencia de formato (DDD entre parenteses, +55 ou separadores): uma sequencia
    # crua de 10 ou 11 digitos e mais provavelmente um protocolo ou numero de pedido.
    _Pattern(
        "TELEFONE",
        re.compile(
            r"(?<![\d.])(?:"
            r"(?:\+?55[\s.-]?)?\(\d{2}\)\s?9?[\s.-]?\d{4}[\s.-]?\d{4}"
            r"|\+55[\s.-]?\d{2}[\s.-]?9?[\s.-]?\d{4}[\s.-]?\d{4}"
            r"|\d{2}[\s.-]9?[\s.-]?\d{4}[\s.-]?\d{4}"
            r"|9\d{4}[\s.-]\d{4}"
            r")(?![\d.])"
        ),
    ),
    _Pattern("CEP", re.compile(r"(?<!\d)\d{5}-\d{3}(?!\d)")),
    _Pattern(
        "NASCIMENTO",
        re.compile(r"\b(?:nasc\w*|born|birth\w*|dob)\b\D{0,20}(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})(?!\d)", re.IGNORECASE),
        group=1,
    ),
    # Segredos digitados no meio da frase. Tres formas, da mais para a menos explicita:
    #   senha: valor / senha = valor      qualquer valor
    #   senha e "valor entre aspas"       o conteudo inteiro das aspas, com espacos
    #   senha e Valor#2024                so se o valor "parece segredo" (tem digito ou simbolo);
    #                                     "a senha e obrigatoria" e "the password is incorrect" nao sao
    _Pattern("SENHA", re.compile(_CREDENTIAL_PREFIX + r"\s*[:=]\s*[\"']?([^\s\"',;]{4,64})", re.IGNORECASE), group=1),
    _Pattern(
        "SENHA",
        re.compile(_CREDENTIAL_PREFIX + r"\s+(?:é|eh|e|is|was|era)\s+[\"']([^\"']{4,64})[\"']", re.IGNORECASE),
        group=1,
    ),
    _Pattern(
        "SENHA",
        re.compile(
            _CREDENTIAL_PREFIX + r"\s+(?:é|eh|is|was|era)\s+((?=[^\s,;]*[\d@#$%&*!_+=^~])[^\s\"',;]{4,64})",
            re.IGNORECASE,
        ),
        group=1,
    ),
    # Nomes so em construcoes explicitas, com inicial maiuscula ou tudo em maiusculas.
    _Pattern(
        "NOME",
        re.compile(
            r"\b(?:[Mm]eu nome (?:e|é)|[Mm]e chamo|[Ss]ou o|[Ss]ou a|[Mm]y name is|[Ii] am called|MEU NOME (?:E|É)"
            r"|MY NAME IS)\s+"
            r"((?:[A-ZÀ-Ý][a-zà-ÿ]+|[A-ZÀ-Ý]{2,})(?:\s+(?:d[aeo]s?\s+|D[AEO]S?\s+)?(?:[A-ZÀ-Ý][a-zà-ÿ]+|[A-ZÀ-Ý]{2,})){0,3})"
        ),
        group=1,
    ),
)


def find_pii(text: str) -> list[tuple[int, int, str]]:
    """Trechos ``(inicio, fim, tipo)`` sem sobreposicao, ja resolvida a prioridade entre padroes."""
    spans: list[tuple[int, int, str]] = []
    for pattern in _PATTERNS:
        for match in pattern.regex.finditer(text):
            start, end = match.span(pattern.group)
            if start == end or (pattern.validator and not pattern.validator(match.group(pattern.group))):
                continue
            if any(start < other_end and other_start < end for other_start, other_end, _ in spans):
                continue
            spans.append((start, end, pattern.label))
    return sorted(spans)


def redact(text: str, allowed_in: str | None = None) -> Redaction:
    """Troca cada dado pessoal por ``[TIPO]`` e devolve o texto mascarado com a contagem por tipo.

    ``allowed_in``: texto de referencia (os trechos do manual). Um valor que ja aparece nele e
    informacao publica do documento, nao dado do usuario, e por isso nao e mascarado.
    """
    spans = find_pii(text)
    if allowed_in:
        spans = [(start, end, label) for start, end, label in spans if text[start:end] not in allowed_in]
    if not spans:
        return Redaction(text=text)
    parts: list[str] = []
    cursor = 0
    for start, end, label in spans:
        parts.append(text[cursor:start])
        parts.append(f"[{label}]")
        cursor = end
    parts.append(text[cursor:])
    return Redaction(text="".join(parts), counts=dict(Counter(label for _, _, label in spans)))
