"""CLIs, rastreamento no MLflow, logging e configuracao."""

from __future__ import annotations

import json
import logging

import pytest

from supportcopilot.config.settings import Settings, get_settings
from supportcopilot.observability.logs import JsonFormatter, configure_logging, request_id_var
from supportcopilot.observability.tracking import Tracker
from supportcopilot.pipelines import drift_report as drift_cli
from supportcopilot.pipelines import ingest as ingest_cli
from supportcopilot.pipelines import train as train_cli
from supportcopilot.rag.embeddings import build_embeddings
from supportcopilot.triage import training
from tests.conftest import FAST_CANDIDATES, build_settings, make_tickets


class TestSettings:
    def test_environment_overrides_and_derived_paths(self, monkeypatch, tmp_path):
        monkeypatch.setenv("COPILOT_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("COPILOT_MAX_TEXT_CHARS", "500")
        monkeypatch.setenv("COPILOT_TECHNICAL_QUEUES", '["A", "B"]')
        settings = Settings(_env_file=None)
        assert settings.raw_dir == tmp_path / "raw"
        assert settings.manuals_dir == tmp_path / "manuals"
        assert settings.max_text_chars == 500
        assert settings.technical_queues == ("A", "B")
        assert settings.dataset_url.startswith("https://huggingface.co/datasets/")
        assert settings.dataset_revision in settings.dataset_url

    @pytest.mark.parametrize(
        ("variable", "provider"),
        [("OPENAI_API_KEY", "openai"), ("GOOGLE_API_KEY", "gemini"), ("GEMINI_API_KEY", "gemini")],
    )
    def test_conventional_provider_variables_are_accepted(self, monkeypatch, variable, provider):
        monkeypatch.setenv(variable, "segredo")
        settings = Settings(_env_file=None)
        assert settings.resolved_llm_provider() == provider
        assert "segredo" not in repr(settings)
        assert "segredo" not in settings.model_dump_json()

    def test_explicit_offline_wins_over_keys(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "segredo")
        assert Settings(_env_file=None, llm_provider="offline").resolved_llm_provider() == "offline"

    def test_invalid_values_fail_at_startup(self):
        with pytest.raises(ValueError, match="max_text_chars"):
            Settings(_env_file=None, max_text_chars=1)

    def test_get_settings_is_cached(self):
        assert get_settings() is get_settings()


class TestLogging:
    def test_json_formatter_includes_request_id_and_extras(self):
        record = logging.LogRecord("copilot", logging.INFO, __file__, 1, "evento %s", ("x",), None)
        record.queue = "Technical Support"
        token = request_id_var.set("req-123")
        try:
            payload = json.loads(JsonFormatter().format(record))
        finally:
            request_id_var.reset(token)
        assert payload["message"] == "evento x"
        assert payload["request_id"] == "req-123"
        assert payload["queue"] == "Technical Support"
        assert payload["level"] == "INFO"

    def test_json_formatter_serializes_exceptions(self):
        try:
            raise ValueError("falhou")
        except ValueError:
            import sys

            record = logging.LogRecord("copilot", logging.ERROR, __file__, 1, "erro", (), sys.exc_info())
        assert "ValueError: falhou" in json.loads(JsonFormatter().format(record))["exception"]

    @pytest.mark.parametrize("json_logs", [True, False])
    def test_configure_logging_installs_a_single_handler(self, json_logs):
        root = logging.getLogger()
        previous_handlers, previous_level = root.handlers[:], root.level
        try:
            configure_logging("warning", json_logs=json_logs)
            assert len(root.handlers) == 1
            assert root.level == logging.WARNING
            assert isinstance(root.handlers[0].formatter, JsonFormatter) is json_logs
            logging.getLogger("teste").warning("mensagem sem request em andamento")
        finally:
            root.handlers[:] = previous_handlers
            root.setLevel(previous_level)


class TestTrackerDisabled:
    def test_every_call_is_a_noop_without_tracking_uri(self, tmp_path):
        tracker = Tracker(None, "experimento")
        assert tracker.enabled is False
        with tracker.run("run") as run_id:
            assert run_id is None
            tracker.log_params({"a": 1})
            tracker.log_metrics({"m": 1.0})
            tracker.log_dict({"k": "v"}, "x.json")
            tracker.log_artifact(tmp_path / "nao-existe.txt")
            tracker.log_confusion_matrix(["a"], ["a"], ["a"], "cm.png")
            assert tracker.log_model(object(), ["x"]) is None


@pytest.mark.slow
class TestMlflowIntegration:
    """Treino e relatorio de drift rastreados em um MLflow real (backend sqlite em disco)."""

    @pytest.fixture(scope="class")
    def tracked(self, tmp_path_factory):
        from supportcopilot.data import ingest

        root = tmp_path_factory.mktemp("mlflow")
        uri = f"sqlite:///{(root / 'mlflow.db').as_posix()}"
        settings = build_settings(root, mlflow_tracking_uri=uri, mlflow_experiment="teste-triagem")
        partitions, _ = ingest.prepare(make_tickets(), settings)
        settings.processed_dir.mkdir(parents=True)
        for name, part in partitions.items():
            part.to_parquet(settings.processed_dir / f"{name}.parquet", index=False)
        import mlflow

        previous = mlflow.get_tracking_uri()
        try:
            metadata = training.train(settings, FAST_CANDIDATES)
            yield settings, metadata
        finally:
            mlflow.set_tracking_uri(previous)

    def test_parent_and_nested_runs_with_metrics_and_artifacts(self, tracked):
        from mlflow.tracking import MlflowClient

        settings, metadata = tracked
        client = MlflowClient(settings.mlflow_tracking_uri)
        experiment = client.get_experiment_by_name("teste-triagem")
        runs = client.search_runs([experiment.experiment_id])
        parents = [run for run in runs if "mlflow.parentRunId" not in run.data.tags]
        children = [run for run in runs if "mlflow.parentRunId" in run.data.tags]
        assert len(parents) == 1
        assert {run.info.run_name for run in children} == {candidate.name for candidate in FAST_CANDIDATES}
        assert all(run.info.status == "FINISHED" for run in runs)

        parent = parents[0]
        assert parent.info.run_id == metadata["mlflow"]["run_id"]
        assert {"test_accuracy", "test_f1_macro", "test_routing_f1", "majority_class_accuracy"} <= set(
            parent.data.metrics
        )
        assert parent.data.metrics["test_accuracy"] == pytest.approx(metadata["metrics"]["test"]["accuracy"])
        assert parent.data.params["winner"] == metadata["candidate"]
        assert parent.data.params["split"] == "group_shuffle_near_duplicates"
        assert {"val_accuracy", "val_f1_macro", "fit_seconds"} <= set(children[0].data.metrics)

        artifacts = {item.path for item in client.list_artifacts(parent.info.run_id)}
        assert {"evaluation", "selection", "drift", "model_card"} <= artifacts
        evaluation = {item.path for item in client.list_artifacts(parent.info.run_id, "evaluation")}
        assert "evaluation/confusion_matrix.png" in evaluation

    def test_model_is_registered_and_loadable(self, tracked):
        import mlflow
        from mlflow.tracking import MlflowClient

        settings, metadata = tracked
        client = MlflowClient(settings.mlflow_tracking_uri)
        versions = client.search_model_versions(f"name='{settings.mlflow_registered_model}'")
        assert [str(version.version) for version in versions] == [metadata["mlflow"]["registered_version"]]
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        model = mlflow.sklearn.load_model(f"models:/{settings.mlflow_registered_model}/{versions[0].version}")
        assert (
            model.predict(["I was charged twice on my invoice, please refund the payment"])[0] == "Billing and Payments"
        )

    def test_drift_runs_are_logged_with_the_html_report(self, tracked):
        from mlflow.tracking import MlflowClient

        settings, _ = tracked
        drift_cli.run(settings, window_size=80)
        client = MlflowClient(settings.mlflow_tracking_uri)
        experiment = client.get_experiment_by_name("teste-triagem" + drift_cli.DRIFT_EXPERIMENT_SUFFIX)
        runs = {run.info.run_name: run for run in client.search_runs([experiment.experiment_id])}
        assert set(runs) == {"drift-controle", "drift-moderado", "drift-severo", "drift-atribuicao"}
        assert "shapley__accuracy__language" in runs["drift-atribuicao"].data.metrics
        severe = runs["drift-severo"]
        assert severe.data.metrics["share_drifted"] > runs["drift-controle"].data.metrics["share_drifted"]
        assert "psi__oov_rate" in severe.data.metrics
        assert [item.path for item in client.list_artifacts(severe.info.run_id, "evidently")] == [
            "evidently/drift_severo.html"
        ]


class TestCommandLines:
    @pytest.fixture
    def cli_settings(self, workspace, tmp_path, monkeypatch):
        settings = build_settings(workspace, reports_dir=tmp_path / "reports", models_dir=tmp_path / "models")
        for module in (ingest_cli, train_cli, drift_cli):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
            monkeypatch.setattr(module, "configure_logging", lambda *args: None)
        return settings

    def test_train_cli_prints_metrics(self, cli_settings, monkeypatch, capsys):
        monkeypatch.setattr(training, "CANDIDATES", FAST_CANDIDATES)
        monkeypatch.setattr(training.train, "__defaults__", (FAST_CANDIDATES,))
        assert train_cli.main([]) == 0
        output = json.loads(capsys.readouterr().out)
        assert output["candidate"] in {"nb", "logreg"}
        assert output["test"]["accuracy"] > 0.5
        assert (cli_settings.triage_dir / "model.joblib").exists()

    @pytest.mark.slow
    def test_drift_cli_runs_a_single_scenario(self, cli_settings, monkeypatch, capsys):
        monkeypatch.setattr(training.train, "__defaults__", (FAST_CANDIDATES,))
        train_cli.main([])
        capsys.readouterr()
        assert drift_cli.main(["--scenario", "severo", "--window-size", "80"]) == 0
        output = capsys.readouterr().out
        assert output.startswith("severo")
        assert (cli_settings.drift_reports_dir / "drift_severo.html").exists()
        assert not (cli_settings.drift_reports_dir / "drift_controle.html").exists()

    def test_ingest_cli_runs_end_to_end(self, tmp_path, monkeypatch, capsys):
        settings = build_settings(tmp_path)
        settings.raw_dir.mkdir(parents=True)
        make_tickets().to_csv(settings.raw_dir / settings.dataset_file, index=False)
        monkeypatch.setattr(ingest_cli, "get_settings", lambda: settings)
        monkeypatch.setattr(ingest_cli, "configure_logging", lambda *args: None)
        assert ingest_cli.main([]) == 0
        summary = json.loads(capsys.readouterr().out)
        assert summary["train_rows"] > 0
        assert summary["drift_pool_rows"] > 0


@pytest.mark.slow
class TestRealEmbeddings:
    """Modelo multilingue real (baixado na primeira execucao): a busca cruza portugues e ingles."""

    @pytest.fixture(scope="class")
    def kb(self, workspace):
        from supportcopilot.guardrails.engine import GuardrailEngine
        from supportcopilot.rag.bootstrap import build_knowledge_base

        settings = Settings(_env_file=None, data_dir=workspace / "data")
        try:
            embeddings = build_embeddings(settings.embedding_model, settings.embedding_cache_dir)
        except Exception as error:  # sem rede para baixar o modelo
            pytest.skip(f"modelo de embeddings indisponivel: {type(error).__name__}")
        return build_knowledge_base(settings, GuardrailEngine(), embeddings)[0], settings

    @pytest.mark.parametrize(
        ("question", "section"),
        [
            ("How do I reset the router to factory settings?", "6.3 Restauração de fábrica"),
            ("The internet light is orange, what should I do?", "7.1 Sem acesso à internet"),
            ("How many devices can join the guest network?", "3.3 Rede de convidados"),
            ("Minha conexão fica caindo o tempo todo", "7.3 A conexão cai com frequência"),
            ("Como libero uma porta para o meu servidor de jogos?", "4.4 Redirecionamento de portas"),
        ],
    )
    def test_cross_lingual_and_paraphrased_questions(self, kb, question, section):
        knowledge_base, _ = kb
        assert section in [chunk.section for chunk in knowledge_base.search(question, k=4)]

    def test_out_of_scope_question_stays_below_the_relevance_gate(self, kb):
        knowledge_base, settings = kb
        in_scope = max(c.similarity for c in knowledge_base.search("Como faço a restauração de fábrica do roteador?"))
        out_scope = max(c.similarity for c in knowledge_base.search("Qual a receita de bolo de cenoura?"))
        assert out_scope < settings.min_relevance < in_scope
