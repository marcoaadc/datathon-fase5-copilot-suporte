"""CLI: baixa o dataset publico (hash conferido), limpa e gera as particoes em ``data/processed``."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from supportcopilot.config.settings import get_settings
from supportcopilot.data import ingest
from supportcopilot.observability.logs import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-download", action="store_true", help="baixa de novo mesmo se o arquivo existir")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    summary = ingest.run(settings, force_download=args.force_download)
    print(json.dumps(asdict(summary), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
