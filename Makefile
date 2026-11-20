# Datathon FIAP Fase 05 - Copilot de Suporte (triagem, RAG com guardrails e observabilidade)
# Requer: Poetry >= 2.0 e make (no Windows, use Git Bash). Sem make, os comandos equivalentes estao no README.

MLFLOW_URI ?= http://127.0.0.1:5000
IMAGE      ?= support-copilot:latest

.PHONY: help install lint format test test-fast test-cov data train drift pipeline mlflow-server api check-llm \
        eval-guardrails eval-rag manual requirements docker-build docker-run compose-up compose-pipelines clean

help:
	@echo "Alvos disponiveis:"
	@echo "  install          Instala dependencias (poetry install)"
	@echo "  lint             ruff check + ruff format --check + requirements em dia"
	@echo "  format           Formata o codigo e aplica fixes do ruff"
	@echo "  test             Suite completa (inclui MLflow, Evidently e embeddings reais, ~2 min)"
	@echo "  test-fast        Apenas os testes rapidos (segundos)"
	@echo "  test-cov         Suite completa com relatorio de cobertura"
	@echo "  mlflow-server    Sobe o servidor local do MLflow em http://127.0.0.1:5000"
	@echo "  data             Baixa o dataset publico (hash conferido) e gera as particoes"
	@echo "  train            Treina o modelo de triagem e registra o experimento no MLflow"
	@echo "  drift            Simula a degradacao e gera os relatorios do Evidently em reports/drift"
	@echo "  pipeline         data -> train -> drift"
	@echo "  api              Sobe a API em http://127.0.0.1:8000/docs"
	@echo "  check-llm        Confere se o provedor de LLM configurado responde"
	@echo "  eval-guardrails  Mede bloqueio de ataques e falso positivo dos guardrails"
	@echo "  eval-rag         Mede a busca do RAG (hit@k, MRR, limiar de relevancia)"
	@echo "  manual           Regera o PDF do manual a partir do fonte em Markdown"
	@echo "  requirements     Regera requirements*.txt a partir do poetry.lock"
	@echo "  docker-build     Constroi a imagem da API"
	@echo "  docker-run       Sobe a imagem da API na porta 8000"
	@echo "  compose-up       API + MLflow com docker compose"
	@echo "  clean            Remove caches e artefatos temporarios"

install:
	poetry install

lint:
	poetry run ruff check .
	poetry run ruff format --check .
	poetry run python scripts/export_requirements.py --check

format:
	poetry run ruff format .
	poetry run ruff check --fix .

test:
	poetry run pytest

test-fast:
	poetry run pytest -m "not slow"

test-cov:
	poetry run pytest --cov --cov-report=term-missing

mlflow-server:
	poetry run mlflow server --backend-store-uri sqlite:///mlflow.db --artifacts-destination ./mlartifacts \
		--host 127.0.0.1 --port 5000

data:
	poetry run python -m supportcopilot.pipelines.ingest

train:
	COPILOT_MLFLOW_TRACKING_URI=$(MLFLOW_URI) poetry run python -m supportcopilot.pipelines.train

drift:
	COPILOT_MLFLOW_TRACKING_URI=$(MLFLOW_URI) poetry run python -m supportcopilot.pipelines.drift_report

pipeline: data train drift

api:
	poetry run uvicorn supportcopilot.api.main:app --host 127.0.0.1 --port 8000

check-llm:
	poetry run python -m supportcopilot.pipelines.check_llm

eval-guardrails:
	poetry run python scripts/evaluate_guardrails.py

eval-rag:
	poetry run python scripts/evaluate_rag.py

manual:
	poetry run python scripts/build_manual.py

requirements:
	poetry run python scripts/export_requirements.py

docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env $(IMAGE)

compose-up:
	docker compose up --build

compose-pipelines:
	docker compose run --rm pipelines

clean:
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage coverage.xml data/drift
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
