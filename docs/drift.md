# Drift: o que é monitorado, como é simulado e como ler os relatórios

Racional das escolhas: [ADR 0004](adr/0004-drift-de-texto-por-descritores-e-psi.md). Resposta operacional a cada padrão: [runbook](runbook.md).

## 1. Por que features, e não o texto

Um teste de drift compara duas distribuições. O modelo de triagem recebe texto livre, que não tem uma distribuição diretamente comparável. A saída é descrever cada chamado por dez números (ou categorias) que mudam quando a produção muda, e que não permitem reconstruir o texto.

| Feature | Definição | Sobe ou muda quando |
|---|---|---|
| `n_chars` | Caracteres do chamado | Mensagens truncadas, outro canal |
| `n_words` | Palavras | Idem |
| `mean_word_length` | Tamanho médio das palavras | Outro idioma (o alemão tem palavras mais longas) |
| `oov_rate` | Fração das palavras fora do vocabulário do TF-IDF | Idioma novo, produto novo, erros de digitação |
| `non_ascii_ratio` | Fração de caracteres fora do ASCII | Idiomas com acentos e letras próprias |
| `upper_ratio` | Fração de letras maiúsculas | Outro estilo de digitação (cliente irritado, canal móvel) |
| `digit_ratio` | Fração de dígitos | Chamados com códigos, protocolos, valores |
| `confidence` | Probabilidade da fila prevista | Cai quando o modelo não reconhece o que vê |
| `technical_probability` | Soma das probabilidades das filas técnicas | Muda a taxa de acionamento do RAG |
| `predicted_queue` | Fila prevista (categórica) | Muda a mistura de filas |

As sete primeiras descrevem a **entrada**; as três últimas, a **decisão**. A ordem em que elas acusam drift conta a história: entrada primeiro, decisão depois.

`oov_rate` conta como "fora do vocabulário" qualquer palavra que o modelo não usa: nunca vista, rara demais ou comum demais no treino. A referência também tem uma taxa de fundo (0,2%); o que se acompanha é o desvio em relação a ela.

## 2. Métrica e limiares

**PSI** (Population Stability Index) entre a distribuição de referência e a da janela:

| PSI | Leitura | Nível |
|---|---|---|
| abaixo de 0,10 | Sem mudança relevante | ok |
| de 0,10 a 0,25 | Mudança moderada | atenção |
| acima de 0,25 | Mudança grande | crítico |

O conjunto é considerado em drift quando **30% das colunas** passam de 0,10 (é o teste "Share of Drifted Columns" que fica vermelho no Evidently), ou quando qualquer coluna passa de 0,25 (critério do monitor da API).

**Referência:** a partição de teste (1.960 chamados em inglês). Ela não participou do treino, então a confiança do modelo nela é honesta. Usar o treino como referência faria qualquer produção parecer "menos confiante".

## 3. Simulação

`python -m supportcopilot.pipelines.drift_report` (ou `make drift`).

A janela de produção parte da partição `production`: 1.970 chamados em inglês que o modelo nunca viu. Sobre ela, quatro mecanismos isoláveis:

| Mecanismo | Causa real representada | Implementação |
|---|---|---|
| `language` | Expansão para outro país | Substitui uma fração da janela por chamados **reais** em alemão do mesmo dataset, com rótulo |
| `prior` | Incidente em massa | Reamostra com pesos por fila (mais "Service Outages", mais "Billing") |
| `noise` | Novo canal (chat no celular) | Erros de digitação (tecla vizinha, omissão, duplicação) e, em metade dos casos, tudo em maiúsculas |
| `truncate` | Integração com limite curto | Corta o texto em 70 caracteres |

| Cenário | `language` | `prior` | `noise` | `truncate` |
|---|---|---|---|---|
| Controle | 0 | nenhum | 0 | 0 |
| Moderado | 15% | 2x indisponibilidade | 10% | 0 |
| Severo | 45% | 6x indisponibilidade, 2x cobrança | 30% | 15% |

A simulação é determinística (seed fixa). Como os chamados em alemão são reais e rotulados, a queda de qualidade medida é real, e não uma consequência de texto embaralhado.

## 4. Resultados

Fonte: [`reports/drift/summary.md`](../reports/drift/summary.md) e [`summary.json`](../reports/drift/summary.json).

| Cenário | Colunas com drift | Acurácia | F1 macro | Confiança média | Fora do vocabulário | Relatório |
|---|---|---|---|---|---|---|
| Referência (teste) | - | 0,634 | 0,642 | 0,668 | 0,2% | |
| Controle | 0/10 | 0,636 | 0,652 | 0,661 | 0,4% | [HTML](../reports/drift/drift_controle.html) |
| Moderado | 3/10 | 0,593 | 0,612 | 0,640 | 12,3% | [HTML](../reports/drift/drift_moderado.html) |
| Severo | 9/10 | 0,471 | 0,426 | 0,605 | 36,0% | [HTML](../reports/drift/drift_severo.html) |

### Leitura

1. **Controle em silêncio.** Chamados novos da mesma distribuição: PSI máximo de 0,020, nenhuma coluna acusa, acurácia igual à da referência. O detector não dá alarme falso com 1.970 amostras.
2. **Moderado: aviso antecipado.** Três colunas da entrada passam do limiar (`oov_rate` 1,18; `upper_ratio` 0,32; `non_ascii_ratio` 0,17). A acurácia já caiu de 0,636 para 0,593, mas `confidence` (0,035) ainda não acusou. Quem olhasse só para a confiança do modelo não veria nada; quem olha para a entrada vê.
3. **Severo: o efeito chega à decisão.** Nove de dez colunas. `confidence`, `predicted_queue` e `technical_probability` entram em drift; a acurácia vai a 0,471 e o F1 macro a 0,426.
4. **A confiança cai menos do que a acurácia.** De 0,668 para 0,605 (queda de 9%), enquanto a acurácia perde 26%. O modelo continua razoavelmente "seguro" em chamados que não entende. É o motivo pelo qual não se pode monitorar só a confiança, e pelo qual `oov_rate` é a feature mais importante do monitor.
5. **`digit_ratio` é o controle negativo.** Nenhum mecanismo altera dígitos, e a coluna fica abaixo de 0,02 nos três cenários.

### No relatório HTML

Cada relatório abre com o resumo dos testes. No cenário severo, os que ficam vermelhos são "Share of Drifted Columns: Less 0.300" e um "Value Drift" por coluna afetada. Abaixo, para cada coluna, o Evidently mostra as distribuições de referência e da janela lado a lado: em `oov_rate`, a referência é um pico em zero e a janela severa tem uma segunda massa perto de 1,0 (os chamados em alemão). A seção de classificação mostra acurácia, precisão, recall e F1 da janela contra os da referência.

## 5. Dois detectores, de propósito

| | Relatório em lote | Monitor da API |
|---|---|---|
| Onde | `pipelines/drift_report.py` | `drift/monitor.py`, exposto em `GET /drift` |
| Quando | Sob demanda ou agendado | A cada chamado triado |
| Janela | Um lote (1.970 chamados) | Deslizante, últimos 500 |
| Ferramenta | Evidently (HTML) | PSI próprio contra o perfil de referência |
| Vê o rótulo? | Sim, se houver | Não |
| Para quê | Diagnóstico, evidência, auditoria | Alerta rápido |

Os dois usam PSI com os mesmos limiares, mas não chegam ao mesmo número: o Evidently monta as faixas de outra forma. O que se espera é que concordem sobre **quais** colunas mudaram, e concordam: no cenário severo, as colunas que o PSI próprio põe acima de 0,10 são as mesmas nove do Evidently (ver `psi_own` em `summary.json`).

O perfil de referência (`models/triage/reference_profile.json`) guarda, por feature, os limites das faixas (decis da referência) e a proporção esperada em cada uma. São agregados: o arquivo é versionado e vai dentro da imagem. Para features concentradas em um valor (como `non_ascii_ratio`, quase sempre zero), o perfil cria um limite logo acima do valor típico; sem isso, um salto de 0 para 0,05 cairia na mesma faixa e passaria despercebido.

## 6. O que este desenho não detecta

- **Drift de conceito.** Se a operação decidir que chamados de "troca de plano" saem de "Customer Service" e vão para "Sales", nenhum texto muda e nenhum monitor acusa. Só uma amostra rotulada periodicamente revela. Mitigação: auditar semanalmente uma amostra dos chamados, com prioridade para os de `needs_human_review`.
- **Mudança semântica com o mesmo vocabulário.** Um produto novo descrito com palavras já conhecidas não mexe em `oov_rate`. Apareceria, com atraso, em `predicted_queue` e `confidence`.
- **Janelas pequenas.** O monitor só opina com 200 chamados. Com dez faixas e pouca amostra, o ruído do PSI sozinho passa do limiar: em 1.000 janelas simuladas sem drift, sorteadas do próprio perfil de referência, 26% davam "atenção" e 12% "crítico" com 100 chamados; com 200, 0,1%; com 500, nenhuma.
