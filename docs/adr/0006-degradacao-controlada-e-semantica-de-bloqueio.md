# ADR 0006 — Degradação controlada e semântica HTTP do bloqueio

**Status:** aceito

## Contexto

O `/chat` depende de um serviço externo (o LLM) que pode falhar, ficar lento, mudar de nome de modelo ou simplesmente não estar configurado. Também precisa comunicar ao cliente da API três desfechos que não são erros: respondeu, não encontrou no manual, bloqueou.

## Decisão

1. **Modo extrativo como piso:** sem LLM configurado, com o provedor fora do ar ou com uma resposta gerada que não se comprova pelo manual, o `/chat` devolve os trechos mais relevantes do manual, com fonte e página. O campo `mode` diz o que aconteceu (`llm` ou `extractive`) e `degraded_reason` diz por quê (`llm_unavailable`, `ungrounded_answer`).
2. **Componentes independentes:** triagem e chat sobem separadamente. Se o modelo de triagem estiver ausente, o `/chat` continua de pé e `GET /ready` responde 503 listando o que falhou.
3. **Bloqueio é resposta, não erro:** guardrail acionado retorna HTTP 200 com `status: "blocked"`, a mensagem de recusa e as regras violadas. Os códigos 4xx ficam para o contrato: 401 (chave), 413 (corpo grande), 422 (entrada inválida), 429 (limite de taxa).
4. **Uma chamada por pergunta:** sem repetição automática além das tentativas internas do cliente do provedor (2), com timeout de 30 segundos.

## Por que 200 no bloqueio

O cliente da API (o front de atendimento) precisa mostrar a recusa ao usuário como mostra uma resposta: mesma estrutura, mesmo `request_id`, sem tratamento de exceção. Um 4xx levaria clientes HTTP a repetir a chamada ou a tratar como falha de integração. O bloqueio continua observável: métrica `copilot_guardrail_violations_total` por regra e campo `guardrails` na resposta.

## Consequências

- A API responde algo útil mesmo sem nenhuma chave configurada, o que torna o container testável por qualquer pessoa.
- A degradação é silenciosa para o usuário e explícita para a operação: `copilot_llm_degraded_total` por motivo deve ter alerta (ver runbook).
- `python -m supportcopilot.pipelines.check_llm` existe para descobrir um nome de modelo inválido antes da primeira pergunta.
