"""CLI: treina o modelo de triagem e registra o experimento no MLflow.

O servidor do MLflow e apontado por ``COPILOT_MLFLOW_TRACKING_URI`` (ex.: ``http://127.0.0.1:5000``).
Sem a variavel, o treino roda sem rastreamento.
"""

from __future__ import annotations

import argparse
import json

from supportcopilot.config.settings import get_settings
from supportcopilot.observability.logs import configure_logging
from supportcopilot.triage import training


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    metadata = training.train(settings)
    test = metadata["metrics"]["test"]
    print(
        json.dumps(
            {
                "model_version": metadata["model_version"],
                "candidate": metadata["candidate"],
                "test": {k: round(v, 4) for k, v in test.items() if isinstance(v, float)},
                "baseline": metadata["metrics"]["baseline"],
                "mlflow": metadata["mlflow"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
