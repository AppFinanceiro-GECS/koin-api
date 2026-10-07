"""Offline regression checks for fixture integrity, scoring and live opt-in."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import fitz
import httpx
import pytest
from PIL import Image

from tests.document_benchmark import (
    BenchmarkRecord,
    cents,
    compare_extraction,
    summarize_benchmark,
)
from tests.live_support import (
    BENCHMARK_RECORDS,
    BENCHMARK_SELECTED,
    BENCHMARK_SKIPPED,
    pytest_collection_modifyitems,
    pytest_runtest_makereport,
    pytest_terminal_summary,
)

FIXTURES = Path(__file__).parent / "fixtures" / "documents"
EXPECTED = {
    "document_type": "fatura_cartao",
    "total_amount": 30.30,
    "items": [
        {"description": "LOJA TESTE ALFA", "amount": 10.10},
        {"description": "LOJA TESTE BETA", "amount": 20.20},
    ],
}


def extracted():
    return {
        "document_type": "fatura_cartao",
        "card_info": {"total_amount": 30.30},
        "items": copy.deepcopy(EXPECTED["items"]),
    }


def test_comparison_accepts_reordering_spacing_and_unstable_metadata():
    actual = extracted()
    actual["items"].reverse()
    actual["items"][0].update(
        description="  loja   teste beta  ", confidence=0.01, category="other"
    )
    comparison = compare_extraction(actual, EXPECTED)
    assert comparison.passed
    assert comparison.correct_items == 2


@pytest.mark.parametrize("defect", ["missing", "extra", "duplicate", "description", "amount"])
def test_comparison_rejects_item_regressions(defect):
    actual = extracted()
    if defect == "missing":
        actual["items"].pop()
    elif defect == "extra":
        actual["items"].append({"description": "LOJA TESTE GAMA", "amount": 2})
    elif defect == "duplicate":
        actual["items"].append(copy.deepcopy(actual["items"][0]))
    elif defect == "description":
        actual["items"][0]["description"] = "LOJA ERRADA"
    else:
        actual["items"][0]["amount"] = 10.11
    comparison = compare_extraction(actual, EXPECTED)
    assert not comparison.passed
    if defect in {"missing", "description", "amount"}:
        assert len(comparison.missing_items) == 1
    if defect in {"extra", "duplicate", "description", "amount"}:
        assert len(comparison.extra_items) == 1
    if defect == "duplicate":
        assert comparison.duplicate_items == 1


@pytest.mark.parametrize("value", [30.31, 30.29, None, "NaN", True])
def test_total_is_strict_to_cents_and_cannot_be_replaced_by_item_sum(value):
    actual = extracted()
    actual["card_info"]["total_amount"] = value
    comparison = compare_extraction(actual, EXPECTED)
    assert not comparison.passed
    assert not comparison.total_correct


@pytest.mark.parametrize("container", ["root", "card_info", "payment_info"])
def test_declared_total_locations(container):
    actual = extracted()
    actual.pop("card_info")
    if container == "root":
        actual["total_amount"] = "30.30"
    elif container == "card_info":
        actual["card_info"] = {"total_amount": "30.30"}
    else:
        actual["payment_info"] = {"total": "30.30"}
    assert compare_extraction(actual, EXPECTED).passed


def test_conflicting_total_sources_fail_even_when_one_is_correct():
    actual = extracted()
    actual["total_amount"] = 30.31
    assert not compare_extraction(actual, EXPECTED).total_correct


@pytest.mark.parametrize("defect", ["date", "installment_current", "installment_total"])
def test_optional_expected_dates_and_installments_are_checked(defect):
    expected = copy.deepcopy(EXPECTED)
    expected["items"][0].update(
        date="2026-02-11",
        is_installment=True,
        installment_current=2,
        installment_total=3,
    )
    actual = extracted()
    actual["items"][0].update(expected["items"][0])
    assert compare_extraction(actual, expected).passed
    actual["items"][0][defect] = "wrong"
    assert not compare_extraction(actual, expected).passed


def test_matching_preserves_expected_multiplicity_and_optional_constraints():
    expected = copy.deepcopy(EXPECTED)
    expected["items"] = [
        {"description": "PRODUTO TESTE", "amount": 15.15},
        {"description": "PRODUTO TESTE", "amount": 15.15, "date": "2026-02-11"},
    ]
    actual = extracted()
    actual["items"] = [
        {"description": "PRODUTO TESTE", "amount": 15.15, "date": "2026-02-11"},
        {"description": "PRODUTO TESTE", "amount": 15.15, "date": "2026-02-12"},
    ]
    result = compare_extraction(actual, expected)
    assert result.passed
    assert result.duplicate_items == 0
    actual["items"].append(copy.deepcopy(actual["items"][0]))
    result = compare_extraction(actual, expected)
    assert not result.passed
    assert result.duplicate_items == 1


def test_wrong_document_type_fails():
    actual = extracted()
    actual["document_type"] = "cupom_fiscal"
    assert not compare_extraction(actual, EXPECTED).type_correct


def test_an_extra_purchase_at_same_store_is_not_a_duplicate():
    actual = extracted()
    actual["items"].append({"description": "LOJA TESTE ALFA", "amount": 4.25})
    result = compare_extraction(actual, EXPECTED)
    assert not result.passed
    assert len(result.extra_items) == 1
    assert result.duplicate_items == 0


@pytest.mark.parametrize("defect", [None, "missing", "extra", "amount", "total"])
def test_record_classifies_processed_quality(defect):
    actual = extracted()
    if defect == "missing":
        actual["items"].pop()
    elif defect == "extra":
        actual["items"].append({"description": "LOJA TESTE GAMA", "amount": 2})
    elif defect == "amount":
        actual["items"][0]["amount"] = 10.11
    elif defect == "total":
        actual["card_info"]["total_amount"] = 30.31
    record = BenchmarkRecord.from_result("a", "model-a", 1.0, actual, EXPECTED)
    assert record.status == ("pass" if defect is None else "quality_failure")
    assert record.comparison is not None
    assert record.error_type is None


def test_one_extracted_item_cannot_satisfy_two_expected_items():
    expected = copy.deepcopy(EXPECTED)
    expected["items"] = [copy.deepcopy(expected["items"][0])] * 2
    actual = extracted()
    actual["items"] = actual["items"][:1]
    comparison = compare_extraction(actual, expected)
    assert comparison.correct_items == 1
    assert len(comparison.missing_items) == 1
    assert not comparison.passed


def test_technical_exception_record_never_contains_error_details():
    exception = TimeoutError("https://secret.example/?key=PRIVATE Authorization: PRIVATE")
    record = BenchmarkRecord.from_exception("a", "model-a", 4.0, exception)
    assert record.status == "technical_error"
    assert record.comparison is None
    assert record.error_type == "TimeoutError"
    assert record.duration_seconds == 4.0
    assert "PRIVATE" not in repr(record)


def test_http_model_not_found_is_technical_without_serializing_request():
    request = httpx.Request("POST", "https://example.test/?key=PRIVATE")
    response = httpx.Response(404, request=request)
    exception = httpx.HTTPStatusError("PRIVATE", request=request, response=response)
    record = BenchmarkRecord.from_exception("a", "model-a", 1.0, exception)
    assert record.status == "technical_error"
    assert record.error_type == "HTTPStatusError"
    assert record.comparison is None
    assert "PRIVATE" not in render_summary([record])


@pytest.mark.parametrize(
    "result,error_type",
    [
        ({"error": "PRIVATE", "items": []}, "ProviderExtractionError"),
        (None, "InvalidExtractionResult"),
        ([], "InvalidExtractionResult"),
        ({"items": "PRIVATE"}, "InvalidExtractionResult"),
        ({"items": ["PRIVATE"]}, "InvalidExtractionResult"),
        ({"card_info": "PRIVATE"}, "InvalidExtractionResult"),
        ({"payment_info": []}, "InvalidExtractionResult"),
    ],
)
def test_provider_errors_and_unprocessable_results_are_technical(result, error_type):
    record = BenchmarkRecord.from_result("a", "model-a", 1.0, result, EXPECTED)
    assert record.status == "technical_error"
    assert record.comparison is None
    assert record.error_type == error_type
    assert "PRIVATE" not in repr(record)


def mixed_records():
    wrong = extracted()
    wrong["items"].pop()
    return [
        BenchmarkRecord.from_result("a", "model-a", 1.0, extracted(), EXPECTED),
        BenchmarkRecord.from_result("b", "model-a", 2.0, extracted(), EXPECTED),
        BenchmarkRecord.from_result("c", "model-a", 3.0, wrong, EXPECTED),
        BenchmarkRecord.from_exception("d", "model-a", 4.0, TimeoutError("PRIVATE")),
    ]


def render_summary(records, selected=8, skipped=0):
    lines = []
    reporter = SimpleNamespace(section=lines.append, write_line=lines.append)
    config = SimpleNamespace(
        stash={
            BENCHMARK_RECORDS: records,
            BENCHMARK_SELECTED: selected,
            BENCHMARK_SKIPPED: skipped,
        },
        getoption=lambda name: True,
    )
    pytest_terminal_summary(reporter, 1, config)
    return "\n".join(lines)


def test_technical_errors_are_excluded_from_quality_denominators():
    stats = summarize_benchmark(mixed_records())["model-a"]
    assert stats == {
        "attempted_cases": 4,
        "completed_cases": 3,
        "passed_cases": 2,
        "quality_failures": 1,
        "technical_errors": 1,
        "expected_items": 6,
        "correct_items": 5,
        "missing_items": 1,
        "extra_items": 0,
        "duplicate_items": 0,
        "correct_totals": 3,
        "completed_duration": 6.0,
        "total_attempt_duration": 10.0,
        "case_accuracy": 2 / 3,
        "mean_completed_seconds": 2.0,
    }
    output = render_summary(mixed_records(), selected=4)
    assert "attempted=4 | completed=3 | technical_errors=1" in output
    assert "case_accuracy=66.667%" in output
    assert "technical_error | N/A | N/A | N/A | N/A | N/A | 4.000 | TimeoutError" in output
    assert "PRIVATE" not in output


def test_only_technical_errors_have_no_quality_accuracy():
    records = [BenchmarkRecord.from_exception("a", "model-a", 2.0, TimeoutError("PRIVATE"))]
    stats = summarize_benchmark(records)["model-a"]
    assert stats["completed_cases"] == 0
    assert stats["case_accuracy"] is None
    assert stats["mean_completed_seconds"] is None
    assert stats["expected_items"] == stats["missing_items"] == 0
    assert stats["total_attempt_duration"] == 2.0
    assert "case_accuracy=N/A (no completed cases)" in render_summary(records)


@pytest.mark.parametrize("selected,skipped", [(4, 0), (8, 2), (8, 0)])
def test_report_detects_partial_skipped_and_interrupted_runs(selected, skipped):
    output = render_summary(mixed_records(), selected, skipped)
    assert "expected=8" in output
    assert "registered=4" in output
    assert f"skipped={skipped}" in output
    assert f"unregistered={max(0, selected - 4 - skipped)}" in output
    assert "matrix=INCOMPLETE" in output


def test_eight_attempts_report_six_completed_and_two_technical_errors():
    records = [
        BenchmarkRecord.from_result(str(i), "model-a", 1.0, extracted(), EXPECTED) for i in range(5)
    ]
    wrong = extracted()
    wrong["items"].pop()
    records.append(BenchmarkRecord.from_result("5", "model-a", 1.0, wrong, EXPECTED))
    records.extend(
        BenchmarkRecord.from_exception(str(i), "model-a", 1.0, TimeoutError()) for i in (6, 7)
    )
    stats = summarize_benchmark(records)["model-a"]
    assert stats["attempted_cases"] == 8
    assert stats["completed_cases"] == 6
    assert stats["passed_cases"] == 5
    assert stats["quality_failures"] == 1
    assert stats["technical_errors"] == 2
    assert stats["case_accuracy"] == 5 / 6
    assert stats["expected_items"] == 12
    assert stats["missing_items"] == 1
    output = render_summary(records)
    assert "attempted=8 | completed=6 | technical_errors=2" in output
    assert "matrix=complete" in output


def test_all_skipped_is_not_a_completed_benchmark():
    output = render_summary([], selected=8, skipped=8)
    assert "registered=0 | attempted=0 | completed=0 | technical_errors=0" in output
    assert "skipped=8 | unregistered=0 | matrix=INCOMPLETE" in output
    assert "Benchmark not executed" in output


def test_models_have_independent_quality_denominators():
    records = mixed_records()
    records.append(BenchmarkRecord.from_exception("a", "model-b", 2.0, TimeoutError()))
    summary = summarize_benchmark(records)
    assert summary["model-a"]["case_accuracy"] == 2 / 3
    assert summary["model-b"]["completed_cases"] == 0
    assert summary["model-b"]["case_accuracy"] is None
    assert summarize_benchmark([]) == {}


def test_comparison_exception_is_recorded_as_technical(monkeypatch):
    def broken_comparison(*args):
        raise RuntimeError("PRIVATE")

    monkeypatch.setattr("tests.document_benchmark.compare_extraction", broken_comparison)
    record = BenchmarkRecord.from_result("a", "model-a", 1.0, extracted(), EXPECTED)
    assert record.status == "technical_error"
    assert record.error_type == "RuntimeError"
    assert record.comparison is None
    assert "PRIVATE" not in repr(record)


@pytest.mark.parametrize("when", ["setup", "call", "teardown"])
def test_skip_tracking_excludes_teardown_and_never_counts_as_model_error(when):
    item = SimpleNamespace(
        get_closest_marker=lambda name: object(),
        path=Path("test_document_extraction_live.py"),
        config=SimpleNamespace(stash={}),
    )
    report = SimpleNamespace(skipped=True, when=when)
    outcome = SimpleNamespace(get_result=lambda: report)
    hook = pytest_runtest_makereport(item, None)
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(outcome)
    assert item.config.stash.get(BENCHMARK_SKIPPED, 0) == int(when != "teardown")


@pytest.mark.parametrize(
    "name,total",
    [
        ("itau_two_columns", "280.00"),
        ("nubank", "150.00"),
        ("bradesco", "160.00"),
        ("cupom_fiscal", "32.00"),
    ],
)
def test_expected_fixtures_have_explicit_consistent_totals(name, total):
    expected = json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))
    assert cents(expected["total_amount"]) == cents(total)
    assert len(expected["items"]) == 4
    assert sum(cents(item["amount"]) for item in expected["items"]) == cents(total)
    assert all("TESTE" in item["description"] for item in expected["items"])
    assert all("confidence" not in item for item in expected["items"])


@pytest.mark.parametrize(
    "name,pages,bank",
    [
        ("itau_two_columns", 2, "Banco Itau"),
        ("nubank", 1, "Nubank"),
        ("bradesco", 2, "Banco Bradesco"),
    ],
)
def test_invoice_pdfs_are_readable_synthetic_and_selectable(name, pages, bank):
    with fitz.open(FIXTURES / f"{name}.pdf") as document:
        assert len(document) == pages
        texts = [page.get_text() for page in document]
        assert all("DOCUMENTO SINTETICO" in text for text in texts)
        assert bank in texts[0]
        expected = json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))
        for item in expected["items"]:
            assert item["description"] in "\n".join(texts)


def test_itau_has_actual_side_by_side_columns_and_future_section():
    with fitz.open(FIXTURES / "itau_two_columns.pdf") as document:
        page = document[1]
        words = page.get_text("words")
        left = next(word for word in words if word[4] == "15/01" and word[0] < 100)
        right = next(word for word in words if word[4] == "23/02")
        assert left[0] < 295 < right[0]
        assert abs(left[1] - right[1]) < 1
        assert "proximas faturas" in page.get_text()
        assert "04/06" in page.get_text()


def test_receipt_is_valid_png_with_sufficient_resolution():
    with Image.open(FIXTURES / "cupom_fiscal.png") as image:
        image.verify()
    with Image.open(FIXTURES / "cupom_fiscal.png") as image:
        assert image.format == "PNG"
        assert image.size == (1100, 1100)
        assert image.getextrema()[0] == (0, 255)


@pytest.mark.parametrize("enabled", [False, True])
def test_live_collection_gate_requires_explicit_opt_in(enabled):
    marks = []
    live = SimpleNamespace(
        get_closest_marker=lambda name: object(),
        add_marker=marks.append,
        path=Path("test_document_extraction_live.py"),
    )
    normal = SimpleNamespace(get_closest_marker=lambda name: None, add_marker=marks.append)
    config = SimpleNamespace(getoption=lambda name: enabled, stash={})
    pytest_collection_modifyitems(config, [live, normal])
    assert config.stash[BENCHMARK_SELECTED] == 1
    assert len(marks) == (0 if enabled else 1)
    if marks:
        assert marks[0].name == "skip"
        assert "--run-live" in marks[0].kwargs["reason"]


@pytest.mark.parametrize("marker_selection", [[], ["-m", "live"]])
def test_live_bodies_are_skipped_without_opt_in(tmp_path, marker_selection):
    """Run a fake live body with the real plugin; never invoke --run-live or an API."""
    test_file = tmp_path / "test_gate.py"
    test_file.write_text(
        "import pytest\n@pytest.mark.live\ndef test_forbidden_body():\n"
        "    raise AssertionError('Live body must never run without opt-in')\n",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parent.parent
    environment = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--noconftest",
            "-p",
            "tests.live_support",
            "-p",
            "no:cacheprovider",
            "-c",
            str(root / "pyproject.toml"),
            "-q",
            str(test_file),
            *marker_selection,
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 skipped" in result.stdout
