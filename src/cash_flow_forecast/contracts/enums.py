from __future__ import annotations
from enum import Enum


class DataType(str, Enum):
    """Supported normalized data types for Silver parsing."""

    STRING = "string"
    FLOAT = "float"
    INTEGER = "int"
    DATE = "date"
    CATEGORY = "category"


class DatasetKind(str, Enum):
    """Supported dataset families."""

    TIME_SERIES = "time_series"
    TABULAR = "tabular"
