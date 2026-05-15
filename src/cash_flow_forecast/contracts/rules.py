from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ColumnRule(BaseModel):
    """Filtering configuration for one business column."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    include_values: list[str] = Field(default_factory=list)
    exclude_values: list[str] = Field(default_factory=list)
    exclude_contains: list[str] = Field(default_factory=list)
    case_sensitive: bool = False

    @field_validator("include_values", "exclude_values", "exclude_contains")
    @classmethod
    def _normalize_values(cls, values: list[str]) -> list[str]:
        return [value for value in values if value is not None]


class Ruleset(BaseModel):
    """Versioned client ruleset used for Gold and dataset generation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    client: str
    description: str = ""
    filters: dict[str, ColumnRule] = Field(default_factory=dict)
    movement_scope_mapping: dict[str, str] = Field(default_factory=dict)
    target_amount_column: str = "SIGNED_AMOUNT"
    truth_date_column: str = "VALUE_DATE"
    availability_date_column: str = "TRADE_DATE"
    entity_column: str = "ENTITY_SHORTNAME"
    currency_column: str = "CURRENCY_SHORTNAME"
    movement_type_column: str = "CASH_MOVEMENT_TYPE_SHORTNAME"
    movement_scope_column: str = "MOVEMENT_SCOPE"
    aggregation_dimensions: list[str] = Field(
        default_factory=lambda: [
            "VALUE_DATE",
            "ENTITY_SHORTNAME",
            "CURRENCY_SHORTNAME",
            "MOVEMENT_SCOPE",
        ]
    )
    default_identity_movement_scope: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def ruleset_id(self) -> str:
        """Return a stable identifier for manifests and logs."""

        return f"{self.name}:{self.version}"

    @property
    def sequence_columns(self) -> list[str]:
        """Return the sequence-defining columns in their canonical order."""

        return [
            self.entity_column,
            self.currency_column,
            self.movement_scope_column,
        ]

    def resolve_movement_scope(self, movement_type: str | None) -> str | None:
        """Resolve the output movement scope for one movement type."""

        if movement_type is None:
            return None
        if movement_type in self.movement_scope_mapping:
            return self.movement_scope_mapping[movement_type]
        if self.default_identity_movement_scope:
            return movement_type
        return None
