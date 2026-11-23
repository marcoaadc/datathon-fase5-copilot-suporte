# Resumo do rastreamento no MLflow

Extraido do servidor `http://127.0.0.1:5000` por `scripts/mlflow_summary.py`.

## Experimento `copilot-triagem`

1 run de treino e 8 runs aninhados (um por candidato).

### Candidatos avaliados na validacao

| Run | Familia | Parametros | val_accuracy | val_f1_macro | val_log_loss | val_routing_f1 | fit_seconds |
|---|---|---|---|---|---|---|---|
| `logreg_c30_balanced` | logistic_regression | C=30.0, class_weight=balanced | 0.6003 | 0.6035 | 1.3083 | 0.8414 | 74.2938 |
| `logreg_c100` | logistic_regression | C=100.0 | 0.6039 | 0.5959 | 1.4736 | 0.8415 | 91.8685 |
| `logreg_c30` | logistic_regression | C=30.0 | 0.6003 | 0.5884 | 1.3445 | 0.8424 | 87.5289 |
| `svc_c10` | linear_svc_calibrated | C=10.0 | 0.5977 | 0.5856 | 1.3067 | 0.8502 | 90.8791 |
| `svc_c3` | linear_svc_calibrated | C=3.0 | 0.5926 | 0.575 | 1.3044 | 0.8519 | 61.8029 |
| `logreg_c10` | logistic_regression | C=10.0 | 0.591 | 0.574 | 1.2894 | 0.8426 | 80.5968 |
| `svc_c1` | linear_svc_calibrated | C=1.0 | 0.574 | 0.5618 | 1.3106 | 0.8471 | 44.723 |
| `nb_alpha0.3` | complement_nb | alpha=0.3 | 0.4626 | 0.3865 | 1.7394 | 0.7299 | 11.9287 |

### Run de treino `treino-triagem` (`5b165cdd34d74f2dbc208af3112c05bb`)

Status: FINISHED. Vencedor: `logreg_c30_balanced`.

| Parametro | Valor |
|---|---|
| `dataset` | Tobi-Bueck/customer-support-tickets@ddf1c81a5475 |
| `dataset_sha256` | f187c090e59581c2 |
| `max_text_chars` | 1000 |
| `n_classes` | 10 |
| `n_test` | 1960 |
| `n_train` | 10467 |
| `n_validation` | 1939 |
| `reference_language` | en |
| `seed` | 42 |
| `split` | group_shuffle_near_duplicates |
| `winner` | logreg_c30_balanced |
| `winner_family` | logistic_regression |

| Metrica (teste) | Valor |
|---|---|
| `test_accuracy` | 0.6342 |
| `test_f1_macro` | 0.6421 |
| `test_f1_weighted` | 0.6341 |
| `test_log_loss` | 1.1703 |
| `test_ece` | 0.0371 |
| `test_routing_precision` | 0.8575 |
| `test_routing_recall` | 0.8685 |
| `test_routing_f1` | 0.8629 |
| `majority_class_accuracy` | 0.301 |
| `test_f1__billing_payments` | 0.8565 |
| `test_f1__customer_service` | 0.5705 |
| `test_f1__general_inquiry` | 0.7317 |
| `test_f1__human_resources` | 0.6098 |
| `test_f1__it_support` | 0.52 |
| `test_f1__product_support` | 0.5714 |
| `test_f1__returns_exchanges` | 0.5517 |
| `test_f1__sales_pre_sales` | 0.6154 |
| `test_f1__service_outages_maintenance` | 0.7273 |
| `test_f1__technical_support` | 0.6672 |

Artefatos:

- `drift/reference_profile.json`
- `evaluation/confusion_matrix.json`
- `evaluation/confusion_matrix.png`
- `evaluation/per_class.json`
- `model_card/metadata.json`
- `selection/leaderboard.json`

## Model Registry: `support-ticket-triage`

| Versao | Run de origem | Status |
|---|---|---|
| 1 | `5b165cdd34d74f2dbc208af3112c05bb` | READY |

## Experimento `copilot-triagem-drift`

Um run por cenario de drift, com o relatorio HTML do Evidently como artefato.

| Run | share_drifted | n_drifted | tests_failed | accuracy | f1_macro | mean_confidence | mean_oov_rate | Artefato |
|---|---|---|---|---|---|---|---|---|
| `drift-controle` | 0 | 0 | 0 | 0.6355 | 0.6519 | 0.6607 | 0.0037 | `evidently/drift_controle.html` |
| `drift-moderado` | 0.3 | 3 | 4 | 0.5934 | 0.6124 | 0.6399 | 0.1229 | `evidently/drift_moderado.html` |
| `drift-severo` | 0.9 | 9 | 14 | 0.4711 | 0.4257 | 0.605 | 0.3599 | `evidently/drift_severo.html` |

### Run `drift-atribuicao` (`5aefb07f568d433ba80ff8423ace890e`)

Valores de Shapley de cada mecanismo do cenario severo, por metrica (seeds [42, 43, 44], 1970 chamados por janela).

| Metrica | Valor |
|---|---|
| `shapley__accuracy__language` | -0.1274 |
| `shapley__accuracy__noise` | -0.0196 |
| `shapley__accuracy__prior` | 0.027 |
| `shapley__accuracy__truncate` | -0.0302 |
| `shapley__f1_macro__language` | -0.1441 |
| `shapley__f1_macro__noise` | -0.0238 |
| `shapley__f1_macro__prior` | -0.0086 |
| `shapley__f1_macro__truncate` | -0.0374 |
| `shapley__mean_confidence__language` | -0.0596 |
| `shapley__mean_confidence__noise` | -0.0133 |
| `shapley__mean_confidence__prior` | 0.0305 |
| `shapley__mean_confidence__truncate` | -0.0108 |
| `shapley__mean_oov_rate__language` | 0.2773 |
| `shapley__mean_oov_rate__noise` | 0.0747 |
| `shapley__mean_oov_rate__prior` | -0.0034 |
| `shapley__mean_oov_rate__truncate` | 0.0054 |
| `shapley__share_drifted__language` | 0.463 |
| `shapley__share_drifted__noise` | 0.1296 |
| `shapley__share_drifted__prior` | -0.0494 |
| `shapley__share_drifted__truncate` | 0.2716 |
| `total_change__accuracy` | -0.1503 |
| `total_change__f1_macro` | -0.2139 |
| `total_change__mean_confidence` | -0.0532 |
| `total_change__mean_oov_rate` | 0.354 |
| `total_change__share_drifted` | 0.8148 |
