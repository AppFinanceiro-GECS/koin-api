"""Pytest live opt-in and a small session benchmark report; no application imports."""

import pytest

from tests.document_benchmark import BenchmarkRecord, summarize_benchmark

BENCHMARK_RECORDS = pytest.StashKey[list[BenchmarkRecord]]()
BENCHMARK_SELECTED = pytest.StashKey[int]()
BENCHMARK_SKIPPED = pytest.StashKey[int]()
EXPECTED_BENCHMARK_CASES = 8


def is_benchmark_case(item):
    return (
        item.get_closest_marker("live") is not None
        and item.path.name == "test_document_extraction_live.py"
    )


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Enable tests calling external AI APIs (requires configured credentials).",
    )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    # Count after pytest's marker deselection, so partial selections remain visible.
    config.stash[BENCHMARK_SELECTED] = sum(is_benchmark_case(item) for item in items)
    if config.getoption("--run-live"):
        return
    skip = pytest.mark.skip(reason="External AI API test: explicitly opt in with --run-live.")
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skip)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    if report.skipped and report.when in {"setup", "call"} and is_benchmark_case(item):
        item.config.stash[BENCHMARK_SKIPPED] = item.config.stash.get(BENCHMARK_SKIPPED, 0) + 1


@pytest.fixture
def live_benchmark(request):
    return request.config.stash.setdefault(BENCHMARK_RECORDS, [])


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    records = config.stash.get(BENCHMARK_RECORDS, [])
    selected = config.stash.get(BENCHMARK_SELECTED, 0)
    skipped = config.stash.get(BENCHMARK_SKIPPED, 0)
    if not records and not (selected and config.getoption("--run-live")):
        return
    terminalreporter.section("Gemini extraction benchmark (no model decision)")
    attempted = len(records)
    technical = sum(record.status == "technical_error" for record in records)
    completed = attempted - technical
    unique_cases = len({(record.fixture, record.model) for record in records})
    unregistered = max(0, selected - attempted - skipped)
    complete = unique_cases == EXPECTED_BENCHMARK_CASES and not skipped and not unregistered
    terminalreporter.write_line(
        f"expected={EXPECTED_BENCHMARK_CASES} | selected={selected} | registered={attempted} | "
        f"attempted={attempted} | completed={completed} | technical_errors={technical} | "
        f"skipped={skipped} | unregistered={unregistered} | "
        f"matrix={'complete' if complete else 'INCOMPLETE'}"
    )
    if not records:
        terminalreporter.write_line("Benchmark not executed; no quality accuracy is calculable.")
        return
    terminalreporter.write_line(
        "fixture | model | status | correct/expected | missing | extra | duplicate | total | seconds | error_type"
    )
    for record in sorted(records, key=lambda row: (row.model, row.fixture)):
        result = record.comparison
        metrics = "N/A | N/A | N/A | N/A | N/A"
        if result is not None:
            metrics = (
                f"{result.correct_items}/{result.expected_items} | {len(result.missing_items)} | "
                f"{len(result.extra_items)} | {result.duplicate_items} | {int(result.total_correct)}"
            )
        terminalreporter.write_line(
            f"{record.fixture} | {record.model} | {record.status} | {metrics} | "
            f"{record.duration_seconds:.3f} | {record.error_type or '-'}"
        )
    for model, stats in summarize_benchmark(records).items():
        accuracy = (
            "N/A (no completed cases)"
            if stats["case_accuracy"] is None
            else f"{stats['case_accuracy']:.3%}"
        )
        mean = (
            "N/A"
            if stats["mean_completed_seconds"] is None
            else f"{stats['mean_completed_seconds']:.3f}"
        )
        terminalreporter.write_line(
            f"{model}: attempted_cases={stats['attempted_cases']}, "
            f"completed_cases={stats['completed_cases']}, passed_cases={stats['passed_cases']}, "
            f"quality_failures={stats['quality_failures']}, technical_errors={stats['technical_errors']}, "
            f"case_accuracy={accuracy}, "
            f"expected_items={stats['expected_items']}, correct_items={stats['correct_items']}, "
            f"missing_items={stats['missing_items']}, extra_items={stats['extra_items']}, "
            f"duplicate_items={stats['duplicate_items']}, "
            f"correct_totals={stats['correct_totals']}, "
            f"completed_seconds={stats['completed_duration']:.3f}, "
            f"total_attempt_seconds={stats['total_attempt_duration']:.3f}, "
            f"mean_completed_seconds={mean}"
        )
