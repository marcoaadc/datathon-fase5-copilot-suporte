"""Estatisticas de drift, features monitoradas, monitor online, simulador e relatorio do Evidently."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from supportcopilot.data.ingest import LANGUAGE, TARGET, TEXT, load_partition
from supportcopilot.drift import attribution
from supportcopilot.drift import report as drift_report
from supportcopilot.drift.features import (
    MONITORED_FEATURES,
    build_frame,
    build_profile,
    describe_text,
    model_vocabulary,
)
from supportcopilot.drift.monitor import CRITICAL, INSUFFICIENT, OK, WARNING, DriftMonitor, level_for
from supportcopilot.drift.simulate import MECHANISM, SCENARIOS, Scenario, add_typos, get_scenario, simulate
from supportcopilot.drift.statistics import (
    bin_proportions,
    categorical_profile,
    category_proportions,
    numeric_profile,
    profile_psi,
    psi,
)
from supportcopilot.pipelines import drift_report as drift_pipeline
from supportcopilot.triage.registry import load_model
from tests.conftest import TECHNICAL


class TestStatistics:
    def test_psi_is_zero_for_identical_distributions(self):
        assert psi([0.2, 0.3, 0.5], [0.2, 0.3, 0.5]) == pytest.approx(0.0)

    def test_psi_grows_with_the_shift_and_is_symmetric(self):
        small = psi([0.5, 0.5], [0.45, 0.55])
        large = psi([0.5, 0.5], [0.1, 0.9])
        assert 0 < small < 0.1 < large
        assert psi([0.5, 0.5], [0.1, 0.9]) == pytest.approx(psi([0.1, 0.9], [0.5, 0.5]))

    def test_psi_tolerates_empty_bins(self):
        assert np.isfinite(psi([0.5, 0.5, 0.0], [0.0, 0.5, 0.5]))

    def test_numeric_profile_uses_reference_quantiles(self):
        profile = numeric_profile(np.arange(1000), bins=10)
        assert len(profile["edges"]) == 9
        assert profile["expected"] == pytest.approx([0.1] * 10, abs=0.01)
        assert profile_psi(profile, np.arange(1000)) == pytest.approx(0.0, abs=1e-6)
        assert profile_psi(profile, np.arange(1000) + 400) > 0.25

    def test_constant_feature_collapses_to_a_single_edge(self):
        profile = numeric_profile([0.0] * 50)
        assert len(profile["edges"]) == 2
        assert profile_psi(profile, [0.0] * 10) == pytest.approx(0.0, abs=1e-6)
        # Sair do valor tipico, para cima ou para baixo, precisa aparecer no PSI.
        assert profile_psi(profile, [0.05] * 10) > 1
        assert profile_psi(profile, [-1.0] * 10) > 1

    def test_numeric_profile_ignores_non_finite_and_rejects_empty(self):
        assert numeric_profile([1.0, np.nan, 2.0, np.inf])["mean"] == pytest.approx(1.5)
        with pytest.raises(ValueError, match="finito"):
            numeric_profile([np.nan])

    def test_bin_proportions_of_empty_sample(self):
        assert bin_proportions([], [1.0, 2.0]) == [0.0, 0.0, 0.0]

    def test_categorical_profile_and_unseen_category(self):
        profile = categorical_profile(["a", "a", "b", "b"])
        assert profile["categories"] == ["a", "b"]
        assert profile_psi(profile, ["a", "b"] * 10) == pytest.approx(0.0, abs=1e-6)
        assert category_proportions(["a", "c", "c", "c"], ["a", "b"]) == [0.25, 0.0, 0.75]
        assert profile_psi(profile, ["c"] * 20) > 1
        with pytest.raises(ValueError, match="categorico"):
            categorical_profile([])


class TestFeatures:
    @pytest.fixture(scope="class")
    def pipeline(self, workspace):
        from tests.conftest import build_settings

        return load_model(build_settings(workspace).triage_dir).pipeline

    def test_describe_text(self, pipeline):
        vocabulary, analyzer = model_vocabulary(pipeline)
        known = describe_text("router wireless connection", vocabulary, analyzer)
        unknown = describe_text("DIE VERBINDUNG BRICHT 123", vocabulary, analyzer)
        assert known["oov_rate"] == 0.0
        assert unknown["oov_rate"] == 1.0
        assert unknown["upper_ratio"] == 1.0
        assert unknown["digit_ratio"] == pytest.approx(3 / 25)
        assert known["n_words"] == 3

    def test_empty_like_text_is_fully_out_of_vocabulary(self, pipeline):
        vocabulary, analyzer = model_vocabulary(pipeline)
        assert describe_text("?!", vocabulary, analyzer)["oov_rate"] == 1.0

    def test_frame_and_profile_have_every_monitored_feature_and_no_text(self, pipeline):
        texts = pd.Series(["the router keeps dropping the connection", "I was charged twice on my invoice"] * 20)
        frame = build_frame(pipeline, texts, TECHNICAL)
        assert list(frame.columns) == MONITORED_FEATURES
        assert frame["confidence"].between(0, 1).all()
        profile = build_profile(frame)
        assert set(profile["features"]) == set(MONITORED_FEATURES)
        assert profile["n_reference"] == 40
        assert "router" not in json.dumps(profile)


class TestMonitor:
    PROFILE = {
        "n_reference": 1000,
        "features": {
            "confidence": numeric_profile(np.linspace(0.5, 1.0, 1000)),
            "oov_rate": numeric_profile(np.linspace(0.0, 0.2, 1000)),
            "predicted_queue": categorical_profile(["a"] * 500 + ["b"] * 500),
        },
    }

    def monitor(self, **kwargs) -> DriftMonitor:
        return DriftMonitor(self.PROFILE, **{"window_size": 200, "min_samples": 50, **kwargs})

    def feed(self, monitor: DriftMonitor, n: int, shifted: bool) -> None:
        rng = np.random.default_rng(0)
        for index in range(n):
            if shifted:
                row = {"confidence": rng.uniform(0.1, 0.4), "oov_rate": rng.uniform(0.6, 1.0), "predicted_queue": "a"}
            else:
                row = {
                    "confidence": rng.uniform(0.5, 1.0),
                    "oov_rate": rng.uniform(0, 0.2),
                    "predicted_queue": "ab"[index % 2],
                }
            monitor.observe({**row, "ignored": "x"})

    def test_levels(self):
        assert [level_for(v, 0.1, 0.25) for v in (0.05, 0.1, 0.25)] == [OK, WARNING, CRITICAL]

    def test_needs_minimum_samples(self):
        monitor = self.monitor()
        self.feed(monitor, 49, shifted=False)
        status = monitor.status()
        assert status["status"] == INSUFFICIENT
        assert status["drift_detected"] is False

    def test_stable_traffic_is_ok(self):
        monitor = self.monitor()
        self.feed(monitor, 200, shifted=False)
        status = monitor.status()
        assert status["status"] == OK
        assert status["drifted_features"] == []

    def test_shifted_traffic_is_critical(self):
        monitor = self.monitor()
        self.feed(monitor, 200, shifted=True)
        status = monitor.status()
        assert status["status"] == CRITICAL
        assert status["drifted_features"] == ["confidence", "oov_rate", "predicted_queue"]
        assert status["share_drifted"] == 1.0

    def test_window_slides_and_recovers(self):
        monitor = self.monitor()
        self.feed(monitor, 200, shifted=True)
        self.feed(monitor, 200, shifted=False)
        status = monitor.status()
        assert status["status"] == OK
        assert status["window_size"] == 200
        assert status["total_observed"] == 400

    def test_many_warnings_escalate_to_warning(self):
        monitor = self.monitor(psi_warning=0.0001, psi_critical=100.0)
        self.feed(monitor, 200, shifted=False)
        assert monitor.status()["status"] == WARNING

    def test_disabled_without_profile(self):
        monitor = DriftMonitor(None)
        monitor.observe({"confidence": 0.5})
        status = monitor.status()
        assert (status["enabled"], status["status"], status["total_observed"]) == (False, INSUFFICIENT, 0)


class TestSimulate:
    @pytest.fixture(scope="class")
    def data(self, workspace):
        from tests.conftest import build_settings

        settings = build_settings(workspace)
        return load_partition(settings, "production"), load_partition(settings, "drift_pool")

    def test_scenarios_are_ordered_from_control_to_severe(self):
        assert [s.name for s in SCENARIOS] == ["controle", "moderado", "severo"]
        assert SCENARIOS[0].is_control
        assert SCENARIOS[1].language_fraction < SCENARIOS[2].language_fraction
        assert get_scenario("severo") is SCENARIOS[2]
        with pytest.raises(KeyError):
            get_scenario("inexistente")

    def test_control_window_is_an_untouched_sample(self, data):
        production, pool = data
        window = simulate(production, pool, get_scenario("controle"), seed=1)
        assert set(window[MECHANISM]) == {"none"}
        assert set(window[TEXT]) <= set(production[TEXT])
        assert set(window[LANGUAGE]) == {"en"}

    def test_language_mechanism_brings_real_foreign_tickets(self, data):
        production, pool = data
        scenario = Scenario("lang", "x", "x", language_fraction=0.4)
        window = simulate(production, pool, scenario, size=100, seed=1)
        foreign = window[window[MECHANISM] == "language"]
        assert len(window) == 100
        assert len(foreign) == 40
        assert set(foreign[LANGUAGE]) == {"de"}
        assert set(foreign[TEXT]) <= set(pool[TEXT])

    def test_prior_mechanism_changes_the_queue_mix_only(self, data):
        production, pool = data
        scenario = Scenario("prior", "x", "x", prior_weights={"Billing and Payments": 8.0})
        window = simulate(production, pool, scenario, size=400, seed=1)
        before = (production[TARGET] == "Billing and Payments").mean()
        after = (window[TARGET] == "Billing and Payments").mean()
        assert after > before + 0.25
        assert set(window[TEXT]) <= set(production[TEXT])

    def test_noise_and_truncation_alter_the_text(self, data):
        production, pool = data
        scenario = Scenario("noise", "x", "x", noise_fraction=0.5, truncate_fraction=0.3, truncate_chars=20)
        window = simulate(production, pool, scenario, size=200, seed=1)
        counts = window[MECHANISM].value_counts()
        assert counts["noise"] == pytest.approx(100, abs=25)
        assert counts["truncate"] == pytest.approx(60, abs=25)
        assert window.loc[window[MECHANISM] == "truncate", TEXT].str.len().max() <= 20
        assert not set(window.loc[window[MECHANISM] == "noise", TEXT]) & set(production[TEXT])

    def test_simulation_is_reproducible(self, data):
        production, pool = data
        first = simulate(production, pool, get_scenario("severo"), size=80, seed=3)
        second = simulate(production, pool, get_scenario("severo"), size=80, seed=3)
        pd.testing.assert_frame_equal(first, second)
        assert not first.equals(simulate(production, pool, get_scenario("severo"), size=80, seed=4))

    def test_language_shift_without_pool_is_an_error(self, data):
        production, pool = data
        with pytest.raises(ValueError, match="reservatorio"):
            simulate(production, pool.iloc[0:0], get_scenario("severo"))

    def test_typos_keep_the_text_recognizable(self):
        rng = np.random.default_rng(0)
        original = "the router keeps dropping the wireless connection every few minutes"
        noisy = add_typos(original, rng, rate=0.2)
        assert noisy != original
        assert abs(len(noisy) - len(original)) < 15


class TestAttribution:
    def test_additive_game_recovers_individual_effects_and_is_efficient(self):
        from itertools import combinations

        weights = {"language": -0.10, "prior": -0.02, "noise": -0.05, "truncate": -0.01}
        value = {
            frozenset(combo): sum(weights[p] for p in combo)
            for size in range(5)
            for combo in combinations(attribution.MECHANISMS, size)
        }
        shapley = attribution.shapley_values(value, attribution.MECHANISMS)
        assert shapley == pytest.approx(weights)
        assert sum(shapley.values()) == pytest.approx(value[frozenset(attribution.MECHANISMS)] - value[frozenset()])

    def test_interaction_is_split_equally(self):
        # Dois mecanismos que so causam dano juntos: cada um recebe metade.
        players = ("a", "b")
        value = {frozenset(): 0.0, frozenset("a"): 0.0, frozenset("b"): 0.0, frozenset("ab"): -0.4}
        assert attribution.shapley_values(value, players) == pytest.approx({"a": -0.2, "b": -0.2})

    def test_scenario_subset_turns_mechanisms_off(self):
        base = get_scenario("severo")
        only_noise = attribution.scenario_subset(base, frozenset({"noise"}))
        assert only_noise.noise_fraction == base.noise_fraction
        assert (only_noise.language_fraction, only_noise.truncate_fraction, only_noise.prior_weights) == (0.0, 0.0, {})
        assert attribution.scenario_subset(base, frozenset()).is_control
        assert (
            attribution.scenario_subset(base, frozenset(attribution.MECHANISMS)).name == "language+noise+prior+truncate"
        )


@pytest.mark.slow
class TestEvidentlyReport:
    @pytest.fixture(scope="class")
    def summary(self, workspace, tmp_path_factory):
        from tests.conftest import build_settings

        reports = tmp_path_factory.mktemp("reports")
        settings = build_settings(workspace, reports_dir=reports, data_dir=workspace / "data")
        return settings, drift_pipeline.run(settings, window_size=150, attribution_seeds=(42,))

    def test_html_reports_and_summary_are_written(self, summary):
        settings = summary[0]
        for scenario in SCENARIOS:
            html = settings.drift_reports_dir / f"drift_{scenario.name}.html"
            assert html.stat().st_size > 100_000
            assert b"\r\n" not in html.read_bytes()[:200_000]
        saved = json.loads((settings.drift_reports_dir / "summary.json").read_text(encoding="utf-8"))
        assert [item["scenario"] for item in saved["scenarios"]] == ["controle", "moderado", "severo"]
        markdown = (settings.drift_reports_dir / "summary.md").read_text(encoding="utf-8")
        assert "| Drift severo |" in markdown
        assert "**drift**" in markdown

    def test_evidently_flags_the_degraded_window_and_not_the_control(self, summary):
        _, result = summary
        by_name = {item["scenario"]: item for item in result["scenarios"]}
        severe, control = by_name["severo"], by_name["controle"]
        assert "oov_rate" in severe["evidently"]["drifted_columns"]
        assert severe["evidently"]["n_drifted"] > control["evidently"]["n_drifted"]
        assert severe["evidently"]["share_drifted"] >= 0.3
        assert severe["evidently"]["tests_failed"] >= 1
        assert severe["evidently"]["n_columns"] == len(MONITORED_FEATURES)

    def test_degradation_shows_up_in_model_quality(self, summary):
        _, result = summary
        by_name = {item["scenario"]: item for item in result["scenarios"]}
        assert by_name["severo"]["quality"]["accuracy"] < by_name["controle"]["quality"]["accuracy"] - 0.1
        assert by_name["severo"]["quality"]["mean_oov_rate"] > by_name["controle"]["quality"]["mean_oov_rate"]
        assert by_name["severo"]["psi_own"]["oov_rate"] > 0.25

    def test_attribution_is_efficient_and_blames_the_language_shift(self, summary):
        settings, result = summary
        report = result["attribution"]
        assert (settings.drift_reports_dir / "attribution.json").exists()
        assert "## Atribuição causal" in (settings.drift_reports_dir / "summary.md").read_text(encoding="utf-8")
        for metric, item in report["metrics"].items():
            assert sum(item["shapley"].values()) == pytest.approx(item["total_change"], abs=1e-9), metric
            assert len(item["by_subset"]) == 16
        accuracy = report["metrics"]["accuracy"]
        assert accuracy["total_change"] < -0.1
        assert accuracy["shapley"]["language"] == min(accuracy["shapley"].values())
        assert report["metrics"]["mean_oov_rate"]["shapley"]["language"] > 0

    def test_own_psi_and_quality_helpers(self, summary):
        settings, _ = summary
        loaded = load_model(settings.triage_dir)
        reference = drift_report.score_window(loaded.pipeline, load_partition(settings, "test"), TECHNICAL)
        assert set(drift_report.own_psi(reference, reference).values()) == {0.0}
        quality = drift_report.quality(reference)
        assert quality["accuracy"] > 0.5
        assert 0 <= quality["mean_oov_rate"] <= 1
