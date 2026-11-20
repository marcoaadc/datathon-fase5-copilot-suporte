# ADR 0004 — Drift de texto medido por descritores, saída do modelo e PSI

**Status:** aceito

## Contexto

O modelo de triagem recebe texto livre. Testes de drift comparam distribuições, e texto bruto não tem uma distribuição diretamente comparável. O enunciado pede um script que simule a degradação e um relatório HTML do Evidently que a aponte.

## Decisão

1. **O que é monitorado:** dez features por chamado, nenhuma capaz de reconstruir o texto. Sete descrevem a forma do texto (`n_chars`, `n_words`, `mean_word_length`, `oov_rate`, `non_ascii_ratio`, `upper_ratio`, `digit_ratio`) e três descrevem a decisão do modelo (`predicted_queue`, `confidence`, `technical_probability`).
2. **Métrica:** PSI, com atenção em 0,10 e crítico em 0,25; o conjunto está em drift quando 30% das colunas passam do limiar.
3. **Simulação com dados reais:** a janela de produção parte de chamados que o modelo nunca viu e aplica quatro mecanismos isoláveis: troca de idioma (chamados reais em alemão do mesmo dataset), mudança na mistura de filas, ruído de digitação e truncamento.
4. **Duas instâncias do mesmo detector:** o relatório em lote (Evidently, com qualidade de classificação) e um monitor em janela deslizante dentro da API (`GET /drift`), que usa um perfil de referência só com agregados.
5. **Cenário de controle obrigatório:** o relatório de uma janela sem drift é gerado e versionado junto. Um detector só é confiável se também fica em silêncio quando não há nada.

## Alternativas consideradas

- **Drift sobre embeddings:** captura mudança semântica, mas o relatório fica ilegível para quem precisa agir ("a dimensão 217 mudou"). Os descritores são interpretáveis: "a taxa de palavras fora do vocabulário foi de 0,2% para 36%" aponta a causa.
- **Classificador de domínio sobre o texto:** detecta bem, explica mal, e exigiria guardar texto de produção, o que conflita com a decisão de privacidade (ADR 0005).
- **Texto perturbado artificialmente como único mecanismo:** drift fabricado não tem rótulo confiável. Usar chamados reais em outro idioma permite medir a queda real do modelo.

## Consequências

- O relatório liga causa e efeito: no cenário severo, 9 de 10 colunas em drift e acurácia de 0,63 para 0,47.
- `digit_ratio` não acusa drift em nenhum cenário, e está certo: nenhum mecanismo mexe em dígitos. Serve de controle negativo dentro do próprio relatório.
- O monitor da API vive na memória de cada réplica e precisa de 100 chamados para opinar; é um alerta rápido, não substitui o relatório em lote.
- Drift de conceito (o mesmo texto passar a pertencer a outra fila) não é detectável sem rótulo. A mitigação é amostrar chamados para rotulagem humana, descrita no runbook.
