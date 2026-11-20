"""Ingestao do dataset publico de chamados: download com hash, limpeza e particoes.

Fonte: ``Tobi-Bueck/customer-support-tickets`` (Hugging Face, CC BY-NC 4.0), chamados em ingles e
alemao rotulados com a fila de atendimento. O projeto usa:

* ingles  -> Referencia: treino, validacao e teste do modelo de triagem, mais uma particao
  ``production`` que o modelo nunca ve e que faz o papel do fluxo futuro de chamados;
* alemao  -> reservatorio de drift: chamados reais em um idioma que o modelo nunca viu, usados
  pelo simulador para degradar a "producao" (ver ``supportcopilot.drift.simulate``).

A separacao entre as particoes e feita por grupos de quase-duplicatas: o dataset e sintetico e
traz parafrases do mesmo chamado; se uma parafrase caisse no treino e outra no teste, a metrica do
teste mediria memorizacao, nao generalizacao.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neighbors import NearestNeighbors

from supportcopilot.config.settings import Settings
from supportcopilot.data.text import compose_ticket, dedup_key, truncate

logger = logging.getLogger(__name__)

TEXT = "text"
TARGET = "queue"
LANGUAGE = "language"
GROUP = "group_id"
COLUMNS = [TEXT, TARGET, LANGUAGE, "priority", "type", GROUP]

NEAR_DUPLICATE_SIMILARITY = 0.80
_DOWNLOAD_TIMEOUT_SECONDS = 300
_CHUNK = 1 << 20


class DatasetIntegrityError(RuntimeError):
    """O arquivo baixado nao confere com o hash esperado."""


@dataclass(frozen=True)
class IngestSummary:
    raw_rows: int
    dropped_empty: int
    dropped_duplicates: int
    truncated: int
    reference_rows: int
    drift_pool_rows: int
    near_duplicate_groups: int
    rows_in_multi_groups: int
    train_rows: int
    validation_rows: int
    test_rows: int
    production_rows: int
    sha256: str


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download_dataset(settings: Settings, force: bool = False) -> Path:
    """Baixa o CSV (se ainda nao existir) e confere o SHA-256 antes de usa-lo."""
    target = settings.raw_dir / settings.dataset_file
    if force or not target.exists():
        url = settings.dataset_url
        if not url.startswith("https://"):
            raise ValueError(f"URL do dataset precisa ser https: {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        logger.info("baixando dataset de %s", url)
        request = urllib.request.Request(url, headers={"User-Agent": "supportcopilot"})  # noqa: S310 (https conferido)
        with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
            with partial.open("wb") as handle:
                for block in iter(lambda: response.read(_CHUNK), b""):
                    handle.write(block)
        partial.replace(target)
    verify_dataset(target, settings.dataset_sha256)
    return target


def verify_dataset(path: Path, expected_sha256: str) -> str:
    actual = sha256_of(path)
    if expected_sha256 and actual != expected_sha256:
        raise DatasetIntegrityError(f"hash de {path.name} nao confere: esperado {expected_sha256}, obtido {actual}")
    return actual


def clean_tickets(raw: pd.DataFrame, max_chars: int) -> tuple[pd.DataFrame, dict[str, int]]:
    """Monta o texto do chamado, aplica o limite do contrato e remove vazios e duplicatas."""
    frame = pd.DataFrame(
        {
            TEXT: [compose_ticket(s, b) for s, b in zip(raw.get("subject"), raw["body"], strict=True)],
            TARGET: raw[TARGET].astype("string").str.strip(),
            LANGUAGE: raw[LANGUAGE].astype("string").str.strip().str.lower(),
            "priority": raw.get("priority", pd.Series(pd.NA, index=raw.index)).astype("string"),
            "type": raw.get("type", pd.Series(pd.NA, index=raw.index)).astype("string"),
        }
    )
    too_long = frame[TEXT].str.len() > max_chars
    frame[TEXT] = frame[TEXT].map(lambda text: truncate(text, max_chars))

    empty = (frame[TEXT].str.len() == 0) | frame[TARGET].isna() | frame[LANGUAGE].isna()
    frame = frame[~empty]
    duplicated = frame[TEXT].map(dedup_key).duplicated()
    frame = frame[~duplicated].reset_index(drop=True)
    stats = {
        "dropped_empty": int(empty.sum()),
        "dropped_duplicates": int(duplicated.sum()),
        "truncated": int(too_long.sum()),
    }
    return frame, stats


def near_duplicate_groups(texts: pd.Series, threshold: float = NEAR_DUPLICATE_SIMILARITY) -> np.ndarray:
    """Agrupa parafrases: componentes conexas do grafo "similaridade de cosseno >= threshold".

    Usa TF-IDF de n-gramas de palavras e vizinhos mais proximos (exato, forca bruta esparsa).
    """
    if len(texts) < 2:
        return np.arange(len(texts))
    matrix = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1).fit_transform(texts)
    neighbors = NearestNeighbors(n_neighbors=min(6, len(texts)), metric="cosine", algorithm="brute").fit(matrix)
    distances, indices = neighbors.kneighbors(matrix)

    parent = np.arange(len(texts))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = int(parent[node])
        return node

    for row, (row_distances, row_indices) in enumerate(zip(distances, indices, strict=True)):
        for distance, other in zip(row_distances, row_indices, strict=True):
            if other != row and 1.0 - distance >= threshold:
                root_a, root_b = find(row), find(int(other))
                if root_a != root_b:
                    parent[max(root_a, root_b)] = min(root_a, root_b)
    roots = np.array([find(node) for node in range(len(texts))])
    _, groups = np.unique(roots, return_inverse=True)
    return groups


def _carve(frame: pd.DataFrame, fraction: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa ``fraction`` das linhas sem partir nenhum grupo de parafrases."""
    splitter = GroupShuffleSplit(n_splits=1, test_size=fraction, random_state=seed)
    rest_idx, carved_idx = next(splitter.split(frame, frame[TARGET], groups=frame[GROUP]))
    return frame.iloc[rest_idx], frame.iloc[carved_idx]


def split_reference(frame: pd.DataFrame, settings: Settings) -> dict[str, pd.DataFrame]:
    """Treino/validacao/teste/producao sem que um grupo de parafrases atravesse particoes."""
    remaining = 1.0
    partitions: dict[str, pd.DataFrame] = {}
    rest = frame
    for name, fraction in (
        ("production", settings.production_fraction),
        ("test", settings.test_fraction),
        ("validation", settings.validation_fraction),
    ):
        rest, partitions[name] = _carve(rest, fraction / remaining, settings.seed)
        remaining -= fraction
    partitions["train"] = rest
    return {name: partitions[name].reset_index(drop=True) for name in ("train", "validation", "test", "production")}


def prepare(raw: pd.DataFrame, settings: Settings) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    """Limpa o dataset bruto e devolve ``train``, ``validation``, ``test``, ``production`` e ``drift_pool``."""
    frame, stats = clean_tickets(raw, settings.max_text_chars)
    reference = frame[frame[LANGUAGE] == settings.reference_language].reset_index(drop=True)
    drift_pool = frame[frame[LANGUAGE] == settings.drift_language].reset_index(drop=True)
    if reference.empty:
        raise ValueError(f"nenhum chamado no idioma de referencia '{settings.reference_language}'")

    reference[GROUP] = near_duplicate_groups(reference[TEXT])
    drift_pool[GROUP] = -1
    sizes = reference[GROUP].value_counts()
    stats.update(
        reference_rows=len(reference),
        drift_pool_rows=len(drift_pool),
        near_duplicate_groups=int((sizes > 1).sum()),
        rows_in_multi_groups=int(sizes[sizes > 1].sum()),
    )
    partitions = split_reference(reference, settings)
    partitions["drift_pool"] = drift_pool
    return {name: part[COLUMNS] for name, part in partitions.items()}, stats


def run(settings: Settings, force_download: bool = False) -> IngestSummary:
    """Etapa completa: download -> limpeza -> particoes em ``data/processed``."""
    path = download_dataset(settings, force=force_download)
    raw = pd.read_csv(path, encoding="utf-8")
    partitions, stats = prepare(raw, settings)

    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    for name, part in partitions.items():
        part.to_parquet(settings.processed_dir / f"{name}.parquet", index=False)

    summary = IngestSummary(
        raw_rows=len(raw),
        train_rows=len(partitions["train"]),
        validation_rows=len(partitions["validation"]),
        test_rows=len(partitions["test"]),
        production_rows=len(partitions["production"]),
        sha256=sha256_of(path),
        **stats,
    )
    (settings.processed_dir / "ingest_summary.json").write_text(
        json.dumps(asdict(summary), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    logger.info("ingestao concluida: %s", asdict(summary))
    return summary


def load_partition(settings: Settings, name: str) -> pd.DataFrame:
    path = settings.processed_dir / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} nao existe; rode `python -m supportcopilot.pipelines.ingest` antes")
    return pd.read_parquet(path)
