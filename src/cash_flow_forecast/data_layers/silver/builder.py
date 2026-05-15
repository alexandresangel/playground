from __future__ import annotations
from collections import defaultdict
import pandas as pd

from cash_flow_forecast.contracts.builders import (
    BronzeTablePayload,
    BuildManifest,
    ColumnIssueSummary,
    SilverBuildRequest,
    SilverBuildResult,
    TableBuildReport,
)
from cash_flow_forecast.contracts.enums import DataType
from cash_flow_forecast.contracts.schema import TableSchema
from cash_flow_forecast.data_layers.silver.transforms import (
    clean_text,
    normalize_columns,
    to_date,
    to_float,
    to_int,
)


LINEAGE_SOURCE_COLUMN = "_lineage_source_name"
LINEAGE_ROW_COLUMN = "_lineage_source_row_number"
MISSING_REQUIRED_FLAG = "_quality_missing_required_fields"
DUPLICATE_ID_FLAG = "_quality_duplicate_id"
REVERSED_DATES_FLAG = "_anomaly_value_date_before_trade_date"
SIGNED_AMOUNT_MISMATCH_FLAG = "_anomaly_signed_amount_mismatch"


class SilverBuilder:
    """Build reusable Silver tables without business-specific target logic."""

    def __init__(self, schema: TableSchema):
        self.schema = schema

    def build(self, request: SilverBuildRequest) -> SilverBuildResult:
        """Build one normalized Silver table per entity across bronze inputs."""

        if request.table_schema != self.schema:
            raise ValueError("Silver build request schema does not match the builder schema.")

        processed_frames: list[pd.DataFrame] = []
        source_reports: list[TableBuildReport] = []

        for payload in request.bronze_tables:
            processed_frame, report = self.process_unique_table(payload)
            processed_frames.append(processed_frame)
            source_reports.append(report)

        if processed_frames:
            combined = pd.concat(processed_frames, ignore_index=True, sort=False)
        else:
            combined = pd.DataFrame(columns=self.schema.column_names)

        entity_tables: dict[str, pd.DataFrame] = {}
        entity_reports: dict[str, TableBuildReport] = {}

        if not combined.empty:
            combined = self._flag_duplicate_ids(combined)
            for entity_name, entity_frame in combined.groupby(
                "ENTITY_SHORTNAME",
                dropna=False,
                observed=False,
            ):
                entity_key = entity_name if pd.notna(entity_name) else "UNKNOWN"
                entity_table = entity_frame.sort_values(
                    ["TRADE_DATE", "VALUE_DATE", "ID"],
                    na_position="last",
                ).reset_index(drop=True)
                issue_counts = {
                    "missing_required_rows": int(entity_table[MISSING_REQUIRED_FLAG].sum()),
                    "duplicate_id_rows": int(entity_table[DUPLICATE_ID_FLAG].sum()),
                    "value_before_trade_rows": int(entity_table[REVERSED_DATES_FLAG].sum()),
                    "signed_amount_mismatch_rows": int(
                        entity_table[SIGNED_AMOUNT_MISMATCH_FLAG].sum()
                    ),
                }
                entity_reports[entity_key] = TableBuildReport(
                    table_name=f"silver_entity_{entity_key}",
                    row_count=len(entity_table),
                    issue_counts=issue_counts,
                )
                entity_tables[entity_key] = entity_table

        manifest = BuildManifest(
            layer="silver",
            row_count=sum(len(table) for table in entity_tables.values()),
            table_names=sorted(entity_tables.keys()),
            metadata={
                "source_reports": [report.model_dump() for report in source_reports],
                "entity_count": len(entity_tables),
            },
        )
        return SilverBuildResult(
            entity_tables=entity_tables,
            entity_reports=entity_reports,
            manifest=manifest,
        )

    def process_unique_table(
        self,
        payload: BronzeTablePayload,
    ) -> tuple[pd.DataFrame, TableBuildReport]:
        """Normalize and validate one raw bronze dataframe."""

        raw = normalize_columns(payload.dataframe)
        raw = raw.copy()
        raw[LINEAGE_SOURCE_COLUMN] = payload.source_name
        raw[LINEAGE_ROW_COLUMN] = range(1, len(raw) + 1)

        parsed, column_issues = self.parse_table(raw)
        checked = self.check_quality_table(parsed)
        checked = self.check_anomaly_table(checked)

        issue_counts = defaultdict(int)
        issue_counts["parse_issues"] = sum(issue.issue_count for issue in column_issues)
        issue_counts["missing_required_rows"] = int(checked[MISSING_REQUIRED_FLAG].sum())
        issue_counts["value_before_trade_rows"] = int(checked[REVERSED_DATES_FLAG].sum())
        issue_counts["signed_amount_mismatch_rows"] = int(
            checked[SIGNED_AMOUNT_MISMATCH_FLAG].sum()
        )

        report = TableBuildReport(
            table_name=payload.source_name,
            row_count=len(checked),
            issue_counts=dict(issue_counts),
            column_issues=column_issues,
        )
        return checked, report

    def parse_table(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[ColumnIssueSummary]]:
        """Parse one raw table into the normalized Silver schema."""

        self.schema.validate_columns(df.columns)
        parsed = df.copy()
        column_issues: list[ColumnIssueSummary] = []

        for column in self.schema.columns:
            if column.name not in parsed.columns:
                parsed[column.name] = pd.NA

            original = parsed[column.name]
            parsed[column.name] = self.parse_column(original, column.dtype)

            cleaned_original = clean_text(original)
            issue_mask = cleaned_original.notna() & parsed[column.name].isna()
            issue_count = int(issue_mask.sum())
            if issue_count:
                column_issues.append(
                    ColumnIssueSummary(
                        column=column.name,
                        issue_type="parse_error",
                        issue_count=issue_count,
                    )
                )

        ordered_columns = self.schema.column_names + [
            column
            for column in parsed.columns
            if column not in self.schema.column_names
        ]
        return parsed[ordered_columns], column_issues

    def check_quality_table(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flag row-level technical quality issues."""

        checked = df.copy()
        required_columns = self.schema.required_columns
        checked[MISSING_REQUIRED_FLAG] = checked[required_columns].isna().any(axis=1)
        checked[DUPLICATE_ID_FLAG] = False
        return checked

    def check_anomaly_table(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flag anomalies that are useful later but not filtered at Silver."""

        checked = df.copy()
        checked[REVERSED_DATES_FLAG] = (
            checked["VALUE_DATE"].notna()
            & checked["TRADE_DATE"].notna()
            & (checked["VALUE_DATE"] < checked["TRADE_DATE"])
        )

        expected_signed = checked["AMOUNT"] * checked["SIGN"].astype("Float64")
        checked[SIGNED_AMOUNT_MISMATCH_FLAG] = (
            checked["SIGNED_AMOUNT"].notna()
            & expected_signed.notna()
            & ((checked["SIGNED_AMOUNT"] - expected_signed).abs() > 0.01)
        )
        return checked

    def parse_column(self, series: pd.Series, target_type: DataType) -> pd.Series:
        """Parse one column according to the normalized target type."""

        if target_type is DataType.STRING:
            return clean_text(series).astype("string")
        if target_type is DataType.FLOAT:
            return to_float(series)
        if target_type is DataType.INTEGER:
            return to_int(series)
        if target_type is DataType.DATE:
            return to_date(series)
        if target_type is DataType.CATEGORY:
            return clean_text(series).astype("category")
        raise ValueError(f"Unsupported target type: {target_type}")

    def _flag_duplicate_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flag duplicate identifiers after entity-level merge."""

        duplicated = df.copy()
        duplicated[DUPLICATE_ID_FLAG] = duplicated.duplicated(
            subset=["ENTITY_SHORTNAME", "ID"],
            keep=False,
        )
        return duplicated