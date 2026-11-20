"""Limpeza de texto, ingestao e particoes."""

from __future__ import annotations

import hashlib

import pandas as pd
import pytest

from supportcopilot.data import ingest
from supportcopilot.data.text import clean_text, compose_ticket, dedup_key, truncate
from tests.conftest import build_settings, make_tickets


class TestCleanText:
    def test_unescapes_newlines_and_breaks(self):
        assert clean_text("Dear team,\\n\\nMy router<br>is down", unescape=True) == "Dear team,\nMy router\nis down"

    def test_backslashes_from_users_are_kept_by_default(self):
        path = "C:\\network\\temp\\new.txt"
        assert clean_text(f"Erro em {path}") == f"Erro em {path}"
        assert compose_ticket(None, "linha 1\\nlinha 2") == "linha 1\nlinha 2"

    def test_removes_invisible_characters(self):
        assert clean_text("ro\u200bte\u202eador\x00") == "roteador"

    def test_collapses_spaces_and_blank_lines(self):
        assert clean_text("  a   b \n\n\n  c  ") == "a b\nc"

    def test_normalizes_unicode_compatibility_forms(self):
        assert clean_text("ｗｉｆｉ ①") == "wifi 1"

    def test_only_whitespace_becomes_empty(self):
        assert clean_text(" \n\t ") == ""


class TestCompose:
    def test_joins_subject_and_body(self):
        assert compose_ticket("Wi-Fi", "Not working") == "Wi-Fi\nNot working"

    @pytest.mark.parametrize(("subject", "body", "expected"), [(None, "body", "body"), ("subject", None, "subject")])
    def test_handles_missing_parts(self, subject, body, expected):
        assert compose_ticket(subject, body) == expected


class TestTruncate:
    def test_short_text_is_untouched(self):
        assert truncate("abc", 10) == "abc"

    def test_cuts_at_word_boundary(self):
        result = truncate("palavra " * 200, 1000)
        assert len(result) <= 1000
        assert result.endswith("palavra")

    def test_single_long_token_is_hard_cut(self):
        assert truncate("x" * 50, 10) == "x" * 10


def test_dedup_key_ignores_case_and_punctuation():
    assert dedup_key("Hello,  World!") == dedup_key("hello world")


class TestCleanTickets:
    def test_drops_empty_and_duplicates_and_truncates(self):
        raw = pd.DataFrame(
            {
                "subject": [None, None, None, None],
                "body": ["Router down", "router  DOWN!", "   ", "word " * 400],
                "queue": ["A", "A", "B", "B"],
                "language": ["en", "en", "en", "EN"],
            }
        )
        frame, stats = ingest.clean_tickets(raw, max_chars=1000)
        assert stats == {"dropped_empty": 1, "dropped_duplicates": 1, "truncated": 1}
        assert len(frame) == 2
        assert frame[ingest.TEXT].str.len().max() <= 1000
        assert set(frame[ingest.LANGUAGE]) == {"en"}


class TestNearDuplicates:
    def test_paraphrases_share_a_group(self):
        texts = pd.Series(
            [
                "The router keeps dropping the wireless connection every few minutes since yesterday",
                "The router keeps dropping the wireless connection every few minutes since last night",
                "I was charged twice on my last invoice and need a refund for the duplicate payment",
            ]
        )
        groups = ingest.near_duplicate_groups(texts, threshold=0.6)
        assert groups[0] == groups[1]
        assert groups[2] != groups[0]

    def test_single_row(self):
        assert list(ingest.near_duplicate_groups(pd.Series(["only one"]))) == [0]


class TestPrepare:
    def test_partitions_do_not_share_groups_or_languages(self, tmp_path):
        settings = build_settings(tmp_path)
        partitions, stats = ingest.prepare(make_tickets(), settings)
        assert set(partitions) == {"train", "validation", "test", "production", "drift_pool"}
        reference = ["train", "validation", "test", "production"]
        seen: set[int] = set()
        for name in reference:
            groups = set(partitions[name][ingest.GROUP])
            assert not groups & seen, f"grupo de parafrases vazou para {name}"
            seen |= groups
            assert set(partitions[name][ingest.LANGUAGE]) == {"en"}
        assert set(partitions["drift_pool"][ingest.LANGUAGE]) == {"de"}
        assert sum(len(partitions[name]) for name in reference) == stats["reference_rows"]
        assert len(partitions["train"]) > len(partitions["test"])

    def test_requires_reference_language(self, tmp_path):
        settings = build_settings(tmp_path, reference_language="pt")
        with pytest.raises(ValueError, match="idioma de referencia"):
            ingest.prepare(make_tickets(per_queue=12), settings)


class TestDownloadAndRun:
    def _write_raw(self, settings) -> str:
        settings.raw_dir.mkdir(parents=True)
        path = settings.raw_dir / settings.dataset_file
        make_tickets().to_csv(path, index=False)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_run_writes_partitions_and_summary(self, tmp_path):
        settings = build_settings(tmp_path)
        digest = self._write_raw(settings)
        settings = build_settings(tmp_path, dataset_sha256=digest)
        summary = ingest.run(settings)
        assert summary.sha256 == digest
        assert summary.train_rows + summary.validation_rows + summary.test_rows + summary.production_rows > 0
        assert (settings.processed_dir / "ingest_summary.json").exists()
        assert len(ingest.load_partition(settings, "train")) == summary.train_rows

    def test_tampered_file_is_rejected(self, tmp_path):
        settings = build_settings(tmp_path, dataset_sha256="0" * 64)
        self._write_raw(settings)
        with pytest.raises(ingest.DatasetIntegrityError):
            ingest.download_dataset(settings)

    def test_non_https_url_is_rejected(self, tmp_path, monkeypatch):
        settings = build_settings(tmp_path)
        monkeypatch.setattr(type(settings), "dataset_url", property(lambda self: "http://example.org/data.csv"))
        with pytest.raises(ValueError, match="https"):
            ingest.download_dataset(settings)

    def test_missing_partition_gives_actionable_error(self, tmp_path):
        with pytest.raises(FileNotFoundError, match=r"pipelines\.ingest"):
            ingest.load_partition(build_settings(tmp_path), "train")
