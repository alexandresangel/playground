from __future__ import annotations
from typing import Iterable
from pydantic import BaseModel, ConfigDict, Field

from cash_flow_forecast.contracts.enums import DataType


class ColumnSchema(BaseModel):
    """Typed definition for one normalized column."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    dtype: DataType
    required: bool = False


class TableSchema(BaseModel):
    """Typed schema for the raw cash movement extract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = "cash_movements"
    columns: list[ColumnSchema] = Field(default_factory=list)

    @property
    def column_names(self) -> list[str]:
        """Return every expected column name in load order."""

        return [column.name for column in self.columns]

    @property
    def required_columns(self) -> list[str]:
        """Return columns that must be present in the incoming table."""

        return [column.name for column in self.columns if column.required]

    def dtype_for(self, column_name: str) -> DataType:
        """Return the normalized data type for a given column."""

        for column in self.columns:
            if column.name == column_name:
                return column.dtype
        raise KeyError(f"Column {column_name!r} is not defined in schema {self.name!r}.")

    def validate_columns(self, columns: Iterable[str]) -> None:
        """Ensure the required columns exist in an incoming dataframe."""

        available = set(columns)
        missing = [column for column in self.required_columns if column not in available]
        if missing:
            raise KeyError(
                f"Missing required columns for schema {self.name!r}: {', '.join(missing)}"
            )
