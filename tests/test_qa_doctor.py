"""Unit tests for tools/store_ext.py:preview_import_counts and
tools/doctor.py:check_imports / check_properties - the real row-count and
group-name checks `make doctor` runs. See docs/how-it-works.md and
README.md "Connect your systems"."""

from __future__ import annotations

import doctor
import store_ext
from core.doctor import FAIL, PASS, WARN


def test_preview_import_counts_reads_real_rows(tmp_path):
    imports_dir = tmp_path / "imports"
    imports_dir.mkdir()
    (imports_dir / "room_status.csv").write_text(
        "property_id,room,status,ready_time\n"
        "aurora-city,101,clean,14:00\n"
        "aurora-city,102,dirty,\n", encoding="utf-8")
    counts = store_ext.preview_import_counts(imports_dir)
    assert counts["room_status.csv"] == 2
    assert counts["journey_touchpoints.csv"] == 0   # missing file counts as 0
    assert set(counts) == set(store_ext.IMPORT_FILES)


def test_preview_import_counts_matches_what_import_signals_csv_loads(tmp_path):
    """The same reader, so the doctor count is never a guess - see
    store_ext.import_signals_csv's own docstring."""
    from core.config import load_settings
    from core.store import Store

    imports_dir = tmp_path / "imports"
    imports_dir.mkdir()
    (imports_dir / "reviews.csv").write_text(
        "property_id,rating,category,text,date\n"
        "aurora-city,4,room,good,2026-08-01\n"
        "aurora-city,2,fnb,bad,2026-08-02\n", encoding="utf-8")

    preview = store_ext.preview_import_counts(imports_dir)

    settings = load_settings(demo=True)
    store = Store(settings, path=tmp_path / "t.db")
    store_ext.migrate(store)
    imported = store_ext.import_signals_csv(store, imports_dir)
    assert preview["reviews.csv"] == imported["qa_reviews"] == 2


def test_check_imports_reports_row_counts_in_the_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path)
    imports_dir = tmp_path / "data" / "imports"
    imports_dir.mkdir(parents=True)
    for name in store_ext.IMPORT_FILES:
        (imports_dir / name).write_text("property_id\naurora-city\n", encoding="utf-8")
    check = doctor.check_imports(settings=None)
    assert check.status == PASS
    assert "room_status.csv=1 row" in check.detail


def test_check_imports_warns_on_an_empty_file(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path)
    imports_dir = tmp_path / "data" / "imports"
    imports_dir.mkdir(parents=True)
    for name in store_ext.IMPORT_FILES:
        (imports_dir / name).write_text(
            "property_id\naurora-city\n" if name != "reviews.csv" else "", encoding="utf-8")
    check = doctor.check_imports(settings=None)
    assert check.status == WARN
    assert "reviews.csv" in check.detail


def test_check_imports_warns_when_nothing_is_there(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path)
    (tmp_path / "data" / "imports").mkdir(parents=True)
    check = doctor.check_imports(settings=None)
    assert check.status == WARN
    assert "no CSVs" in check.detail


def test_check_properties_warns_when_group_name_is_missing(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    settings.agent.pop("group_name", None)
    check = doctor.check_properties(settings)
    assert check.status == WARN
    assert "group_name" in check.detail


def test_check_properties_passes_with_group_name_set(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    settings.agent["group_name"] = "Test Group"
    check = doctor.check_properties(settings)
    assert check.status == PASS
    assert "Test Group" in check.detail
