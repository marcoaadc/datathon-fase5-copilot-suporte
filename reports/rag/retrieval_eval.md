# Avaliacao da busca do RAG

Modelo de embeddings `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 50 chunks (tamanho 700, sobreposicao 120) | k = 4 | 60 perguntas respondiveis e 20 fora do escopo.

| Estrategia | hit@1 | hit@4 | MRR |
|---|---|---|---|
| hybrid | 81.7% | 98.3% | 0.890 |
| dense | 78.3% | 96.7% | 0.850 |
| lexical | 68.3% | 88.3% | 0.765 |

## Limiar de relevancia

Similaridade do melhor trecho: perguntas respondiveis de 0.296 (minimo) a media 0.598; fora do escopo, media 0.178 e maximo 0.405. Limiar em uso: 0.35.

| Limiar | Respondiveis que passam | Fora do escopo recusadas |
|---|---|---|
| 0.20 | 100.0% | 55.0% |
| 0.25 | 100.0% | 80.0% |
| 0.30 | 98.3% | 85.0% |
| 0.35 (em uso) | 98.3% | 85.0% |
| 0.40 | 95.0% | 95.0% |
| 0.45 | 90.0% | 100.0% |
| 0.50 | 80.0% | 100.0% |

## Perguntas em que a secao esperada ficou fora do top 4 (hibrida)

- O que vem na caixa do produto? (esperada 1.1; veio 9.1 Garantia, 1 Visão geral do produto, , 5.5 Acesso remoto)
