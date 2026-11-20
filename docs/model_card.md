# Model Card — Triagem de chamados de suporte

## Identificação

| | |
|---|---|
| Nome | `support-ticket-triage` |
| Tipo | Classificação multiclasse de texto (10 filas) |
| Algoritmo | TF-IDF (palavras 1-2 gramas + caracteres 2-5 gramas) e regressão logística (C=30, pesos de classe balanceados) |
| Artefato | `models/triage/model.joblib` (5,4 MB), com SHA-256 em `metadata.json` |
| Bibliotecas | scikit-learn 1.7.2, numpy 2.2.6 |
| Rastreamento | MLflow, experimento `copilot-triagem`; resumo em [`reports/mlflow/summary.md`](../reports/mlflow/summary.md) |

## Uso pretendido

- **Para quê:** sugerir a fila de atendimento de um chamado de suporte e decidir se ele é um problema técnico, o que aciona a resposta automática baseada no manual.
- **Quem usa:** a API do copilot (`POST /triage`, `POST /tickets`).
- **Decisão humana preservada:** o modelo roteia e sugere. Chamados com confiança abaixo de 0,40 saem marcados para revisão humana, e nenhum chamado é encerrado pelo modelo.

**Fora do escopo:** priorização por urgência, análise de sentimento, qualquer decisão sobre o cliente (crédito, cancelamento, bloqueio), e chamados em idiomas diferentes do inglês.

## Dados

| | |
|---|---|
| Fonte | [Tobi-Bueck/customer-support-tickets](https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets), revisão `ddf1c81a5475`, CC BY-NC 4.0 |
| Natureza | Chamados **sintéticos** (gerados por LLM), em inglês e alemão, com dados pessoais já substituídos por marcadores na origem |
| Usado no treino | 16.336 chamados em inglês, depois da limpeza |
| Partições | Treino 10.467, validação 1.939, teste 1.960, produção (simulação de drift) 1.970 |
| Pré-processamento | Assunto + corpo, normalização Unicode, remoção de duplicatas exatas, truncamento em 1000 caracteres (o limite do contrato da API) |
| Separação | Por grupos de quase-duplicatas (926 grupos, 2.126 chamados): nenhuma paráfrase atravessa partições |

Distribuição das filas no treino: Technical Support 28,3%, Product Support 19,3%, Customer Service 14,6%, IT Support 12,0%, Billing and Payments 9,7%, Returns and Exchanges 5,3%, Service Outages and Maintenance 4,0%, Sales and Pre-Sales 3,2%, Human Resources 2,1%, General Inquiry 1,4%.

## Desempenho

Teste (1.960 chamados, usados uma única vez, depois de todas as escolhas):

| Métrica | Valor |
|---|---|
| Acurácia | 0,634 |
| F1 macro | 0,642 |
| F1 ponderado | 0,634 |
| Log loss | 1,170 |
| Erro de calibração esperado (ECE, 10 faixas) | 0,037 |
| Baseline (fila mais frequente) | 0,301 |

Decisão de roteamento (técnico = Technical Support, IT Support, Product Support ou Service Outages and Maintenance; limiar 0,5 sobre a soma das probabilidades):

| Métrica | Valor |
|---|---|
| Acurácia | 0,825 |
| Precisão | 0,858 |
| Recall | 0,869 |
| F1 | 0,863 |

Por fila:

| Fila | Precisão | Recall | F1 | Suporte |
|---|---|---|---|---|
| Billing and Payments | 0,844 | 0,869 | 0,856 | 206 |
| General Inquiry | 0,833 | 0,652 | 0,732 | 23 |
| Service Outages and Maintenance | 0,727 | 0,727 | 0,727 | 77 |
| Technical Support | 0,662 | 0,673 | 0,667 | 590 |
| Sales and Pre-Sales | 0,635 | 0,597 | 0,615 | 67 |
| Human Resources | 0,758 | 0,510 | 0,610 | 49 |
| Product Support | 0,581 | 0,562 | 0,571 | 363 |
| Customer Service | 0,559 | 0,582 | 0,570 | 292 |
| Returns and Exchanges | 0,580 | 0,526 | 0,552 | 76 |
| IT Support | 0,502 | 0,539 | 0,520 | 217 |

### Interpretação

- Filas com vocabulário próprio (cobrança, indisponibilidade) passam de 0,72 de F1. As filas de suporte (Technical, IT, Product) e o atendimento geral se confundem entre si: a sobreposição está nos rótulos do dataset, e nenhum dos oito candidatos a superou.
- A decisão que o produto usa é a binária, e nela o modelo acerta 82,5% dos chamados. De cada 100 chamados que ele manda para o RAG, 86 são de fato técnicos; de cada 100 técnicos, ele encontra 87.
- **O custo dos dois erros é assimétrico e baixo.** Um chamado não técnico enviado ao RAG recebe "não encontrei no manual" (o portão de relevância segura). Um chamado técnico enviado à fila humana é atendido por uma pessoa, como seria sem o copilot.
- A calibração é boa (ECE 0,037): quando o modelo diz 70%, acerta perto de 70%. Isso sustenta o uso da confiança como gatilho de revisão humana.

## Seleção

Oito candidatos de três famílias, escolhidos por F1 macro na validação (as filas são desbalanceadas). O vencedor foi retreinado em treino + validação. A tabela completa está na seção 6.3 do [README](../README.md) e no MLflow.

Os pesos balanceados foram o que mais ajudou as filas pequenas: com o mesmo C=30, o F1 macro de validação vai de 0,588 para 0,604 sem perder acurácia.

## Robustez a drift

Medido com chamados reais fora da distribuição de treino ([docs/drift.md](drift.md)):

| Janela | Acurácia | F1 macro | Confiança média |
|---|---|---|---|
| Chamados novos, mesma distribuição | 0,636 | 0,652 | 0,661 |
| 15% em alemão, ruído leve | 0,593 | 0,612 | 0,640 |
| 45% em alemão, ruído e truncamento | 0,471 | 0,426 | 0,605 |

**Ponto de atenção:** a confiança cai bem menos que a acurácia. O modelo não "sabe que não sabe" quando o idioma muda. Por isso o monitoramento usa a taxa de palavras fora do vocabulário, e não apenas a confiança.

## Limitações

- **Idioma:** treinado só em inglês. Chamados em português, alemão ou outro idioma não são classificados de forma confiável.
- **Dados sintéticos:** o desempenho em chamados reais de uma operação não foi medido. O protocolo (partição por grupos, teste único, baseline) é o que se transfere; os números, não.
- **Rótulos sobrepostos:** a fronteira entre Technical, IT e Product Support é difusa na origem.
- **Texto curto:** chamados com poucas palavras ("não funciona") têm pouca informação; tendem a cair na fila mais frequente com baixa confiança.
- **Sem drift de conceito:** se as regras de roteamento da operação mudarem, o modelo continua aplicando as antigas até ser retreinado.

## Considerações éticas e de privacidade

- O modelo não usa nenhum atributo do cliente, só o texto do chamado. Não há atributo protegido como entrada.
- Ainda assim, o estilo de escrita correlaciona com o perfil de quem escreve. Um modelo que erra mais em textos com erros de digitação ou fora do inglês padrão atende pior a quem escreve assim. O cenário de drift com ruído mede isso, e a revisão humana por baixa confiança é a mitigação.
- O dataset já vem com dados pessoais substituídos por marcadores. O vocabulário do modelo é derivado de texto sintético; não há dado de titular real no artefato.
- Uso não comercial: o modelo herda a licença CC BY-NC 4.0 do dataset.

## Manutenção

| | |
|---|---|
| Retreino | `make data train`, com o servidor MLflow de pé |
| Gatilhos | Drift crítico sustentado (`GET /drift`), queda de acurácia em amostra rotulada, nova fila ou novo idioma na operação |
| Critério de promoção | Superar o modelo atual no mesmo conjunto de teste, sem piorar o F1 de roteamento |
| Rollback | Versão anterior no Model Registry do MLflow; a imagem anterior da API continua no registro de imagens |
| Integridade | A API recusa carregar um artefato cujo SHA-256 não confira com `metadata.json` |
