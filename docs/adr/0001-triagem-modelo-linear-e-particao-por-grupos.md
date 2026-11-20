# ADR 0001 — Triagem com modelo linear sobre TF-IDF e partição por grupos de paráfrases

**Status:** aceito

## Contexto

A triagem precisa classificar o chamado em uma de dez filas e decidir se ele é um problema técnico (o que aciona o RAG). O enunciado pede um modelo clássico (scikit-learn ou XGBoost). O dataset público é sintético e contém paráfrases do mesmo chamado: 2.126 dos 16.336 chamados em inglês (13%) têm ao menos um quase-duplicado.

## Decisão

1. **Representação:** TF-IDF de palavras (uni e bigramas) unido a TF-IDF de n-gramas de caracteres (2 a 5). Os n-gramas de caracteres toleram erro de digitação e palavras que nunca apareceram inteiras no treino.
2. **Modelo:** família linear (regressão logística, SVM linear calibrado, Complement Naive Bayes), escolhida por F1 macro na validação. Acurácia sozinha premiaria quem acerta só as filas grandes: a maior fila tem 28% dos chamados e a menor, 1,5%.
3. **Partição:** os chamados são agrupados por similaridade de cosseno (TF-IDF, limiar 0,80, componentes conexas) e a separação treino/validação/teste/produção nunca divide um grupo.
4. **Teste usado uma única vez:** o vencedor é retreinado em treino + validação e avaliado no teste, que não participou de nenhuma escolha.

## Alternativas consideradas

- **XGBoost sobre TF-IDF:** em matriz esparsa com dezenas de milhares de colunas, modelos lineares costumam empatar ou vencer árvores, treinam em segundos e geram um artefato pequeno. Não justificava o custo.
- **Embeddings + classificador:** exigiria o modelo de embeddings também no caminho da triagem e não é "modelo clássico" no sentido do enunciado.
- **Partição aleatória estratificada:** foi o primeiro experimento e deu acurácia 0,70. Com a partição por grupos, a mesma configuração cai para 0,63 a 0,66. A diferença é memorização de paráfrases, não capacidade de generalizar; a métrica honesta é a menor.

## Consequências

- A acurácia reportada (0,63) é mais baixa do que seria com partição aleatória, e é a que se deve esperar em chamados novos.
- A decisão que importa para o produto é binária (técnico ou não) e é bem mais robusta que a fila exata: F1 de 0,86. Confundir "Technical Support" com "IT Support" não muda o roteamento.
- O artefato é um `joblib` (pickle). Ele só é carregado depois de o SHA-256 conferir com o registrado em `metadata.json`.
