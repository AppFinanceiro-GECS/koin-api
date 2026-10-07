"""Strict, order-independent comparison of normalized extraction results (tests only)."""

import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal


class ProviderExtractionError(ValueError):
    """The service returned an error instead of an evaluable extraction."""


class InvalidExtractionResult(ValueError):
    """The extraction has no processable result structure."""


def cents(value) -> Decimal:
    """Compare monetary values in BRL cents, rejecting missing/non-finite amounts."""
    if value is None or isinstance(value, bool):
        raise ValueError("Missing or invalid monetary amount")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise ValueError("Non-finite monetary amount")
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Invalid monetary amount") from exc


def description(value) -> str:
    """Ignore capitalization/spacing, preserving accents, words and punctuation."""
    return " ".join(unicodedata.normalize("NFC", str(value or "")).casefold().split())


def item_matches(actual: dict, expected: dict) -> bool:
    try:
        if description(actual.get("description")) != description(expected["description"]):
            return False
        if cents(actual.get("amount")) != cents(expected["amount"]):
            return False
    except ValueError:
        return False
    return all(
        actual.get(field) == value
        for field, value in expected.items()
        if field not in {"description", "amount"}
    )


@dataclass
class Comparison:
    expected_items: int
    correct_items: int
    missing_items: list[dict]
    extra_items: list[dict]
    duplicate_items: int
    type_correct: bool
    total_correct: bool
    issues: list[str]

    @property
    def passed(self) -> bool:
        return not self.issues

    def failure_message(self) -> str:
        return "\n".join(self.issues)


def compare_extraction(actual: dict, expected: dict) -> Comparison:
    """Match a multiset of items and compare every supplied declared total.

    Wrong descriptions/values count as a missing expected item plus an extra item.
    Maximum matching also handles repeated items and optional expected fields.
    Never substitute the extracted item sum for a missing declared total.
    """
    if not isinstance(actual, dict):
        raise InvalidExtractionResult
    if actual.get("error"):
        raise ProviderExtractionError
    if actual.get("items") is not None and (
        not isinstance(actual["items"], list)
        or any(not isinstance(item, dict) for item in actual["items"])
    ):
        raise InvalidExtractionResult
    for container in ("card_info", "payment_info"):
        if actual.get(container) is not None and not isinstance(actual[container], dict):
            raise InvalidExtractionResult

    expected_items = expected["items"]
    actual_items = actual.get("items") or []
    issues = []

    assigned = {}

    def assign(expected_index, visited):
        for actual_index, actual_item in enumerate(actual_items):
            if actual_index in visited or not item_matches(
                actual_item, expected_items[expected_index]
            ):
                continue
            visited.add(actual_index)
            previous = assigned.get(actual_index)
            if previous is None or assign(previous, visited):
                assigned[actual_index] = expected_index
                return True
        return False

    for expected_index in range(len(expected_items)):
        assign(expected_index, set())
    matched_expected = set(assigned.values())
    missing = [item for index, item in enumerate(expected_items) if index not in matched_expected]
    extra = [item for index, item in enumerate(actual_items) if index not in assigned]

    def identities(items):
        counts = Counter()
        for item in items:
            try:
                counts[(description(item.get("description")), cents(item.get("amount")))] += 1
            except ValueError:
                continue
        return counts

    expected_identities = identities(expected_items)
    actual_identities = identities(actual_items)
    duplicates = sum(
        max(0, count - max(1, expected_identities[identity]))
        for identity, count in actual_identities.items()
    )
    if missing:
        issues.append(f"Missing or incorrect expected items: {missing!r}")
    if extra:
        # Keep diagnostics focused on fields under test, never dump a whole AI response.
        projected = [
            {key: item.get(key) for key in ("description", "amount", "date")} for item in extra
        ]
        issues.append(f"Extra or incorrect extracted items: {projected!r}")
    if duplicates:
        issues.append(f"Duplicated extracted items: {duplicates}")

    type_correct = actual.get("document_type") == expected["document_type"]
    if not type_correct:
        issues.append("Document type differs from expected.")

    totals = {}
    if actual.get("total_amount") is not None:
        totals["total_amount"] = actual["total_amount"]
    for container, field in (("card_info", "total_amount"), ("payment_info", "total")):
        data = actual.get(container) or {}
        if data.get(field) is not None:
            totals[f"{container}.{field}"] = data[field]
    total_correct = bool(totals)
    expected_total = cents(expected["total_amount"])
    if not totals:
        issues.append("Missing declared total; the item sum is not a substitute.")
    for source, value in totals.items():
        try:
            correct = cents(value) == expected_total
        except ValueError:
            correct = False
        if not correct:
            total_correct = False
            issues.append(f"Incorrect total at {source}; expected BRL {expected_total}.")

    return Comparison(
        len(expected_items),
        len(assigned),
        missing,
        extra,
        duplicates,
        type_correct,
        total_correct,
        issues,
    )


@dataclass
class BenchmarkRecord:
    fixture: str
    model: str
    status: Literal["pass", "quality_failure", "technical_error"]
    duration_seconds: float
    comparison: Comparison | None = None
    error_type: str | None = None

    @classmethod
    def from_exception(cls, fixture, model, duration_seconds, exception):
        # Never retain exception text, URLs, headers, provider responses or credentials.
        return cls(
            fixture,
            model,
            "technical_error",
            duration_seconds,
            error_type=type(exception).__name__,
        )

    @classmethod
    def from_result(cls, fixture, model, duration_seconds, result, expected):
        try:
            comparison = compare_extraction(result, expected)
        except Exception as exception:
            return cls.from_exception(fixture, model, duration_seconds, exception)
        status = "pass" if comparison.passed else "quality_failure"
        return cls(fixture, model, status, duration_seconds, comparison=comparison)


def summarize_benchmark(records: list[BenchmarkRecord]) -> dict[str, dict]:
    """Keep technical availability separate from quality of completed extractions."""
    summary = {}
    for record in records:
        model = record.model
        stats = summary.setdefault(
            model,
            {
                "attempted_cases": 0,
                "completed_cases": 0,
                "passed_cases": 0,
                "quality_failures": 0,
                "technical_errors": 0,
                "expected_items": 0,
                "correct_items": 0,
                "missing_items": 0,
                "extra_items": 0,
                "duplicate_items": 0,
                "correct_totals": 0,
                "completed_duration": 0.0,
                "total_attempt_duration": 0.0,
            },
        )
        stats["attempted_cases"] += 1
        stats["total_attempt_duration"] += record.duration_seconds
        if record.status == "technical_error":
            stats["technical_errors"] += 1
            continue
        comparison = record.comparison
        assert comparison is not None
        stats["completed_cases"] += 1
        stats["passed_cases"] += int(record.status == "pass")
        stats["quality_failures"] += int(record.status == "quality_failure")
        stats["expected_items"] += comparison.expected_items
        stats["correct_items"] += comparison.correct_items
        stats["missing_items"] += len(comparison.missing_items)
        stats["extra_items"] += len(comparison.extra_items)
        stats["duplicate_items"] += comparison.duplicate_items
        stats["correct_totals"] += int(comparison.total_correct)
        stats["completed_duration"] += record.duration_seconds
    for stats in summary.values():
        completed = stats["completed_cases"]
        stats["case_accuracy"] = stats["passed_cases"] / completed if completed else None
        stats["mean_completed_seconds"] = (
            stats["completed_duration"] / completed if completed else None
        )
    return dict(sorted(summary.items()))
