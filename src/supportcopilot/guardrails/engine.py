"""Motor de guardrails: avaliacao da entrada, do contexto recuperado e da saida do LLM.

Tres pontos de controle, em camadas (nenhum depende de o LLM "se comportar"):

1. **entrada** (``check_input``): a pergunta e avaliada antes de qualquer busca ou chamada ao LLM.
   Pergunta bloqueada nao gera custo nem sai da aplicacao;
2. **contexto** (``check_context``): cada trecho do PDF e avaliado na indexacao. Um manual
   adulterado com instrucoes embutidas (injecao indireta) nao chega ao prompt;
3. **saida** (``check_output``): a resposta do LLM e verificada antes de ser devolvida: vazamento
   do prompt de sistema, ausencia de citacao e valores que nao existem no manual.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass, field

from supportcopilot.guardrails import rules
from supportcopilot.guardrails.normalize import matching_views, normalize_for_matching, strip_accents

MAX_REPEATED_RUN = 40
LEAK_WINDOW_WORDS = 8
MIN_UNIQUE_TOKEN_RATIO = 0.2
FLOOD_MIN_TOKENS = 30

OUT_PROMPT_LEAK = "GO-01"
OUT_NO_CITATION = "GO-02"
OUT_UNGROUNDED_VALUE = "GO-03"
OUT_UNSAFE_CONTENT = "GO-04"
OUTPUT_RULES: dict[str, str] = {
    OUT_PROMPT_LEAK: "A resposta reproduz o prompt de sistema (canario ou regras internas).",
    OUT_NO_CITATION: "A resposta nao cita nenhum trecho valido do manual.",
    OUT_UNGROUNDED_VALUE: "A resposta traz numero, endereco IP ou URL que nao existe nos trechos recuperados.",
    OUT_UNSAFE_CONTENT: "A resposta indica que o modelo aceitou trocar de papel ou contem termo proibido.",
}


@dataclass(frozen=True)
class Violation:
    rule_id: str
    category: str
    description: str


@dataclass(frozen=True)
class Verdict:
    violations: list[Violation] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return not self.violations

    @property
    def rule_ids(self) -> list[str]:
        return sorted({violation.rule_id for violation in self.violations})


_CITATION = re.compile(r"\[(\d{1,2})\]")
_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)
_DOMAIN = re.compile(
    r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|br|io|gov|edu|local|lan)(?:\.[a-z]{2})?\b", re.IGNORECASE
)
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_STEP_NUMBER = re.compile(r"(?m)^\s*\d{1,2}[.)](?=\s)")
_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w]*\])")
_COMPLIANCE = re.compile(
    r"\b(?:modo (?:desenvolvedor|dev|deus|irrestrito) (?:ativado|habilitado|ligado)|developer mode (?:enabled|activated|on)"
    r"|jailbreak (?:ativado|enabled|successful)|as dan\b|como dan\b|\[dan\]|i am now (?:free|unrestricted|dan)"
    r"|agora (?:estou|sou) (?:livre|sem restricoes)|ignorando (?:as )?(?:instrucoes|regras) anteriores"
    r"|ignoring (?:my |the )?previous instructions)"
)


class GuardrailEngine:
    def __init__(self, extra_blocked_terms: tuple[str, ...] = ()) -> None:
        self._blocked_terms = rules.blocked_terms_pattern(extra_blocked_terms)

    # ------------------------------------------------------------------ entrada
    def check_input(self, text: str) -> Verdict:
        """Avalia a pergunta do usuario. Qualquer violacao bloqueia."""
        violations = self._match_rules(text)
        violations.extend(self._decoded_payload_violations(text, {v.rule_id for v in violations}))
        if self._blocked_terms.search(normalize_for_matching(text)) or self._blocked_terms.search(
            normalize_for_matching(text, leet=True)
        ):
            violations.append(
                Violation(
                    rules.BLOCKED_TERMS_RULE_ID, "blocked_term", "A pergunta contem palavra ou expressao proibida."
                )
            )
        if self._is_flooding(text):
            violations.append(
                Violation(
                    rules.FLOODING_RULE_ID, "flooding", "Texto repetitivo usado para diluir as instrucoes do sistema."
                )
            )
        return Verdict(violations)

    def _match_rules(self, text: str, rule_set: tuple[rules.Rule, ...] = rules.INPUT_RULES) -> list[Violation]:
        views = matching_views(text)
        found: list[Violation] = []
        for rule in rule_set:
            targets = (text,) if rule.raw else views
            if any(pattern.search(target) for pattern in rule.patterns for target in targets):
                found.append(Violation(rule.rule_id, rule.category, rule.description))
        return found

    def _decoded_payload_violations(self, text: str, already: set[str]) -> list[Violation]:
        """Decodifica blocos base64 e reavalia o conteudo: o disfarce nao esconde a instrucao.

        O limiar aqui e menor que o de GR-06 (que bloqueia qualquer bloco longo): um payload curto
        como "aWdub3JlIHByZXZpb3VzIGluc3RydWN0aW9ucw==" so e bloqueado se, decodificado, violar
        alguma regra. Uma palavra comum que por acaso use o alfabeto base64 decodifica em lixo e
        nao casa com nada.
        """
        found: list[Violation] = []
        for match in rules.BASE64_DECODE_PATTERN.finditer(text):
            try:
                decoded = base64.b64decode(match.group(0), validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError, ValueError):
                continue
            decoded_violations = [
                violation
                for violation in self._match_rules(decoded)
                if violation.rule_id != rules.ENCODED_PAYLOAD_RULE_ID
            ]
            if decoded_violations and rules.ENCODED_PAYLOAD_RULE_ID not in already:
                already.add(rules.ENCODED_PAYLOAD_RULE_ID)
                payload_rule = next(r for r in rules.INPUT_RULES if r.rule_id == rules.ENCODED_PAYLOAD_RULE_ID)
                found.append(Violation(payload_rule.rule_id, payload_rule.category, payload_rule.description))
            for violation in decoded_violations:
                if violation.rule_id not in already:
                    already.add(violation.rule_id)
                    found.append(violation)
        return found

    @staticmethod
    def _is_flooding(text: str) -> bool:
        # So letras e digitos: uma linha de tracos colada como separador nao e flooding.
        if re.search(r"([^\W_])\1{" + str(MAX_REPEATED_RUN) + r",}", text):
            return True
        tokens = text.casefold().split()
        return len(tokens) >= FLOOD_MIN_TOKENS and len(set(tokens)) / len(tokens) < MIN_UNIQUE_TOKEN_RATIO

    # ------------------------------------------------------------------ contexto (injecao indireta)
    def check_context(self, text: str) -> Verdict:
        """Avalia um trecho do documento: instrucoes embutidas no PDF nao podem chegar ao prompt."""
        injection_rules = tuple(rule for rule in rules.INPUT_RULES if rule.rule_id in rules.CONTEXT_RULE_IDS)
        return Verdict(self._match_rules(text, injection_rules))

    # ------------------------------------------------------------------ saida
    def check_output(
        self,
        answer: str,
        contexts: list[str],
        question: str = "",
        canary: str | None = None,
        protected_text: str | None = None,
        require_citation: bool = True,
        check_grounding: bool = True,
    ) -> Verdict:
        violations: list[Violation] = []
        normalized = normalize_for_matching(answer)

        leaked = canary is not None and canary.casefold() in answer.casefold()
        leaked = leaked or (protected_text is not None and shares_passage(answer, protected_text))
        if leaked:
            violations.append(self._output_violation(OUT_PROMPT_LEAK, "prompt_leak"))

        if _COMPLIANCE.search(normalized) or self._blocked_terms.search(normalized):
            violations.append(self._output_violation(OUT_UNSAFE_CONTENT, "unsafe_content"))

        if require_citation:
            cited = {int(number) for number in _CITATION.findall(answer)}
            if not cited or not cited.issubset(range(1, len(contexts) + 1)):
                violations.append(self._output_violation(OUT_NO_CITATION, "missing_citation"))

        if check_grounding and unsupported_values(answer, [*contexts, question]):
            violations.append(self._output_violation(OUT_UNGROUNDED_VALUE, "ungrounded_value"))
        return Verdict(violations)

    @staticmethod
    def _output_violation(rule_id: str, category: str) -> Violation:
        return Violation(rule_id, category, OUTPUT_RULES[rule_id])


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", normalize_for_matching(text))


def shares_passage(answer: str, protected: str, window: int = LEAK_WINDOW_WORDS) -> bool:
    """True se a resposta reproduz uma sequencia de ``window`` palavras do texto protegido.

    Detecta o vazamento do prompt de sistema mesmo parcial (so uma regra), sem depender de o
    modelo ter copiado o canario. A janela precisa ser longa o bastante para nao confundir com
    vazamento uma abertura comum de resposta ("com base nos trechos do manual, ...").
    """
    protected_words = _words(protected)
    passages = {" ".join(protected_words[i : i + window]) for i in range(len(protected_words) - window + 1)}
    answer_words = _words(answer)
    return any(" ".join(answer_words[i : i + window]) in passages for i in range(len(answer_words) - window + 1))


def _canonical(text: str) -> str:
    """Forma comparavel: minusculas, sem acento, virgula decimal como ponto, sem separador de milhar."""
    text = strip_accents(text.casefold())
    return re.sub(r"(?<=\d),(?=\d)", ".", text)


def _bare(value: str) -> str:
    """Endereco sem esquema, sem ``www.`` e sem pontuacao final: ``http://x.y/`` e ``x.y`` sao o mesmo valor."""
    return re.sub(r"^(?:https?://)?(?:www\.)?", "", value).rstrip(".,;:/")


def _hard_values(text: str) -> set[str]:
    """Valores "duros" de um texto: URLs, dominios, IPs e numeros com dois digitos ou mais.

    Numeracao de passos ("10. Clique em Salvar") e citacoes ("[2]") nao sao valores.
    """
    canonical = _canonical(_CITATION.sub(" ", text))
    canonical = _STEP_NUMBER.sub(" ", canonical)
    values: set[str] = set()
    for pattern in (_URL, _DOMAIN, _IPV4):
        for match in pattern.finditer(canonical):
            bare = _bare(match.group(0))
            values.add(bare)
            values.add(bare.split("/", 1)[0])  # o host de uma URL tambem conta
        canonical = pattern.sub(" ", canonical)
    for match in _NUMBER.finditer(canonical):
        number = match.group(0).rstrip(".,")
        if sum(char.isdigit() for char in number) >= 2:
            values.add(number)
    return values


def unsupported_values(answer: str, sources: list[str]) -> list[str]:
    """Valores duros da resposta que nao aparecem em nenhuma fonte (trechos do manual ou pergunta).

    E uma checagem independente de idioma: o LLM pode reescrever o texto, mas um IP, uma URL, um
    tempo de espera ou um numero de porta precisam existir no manual. Valor inventado e o tipo de
    alucinacao mais perigoso em suporte tecnico.

    A comparacao e por valor inteiro, nao por trecho de texto: "192.168.10.10" nao e sustentado por
    "192.168.10.100", nem "16" por "192.168.10.1".
    """
    supported = _hard_values(" \n ".join(sources))
    return sorted(value for value in _hard_values(answer) if value not in supported)
