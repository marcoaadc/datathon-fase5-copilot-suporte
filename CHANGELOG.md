# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [1.0.0] - 2026-11-20

Primeira entrega: copilot de suporte de ponta a ponta para o Datathon da Fase 5.

### Adicionado

- **Triagem.** Ingestão do dataset público com revisão e hash fixos, limpeza compartilhada entre treino e API, partição por grupos de paráfrases, seleção entre oito candidatos lineares por F1 macro, registro do modelo com conferência de integridade.
- **Rastreamento.** Experimentos no MLflow com runs aninhados por candidato, métricas de teste, matriz de confusão, perfil de referência e modelo no Model Registry; resumo versionado em `reports/mlflow/summary.md`.
- **API FastAPI.** `POST /triage`, `POST /chat`, `POST /tickets` (fluxo completo), `GET /drift`, `/info`, `/health`, `/ready` e `/metrics`; contrato Pydantic (texto de 1 a 1000 caracteres, campos desconhecidos rejeitados), envelope único de erro, chave de API opcional e limite de requisições.
- **RAG.** Leitura de PDF com LangChain, chunking por seção, embeddings multilíngues locais, busca híbrida FAISS + BM25 com RRF, portão de relevância, LLM da OpenAI ou do Gemini e modo extrativo quando não há LLM.
- **Guardrails.** Nove regras de entrada com normalização anti-evasão, quarentena de trechos do PDF com instruções embutidas, quatro regras de saída (vazamento de prompt, citação obrigatória, valores fora do manual, troca de papel).
- **Privacidade.** Mascaramento de CPF, CNPJ, RG, cartão, e-mail, telefone, CEP, data de nascimento, MAC, IP público, senha e nome antes do envio ao LLM; nenhum conteúdo em logs ou erros.
- **Drift.** Dez features monitoradas, simulador com quatro mecanismos (idioma, mistura de filas, ruído, truncamento), relatórios do Evidently para três cenários e monitor por PSI em janela deslizante na API.
- **Avaliação.** Suíte de ataques e perguntas legítimas, conjunto cego escrito por revisor independente, avaliação da busca com ablação (densa, lexical, híbrida) e varredura do limiar de relevância.
- **Engenharia.** Imagem Docker multi-stage não-root com o modelo de embeddings embarcado, `docker-compose` com MLflow, `requirements.txt` com hashes gerado do lock, CI com lint, testes em Python 3.10 a 3.12 e teste de fumaça do container sem rede.
- **Documentação.** README com arquitetura de nuvem e LGPD, seis ADRs, referência de guardrails, guia de drift, model card e runbook.

### Decisões registradas durante o desenvolvimento

- A partição aleatória inicial inflava a acurácia (perto de 0,70) por memorização de paráfrases; a partição por grupos trouxe o número honesto (0,634).
- A primeira versão das regras de guardrail bloqueou 38 de 51 ataques do conjunto cego; as falhas viraram generalizações das regras, e a primeira medição ficou registrada como a estimativa de eficácia.
- A detecção de vazamento do prompt só reconhecia o canário e duas frases fixas; um teste mostrou que copiar o início do prompt passava. Passou a comparar sequências de palavras da resposta com o prompt inteiro.
- O PSI próprio era cego a features concentradas em zero (`non_ascii_ratio`); o perfil de referência ganhou um limite logo acima do valor típico.
- Uma revisão independente do código, feita antes da entrega, encontrou e levou à correção de: máscara de senha que mutilava perguntas comuns ("esqueci a senha e preciso..."); checagem de valores da saída por trecho de texto em vez de valor inteiro; detecção de vazamento que bloquearia a abertura "com base nos trechos do manual"; oito falsos positivos e dois bypasses nas regras de entrada; preflight de CORS barrado pela autenticação; limite de corpo contornável por envio em blocos; chave de API vazia aceita como válida; piso do monitor de drift baixo demais (alarme falso por ruído amostral); e o servidor MLflow do compose recusando o nome do serviço como host.
