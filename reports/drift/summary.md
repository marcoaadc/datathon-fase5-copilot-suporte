# Resumo dos relatorios de drift

Modelo `20261120181832` | referencia: 1960 chamados da particao de teste | metodo: PSI, limiar 0.1, alerta com 30% das colunas.

| Cenario | Colunas com drift | Testes reprovados | Acuracia | F1 macro | Confianca media | Fora do vocabulario | Relatorio |
|---|---|---|---|---|---|---|---|
| Controle (sem drift) | 0/10 (0%) | 0/15 | 0.636 | 0.652 | 0.661 | 0.004 | [drift_controle.html](drift_controle.html) |
| Drift moderado | 3/10 (30%) | 4/15 | 0.593 | 0.612 | 0.640 | 0.123 | [drift_moderado.html](drift_moderado.html) |
| Drift severo | 9/10 (90%) | 14/15 | 0.471 | 0.426 | 0.605 | 0.360 | [drift_severo.html](drift_severo.html) |

Referencia (teste): acuracia 0.634, F1 macro 0.642, confianca media 0.668, fora do vocabulario 0.002.

## PSI por coluna (Evidently)

| Coluna | Controle (sem drift) | Drift moderado | Drift severo |
|---|---|---|---|
| `confidence` | 0.010 | 0.035 | 0.168 **drift** |
| `digit_ratio` | 0.012 | 0.013 | 0.018 |
| `mean_word_length` | 0.002 | 0.078 | 0.498 **drift** |
| `n_chars` | 0.014 | 0.031 | 0.350 **drift** |
| `n_words` | 0.020 | 0.018 | 0.234 **drift** |
| `non_ascii_ratio` | 0.013 | 0.169 **drift** | 0.664 **drift** |
| `oov_rate` | 0.005 | 1.176 **drift** | 4.134 **drift** |
| `predicted_queue` | 0.008 | 0.037 | 0.143 **drift** |
| `technical_probability` | 0.012 | 0.030 | 0.110 **drift** |
| `upper_ratio` | 0.012 | 0.321 **drift** | 1.346 **drift** |

## Atribuição causal da degradação (valores de Shapley)

Cenário `severo` decomposto nas 16 combinações dos 4 mecanismos, 3 seeds por combinação, 1970 chamados por janela. Acurácia: controle 0.636, tudo ligado 0.485 (variação -0.150).

| Mecanismo | Shapley (acurácia) | Isolado (acurácia) | Shapley (F1 macro) | Shapley (fora do vocab.) | Shapley (colunas em drift) |
|---|---|---|---|---|---|
| Idioma (chamados em alemao) | -0.127 | -0.125 | -0.144 | +0.277 | +0.46 |
| Mistura de filas (incidente) | +0.027 | +0.042 | -0.009 | -0.003 | -0.05 |
| Ruido de digitacao e maiusculas | -0.020 | -0.026 | -0.024 | +0.075 | +0.13 |
| Mensagens truncadas | -0.030 | -0.040 | -0.037 | +0.005 | +0.27 |
| **Total (tudo ligado − controle)** | **-0.150** | **-0.150** | **-0.214** | **+0.354** | **+0.81** |
