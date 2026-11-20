"""Gera os arquivos ``requirements*.txt`` a partir do ``poetry.lock``.

O ``poetry.lock`` e a fonte da verdade das versoes; os ``requirements`` sao derivados dele para
quem instala com ``pip`` (a imagem Docker, por exemplo). Cada pacote sai com a versao exata, os
marcadores de plataforma e os hashes SHA-256 dos arquivos: ``pip install --require-hashes`` recusa
qualquer artefato que nao seja exatamente o que foi resolvido e testado.

* ``requirements.txt``            dependencias de runtime da API (grupo ``main``);
* ``requirements-pipelines.txt``  runtime + treino, MLflow, Evidently (grupos ``main`` e ``pipelines``).

Uso:
    python scripts/export_requirements.py           # regrava os arquivos
    python scripts/export_requirements.py --check   # falha se estiverem desatualizados (CI)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "poetry.lock"
TARGETS = {
    "requirements.txt": ("main",),
    "requirements-pipelines.txt": ("main", "pipelines"),
}
HEADER = (
    "# Gerado por scripts/export_requirements.py a partir do poetry.lock. Nao edite a mao.\n"
    "# Instale com: pip install --require-hashes -r {name}\n"
)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _marker(package: dict, groups: tuple[str, ...]) -> str | None:
    """Marcador de ambiente do pacote para os grupos pedidos (``None`` = sem restricao)."""
    markers = package.get("markers")
    if markers is None or isinstance(markers, str):
        return markers
    selected = [markers.get(group) for group in groups if group in package["groups"]]
    if any(marker is None for marker in selected):
        return None
    unique = list(dict.fromkeys(selected))
    return unique[0] if len(unique) == 1 else " or ".join(f"({marker})" for marker in unique)


def render(groups: tuple[str, ...], name: str) -> str:
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    lines = [HEADER.format(name=name)]
    packages = [p for p in lock["package"] if set(p.get("groups", ())) & set(groups)]
    for package in sorted(packages, key=lambda item: _normalize(item["name"])):
        requirement = f"{_normalize(package['name'])}=={package['version']}"
        marker = _marker(package, groups)
        if marker:
            requirement += f" ; {marker}"
        hashes = sorted({file["hash"] for file in package.get("files", [])})
        lines.append(" \\\n    ".join([requirement, *[f"--hash={digest}" for digest in hashes]]))
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for name, groups in TARGETS.items():
        content = render(groups, name)
        path = ROOT / name
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(name)
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
            print(f"{name}: {content.count('==')} pacotes")
    if stale:
        print(f"desatualizado(s): {', '.join(stale)}. Rode: python scripts/export_requirements.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
