# syntax=docker/dockerfile:1
#
# Imagem do Copilot de Suporte (API FastAPI: triagem + RAG com guardrails).
#
#   builder    instala as dependencias de runtime (versoes e hashes travados em requirements.txt)
#              e baixa o modelo de embeddings, para o container nao depender de rede ao subir
#   runtime    imagem final enxuta: sem pip, sem toolchain, usuario nao-root, healthcheck embutido
#   pipelines  alvo opcional com MLflow e Evidently, para rodar treino e relatorio de drift
#
# Build:  docker build -t support-copilot:latest .
# Run:    docker run --rm -p 8000:8000 --env-file .env support-copilot:latest
#
# A imagem e autossuficiente: leva o modelo de triagem (models/triage) e os manuais (data/manuals).
# Para servir um modelo retreinado ou outros PDFs sem rebuild, monte volumes nesses caminhos.
# Nenhum segredo entra na imagem: as chaves de LLM chegam por variavel de ambiente em tempo de execucao.

ARG PYTHON_VERSION=3.12

# --------------------------------------------------------------------------- builder
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Somente o manifesto primeiro: a camada de dependencias so e refeita quando ele muda.
COPY requirements.txt ./
RUN pip install --require-hashes -r requirements.txt

# Modelo de embeddings (ONNX) baixado no build e embarcado na imagem.
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='${EMBEDDING_MODEL}', cache_dir='/opt/fastembed')"

# --------------------------------------------------------------------------- runtime
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ARG APP_VERSION=dev
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
LABEL org.opencontainers.image.title="support-copilot" \
      org.opencontainers.image.description="Copilot de suporte: triagem de chamados, RAG sobre manuais em PDF com guardrails e monitoramento de drift" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    COPILOT_ENVIRONMENT=docker \
    COPILOT_LOG_JSON=true \
    COPILOT_DATA_DIR=/app/data \
    COPILOT_MODELS_DIR=/app/models \
    COPILOT_REPORTS_DIR=/app/reports \
    COPILOT_EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    COPILOT_EMBEDDING_CACHE_DIR=/opt/fastembed \
    HF_HUB_OFFLINE=1

RUN groupadd --gid 10001 copilot \
    && useradd --uid 10001 --gid copilot --no-create-home --shell /usr/sbin/nologin copilot

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=copilot:copilot /opt/fastembed /opt/fastembed
COPY src/ ./src/
COPY models/triage/ ./models/triage/
COPY data/manuals/*.pdf ./data/manuals/

USER copilot
EXPOSE 8000

# /ready so responde 200 com o modelo de triagem e a base de conhecimento carregados.
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4).status == 200 else 1)"]

# Um worker por container: o indice vetorial e o monitor de drift vivem na memoria do processo.
# A escala e horizontal (mais replicas atras do balanceador), nao por workers.
CMD ["uvicorn", "supportcopilot.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--no-server-header"]

# --------------------------------------------------------------------------- pipelines
# docker build --target pipelines -t support-copilot-pipelines .
FROM python:${PYTHON_VERSION}-slim-bookworm AS pipelines

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    MLFLOW_DISABLE_AGENT_HINT=1

WORKDIR /app
COPY requirements-pipelines.txt ./
RUN pip install --require-hashes -r requirements-pipelines.txt
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY data/manuals/ ./data/manuals/

# Baixa o dataset (hash conferido), treina com rastreamento no MLflow e gera os relatorios de drift.
CMD ["sh", "-c", "python -m supportcopilot.pipelines.ingest && python -m supportcopilot.pipelines.train && python -m supportcopilot.pipelines.drift_report"]
