"""CLI: simula a degradacao dos dados e gera os relatorios de drift do Evidently.

Para cada cenario (controle, moderado, severo):

1. monta uma janela de producao simulada a partir de chamados que o modelo nunca viu;
2. extrai as features monitoradas e aplica o modelo;
3. gera ``reports/drift/drift_<cenario>.html`` com o Evidently;
4. resume o veredito, o PSI do detector proprio e a qualidade do modelo em ``summary.json``/``summary.md``;
5. reparte a degradacao do cenario severo entre os mecanismos por valores de Shapley (``attribution.json``).

Com ``COPILOT_MLFLOW_TRACKING_URI`` definido, cada cenario vira um run no experimento de drift.
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from supportcopilot.config.settings import Settings, get_settings
from supportcopilot.data.ingest import TEXT, load_partition
from supportcopilot.drift import attribution
from supportcopilot.drift import report as drift_report
from supportcopilot.drift.simulate import MECHANISM, SCENARIOS, Scenario, get_scenario, simulate
from supportcopilot.observability.logs import configure_logging
from supportcopilot.observability.tracking import Tracker
from supportcopilot.triage.registry import load_model, write_json

logger = logging.getLogger(__name__)

DRIFT_EXPERIMENT_SUFFIX = "-drift"


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Resumo dos relatorios de drift",
        "",
        f"Modelo `{summary['model_version']}` | referencia: {summary['reference_rows']} chamados da particao de "
        f"teste | metodo: PSI, limiar {summary['psi_threshold']}, alerta com {summary['drift_share']:.0%} das colunas.",
        "",
        "| Cenario | Colunas com drift | Testes reprovados | Acuracia | F1 macro | Confianca media "
        "| Fora do vocabulario | Relatorio |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in summary["scenarios"]:
        evidently, quality = item["evidently"], item["quality"]
        lines.append(
            f"| {item['title']} | {evidently['n_drifted']}/{evidently['n_columns']} ({evidently['share_drifted']:.0%}) "
            f"| {evidently['tests_failed']}/{evidently['tests_total']} | {quality['accuracy']:.3f} "
            f"| {quality['f1_macro']:.3f} | {quality['mean_confidence']:.3f} | {quality['mean_oov_rate']:.3f} "
            f"| [{item['html']}]({item['html']}) |"
        )
    reference = summary["reference_quality"]
    lines += [
        "",
        f"Referencia (teste): acuracia {reference['accuracy']:.3f}, F1 macro {reference['f1_macro']:.3f}, "
        f"confianca media {reference['mean_confidence']:.3f}, fora do vocabulario {reference['mean_oov_rate']:.3f}.",
        "",
        "## PSI por coluna (Evidently)",
        "",
        "| Coluna | " + " | ".join(item["title"] for item in summary["scenarios"]) + " |",
        "|---|" + "---|" * len(summary["scenarios"]),
    ]
    columns = sorted({column for item in summary["scenarios"] for column in item["evidently"]["psi"]})
    for column in columns:
        cells = []
        for item in summary["scenarios"]:
            value = item["evidently"]["psi"].get(column)
            flag = " **drift**" if value is not None and value >= summary["psi_threshold"] else ""
            cells.append("-" if value is None else f"{value:.3f}{flag}")
        lines.append(f"| `{column}` | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def run(
    settings: Settings,
    scenarios: tuple[Scenario, ...] = SCENARIOS,
    window_size: int | None = None,
    attribution_seeds: tuple[int, ...] | None = None,
    with_attribution: bool = True,
) -> dict:
    loaded = load_model(settings.triage_dir)
    technical = tuple(settings.technical_queues)
    reference_raw = load_partition(settings, "test")
    production = load_partition(settings, "production")
    drift_pool = load_partition(settings, "drift_pool")
    out_dir = settings.drift_reports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    windows_dir = settings.data_dir / "drift"
    windows_dir.mkdir(parents=True, exist_ok=True)

    reference = drift_report.score_window(loaded.pipeline, reference_raw, technical)
    tracker = Tracker(settings.mlflow_tracking_uri, settings.mlflow_experiment + DRIFT_EXPERIMENT_SUFFIX)
    summary: dict[str, Any] = {
        "model_version": loaded.metadata.get("model_version"),
        "reference_rows": len(reference),
        "psi_threshold": settings.psi_warning,
        "drift_share": drift_report_share(),
        "reference_quality": drift_report.quality(reference),
        "scenarios": [],
    }

    for scenario in scenarios:
        window = simulate(production, drift_pool, scenario, size=window_size, seed=settings.seed)
        window.to_parquet(windows_dir / f"window_{scenario.name}.parquet", index=False)
        current = drift_report.score_window(loaded.pipeline, window, technical)
        snapshot = drift_report.run_evidently(
            reference, current, settings.psi_warning, summary["drift_share"], name=f"drift-{scenario.name}"
        )
        html = drift_report.save_html(snapshot, out_dir / f"drift_{scenario.name}.html")
        evidently = drift_report.summarize(snapshot, settings.psi_warning)
        item = {
            "scenario": scenario.name,
            "title": scenario.title,
            "description": scenario.description,
            "rows": len(window),
            "mechanisms": window[MECHANISM].value_counts().to_dict(),
            "mean_chars": float(window[TEXT].str.len().mean()),
            "evidently": evidently,
            "psi_own": drift_report.own_psi(reference, current),
            "quality": drift_report.quality(current),
            "html": html.name,
        }
        summary["scenarios"].append(item)
        logger.info(
            "cenario %s: %d/%d colunas com drift, acuracia %.3f",
            scenario.name,
            evidently["n_drifted"],
            evidently["n_columns"],
            item["quality"]["accuracy"],
        )
        with tracker.run(f"drift-{scenario.name}", tags={"stage": "drift", "scenario": scenario.name}):
            tracker.log_params(
                {
                    "scenario": scenario.name,
                    "model_version": summary["model_version"],
                    "language_fraction": scenario.language_fraction,
                    "noise_fraction": scenario.noise_fraction,
                    "truncate_fraction": scenario.truncate_fraction,
                    "prior_weights": json.dumps(scenario.prior_weights),
                    "rows": len(window),
                }
            )
            tracker.log_metrics(
                {
                    **item["quality"],
                    "share_drifted": evidently["share_drifted"],
                    "n_drifted": evidently["n_drifted"],
                    "tests_failed": evidently["tests_failed"],
                    **{f"psi__{column}": value for column, value in evidently["psi"].items()},
                }
            )
            tracker.log_artifact(html, "evidently")

    markdown = _markdown(summary)
    if with_attribution:
        seeds = attribution_seeds or (settings.seed, settings.seed + 1, settings.seed + 2)
        report = attribution.attribute(
            loaded.pipeline,
            reference,
            production,
            drift_pool,
            get_scenario("severo"),
            technical,
            settings.psi_warning,
            seeds=seeds,
            window_size=window_size,
        )
        summary["attribution"] = report
        write_json(out_dir / "attribution.json", report)
        markdown += "\n" + attribution.to_markdown(report)
        with tracker.run("drift-atribuicao", tags={"stage": "drift", "scenario": "severo"}):
            tracker.log_params({"seeds": json.dumps(list(seeds)), "rows": report["rows_per_window"]})
            tracker.log_metrics(
                {
                    f"shapley__{metric}__{mechanism}": value
                    for metric, item in report["metrics"].items()
                    for mechanism, value in item["shapley"].items()
                }
                | {f"total_change__{metric}": item["total_change"] for metric, item in report["metrics"].items()}
            )
            tracker.log_dict(report, "attribution.json")

    write_json(out_dir / "summary.json", summary)
    (out_dir / "summary.md").write_text(markdown, encoding="utf-8", newline="\n")
    return summary


def drift_report_share() -> float:
    """Fracao de colunas com drift a partir da qual o conjunto e considerado em drift."""
    return 0.30


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", choices=[s.name for s in SCENARIOS], action="append", help="padrao: todos")
    parser.add_argument("--window-size", type=int, default=None, help="chamados por janela (padrao: a particao toda)")
    parser.add_argument("--no-attribution", action="store_true", help="pula a atribuicao causal por Shapley")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    chosen = tuple(s for s in SCENARIOS if not args.scenario or s.name in args.scenario)
    summary = run(settings, chosen, args.window_size, with_attribution=not args.no_attribution)
    for item in summary["scenarios"]:
        evidently = item["evidently"]
        print(
            f"{item['scenario']:10s} drift em {evidently['n_drifted']}/{evidently['n_columns']} colunas | "
            f"acuracia {item['quality']['accuracy']:.3f} | {settings.drift_reports_dir / item['html']}"
        )
    if "attribution" in summary:
        shapley = summary["attribution"]["metrics"]["accuracy"]["shapley"]
        print("atribuicao da queda de acuracia (Shapley): " + ", ".join(f"{m}={v:+.3f}" for m, v in shapley.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
