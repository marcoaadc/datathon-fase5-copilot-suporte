"""Catalogo de regras de guardrail de entrada.

Cada regra tem um identificador estavel (``GR-xx``), usado nas respostas da API, nas metricas e na
documentacao (``docs/guardrails.md``). As expressoes rodam sobre o texto normalizado (minusculas,
sem acento, disfarces desfeitos), entao sao escritas sem acento e cobrem portugues e ingles.

O desafio de um filtro por padroes nao e bloquear o ataque obvio, e nao bloquear o cliente
legitimo. "O firewall esta ignorando minhas regras de redirecionamento" e "esqueci a senha, o
manual explica?" sao chamados validos que compartilham vocabulario com "ignore as regras" e
"esqueca o manual". Por isso as regras exigem a *construcao* do ataque (verbo no imperativo + alvo
que so faz sentido para o assistente), e nao palavras soltas. A suite ``tests/data/guardrail_cases.json``
mede as duas taxas: bloqueio de ataques e falso positivo em perguntas legitimas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


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
# Verbos de "anular", so em formas de comando ou infinitivo: "esqueci" (primeira pessoa) fica de fora.
_IGNORE = (
    r"(?:ignor(?:e|em|ar|a|ando|ing)?|desconsider(?:e|em|ar|a|ando)|esquec(?:a|am|e|er)|disregard(?:ing)?"
    r"|forget(?:ting)?|overrid(?:e|ing)|bypass(?:ing)?|burl(?:e|ar|ando)|descart(?:e|ar)|desobedec(?:a|er)|disobey"
    r"|viol(?:e|ar|ate)|skip|drop|abandon(?:e|ar)?|nao (?:siga|obedeca|respeite)(?: mais)?"
    r"|do not follow|don'?t follow|stop following|pare de seguir|deix(?:e|a|ar) de (?:lado|seguir)"
    r"|(?:deix(?:e|a|ar)|ponha|coloque|bot[ea]) .{0,40}(?:de lado|pra la|para la)|set .{0,40}aside|put .{0,40}aside"
    r"|set aside|put aside)"
)
# Alvos que so existem para o assistente: instrucoes, prompt, diretrizes.
_STRONG_TARGET = (
    r"(?:instruc\w*|instruct\w*|prompts?|diretriz\w*|guidelines?|guardrails?|salvaguardas?|safeguards?"
    r"|system message|mensagem d[eo] sistema|comandos? anterior\w*|previous (?:commands?|messages?)"
    r"|tudo (?:acima|anterior|que foi dito|o que foi dito)|everything (?:above|before|you were told)"
    r"|all (?:of )?the above|what you were told|(?:tudo )?o que (?:te|lhe) (?:disseram|foi dito|mandaram|pediram)"
    r"|orientac\w+ (?:que (?:voce )?recebeu|d[eo] sistema|anterior\w*)|(?:prior|previous|earlier) directions"
    r"|directions you were given|what(?:ever)? you were (?:told|given|instructed))"
)
# Alvos ambiguos ("regras" de firewall, "filtro" de MAC): so contam com um qualificador ao lado.
_WEAK_TARGET = (
    r"(?:regras?|rules?|restric\w*|restrict\w*|filtros?|filters?|limitac\w*|limitations?|polic\w*|politic\w*)"
)
# "regras de firewall", "filtro de MAC", "politica de devolucao": sao do produto, nao do assistente.
_NOT_DEVICE_RULES = (
    r"(?!\s+(?:d[eoa]s?|of|for|para)\s+(?:(?:o|a|the)\s+)?(?:firewall|redirecionamento|portas?|port|nat|qos|controle"
    r"|roteamento|routing|rede|network|acesso|access|mac|conteudo parental|horario|devoluc\w+|return|troca|garantia"
    r"|warranty|uso da rede|senha|password))"
)
_OWNER_BEFORE = r"(?:(?:as |os )?(?:su|tu)as?|(?:os )?(?:s|t)eus?|your|its own|these|essas|estas|esses|estes)"
_QUALIFIER_AFTER = (
    r"(?:anterior\w*|acima|previous|above|prior|earlier|d[eo] sistema|d[eo] seguranca|safety|d[eo] uso|d[eo] conteudo"
    r"|content|que (?:te|lhe) (?:deram|foram dadas|passaram)|you were given|(?:im)?post[ao]s? a voce)"
)
_KNOWLEDGE_BASE = (
    r"(?:pdfs?|manua(?:l|is)|documentos?|documents?|contextos?|context|base de conhecimento|knowledge base"
    r"|fontes?|sources?|trechos?|passages?|excerpts?|material fornecido|provided (?:material|text|content))"
)
_NOT_USE = (
    r"(?:nao (?:use|utilize|consulte|considere|olhe|leia|se baseie|se limite)|sem (?:usar|utilizar|consultar|considerar"
    r"|olhar|se basear|se limitar)|do not (?:use|consult|rely|limit)|don'?t (?:use|consult|rely|limit)"
    r"|without (?:using|consulting|relying)|independente(?:mente)? d[oe]|regardless of|instead of(?: using)?"
    r"|em vez d[oe](?: usar)?|ao inves d[oe](?: usar)?)"
)
# Quem recebe a ordem e o assistente (e nao o roteador).
_ASSISTANT = (
    r"(?:voce|vc|tu|you|responda|respond[ae]r?|answer|respond|reply|fale|falar|speak|talk|diga|escreva|aja|act|seja"
    r"|\bia\b|\bai\b|assistente|assistant|chatbot|copilot|modelo|model|bot)"
)
_REVEAL = (
    r"(?:mostr(?:e|ar|a)|revel(?:e|ar|a)|exib(?:a|ir|e)|repit(?:a|am)|repet(?:ir|e)|imprim(?:a|ir|e)|dig(?:a|am)"
    r"|list(?:e|ar)|escrev(?:a|er|e)|copi(?:e|ar)|transcrev(?:a|er)|vaz(?:e|ar)|inform(?:e|ar)|show(?: me)?|reveal"
    r"|print|repeat|display|tell(?: me)?|output|leak|dump|write(?: out)?|give(?: me)?|share|send(?: me)?"
    r"|traduz(?:a|ir)|translate|resum(?:a|ir)|summari[sz]e|parafrase(?:ie|ar)|paraphrase|(?:me )?pass(?:a|e|ar)"
    r"|(?:me )?envi(?:a|e|ar)|(?:me )?mand(?:a|e|ar)|quero ver|let me see"
    r"|what (?:is|are|were|was)|qual (?:e|era|foi)|quais (?:sao|eram|foram))"
)
_PROMPT_TARGET = (
    r"(?:system prompt|prompt (?:d[oe] )?sistema|prompt inicial|initial prompt|prompt original|original prompt"
    r"|(?:s|t)eu prompt|your prompt"
    r"|(?:instruc\w+|regras|orientac\w+|diretrizes) que (?:voce|vc|te|lhe) (?:recebeu|receberam|programaram|deram|passaram)"
    r"|(?:instructions|rules|directions) (?:that )?you (?:received|were given|got|were programmed with)"
    r"|como (?:voce|vc) foi (?:configurad\w+|programad\w+|instruid\w+)|how you (?:were|are) (?:configured|programmed|prompted)"
    r"|(?:su|tu)as? (?:proprias? )?(?:instruc\w+|regras|diretrizes|configurac\w+|orientac\w+)"
    r"|your (?:own )?(?:instructions|rules|guidelines|configuration|directives)"
    r"|instruc\w+ (?:originais|iniciais|internas|secretas|ocultas|d[oe] sistema)"
    r"|(?:hidden|secret|internal|initial|original|system) instructions"
    r"|(?:texto|mensagem|conteudo) (?:acima|anterior|inicial)|(?:text|message|everything|anything) above"
    r"|tudo (?:acima|que esta acima|que veio antes))"
)
_MALICIOUS_TOOLS = (
    r"(?:ddos|dos attack|ataque dos|malware|ransomware|keylogger|botnet|trojan|cavalo de troia|spyware|rootkit"
    r"|virus|worm|phishing|exploit|backdoor|deauth\w*|brute ?force|forca bruta|man[- ]in[- ]the[- ]middle)"
)
_MAKE = (
    r"(?:fazer|faco|faz|criar|crio|cria|montar|realizar|lancar|executar|rodar|programar|escrever|desenvolver"
    r"|disparar|make|create|build|launch|perform|run|write|code|develop|deploy|carry out|set up)"
)
# Pedido de "como fazer" (e nao o relato de uma vitima: "alguem invadiu minha rede").
_INTENT = (
    r"(?:como|how (?:to|do i|can i|could i|would i)|quero|queria|gostaria de|preciso|i want to|i need to|i would like to"
    r"|ensine|me ensina|teach me|me ajud[ae]|help me|consigo|can i|is it possible to|da para|tem como|e possivel"
    r"|qual (?:a|o) (?:forma|jeito|maneira|comando|programa|app|aplicativo)|what (?:tool|app|command))"
)
_BREAK_IN = (
    r"(?:invad\w*|hack\w*|crack\w*|quebr\w*|roub\w*|descobr\w*|pirat\w*|derrub\w*|espion\w*|intercept\w*|clon\w*"
    r"|steal\w*|break(?:ing)? into|spy(?:ing)? on|take down|eavesdrop\w*|snoop\w*|get(?:ting)? into|gain access to"
    r"|entrar n[oa])"
)
_NETWORK_ASSET = (
    r"(?:wi-?fi|wireless|rede|network|senha|password|roteador|router|modem|internet|conexao|connection|cameras?"
    r"|dispositivos?|devices?|trafego|traffic|celular|phone|computador|computer)"
)
_THIRD_PARTY = (
    r"(?:(?:d[oae]s? |d[eo] (?:meu|minha) |meu |minha |my )?vizinh\w*|alhei\w*|de outr[ao]s? pessoas?"
    r"|d[oa] (?:meu|minha) ex\w*|que nao (?:e|sao) (?:meu|minha|nosso|nossa)s?|neighbou?r\w*|someone else'?s?"
    r"|somebody else'?s?|other people'?s?|another person'?s?|that (?:is not|isn'?t) mine|d[ao] empresa concorrente)"
)
_NO_CONSENT = (
    r"(?:sem (?:a )?(?:permissao|autorizacao|consentimento)|sem (?:el[ea]s?|o dono|a pessoa) (?:saber|perceber)"
    r"|escondido|as escondidas|without (?:their |his |her |the owner'?s? )?(?:permission|authori[sz]ation|consent|knowledge)"
    r"|without (?:them|him|her) knowing)"
)

INPUT_RULES: tuple[Rule, ...] = (
    Rule(
        "GR-01",
        "instruction_override",
        'Tentativa de anular as instrucoes do sistema ("ignore as instrucoes anteriores").',
        _compile(
            rf"\b{_IGNORE}\b.{{0,50}}\b{_STRONG_TARGET}",
            rf"\b{_IGNORE}\b.{{0,40}}\b{_WEAK_TARGET}\b{_NOT_DEVICE_RULES}.{{0,25}}\b{_QUALIFIER_AFTER}",
            rf"\b{_IGNORE}\b.{{0,25}}\b{_OWNER_BEFORE}\b.{{0,15}}\b{_WEAK_TARGET}\b{_NOT_DEVICE_RULES}",
            rf"(?:^|[.!?:;\n]\s*)(?:por favor,?\s*|please,?\s*)?{_IGNORE}\s+(?:todas as |todos os |all (?:of )?(?:the |your )?"
            rf"|as |os |the )?{_WEAK_TARGET}\s*(?:$|[.!?,;\n]|e\b|and\b)",
            rf"\b{_STRONG_TARGET}\b.{{0,40}}\b(?:nao (?:valem|se aplicam|importam)(?: mais)?|no longer appl\w+"
            r"|do(?:es)? not apply|foram (?:revogad\w+|cancelad\w+|removid\w+)"
            r"|(?:are|were|have been) (?:revoked|cancell?ed|removed|lifted))",
            r"\b(?:novas?|new|updated|atualizad\w+) (?:instruc\w+|instructions|diretrizes|guidelines)\s*:",
            # Tomada de autoridade: "obedeca somente a mim", "valem apenas as minhas".
            r"\b(?:obedec\w+|obey|siga|follow|escute|listen to)\b.{0,12}\b(?:so|somente|apenas|only)\b.{0,25}"
            r"\b(?:a mim|me|eu|minhas?|meus?|my|mine|i say|eu (?:disser|mandar|pedir))\b",
            r"\b(?:valem|vale|contam|apply|count)\b.{0,10}\b(?:so|somente|apenas|only)\b.{0,10}\b(?:as minhas|os meus|mine|my)\b",
        ),
    ),
    Rule(
        "GR-02",
        "context_evasion",
        "Tentativa de fazer a IA ignorar o PDF/manual e responder com conhecimento proprio.",
        _compile(
            # A base de conhecimento precisa ser o objeto do verbo (ate tres palavras depois dele):
            # "esqueca o PDF" bloqueia; "o roteador esquece a senha toda vez, o manual diz algo?" nao.
            rf"\b{_IGNORE}\b(?:\s+[^\s.,;:!?]+){{0,3}}?\s+{_KNOWLEDGE_BASE}\b",
            rf"\b{_NOT_USE}\b(?:\s+[^\s.,;:!?]+){{0,3}}?\s+{_KNOWLEDGE_BASE}\b",
            r"(?:^|[.!?,;:\n]\s*)(?:please\s+)?(?:answer|respond|reply)\b.{0,40}\bnot (?:from |using |in |with )?the\b.{0,10}"
            rf"\b{_KNOWLEDGE_BASE}\b",
            r"\b(?:use|usa|usando|utilize|utilizando|com base n[oa]|baseado n[oa]|a partir d[oa]|com (?:o|a)|using|based on"
            r"|from|with)\b.{0,25}\b(?:(?:s|t)eu|(?:s|t)ua|your|proprio|propria|own)\b.{0,25}"
            r"\b(?:conhecimento|knowledge|treinamento|training|memoria|memory|dados de treino|training data)\b",
            r"\b(?:conhecimento geral|general knowledge|conhecimento previo|prior knowledge|world knowledge"
            r"|conhecimentos? gera(?:l|is)|conhecimento de mundo|o que voce (?:sabe|ja sabe)"
            r"|what you (?:already |personally )?know)\b",
            r"\b(?:complet(?:e|a|ar)|preench(?:a|e|er)|fill in|supplement|complement(?:e|ar)?)\b.{0,30}"
            r"\b(?:dados|informac\w+|conhecimento|data|information|knowledge)\b.{0,15}\b(?:de fora|extern\w+|outside|external)\b",
            r"\b(?:mesmo|ainda) que nao (?:esteja|conste|exista|apareca)\b.{0,30}\b(?:pdf|manual|documento|contexto)\b",
            r"\beven if (?:it(?: is|'s)|that(?: is|'s)|this(?: is|'s)) not in\b.{0,30}\b(?:pdf|manual|document|context)\b",
            r"\b(?:invent(?:e|a|ar|em)|make up|fabricate|chut(?:e|ar)|suponha|improvise)\b.{0,40}\b(?:resposta|answer|informac\w+"
            r"|information|dados|data|valor\w*|values?)\b",
        ),
    ),
    Rule(
        "GR-03",
        "role_hijack",
        'Tentativa de trocar o papel do assistente (jailbreak, "modo desenvolvedor", DAN).',
        _compile(
            r"\b(?:you are|you're|voce e|voce esta|vc e|tu es) (?:now|agora|a partir de agora)\b",
            r"\b(?:voce|vc) (?:nao e mais|deixou de ser)\b|\byou(?: are|'re) no longer\b",
            r"\b(?:assum(?:a|e|ir)|adot(?:e|a|ar)|incorpor(?:e|a|ar)|take on|adopt|assume)\b.{0,15}"
            r"\b(?:persona\w*|papel|personagem|role|character|identity|identidade)\b",
            r"\b(?:interpret(?:a|e|ar)|play(?:ing)?|brincar de|vamos brincar)\b.{0,40}\b(?:uma? ia|an? ai|personagem|character)\b",
            r"\b(?:ia|ai|assistente|assistant|persona\w*|personagem)\b.{0,40}\b(?:que nao segue|sem se preocupar com"
            r"|that (?:does not|doesn'?t) follow|with no regard for|que ignora)\b.{0,30}\b(?:politic\w+|polic\w+|regras|rules)\b",
            # "A partir de agora voce e/sera/deve...": o sujeito "voce" vem logo depois (ate duas palavras)
            # e o verbo e de identidade ou obrigacao. "From now on, how can I ... so you can help" nao casa.
            r"\b(?:a partir de agora|de agora em diante|from now on|starting now|henceforth)[,:]?(?:\s+[^\s.,;:!?]+){0,2}?"
            r"\s+(?:voce|vc|you)\s+(?:nao\s+|not\s+)?(?:e|es|sera|vai|deve|tem|are|will|must|shall|should|have)\b",
            r"\b(?:a partir de agora|de agora em diante|from now on|starting now|henceforth)[,:]?\s+"
            r"(?:responda|answer|respond|aja|act|ignore|fale|speak|reply|behave|comporte-se)\b",
            r"\b(?:aja|atue|comporte-se|finja|simule ser|faca de conta|pretend|roleplay|role-play|impersonate)\b"
            r".{0,12}\b(?:como|que|ser|to be|as|you|voce|that)\b",
            r"(?:^|[.!?:;\n]\s*|\byou (?:will|must|should|shall|are to|have to) |\bnow |\bplease )act as\b",
            r"\b(?:modo|mode)\s*(?:desenvolvedor|dev|deus|god|irrestrito|sem (?:filtro|restric\w+|censura))\b",
            r"\b(?:developer|dev|god|sudo|unrestricted|jailbreak|jailbroken|dan|evil|uncensored)\s*mode\b",
            r"\b(?:jailbreak\w*|do anything now|stan mode|anti-?dan|dude mode)\b",
            r"\b(?:voce (?:agora )?e|vc (?:agora )?e|you are(?: now)?|act as|respond as|answer as|responda como|como)"
            r"(?: o| a| um| the)? dan\b",
            rf"\b{_ASSISTANT}\b.{{0,40}}\bsem (?:censura|filtros?|restric\w+|limites|regras|moderacao|guardrails?)\b",
            rf"\b{_ASSISTANT}\b.{{0,40}}\b(?:unrestricted|without (?:any )?(?:restrictions|filters?|limits|rules|censorship)"
            r"|with no (?:restrictions|filters?|limits|rules|censorship)|no (?:restrictions|filters|censorship))\b",
            r"\b(?:unfiltered|uncensored)\b",
            r"\b(?:voce|vc|you)\b.{0,20}\b(?:nao tem|nao possui|no longer have|do not have|don'?t have|have no)\b.{0,20}"
            r"\b(?:restric\w+|restrictions|regras|rules|limites|limits|filtros?|filters?)\b",
        ),
    ),
    Rule(
        "GR-04",
        "prompt_extraction",
        "Tentativa de extrair o prompt de sistema ou as instrucoes internas.",
        _compile(
            # Pedido e alvo na mesma frase: "What is your return policy? Your rules say..." nao casa.
            rf"\b{_REVEAL}\b[^.?!\n]{{0,50}}\b{_PROMPT_TARGET}{_NOT_DEVICE_RULES}",
            rf"\b{_PROMPT_TARGET}\b.{{0,30}}\b(?:palavra por palavra|na integra|verbatim|word for word|literalmente|completo"
            r"|inteiro|in full)\b",
        ),
    ),
    Rule(
        "GR-05",
        "delimiter_injection",
        "Marcadores de papel ou de bloco usados para forjar mensagens de sistema.",
        _compile(
            r"</?\s*(?:system|assistant|user|context|contexto|instructions?|instrucoes|manual|question|pergunta|prompt"
            r"|trecho)\b[^>]*>",
            r"\[/?\s*(?:INST|SYS|SYSTEM)\s*\]",
            r"<\|[^|>]{1,40}\|>",
            # Linha que imita uma mensagem de papel E fala com o assistente. So o rotulo nao basta:
            # "Sistema: Windows 11" e uma linha normal de um chamado.
            r"^\s*(?:system|assistant|sistema|assistente|developer)\s*:[^\n]{0,120}?\b(?:voc[eê]|vc|you|ignor\w+|obede\w+"
            r"|obey|instru\w+|regras|rules|prompt|respond\w+|answer|assistente|assistant|ordens|orders|a partir de agora"
            r"|from now on)\b",
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
            # Excecao: exatamente 64 caracteres hexadecimais e o formato de uma chave WPA, nao um payload.
            r"(?<![A-Za-z0-9+/=])(?![0-9A-Fa-f]{64}(?![A-Za-z0-9+/=]))(?:[A-Za-z0-9+/]{4}){12,}"
            r"(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?(?![A-Za-z0-9+/=])",
            # Acima de 40 bytes: uma chave WPA em hexadecimal (64 caracteres) nao e um payload.
            r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[\s:]?){40,}(?![0-9A-Fa-f])",
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
            rf"\b{_INTENT}\b.{{0,40}}\b{_BREAK_IN}\b.{{0,50}}\b{_THIRD_PARTY}",
            rf"\b{_INTENT}\b.{{0,40}}\b{_BREAK_IN}\b.{{0,40}}\b{_NETWORK_ASSET}\b.{{0,40}}\b{_NO_CONSENT}",
            rf"\b{_INTENT}\b.{{0,30}}\b{_MAKE}\b.{{0,30}}\b(?:um |uma |a |an |o |the )?(?:ataque (?:de )?|attack )?"
            rf"{_MALICIOUS_TOOLS}\b",
            rf"\b{_MAKE}\b.{{0,15}}\b(?:um |uma |a |an )(?:ataque (?:de )?)?{_MALICIOUS_TOOLS}\b(?: attack)?\b.{{0,30}}"
            r"\b(?:contra|against|n[oa]|on|usando|using)\b",
        ),
    ),
)

ENCODED_PAYLOAD_RULE_ID = "GR-06"
BASE64_PATTERN = next(rule for rule in INPUT_RULES if rule.rule_id == ENCODED_PAYLOAD_RULE_ID).patterns[0]
# Para decodificar e reavaliar: blocos a partir de 16 caracteres (12 bytes), com padding opcional.
BASE64_DECODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9+/=])(?:[A-Za-z0-9+/]{4}){4,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?(?![A-Za-z0-9+/=])"
)
# Regras que tambem valem para o conteudo dos documentos (injecao indireta).
CONTEXT_RULE_IDS = frozenset({"GR-01", "GR-03", "GR-04", "GR-05"})

# Palavras proibidas: casadas como palavra inteira no texto normalizado. Lista curta e explicita,
# extensivel por COPILOT_EXTRA_BLOCKED_TERMS (termos da operacao, nomes de concorrentes etc.).
BLOCKED_TERMS: tuple[str, ...] = (
    "bomba caseira",
    "explosivo caseiro",
    "arma de fogo",
    "como matar",
    "pornografia",
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
    "idiotas",
    "imbecil",
    "imbecis",
    "otario",
    "otarios",
    "babaca",
    "babacas",
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
