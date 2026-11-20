# Runbook

O que observar em produção e o que fazer quando cada sinal dispara. As métricas estão em `GET /metrics` (formato Prometheus).

## Sinais e alertas sugeridos

| Sinal | Métrica | Alerta sugerido | Severidade |
|---|---|---|---|
| Drift dos dados | `copilot_drift_status` (0 ok, 1 atenção, 2 crítico) | `>= 2` por 30 min | Alta |
| PSI por feature | `copilot_drift_psi{feature}` | `oov_rate` ou `confidence` acima de 0,25 | Alta |
| Confiança baixa | `copilot_triage_low_confidence_total` / `copilot_triage_predictions_total` | Fração acima de 2x a da referência por 1 h | Média |
| LLM degradado | `copilot_llm_degraded_total{reason}` | Qualquer aumento de `llm_unavailable` por 5 min | Alta |
| Respostas descartadas | `copilot_llm_degraded_total{reason="ungrounded_answer"}` | Acima de 10% das respostas por 1 h | Média |
| Tentativas de ataque | `copilot_guardrail_violations_total{stage="input"}` | Pico acima de 5x a média | Média |
| Saída insegura | `copilot_guardrail_violations_total{stage="output",rule=~"GO-01|GO-04"}` | Qualquer ocorrência | Alta |
| Perguntas fora do manual | `copilot_chat_total{status="not_found"}` | Acima de 30% por 1 dia | Baixa |
| Latência | `copilot_http_request_duration_seconds` | p95 do `/chat` acima de 8 s | Média |
| Erros | `copilot_http_requests_total{status=~"5.."}` | Acima de 1% por 5 min | Alta |
| Entrada inválida | `copilot_validation_errors_total` | Pico súbito (integração quebrada no cliente) | Baixa |

## Drift crítico (`copilot_drift_status = 2`)

1. Abra `GET /drift` e veja quais features passaram do limiar.
2. Interprete pelo padrão:

| Padrão | Causa provável | Ação |
|---|---|---|
| `oov_rate` e `non_ascii_ratio` sobem, `confidence` cai | Outro idioma ou novo produto com vocabulário próprio | Confirmar com a operação; rotular amostra e retreinar incluindo o novo perfil |
| `upper_ratio` sobe, `mean_word_length` muda | Novo canal de entrada (app, chat) com outro estilo de escrita | Normalizar na entrada ou retreinar com amostra do canal |
| `n_chars` e `n_words` caem | Integração truncando a mensagem | Corrigir a integração; não é problema do modelo |
| Só `predicted_queue` muda | Incidente em massa (mistura de filas) | Esperado; acompanhar. O modelo não piorou, a demanda mudou |
| Nada muda, mas a operação reclama de roteamento errado | Drift de conceito (regra de negócio mudou) | Não é detectável sem rótulo: auditar amostra rotulada |

3. Gere o relatório completo com uma amostra recente: `make drift` (ou o job agendado em nuvem) e anexe o HTML ao incidente.
4. Enquanto investiga, o campo `needs_human_review` já desvia para revisão humana os chamados em que o modelo está inseguro. Se necessário, suba `COPILOT_LOW_CONFIDENCE_THRESHOLD` para desviar mais.
5. Retreino: `make data train`, confira no MLflow que o novo modelo supera o atual **no mesmo teste**, publique a nova imagem. O modelo anterior continua disponível no Model Registry para rollback.

## LLM indisponível (`llm_unavailable`)

O `/chat` continua respondendo em modo extrativo; não há indisponibilidade para o usuário, há perda de qualidade.

1. `python -m supportcopilot.pipelines.check_llm` mostra o erro do provedor.
2. Modelo descontinuado ou nome inválido: ajuste `COPILOT_OPENAI_MODEL` / `COPILOT_GEMINI_MODEL` e reinicie.
3. Cota ou falha do provedor: troque o provedor (`COPILOT_LLM_PROVIDER`) se houver a outra chave configurada.
4. Chave vazada ou revogada: gere outra no provedor, atualize o segredo, reinicie as réplicas. Nenhuma chave fica na imagem nem no repositório.

## Saída insegura (GO-01 ou GO-04)

Significa que um ataque passou pela entrada e o modelo cedeu; a resposta foi bloqueada antes de sair.

1. Localize o `request_id` no log (`"message": "chat"`, com `output_rules`). O log não contém a pergunta: por desenho, o texto não é persistido.
2. Reproduza com o conjunto de ataques (`make eval-guardrails`) para ver se há regressão.
3. Se o padrão for novo, adicione o caso em `tests/data/guardrail_cases.json`, generalize a regra de entrada e publique.

## Atualização do manual

1. Substitua ou adicione o PDF em `data/manuals/` (na nuvem: no bucket de manuais).
2. Rode `make eval-rag` com perguntas do novo conteúdo adicionadas a `tests/data/rag_golden.json`.
3. Publique a nova imagem (ou reinicie as réplicas, se os manuais vierem de volume).
4. Confira `GET /info`: `chunks_indexed`, `sources` e `chunks_quarantined` (deve ser 0; se não for, o PDF contém texto que parece instrução para o assistente).

## Subida e verificação

| Verificação | Comando | Esperado |
|---|---|---|
| Processo de pé | `GET /health` | 200 |
| Pronto para tráfego | `GET /ready` | 200, `ready: true` |
| Versões em uso | `GET /info` | versão do modelo, PDFs indexados, provedor de LLM |
| LLM responde | `python -m supportcopilot.pipelines.check_llm` | `OK: ...` |

`/ready` com 503 lista o componente que falhou em `errors` (`triage`: modelo ausente ou com hash divergente; `chat`: nenhum PDF ou modelo de embeddings indisponível).
