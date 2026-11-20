"""Catalogo de regras de guardrail de entrada.

Cada regra tem um identificador estavel (``GR-xx``), usado nas respostas da API, nas metricas e na
documentacao (``docs/guardrails.md``). As expressoes rodam sobre o texto normalizado (minusculas,
sem acento, disfarces desfeitos), entao sao escritas sem acento e cobrem portugues e ingles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BLOCK = "block"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    description: str
    patterns: tuple[re.Pattern[str], ...]
    raw: bool = False  # True: roda sobre o texto original (delimitadores, blobs codificados)


def _compile(*patterns: str, flags: int = re.IGNORECASE) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, flags) for pattern in patterns)


# Vocabulario reutilizado entre regras -----------------------------------------------------------
_IGNORE = (
    r"(?:ignor\w*|desconsider\w*|esquec\w*|disregard\w*|forget\w*|overrid\w*|bypass\w*|burl\w*|descart\w*"
    r"|desobedec\w*|disobey\w*|viol[ae]\w*|quebr\w*|skip\w*|pul[ae]\w*|drop|abandon\w*|nao (?:siga|obedeca|respeite)"
    r"|do not follow|don'?t follow|stop following|pare de seguir|deixe de (?:lado|seguir))"
)
_RULES_WORDS = (
    r"(?:instruc\w*|instruct\w*|regras?|rules?|prompts?|diretriz\w*|guidelines?|orientac\w*|restric\w*|restrict\w*"
    r"|polic\w*|politic\w*|limitac\w*|limitation\w*|filtros?|filters?|safeguards?|guardrails?|salvaguardas?"
    r"|comandos? anterior\w*|previous (?:commands?|messages?)|tudo (?:acima|anterior|que foi dito)"
    r"|everything (?:above|before)|all (?:of )?the above)"
)
_KNOWLEDGE_BASE = (
    r"(?:pdfs?|manua(?:l|is)|documentos?|documents?|contextos?|context|base de conhecimento|knowledge base"
    r"|fontes?|sources?|trechos?|passages?|excerpts?|material fornecido|provided (?:material|text|content))"
)
_NOT_USE = (
    r"(?:nao (?:use|utilize|consulte|considere|olhe|leia|se baseie|se limite)|sem (?:usar|utilizar|consultar|considerar"
    r"|olhar|se basear|se limitar)|do not (?:use|consult|rely|limit)|don'?t (?:use|consult|rely|limit)"
    r"|without (?:using|consulting|relying)|independente(?:mente)? d[oe]|regardless of|instead of(?: using)?"
    r"|em vez d[oe](?: usar)?|ao inves d[oe](?: usar)?|fora d[oe]|outside(?: of)?|alem d[oe]|beyond)"
)
_REVEAL = (
    r"(?:mostr\w*|revel\w*|exib\w*|repit\w*|repet\w*|imprim\w*|dig[ao]\w*|list\w*|escrev\w*|copi\w*|transcrev\w*"
    r"|vaz\w*|show\w*|reveal\w*|print\w*|repeat\w*|display\w*|tell\w*|output\w*|leak\w*|dump\w*|write\w*|give\w*"
    r"|what (?:is|are|were)|qual (?:e|era|foi)|quais (?:sao|eram|foram))"
)
_PROMPT_TARGET = (
    r"(?:system prompt|prompt (?:d[oe] )?sistema|prompt inicial|initial prompt|prompt original|original prompt"
    r"|(?:su|tu)as? (?:proprias? )?(?:instruc\w+|regras|diretrizes|configurac\w+|orientac\w+)"
    r"|your (?:own )?(?:instructions|rules|guidelines|prompt|configuration|directives)"
    r"|instruc\w+ (?:originais|iniciais|internas|secretas|ocultas|d[oe] sistema)"
    r"|(?:hidden|secret|internal|initial|original) instructions"
    r"|(?:texto|mensagem|conteudo) (?:acima|anterior|inicial)|(?:text|message|everything) above"
    r"|tudo (?:acima|que esta acima|que veio antes))"
)
_MALICIOUS_TOOLS = (
    r"(?:ddos|dos attack|ataque dos|malware|ransomware|keylogger|botnet|trojan|cavalo de troia|spyware|rootkit"
    r"|virus|worm|phishing|exploit|backdoor|sniffer|deauth\w*|brute ?force|forca bruta|man[- ]in[- ]the[- ]middle)"
)
_MAKE = (
    r"(?:fazer|faco|faz|criar|crio|cria|montar|realizar|lancar|executar|rodar|programar|escrever|desenvolver"
    r"|instalar em|usar contra|make|create|build|launch|perform|run|write|code|develop|deploy|carry out|set up)"
)
_BREAK_IN = (
    r"(?:invad\w*|hack\w*|crack\w*|quebr\w*|roub\w*|descobr\w*|pirat\w*|derrub\w*|espion\w*|intercept\w*|clon\w*"
    r"|steal\w*|break into|breaking into|spy on|take down|eavesdrop\w*|snoop\w*|get into|gain access to)"
)
_NETWORK_ASSET = (
    r"(?:wi-?fi|wireless|rede|network|senha|password|roteador|router|modem|internet|conexao|connection|camera"
    r"|dispositivos?|devices?|trafego|traffic)"
)
_THIRD_PARTY = (
    r"(?:vizinh\w*|alhei\w*|de outr[ao] pessoa|de outr[ao]s pessoas|de terceiros?|d[oa] (?:meu|minha) ex\w*"
    r"|que nao (?:e|sao) (?:meu|minha|nosso|nossa)s?|neighbou?r\w*|someone else\w*|somebody else\w*|other people\w*"
    r"|another person\w*|that (?:is not|isn'?t) mine|d[ao] empresa (?:concorrente|rival)|sem (?:permissao|autorizacao)"
    r"|without (?:permission|authori[sz]ation))"
)

INPUT_RULES: tuple[Rule, ...] = (
    Rule(
        "GR-01",
        "instruction_override",
        'Tentativa de anular as instrucoes do sistema ("ignore as instrucoes anteriores").',
        _compile(
            rf"\b{_IGNORE}\b.{{0,60}}\b{_RULES_WORDS}",
            rf"\b{_RULES_WORDS}\b.{{0,40}}\b(?:nao (?:valem|se aplicam|importam)|no longer appl\w+|do(?:es)? not apply"
            r"|foram (?:revogad\w+|cancelad\w+|removid\w+)|(?:are|were|have been) (?:revoked|cancell?ed|removed|lifted))",
            r"\b(?:novas?|new|updated|atualizad\w+) (?:instruc\w+|instructions|regras|rules|diretrizes|guidelines)\s*:",
        ),
    ),
    Rule(
        "GR-02",
        "context_evasion",
        "Tentativa de fazer a IA ignorar o PDF/manual e responder com conhecimento proprio.",
        _compile(
            rf"\b{_IGNORE}\b.{{0,40}}\b{_KNOWLEDGE_BASE}\b",
            rf"\b{_NOT_USE}\b.{{0,30}}\b{_KNOWLEDGE_BASE}\b",
            r"\b(?:use|usa|usando|utilize|utilizando|com base n[oa]|baseado n[oa]|a partir d[oa]|using|based on|from|with)"
            r"\b.{0,25}\b(?:(?:s|t)eu|(?:s|t)ua|your|proprio|propria|own)\b.{0,25}"
            r"\b(?:conhecimento|knowledge|treinamento|training|memoria|memory|dados de treino|training data)\b",
            r"\b(?:conhecimento geral|general knowledge|conhecimento previo|prior knowledge|world knowledge"
            r"|conhecimento de mundo)\b",
            r"\b(?:mesmo|ainda) que nao (?:esteja|conste|exista|apareca)\b.{0,30}\b(?:pdf|manual|documento|contexto)\b",
            r"\beven if (?:it(?: is|'s)|that(?: is|'s)|this(?: is|'s)) not in\b.{0,30}\b(?:pdf|manual|document|context)\b",
            r"\b(?:invent[ea]\w*|make up|fabricat\w+|chut[ea]\w*|suponha|guess)\b.{0,40}\b(?:resposta|answer|informac\w+"
            r"|information|dados|data|valor\w*|values?)\b",
        ),
    ),
    Rule(
        "GR-03",
        "role_hijack",
        'Tentativa de trocar o papel do assistente (jailbreak, "modo desenvolvedor", DAN).',
        _compile(
            r"\b(?:you are|you're|voce e|voce esta|vc e|tu es) (?:now|agora|a partir de agora)\b",
            r"\b(?:a partir de agora|de agora em diante|from now on|starting now|henceforth)\b.{0,60}"
            r"\b(?:voce|vc|you|responda|answer|respond|aja|act|sera|will be|deve|must)\b",
            r"\b(?:aja|atue|comporte-se|haja|finja|simule ser|faca de conta|pretend|roleplay|role-play|impersonate)\b"
            r".{0,10}\b(?:como|que|ser|de|to be|as|you|voce|that)\b",
            r"(?:^|[.!?:;\n]\s*|\byou (?:will|must|should|shall|can|are to|have to) |\bnow |\bplease )act as\b",
            r"\b(?:modo|mode)\s*(?:desenvolvedor|dev|deus|god|irrestrito|livre|admin|root|sudo|debug|sem (?:filtro|restric\w+))",
            r"\b(?:developer|dev|god|admin|sudo|debug|unrestricted|jailbreak|jailbroken|dan|evil|uncensored)\s*mode\b",
            r"\b(?:jailbreak\w*|do anything now|\bdan\b|stan mode|anti-?dan|dude mode)\b",
            r"\bsem (?:censura|filtros?|restric\w+|limites|regras|moderacao|guardrails?)\b",
            r"\b(?:unfiltered|uncensored|unrestricted|no (?:restrictions|filters?|limits|rules|censorship))\b",
            r"\b(?:voce|vc|you)\b.{0,20}\b(?:nao tem|nao possui|no longer have|do not have|don'?t have|have no)\b.{0,20}"
            r"\b(?:restric\w+|restrictions|regras|rules|limites|limits|filtros?|filters?)\b",
        ),
    ),
    Rule(
        "GR-04",
        "prompt_extraction",
        "Tentativa de extrair o prompt de sistema ou as instrucoes internas.",
        _compile(
            rf"\b{_REVEAL}\b.{{0,50}}\b{_PROMPT_TARGET}",
            rf"\b{_PROMPT_TARGET}\b.{{0,30}}\b(?:palavra por palavra|na integra|verbatim|word for word|literalmente|completo"
            r"|inteiro|in full)\b",
        ),
    ),
    Rule(
        "GR-05",
        "delimiter_injection",
        "Marcadores de papel ou de bloco usados para forjar mensagens de sistema.",
        _compile(
            r"</?\s*(?:system|assistant|user|context|contexto|instructions?|instrucoes|manual|question|pergunta|prompt)\b[^>]*>",
            r"\[/?\s*(?:INST|SYS|SYSTEM)\s*\]",
            r"<\|[^|>]{1,40}\|>",
            r"^\s*(?:system|assistant|sistema|assistente|developer)\s*:",
            r"#{2,}\s*(?:system|sistema|instruc\w+|instruction\w*|new task|nova tarefa)\b",
            r"\bBEGIN (?:SYSTEM|INSTRUCTIONS?|PROMPT)\b|\bEND (?:OF )?(?:CONTEXT|SYSTEM|INSTRUCTIONS?|PROMPT)\b",
            flags=re.IGNORECASE | re.MULTILINE,
        ),
        raw=True,
    ),
    Rule(
        "GR-06",
        "encoded_payload",
        "Bloco codificado (base64/hex) longo, usado para esconder instrucoes do filtro.",
        _compile(
            r"(?<![A-Za-z0-9+/=])(?:[A-Za-z0-9+/]{4}){12,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?(?![A-Za-z0-9+/=])",
            r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[\s:]?){32,}(?![0-9A-Fa-f])",
            r"(?:\\x[0-9A-Fa-f]{2}){8,}|(?:\\u[0-9A-Fa-f]{4}){8,}|(?:%[0-9A-Fa-f]{2}){12,}",
            flags=0,
        ),
        raw=True,
    ),
    Rule(
        "GR-07",
        "forbidden_topic",
        "Pedido fora da politica de uso: invasao de redes de terceiros ou criacao de ferramenta maliciosa.",
        _compile(
            rf"\b{_BREAK_IN}\b.{{0,50}}\b{_NETWORK_ASSET}\b.{{0,40}}\b{_THIRD_PARTY}",
            rf"\b{_BREAK_IN}\b.{{0,40}}\b{_THIRD_PARTY}",
            rf"\b{_NETWORK_ASSET}\b.{{0,30}}\b{_THIRD_PARTY}\b.{{0,40}}\b{_BREAK_IN}\b",
            rf"\b{_MAKE}\b.{{0,30}}\b(?:um |uma |a |an |o |the )?(?:ataque (?:de )?|attack )?{_MALICIOUS_TOOLS}\b",
            rf"\b(?:como|how (?:to|do i|can i)|ensine|teach me|me ajude a|help me)\b.{{0,40}}\b{_BREAK_IN}\b.{{0,40}}"
            r"\b(?:senha|password|wi-?fi|rede|network)\b.{0,30}\b(?:que nao|sem|without|not my|alhei\w*|vizinh\w*|neighbou?r\w*)",
        ),
    ),
)

# Palavras proibidas: casadas como palavra inteira no texto normalizado. Lista curta e explicita,
# extensivel por COPILOT_EXTRA_BLOCKED_TERMS (termos da operacao, nomes de concorrentes etc.).
BLOCKED_TERMS: tuple[str, ...] = (
    "bomba caseira",
    "explosivo caseiro",
    "arma de fogo",
    "como matar",
    "pornografia",
    "pornografia infantil",
    "pedofilia",
    "trafico de drogas",
    "lavagem de dinheiro",
    "cartao clonado",
    "clonar cartao",
    "homemade bomb",
    "child porn",
    "how to kill",
    "money laundering",
    "cloned card",
    "carding",
    "idiota",
    "imbecil",
    "otario",
    "babaca",
    "desgracado",
    "filho da puta",
    "fdp",
    "vai se foder",
    "vai tomar no cu",
    "vtnc",
    "porra",
    "caralho",
    "merda",
    "fuck",
    "fucking",
    "shit",
    "bullshit",
    "asshole",
    "bastard",
    "motherfucker",
)
BLOCKED_TERMS_RULE_ID = "GR-08"
FLOODING_RULE_ID = "GR-09"


def blocked_terms_pattern(extra: tuple[str, ...] = ()) -> re.Pattern[str]:
    terms = sorted(
        {term.strip().casefold() for term in (*BLOCKED_TERMS, *extra) if term.strip()}, key=len, reverse=True
    )
    return re.compile(r"(?<![^\W_])(?:" + "|".join(re.escape(term) for term in terms) + r")(?![^\W_])")
