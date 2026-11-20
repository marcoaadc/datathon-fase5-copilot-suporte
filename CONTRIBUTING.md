# Contribuindo

## Setup

```bash
poetry install
poetry run pre-commit install
cp .env.example .env
make test-fast       # testes rápidos, em segundos
make api             # API em http://127.0.0.1:8000/docs
```

O repositório já traz o modelo de triagem, o manual e os relatórios. Para refazê-los do zero: `make mlflow-server` em um terminal e `make pipeline` em outro.

## Fluxo de trabalho

1. Crie uma branch a partir de `main` (`feat/...`, `fix/...`, `docs/...`).
2. Rode `make lint test` antes de abrir o PR. O CI está definido para executar lint, testes em Python 3.10 a 3.12 e o build da imagem Docker com teste de fumaça (enquanto o Actions da conta estiver bloqueado, rode `make lint test` localmente).
3. Mensagens de commit seguem [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `build:`, `chore:`, com escopo quando ajuda (`feat(guardrails): ...`).
4. Registre mudanças relevantes em `CHANGELOG.md`, em uma seção *Não lançado* no topo (crie-a se não existir).

## Quando regenerar os artefatos

O modelo em `models/`, os relatórios em `reports/` e o PDF em `data/manuals/` são a evidência do projeto e precisam refletir o código. Regenere e inclua no mesmo PR quando mudar:

| Mudança | Regenerar | Comando |
|---|---|---|
| Limpeza de texto, partição, candidatos, features do modelo | Modelo e relatórios de drift | `make pipeline` |
| Features monitoradas, cenários ou mecanismos de drift, limiares | Relatórios de drift | `make drift` |
| Chunking, embeddings, busca, limiar de relevância | Avaliação da busca | `make eval-rag` |
| Fonte do manual (`data/manuals/source/*.md`) | PDF e avaliação da busca | `make manual eval-rag` |
| Dependências (`pyproject.toml`) | Lock e requirements | `poetry lock && make requirements` |

Se os números mudarem, atualize as tabelas do `README.md` e de `docs/`, e o Model Card se a mudança for no modelo.

## Convenções

- Python 3.10+, `ruff` (linhas de 120 colunas), *type hints* em funções públicas.
- Configuração só via `Settings` (`pydantic-settings`, prefixo `COPILOT_`); nada de `os.environ` espalhado.
- Estágios de pipeline são funções em `src/supportcopilot/`; as CLIs em `pipelines/` apenas as chamam.
- **Guardrails:** toda regra nova entra no catálogo (`guardrails/rules.py`) com identificador `GR-xx`, ganha ao menos um ataque e uma pergunta legítima parecida em `tests/data/guardrail_cases.json`, e é documentada em `docs/guardrails.md`. Regra que só passa a bloquear um ataque às custas de bloquear uma pergunta legítima não entra.
- **Conjunto cego:** os casos `allow` de `tests/data/guardrail_heldout.json` não devem ser usados para ajustar padrões. Se um deles falhar, a regra que causou o falso positivo está errada.
- **Texto do modelo:** a limpeza usada no treino e na API é a mesma função (`data/text.py`). Mudar uma exige retreinar.
- Toda função estatística nova tem teste com um caso de resposta conhecida.
- Textos exibidos ao usuário (respostas da API, relatórios, documentação) são acentuados; comentários e docstrings ficam em ASCII.

## Privacidade

- Nenhum conteúdo de chamado, pergunta ou resposta em logs, métricas ou mensagens de erro: registre contagens, durações, filas e identificadores de regra. Há um teste que falha se o texto aparecer no log.
- Nada que saia da aplicação para o LLM pode pular o mascaramento (`guardrails/pii.py`).
- Exemplos e testes usam apenas dados fictícios. O CPF dos testes (`529.982.247-25`) é um número de exemplo comum em documentação de validadores; não foi obtido de nenhum cadastro.
- Um novo tipo de dado pessoal detectável entra em `pii.py` com padrão, validador (quando existir) e teste de falso positivo em texto técnico.
- Chaves de LLM só por variável de ambiente ou `.env` (ignorado pelo Git). Nunca em código, imagem ou exemplo.
