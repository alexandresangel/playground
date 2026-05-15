from __future__ import annotations
from decimal import Decimal


PREDICTION_LOWER_PREFIX = "PREDICTION_LOWER_"
PREDICTION_UPPER_PREFIX = "PREDICTION_UPPER_"


def coverage_label(coverage: float) -> str:
    """Return a stable percentage-style interval column suffix."""

    percentage = Decimal(str(float(coverage))) * Decimal("100")
    label = format(percentage.normalize(), "f")
    if "." in label:
        label = label.rstrip("0").rstrip(".")
    return label.replace("-", "minus").replace(".", "_")


def interval_lower_column(coverage: float) -> str:
    return f"{PREDICTION_LOWER_PREFIX}{coverage_label(coverage)}"


def interval_upper_column(coverage: float) -> str:
    return f"{PREDICTION_UPPER_PREFIX}{coverage_label(coverage)}"


def interval_columns(coverages: list[float]) -> list[str]:
    columns: list[str] = []
    for coverage in coverages:
        columns.extend([interval_lower_column(coverage), interval_upper_column(coverage)])
    return columns
