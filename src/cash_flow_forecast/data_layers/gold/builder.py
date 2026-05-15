from __future__ import annotations
import re
import pandas as pd

from cash_flow_forecast.contracts.builders import BuildManifest, GoldBuildRequest, GoldBuildResult
from cash_flow_forecast.contracts.rules import ColumnRule, Ruleset


TARGET_AMOUNT_COLUMN = "TARGET_AMOUNT"
KNOWN_AMOUNT_COLUMN = "KNOWN_AMOUNT"
KNOWN_COUNT_COLUMN = "KNOWN_COUNT"
OBSERVATION_COUNT_COLUMN = "OBSERVATION_COUNT"
SEQUENCE_ID_COLUMN = "SEQUENCE_ID"
DATE_COLUMN = "DATE"


def _combine_silver_tables(silver_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Concatenate entity Silver tables into one normalized dataframe."""

    if not silver_tables:
        return pd.DataFrame()
    return pd.concat(silver_tables.values(), ignore_index=True, sort=False)


def _normalize_for_filtering(series: pd.Series, case_sensitive: bool) -> pd.Series:
    text = series.astype("string")
    return text if case_sensitive else text.str.lower()


def apply_column_rule(df: pd.DataFrame, column_name: str, rule: ColumnRule) -> pd.DataFrame:
    """Apply one include/exclude rule to a dataframe."""

    filtered = df.copy()
    normalized = _normalize_for_filtering(filtered[column_name], rule.case_sensitive)

    if rule.include_values:
        include_values = {
            value if rule.case_sensitive else value.lower()
            for value in rule.include_values
        }
        filtered = filtered[normalized.isin(include_values)]
        normalized = _normalize_for_filtering(filtered[column_name], rule.case_sensitive)

    if rule.exclude_values:
        exclude_values = {
            value if rule.case_sensitive else value.lower()
            for value in rule.exclude_values
        }
        filtered = filtered[~normalized.isin(exclude_values)]
        normalized = _normalize_for_filtering(filtered[column_name], rule.case_sensitive)

    if rule.exclude_contains:
        contains_values = [
            value if rule.case_sensitive else value.lower()
            for value in rule.exclude_contains
        ]
        pattern = "|".join(re.escape(value) for value in contains_values)
        contains_mask = normalized.fillna("").str.contains(pattern, regex=True, na=False)
        filtered = filtered[~contains_mask]

    return filtered


def apply_ruleset_filters(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    """Apply every client business filter declared in the ruleset."""

    filtered = df.copy()
    for column_name, rule in ruleset.filters.items():
        if column_name not in filtered.columns:
            continue
        filtered = apply_column_rule(filtered, column_name, rule)
    return filtered.reset_index(drop=True)


def add_movement_scope(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    """Resolve the Gold movement scope for every row."""

    scoped = df.copy()
    scoped[ruleset.movement_scope_column] = scoped[ruleset.movement_type_column].astype("string").map(
        ruleset.resolve_movement_scope
    )
    scoped = scoped[scoped[ruleset.movement_scope_column].notna()].reset_index(drop=True)
    return scoped


def add_sequence_identifier(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    """Add a stable sequence identifier across outputs."""

    identified = df.copy()
    identified[SEQUENCE_ID_COLUMN] = (
        identified[ruleset.entity_column].astype("string")
        + "|"
        + identified[ruleset.currency_column].astype("string")
        + "|"
        + identified[ruleset.movement_scope_column].astype("string")
    )
    return identified


class GoldRealizedBuilder:
    """Build realized cash-in labels at the target grain."""

    def __init__(self, ruleset: Ruleset):
        self.ruleset = ruleset

    def build(self, filtered_table: pd.DataFrame) -> pd.DataFrame:
        """Aggregate realized values by VALUE_DATE and sequence."""

        if filtered_table.empty:
            columns = self.ruleset.aggregation_dimensions + [
                TARGET_AMOUNT_COLUMN,
                OBSERVATION_COUNT_COLUMN,
                SEQUENCE_ID_COLUMN,
            ]
            return pd.DataFrame(columns=columns)

        realized = filtered_table.copy()
        target_amount = realized[self.ruleset.target_amount_column].fillna(
            realized["AMOUNT"] * realized["SIGN"].astype("Float64")
        )
        realized = realized.assign(_target_amount=target_amount)
        aggregated = (
            realized.groupby(
                self.ruleset.aggregation_dimensions,
                dropna=False,
                observed=True,
            )
            .agg(
                TARGET_AMOUNT=("_target_amount", "sum"),
                OBSERVATION_COUNT=("ID", "count"),
            )
            .reset_index()
        )
        return add_sequence_identifier(aggregated, self.ruleset)


class GoldFeatureSourceBuilder:
    """Build reusable availability-aware feature sources."""

    def __init__(self, ruleset: Ruleset):
        self.ruleset = ruleset

    def build(self, filtered_table: pd.DataFrame) -> pd.DataFrame:
        """Aggregate known movements by trade date and value date."""

        if filtered_table.empty:
            columns = [
                self.ruleset.availability_date_column,
                self.ruleset.truth_date_column,
                self.ruleset.entity_column,
                self.ruleset.currency_column,
                self.ruleset.movement_scope_column,
                KNOWN_AMOUNT_COLUMN,
                KNOWN_COUNT_COLUMN,
                SEQUENCE_ID_COLUMN,
            ]
            return pd.DataFrame(columns=columns)

        feature_source = filtered_table.copy()
        known_amount = feature_source[self.ruleset.target_amount_column].fillna(
            feature_source["AMOUNT"] * feature_source["SIGN"].astype("Float64")
        )
        feature_source = feature_source.assign(_known_amount=known_amount)
        aggregated = (
            feature_source.groupby(
                [
                    self.ruleset.availability_date_column,
                    self.ruleset.truth_date_column,
                    self.ruleset.entity_column,
                    self.ruleset.currency_column,
                    self.ruleset.movement_scope_column,
                ],
                dropna=False,
                observed=True,
            )
            .agg(
                KNOWN_AMOUNT=("_known_amount", "sum"),
                KNOWN_COUNT=("ID", "count"),
            )
            .reset_index()
        )
        return add_sequence_identifier(aggregated, self.ruleset)


class ReferenceBuilder:
    """Build shared Gold reference tables."""

    def __init__(self, ruleset: Ruleset):
        self.ruleset = ruleset

    def build_sequence_reference(
        self,
        realized_cash_in: pd.DataFrame,
        known_movements_daily: pd.DataFrame,
    ) -> pd.DataFrame:
        """Build the distinct list of sequences used downstream."""

        frames = [frame for frame in [realized_cash_in, known_movements_daily] if not frame.empty]
        if not frames:
            columns = self.ruleset.sequence_columns + [SEQUENCE_ID_COLUMN]
            return pd.DataFrame(columns=columns)

        combined = pd.concat(frames, ignore_index=True, sort=False)
        return (
            combined[self.ruleset.sequence_columns + [SEQUENCE_ID_COLUMN]]
            .drop_duplicates()
            .sort_values(self.ruleset.sequence_columns)
            .reset_index(drop=True)
        )

    def build_calendar_daily(self, filtered_table: pd.DataFrame) -> pd.DataFrame:
        """Build a dense daily calendar covering the Gold data horizon."""

        if filtered_table.empty:
            columns = [
                DATE_COLUMN,
                "DAY_OF_WEEK",
                "DAY_OF_MONTH",
                "IS_MONTH_END",
                "IS_MONTH_START",
                "IS_WEEKEND",
            ]
            return pd.DataFrame(columns=columns)

        min_date = min(
            filtered_table[self.ruleset.truth_date_column].min(),
            filtered_table[self.ruleset.availability_date_column].min(),
        )
        max_date = max(
            filtered_table[self.ruleset.truth_date_column].max(),
            filtered_table[self.ruleset.availability_date_column].max(),
        )
        calendar = pd.DataFrame({DATE_COLUMN: pd.date_range(min_date, max_date, freq="D")})
        calendar["DAY_OF_WEEK"] = calendar[DATE_COLUMN].dt.dayofweek
        calendar["DAY_OF_MONTH"] = calendar[DATE_COLUMN].dt.day
        calendar["IS_MONTH_END"] = calendar[DATE_COLUMN].dt.is_month_end
        calendar["IS_MONTH_START"] = calendar[DATE_COLUMN].dt.is_month_start
        calendar["IS_WEEKEND"] = calendar["DAY_OF_WEEK"] >= 5
        return calendar


class GoldBuilder:
    """Orchestrate Gold outputs from Silver tables and a ruleset."""

    def __init__(self, ruleset: Ruleset):
        self.ruleset = ruleset
        self.realized_builder = GoldRealizedBuilder(ruleset)
        self.feature_builder = GoldFeatureSourceBuilder(ruleset)
        self.reference_builder = ReferenceBuilder(ruleset)

    def build(self, request: GoldBuildRequest) -> GoldBuildResult:
        """Build Gold outputs from reusable Silver entity tables."""

        silver_table = _combine_silver_tables(request.silver_tables)
        if silver_table.empty:
            realized_cash_in = self.realized_builder.build(silver_table)
            known_movements_daily = self.feature_builder.build(silver_table)
            sequence_reference = self.reference_builder.build_sequence_reference(
                realized_cash_in,
                known_movements_daily,
            )
            calendar_daily = self.reference_builder.build_calendar_daily(silver_table)
        else:
            filtered = apply_ruleset_filters(silver_table, self.ruleset)
            filtered = add_movement_scope(filtered, self.ruleset)
            filtered = add_sequence_identifier(filtered, self.ruleset)
            realized_cash_in = self.realized_builder.build(filtered)
            known_movements_daily = self.feature_builder.build(filtered)
            sequence_reference = self.reference_builder.build_sequence_reference(
                realized_cash_in,
                known_movements_daily,
            )
            calendar_daily = self.reference_builder.build_calendar_daily(filtered)

        manifest = BuildManifest(
            layer="gold",
            row_count=(
                len(realized_cash_in)
                + len(known_movements_daily)
                + len(sequence_reference)
                + len(calendar_daily)
            ),
            table_names=[
                "realized_cash_in",
                "known_movements_daily",
                "sequence_reference",
                "calendar_daily",
            ],
            metadata={"ruleset_id": self.ruleset.ruleset_id},
        )
        return GoldBuildResult(
            realized_cash_in=realized_cash_in,
            known_movements_daily=known_movements_daily,
            sequence_reference=sequence_reference,
            calendar_daily=calendar_daily,
            manifest=manifest,
        )
