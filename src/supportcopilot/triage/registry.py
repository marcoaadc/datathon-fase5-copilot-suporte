"""Registro local do modelo de triagem: artefato joblib + metadados + conferencia de integridade.

``joblib`` desserializa com pickle, que executa codigo arbitrario. Por isso o artefato so e
carregado depois de o SHA-256 do arquivo conferir com o registrado em ``metadata.json`` no momento
do treino: um ``model.joblib`` trocado ou corrompido e recusado antes de ser aberto.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
from sklearn.pipeline import Pipeline

MODEL_FILE = "model.joblib"
METADATA_FILE = "metadata.json"
REFERENCE_PROFILE_FILE = "reference_profile.json"


class ModelIntegrityError(RuntimeError):
    """O artefato do modelo nao confere com o hash registrado nos metadados."""


@dataclass(frozen=True)
class LoadedModel:
    pipeline: Pipeline
    metadata: dict[str, Any]
    reference_profile: dict[str, Any] | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def save_model(
    directory: Path,
    pipeline: Pipeline,
    metadata: dict[str, Any],
    reference_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / MODEL_FILE
    joblib.dump(pipeline, model_path, compress=3)
    metadata = {**metadata, "artifact": {"file": MODEL_FILE, "sha256": _sha256(model_path)}}
    write_json(directory / METADATA_FILE, metadata)
    if reference_profile is not None:
        write_json(directory / REFERENCE_PROFILE_FILE, reference_profile)
    return metadata


def load_model(directory: Path) -> LoadedModel:
    directory = Path(directory)
    metadata_path = directory / METADATA_FILE
    model_path = directory / MODEL_FILE
    if not metadata_path.exists() or not model_path.exists():
        raise FileNotFoundError(f"modelo de triagem nao encontrado em {directory}; rode o treino antes")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = metadata.get("artifact", {}).get("sha256")
    actual = _sha256(model_path)
    if not expected or actual != expected:
        raise ModelIntegrityError(f"hash de {model_path} nao confere com metadata.json (esperado {expected})")
    pipeline = joblib.load(model_path)
    profile_path = directory / REFERENCE_PROFILE_FILE
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else None
    return LoadedModel(pipeline=pipeline, metadata=metadata, reference_profile=profile)
