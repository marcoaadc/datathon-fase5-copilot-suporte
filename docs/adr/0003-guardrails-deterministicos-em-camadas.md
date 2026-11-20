# ADR 0003 — Guardrails determinísticos em três camadas

**Status:** aceito

## Contexto

O enunciado pede lógica de guardrails no código: bloquear perguntas com palavras proibidas ou que tentem fazer a IA ignorar o PDF. Um guardrail que depende de o LLM "se comportar" não é um controle: é uma esperança.

## Decisão

Três pontos de controle, todos em código determinístico, cada um com regras identificadas (`GR-xx` na entrada, `GO-xx` na saída):

1. **Entrada:** a pergunta é avaliada antes de qualquer busca ou chamada ao LLM. Pergunta bloqueada não gera custo e não sai da aplicação.
2. **Contexto:** cada chunk do PDF é avaliado na indexação. Trechos com instruções embutidas (injeção indireta) ficam em quarentena e não entram no índice.
3. **Saída:** a resposta do LLM é verificada antes de ser devolvida. Vazamento do prompt e resposta que indica troca de papel bloqueiam. Resposta sem citação ou com valor que não existe no manual (número, IP, URL) é descartada e substituída pelos trechos originais.

As regras de entrada rodam sobre o texto normalizado (minúsculas, sem acento, sem caracteres invisíveis, letras espaçadas reagrupadas, homoglifos e leetspeak desfeitos) e exigem a *construção* do ataque, não palavras soltas.

## Alternativas consideradas

- **LLM como juiz (moderação por um segundo modelo):** generaliza melhor para ataques novos, mas dobra custo e latência, é não determinístico, não é auditável regra a regra e é, ele mesmo, alvo de injeção. Fica como camada adicional recomendada para produção, não como substituto.
- **Lista de palavras proibidas apenas:** bloqueia "ignorar" e com isso o cliente que escreve "o firewall está ignorando minhas regras". O falso positivo em suporte técnico seria inaceitável.
- **Confiar no prompt de sistema:** o prompt tem as defesas usuais (delimitadores, sanduíche, sentinela, canário), mas é tratado como última camada.

## Evidência

- Suíte de desenvolvimento (`tests/data/guardrail_cases.json`): 58 ataques e 50 perguntas legítimas, todos classificados corretamente. As regras foram ajustadas contra ela, então isso mede regressão, não eficácia.
- Conjunto cego, escrito por um revisor sem acesso às regras (`tests/data/guardrail_heldout.json`): **38 de 51 ataques bloqueados (74,5%) na primeira medição** e 70 de 70 perguntas legítimas liberadas. As 13 falhas eram paráfrases sem as palavras-chave esperadas ("deixe de lado as orientações que recebeu", "assuma a persona...") e orientaram generalizações das regras.
- Revisão independente do código (`tests/data/guardrail_review.json`): encontrou oito falsos positivos e dois bypasses que as suítes não cobriam; todos corrigidos e mantidos como teste de regressão.

## Consequências

- A taxa realista contra ataques inéditos é a do conjunto cego: cerca de três em quatro. Um filtro por padrões não detecta todo ataque novo, e por isso existem a camada de saída e o portão de relevância: o que passa pela entrada ainda precisa produzir uma resposta citada e comprovável pelo manual.
- Bloqueio retorna HTTP 200 com `status: "blocked"` e as regras violadas (ver ADR 0006).
- Toda regra nova entra no catálogo com identificador, ganha casos na suíte e aparece em `GET /info`.
