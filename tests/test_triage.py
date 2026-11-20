"""Modelagem, metricas, registro e servico de inferencia da triagem."""

from __future__ import annotations

import json

import numpy as np
import pytest

from supportcopilot.data.ingest import TARGET, TEXT, load_partition
from supportcopilot.triage import registry, training
from supportcopilot.triage.modeling import (
    CANDIDATES,
    Candidate,
    build_pipeline,
    evaluate,
    expected_calibration_error,
    scalar_metrics,
    technical_probability,
)
from supportcopilot.triage.service import TriageService
from tests.conftest import FAST_CANDIDATES, TECHNICAL, build_settings


class TestModeling:
    @pytest.mark.parametrize("family", sorted({candidate.family for candidate in CANDIDATES}))
    def test_every_family_fits_and_outputs_probabilities(self, settings, family):
        candidate = next(c for c in CANDIDATES if c.family == family)
        train = load_partition(settings, "train")
        pipeline = build_pipeline(candidate, seed=0).fit(train[TEXT], train[TARGET])
        probabilities = pipeline.predict_proba(train[TEXT].head(5))
        assert probabilities.shape == (5, train[TARGET].nunique())
        assert np.allclose(probabilities.sum(axis=1), 1.0)

    def test_unknown_family_is_rejected(self):
        with pytest.raises(ValueError, match="desconhecida"):
            build_pipeline(Candidate("x", "random_forest", {}), seed=0)

    def test_ece_is_zero_when_confidence_matches_accuracy(self):
        confidence = np.array([1.0, 1.0, 1.0, 1.0])
        assert expected_calibration_error(confidence, np.array([True, True, True, True])) == 0.0

    def test_ece_measures_overconfidence(self):
        confidence = np.full(10, 0.95)
        correct = np.array([True] * 5 + [False] * 5)
        assert expected_calibration_error(confidence, correct) == pytest.approx(0.45)

    def test_technical_probability_sums_technical_columns(self):
        probabilities = np.array([[0.1, 0.2, 0.7], [0.5, 0.5, 0.0]])
        result = technical_probability(probabilities, ["a", "b", "c"], ("a", "c"))
        assert result == pytest.approx([0.8, 0.5])

    def test_evaluate_reports_queue_and_routing_metrics(self):
        classes = ["Billing", "IT Support", "Technical Support"]
        y_true = ["Billing", "IT Support", "Technical Support", "Technical Support"]
        probabilities = np.array([[0.9, 0.05, 0.05], [0.1, 0.2, 0.7], [0.1, 0.1, 0.8], [0.8, 0.1, 0.1]])
        metrics = evaluate(y_true, probabilities, classes, ("IT Support", "Technical Support"))
        assert metrics["accuracy"] == pytest.approx(0.5)
        # O chamado de TI previsto como "Technical Support" erra a fila, mas acerta o roteamento.
        assert metrics["routing_accuracy"] == pytest.approx(0.75)
        assert metrics["routing_precision"] == pytest.approx(1.0)
        assert metrics["routing_recall"] == pytest.approx(2 / 3)
        assert metrics["per_class"]["Billing"]["support"] == 1
        flat = scalar_metrics(metrics, "test_")
        assert flat["test_accuracy"] == pytest.approx(0.5)
        assert "test_f1__technical_support" in flat
        assert all(isinstance(value, float) for value in flat.values())


class TestTraining:
    def test_training_selects_by_validation_f1_and_writes_artifacts(self, workspace):
        settings = build_settings(workspace)
        metadata = json.loads((settings.triage_dir / registry.METADATA_FILE).read_text(encoding="utf-8"))
        board = metadata["leaderboard"]
        assert board[0]["candidate"] == metadata["candidate"]
        assert board == sorted(board, key=lambda row: (row["val_f1_macro"], -row["val_log_loss"]), reverse=True)
        assert {row["candidate"] for row in board} == {c.name for c in FAST_CANDIDATES}
        test = metadata["metrics"]["test"]
        assert test["accuracy"] > metadata["metrics"]["baseline"]["majority_class_accuracy"]
        assert test["accuracy"] > 0.9  # dataset sintetico separavel
        assert metadata["mlflow"] == {"tracking_uri": None, "run_id": None}
        assert (settings.triage_dir / registry.REFERENCE_PROFILE_FILE).exists()

    def test_majority_baseline(self, settings):
        train, test = load_partition(settings, "train"), load_partition(settings, "test")
        baseline = training.majority_baseline(train, test)["majority_class_accuracy"]
        assert 0.0 < baseline < 0.6


class TestRegistry:
    def test_roundtrip_preserves_predictions(self, settings, tmp_path):
        loaded = registry.load_model(settings.triage_dir)
        registry.save_model(tmp_path / "copy", loaded.pipeline, {"model_version": "x"}, {"n_reference": 1})
        copy = registry.load_model(tmp_path / "copy")
        texts = ["I was charged twice on invoice 5"]
        assert list(copy.pipeline.predict(texts)) == list(loaded.pipeline.predict(texts))
        assert copy.metadata["artifact"]["sha256"]
        assert copy.reference_profile == {"n_reference": 1}

    def test_tampered_artifact_is_refused_before_unpickling(self, settings, tmp_path):
        loaded = registry.load_model(settings.triage_dir)
        registry.save_model(tmp_path / "m", loaded.pipeline, {"model_version": "x"})
        with (tmp_path / "m" / registry.MODEL_FILE).open("ab") as handle:
            handle.write(b"payload")
        with pytest.raises(registry.ModelIntegrityError):
            registry.load_model(tmp_path / "m")

    def test_metadata_without_hash_is_refused(self, settings, tmp_path):
        loaded = registry.load_model(settings.triage_dir)
        registry.save_model(tmp_path / "m", loaded.pipeline, {"model_version": "x"})
        registry.write_json(tmp_path / "m" / registry.METADATA_FILE, {"model_version": "x"})
        with pytest.raises(registry.ModelIntegrityError):
            registry.load_model(tmp_path / "m")

    def test_missing_model_gives_actionable_error(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="treino"):
            registry.load_model(tmp_path)


class TestService:
    @pytest.fixture
    def service(self, settings) -> TriageService:
        return TriageService.from_directory(settings.triage_dir, technical_queues=TECHNICAL)

    def test_technical_ticket_is_routed_to_rag(self, service):
        prediction = service.predict("Hi, the router keeps dropping the wireless connection and the wifi is slow")
        assert prediction.queue == "Technical Support"
        assert prediction.is_technical
        assert prediction.technical_probability >= 0.5
        assert prediction.top[0] == (prediction.queue, pytest.approx(prediction.confidence))
        assert sum(probability for _, probability in service.predict("x y z", top_k=10).top) == pytest.approx(1.0)

    def test_billing_ticket_goes_to_human_queue(self, service):
        prediction = service.predict("I was charged twice on my invoice, please refund the payment")
        assert prediction.queue == "Billing and Payments"
        assert not prediction.is_technical

    def test_low_confidence_flags_human_review(self, settings):
        strict = TriageService.from_directory(
            settings.triage_dir, technical_queues=TECHNICAL, low_confidence_threshold=0.999
        )
        assert strict.predict("qwerty asdf zxcv").needs_human_review

    def test_features_carry_no_text(self, service):
        features = service.predict("My password is hunter2 and the router is down").features
        assert set(features) >= {"n_chars", "oov_rate", "confidence", "predicted_queue"}
        assert all(not isinstance(value, str) or value in service.classes for value in features.values())

    def test_same_cleaning_as_training(self, service):
        raw = "The router keeps dropping\\n\\nthe wireless   connection every 3 minutes"
        clean = "The router keeps dropping\nthe wireless connection every 3 minutes"
        assert service.predict(raw).confidence == pytest.approx(service.predict(clean).confidence)

    def test_version_comes_from_metadata(self, service):
        assert service.version == service.metadata["model_version"]
