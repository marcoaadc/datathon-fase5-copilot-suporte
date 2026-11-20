# ADR 0002 — RAG com busca híbrida, embeddings locais e índice em memória

**Status:** aceito

## Contexto

O `/chat` precisa responder apenas com base em manuais em PDF: carregar o PDF, quebrar em chunks, indexar em um banco vetorial em memória (FAISS ou Chroma) e consultar um LLM (OpenAI ou Gemini).

## Decisão

1. **Chunking por seção:** o texto é dividido primeiro nos títulos numerados do manual e só depois por tamanho (700 caracteres, sobreposição de 120). Um chunk nunca mistura duas seções, e a seção vira metadado, texto indexado e citação.
2. **Busca híbrida:** FAISS (densa, cosseno) e BM25 (lexical), combinadas por Reciprocal Rank Fusion.
3. **Embeddings locais:** `paraphrase-multilingual-MiniLM-L12-v2` via ONNX (fastembed), dentro da aplicação.
4. **Portão de relevância:** se nenhum trecho recuperado atinge similaridade 0,35, a resposta é "não encontrei" e o LLM não é chamado.
5. **Índice em memória, reconstruído na subida:** o corpus é pequeno (50 chunks); indexar leva menos de 2 segundos.

## Evidência

Medido em `reports/rag/retrieval_eval.md` (60 perguntas com a seção esperada, 20 fora do escopo):

| Estratégia | hit@1 | hit@4 | MRR |
|---|---|---|---|
| híbrida | 81,7% | 98,3% | 0,890 |
| densa | 78,3% | 96,7% | 0,850 |
| lexical | 68,3% | 88,3% | 0,765 |

A lexical encontra o termo exato (`E301`, `WPS`, `192.168.10.1`) que o embedding dilui; a densa encontra a paráfrase ("a conexão fica caindo") e cruza idiomas, o que a lexical não faz. A fusão fica acima das duas.

## Alternativas consideradas

- **Embeddings do provedor de LLM:** enviaria a pergunta do usuário a um terceiro duas vezes (embedding e geração), custaria por indexação e tornaria a busca impossível de testar sem chave. Rejeitado por privacidade, custo e testabilidade.
- **Só busca densa:** mais simples, mas perde 1,6 ponto de hit@4 e erra justamente códigos de erro e endereços, que são o que o suporte técnico mais precisa acertar.
- **Reranker (cross-encoder):** melhoraria o hit@1, mas adiciona um segundo modelo e latência. Com 98% de hit@4 e o LLM lendo os quatro trechos, não se pagava.
- **Banco vetorial gerenciado:** desnecessário para dezenas de chunks. O caminho de evolução está descrito na arquitetura de nuvem (README, seção 9).

## Consequências

- A imagem Docker leva o modelo de embeddings (cerca de 220 MB) e sobe sem rede.
- Cada réplica tem o seu índice; atualizar um manual exige nova imagem ou novo volume e reinício.
- O portão de relevância recusa 85% das perguntas fora do escopo sem custo de LLM; as demais dependem da sentinela `[[SEM_RESPOSTA_NO_MANUAL]]` que o prompt exige.
