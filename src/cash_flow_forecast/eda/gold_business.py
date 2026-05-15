from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from cash_flow_forecast.contracts.rules import Ruleset
from cash_flow_forecast.data_layers.gold.builder import (
    KNOWN_AMOUNT_COLUMN,
    KNOWN_COUNT_COLUMN,
    SEQUENCE_ID_COLUMN,
    TARGET_AMOUNT_COLUMN,
    apply_column_rule,
    apply_ruleset_filters,
    add_movement_scope,
)


ENTITY_COL = "ENTITY_SHORTNAME"
CURRENCY_COL = "CURRENCY_SHORTNAME"
MOVEMENT_COL = "MOVEMENT_SCOPE"
MOVEMENT_TYPE_COL = "CASH_MOVEMENT_TYPE_SHORTNAME"
DATE_COL = "DATE"
TRADE_DATE_COL = "TRADE_DATE"
VALUE_DATE_COL = "VALUE_DATE"
OBSERVATION_COUNT_COLUMN = "OBSERVATION_COUNT"
TRADE_MINUS_VALUE_DAYS_COL = "TRADE_MINUS_VALUE_DAYS"
TRADE_VALUE_LAG_BUCKET_COL = "TRADE_VALUE_LAG_BUCKET"
RULE_STEP_COL = "RULE_STEP"
REMOVED_SUFFIX = "_REMOVED"

GOLD_TABLE_FILES = {
    "calendar_daily": "calendar_daily.parquet",
    "known_movements_daily": "known_movements_daily.parquet",
    "realized_cash_in": "realized_cash_in.parquet",
    "sequence_reference": "sequence_reference.parquet",
}

TABLE_CONTRACTS = {
    "known_movements_daily": {
        "date_col": VALUE_DATE_COL,
        "availability_date_col": TRADE_DATE_COL,
        "amount_col": KNOWN_AMOUNT_COLUMN,
        "count_col": KNOWN_COUNT_COLUMN,
    },
    "realized_cash_in": {
        "date_col": VALUE_DATE_COL,
        "amount_col": TARGET_AMOUNT_COLUMN,
        "count_col": OBSERVATION_COUNT_COLUMN,
    },
}


DAILY_SEQUENCE_KEY = [ENTITY_COL, CURRENCY_COL, MOVEMENT_COL, SEQUENCE_ID_COLUMN]

LAG_BUCKET_ORDER = [
    "5+ days before value",
    "4 days before value",
    "3 days before value",
    "2 days before value",
    "1 day before value",
    "same day",
    "1 day after value",
    "2 days after value",
    "3 days after value",
    "4 days after value",
    "5+ days after value",
]

DATE_COLUMNS = [
    DATE_COL,
    TRADE_DATE_COL,
    VALUE_DATE_COL,
]


def load_gold_tables(gold_path: str | Path) -> dict[str, pd.DataFrame]:
    """Load every available Gold parquet table from a directory."""

    source = Path(gold_path)
    tables: dict[str, pd.DataFrame] = {}
    for table_name, filename in GOLD_TABLE_FILES.items():
        path = source / filename
        if path.exists():
            tables[table_name] = normalize_table(pd.read_parquet(path))
    return tables


def load_silver_tables(silver_path: str | Path) -> dict[str, pd.DataFrame]:
    """Load Silver entity parquet files, ignoring manifests or non-table files."""

    source = Path(silver_path)
    if not source.exists():
        return {}

    tables = {}
    for path in sorted(source.glob("*.parquet")):
        if path.name.startswith("_") or path.stem in {"manifest"}:
            continue
        tables[path.stem] = normalize_table(pd.read_parquet(path))
    return tables


def normalize_table(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize date and common numeric columns without changing the business grain."""

    out = df.copy()
    for column in DATE_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column], errors="coerce").dt.normalize()

    for column in [
        TARGET_AMOUNT_COLUMN,
        KNOWN_AMOUNT_COLUMN,
        KNOWN_COUNT_COLUMN,
        OBSERVATION_COUNT_COLUMN,
        "SIGNED_AMOUNT",
        "AMOUNT",
        "SIGN",
    ]:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")

    for column in [ENTITY_COL, CURRENCY_COL, MOVEMENT_COL, MOVEMENT_TYPE_COL, SEQUENCE_ID_COLUMN]:
        if column in out.columns:
            out[column] = out[column].astype("string")

    return out


def clean_gold_tables(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Drop synthetic zero-count Gold rows and stale zero-only sequence references."""

    cleaned = {name: frame.copy() for name, frame in tables.items()}
    observed_sequence_ids: set[str] = set()

    for table_name, count_col in [
        ("realized_cash_in", OBSERVATION_COUNT_COLUMN),
        ("known_movements_daily", KNOWN_COUNT_COLUMN),
    ]:
        frame = cleaned.get(table_name)
        if frame is None or count_col not in frame.columns:
            continue
        frame = frame.loc[frame[count_col].fillna(0) > 0].reset_index(drop=True)
        cleaned[table_name] = frame
        if SEQUENCE_ID_COLUMN in frame.columns:
            observed_sequence_ids.update(frame[SEQUENCE_ID_COLUMN].dropna().astype(str))

    sequence_reference = cleaned.get("sequence_reference")
    if sequence_reference is not None and observed_sequence_ids and SEQUENCE_ID_COLUMN in sequence_reference.columns:
        cleaned["sequence_reference"] = sequence_reference.loc[
            sequence_reference[SEQUENCE_ID_COLUMN].astype(str).isin(observed_sequence_ids)
        ].reset_index(drop=True)

    return cleaned


def zero_count_guardrail_summary(
    raw_tables: dict[str, pd.DataFrame],
    cleaned_tables: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Summarize synthetic zero-count rows removed by the EDA guardrail."""

    rows = []
    for table_name, count_col in [
        ("realized_cash_in", OBSERVATION_COUNT_COLUMN),
        ("known_movements_daily", KNOWN_COUNT_COLUMN),
    ]:
        raw = raw_tables.get(table_name, pd.DataFrame())
        cleaned = cleaned_tables.get(table_name, pd.DataFrame())
        zero_count_rows = int((raw[count_col].fillna(0) == 0).sum()) if count_col in raw.columns else 0
        rows.append(
            {
                "TABLE_NAME": table_name,
                "RAW_ROWS": len(raw),
                "CLEANED_ROWS": len(cleaned),
                "ZERO_COUNT_ROWS_REMOVED": zero_count_rows,
                "ZERO_COUNT_ROW_SHARE": zero_count_rows / len(raw) if len(raw) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def discover_dimensions(
    gold_tables: dict[str, pd.DataFrame],
    silver_tables: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Return discovered entities, currencies, movements, sequences, and date ranges."""

    silver_tables = silver_tables or {}
    frames = [
        frame
        for name in ["sequence_reference", "realized_cash_in", "known_movements_daily"]
        if not (frame := gold_tables.get(name, pd.DataFrame())).empty
    ]
    gold_dim = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()

    rows = []
    if not gold_dim.empty:
        grouped_cols = [col for col in [ENTITY_COL, CURRENCY_COL, MOVEMENT_COL, SEQUENCE_ID_COLUMN] if col in gold_dim.columns]
        if grouped_cols:
            base = gold_dim[grouped_cols].drop_duplicates()
            for _, row in base.iterrows():
                rows.append(
                    {
                        ENTITY_COL: row.get(ENTITY_COL, pd.NA),
                        CURRENCY_COL: row.get(CURRENCY_COL, pd.NA),
                        MOVEMENT_COL: row.get(MOVEMENT_COL, pd.NA),
                        SEQUENCE_ID_COLUMN: row.get(SEQUENCE_ID_COLUMN, pd.NA),
                        "SOURCE": "gold",
                    }
                )

    for entity_name, frame in silver_tables.items():
        if frame.empty:
            rows.append({ENTITY_COL: entity_name, "SOURCE": "silver_file"})
            continue
        entity_values = frame[ENTITY_COL].dropna().astype(str).unique() if ENTITY_COL in frame.columns else [entity_name]
        for entity in entity_values:
            rows.append({ENTITY_COL: entity, "SOURCE": "silver"})

    dimensions = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True) if rows else pd.DataFrame()
    min_date, max_date = gold_date_range(gold_tables)
    if not dimensions.empty:
        dimensions["GOLD_MIN_DATE"] = min_date
        dimensions["GOLD_MAX_DATE"] = max_date
    return dimensions


def gold_date_range(tables: dict[str, pd.DataFrame]) -> tuple[pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT]:
    """Return min/max business date across Gold tables."""

    dates: list[pd.Series] = []
    for table_name, contract in TABLE_CONTRACTS.items():
        frame = tables.get(table_name, pd.DataFrame())
        date_col = contract["date_col"]
        if not frame.empty and date_col in frame.columns:
            dates.append(pd.to_datetime(frame[date_col], errors="coerce"))
    calendar = tables.get("calendar_daily", pd.DataFrame())
    if not calendar.empty and DATE_COL in calendar.columns:
        dates.append(pd.to_datetime(calendar[DATE_COL], errors="coerce"))
    if not dates:
        return pd.NaT, pd.NaT
    combined = pd.concat(dates).dropna()
    if combined.empty:
        return pd.NaT, pd.NaT
    return combined.min(), combined.max()


def rule_waterfall(silver_tables: dict[str, pd.DataFrame], ruleset: Ruleset) -> pd.DataFrame:
    """Show how each business rule changes row and amount coverage."""

    if not silver_tables:
        return pd.DataFrame()
    current = normalize_table(pd.concat(silver_tables.values(), ignore_index=True, sort=False))
    steps = [_rule_step("silver_input", current)]

    for column_name, rule in ruleset.filters.items():
        before = current
        current = apply_column_rule(before, column_name, rule) if column_name in before.columns else before.copy()
        step = _rule_step(f"after_{column_name}", current)
        removed = _rule_step(f"removed_by_{column_name}", before.loc[~before.index.isin(current.index)])
        step.update(
            {
                f"ROWS{REMOVED_SUFFIX}": removed["ROWS"],
                f"SIGNED_AMOUNT{REMOVED_SUFFIX}": removed["SIGNED_AMOUNT"],
                f"ABS_SIGNED_AMOUNT{REMOVED_SUFFIX}": removed["ABS_SIGNED_AMOUNT"],
            }
        )
        steps.append(step)

    scoped = add_movement_scope(current, ruleset) if not current.empty else current.copy()
    step = _rule_step("after_movement_scope", scoped)
    step.update(
        {
            f"ROWS{REMOVED_SUFFIX}": len(current) - len(scoped),
            f"SIGNED_AMOUNT{REMOVED_SUFFIX}": _sum_numeric(current, "SIGNED_AMOUNT") - _sum_numeric(scoped, "SIGNED_AMOUNT"),
            f"ABS_SIGNED_AMOUNT{REMOVED_SUFFIX}": _sum_abs_numeric(current, "SIGNED_AMOUNT") - _sum_abs_numeric(scoped, "SIGNED_AMOUNT"),
        }
    )
    steps.append(step)
    return pd.DataFrame(steps)


def trade_value_lag_summary(
    known_movements_daily: pd.DataFrame,
    group_cols: Iterable[str] = (ENTITY_COL, CURRENCY_COL, MOVEMENT_COL),
) -> pd.DataFrame:
    """Count Trade Date versus Value Date timing buckets."""

    if known_movements_daily.empty:
        return pd.DataFrame()
    required = [TRADE_DATE_COL, VALUE_DATE_COL, KNOWN_COUNT_COLUMN, KNOWN_AMOUNT_COLUMN]
    if any(column not in known_movements_daily.columns for column in required):
        return pd.DataFrame()

    work = known_movements_daily.copy()
    work[TRADE_MINUS_VALUE_DAYS_COL] = (
        pd.to_datetime(work[TRADE_DATE_COL], errors="coerce")
        - pd.to_datetime(work[VALUE_DATE_COL], errors="coerce")
    ).dt.days
    work[TRADE_VALUE_LAG_BUCKET_COL] = work[TRADE_MINUS_VALUE_DAYS_COL].map(trade_value_lag_bucket)
    group_cols = [column for column in group_cols if column in work.columns]
    grouped = (
        work.groupby(group_cols + [TRADE_VALUE_LAG_BUCKET_COL], dropna=False, observed=True)
        .agg(
            AGGREGATE_ROWS=(KNOWN_COUNT_COLUMN, "size"),
            SOURCE_ROWS=(KNOWN_COUNT_COLUMN, "sum"),
            KNOWN_AMOUNT=(KNOWN_AMOUNT_COLUMN, "sum"),
            ABS_KNOWN_AMOUNT=(KNOWN_AMOUNT_COLUMN, lambda s: float(s.abs().sum())),
        )
        .reset_index()
    )
    grouped[TRADE_VALUE_LAG_BUCKET_COL] = pd.Categorical(
        grouped[TRADE_VALUE_LAG_BUCKET_COL],
        categories=LAG_BUCKET_ORDER,
        ordered=True,
    )
    return grouped.sort_values(group_cols + [TRADE_VALUE_LAG_BUCKET_COL]).reset_index(drop=True)


def trade_value_lag_bucket(days: float | int | None) -> str:
    """Map TRADE_DATE - VALUE_DATE to stable business timing buckets."""

    if pd.isna(days):
        return "missing"
    value = int(days)
    if value <= -5:
        return LAG_BUCKET_ORDER[0]
    if value >= 5:
        return LAG_BUCKET_ORDER[-1]
    return {
        -4: LAG_BUCKET_ORDER[1],
        -3: LAG_BUCKET_ORDER[2],
        -2: LAG_BUCKET_ORDER[3],
        -1: LAG_BUCKET_ORDER[4],
        0: LAG_BUCKET_ORDER[5],
        1: LAG_BUCKET_ORDER[6],
        2: LAG_BUCKET_ORDER[7],
        3: LAG_BUCKET_ORDER[8],
        4: LAG_BUCKET_ORDER[9],
    }[value]


def availability_summary(
    realized_cash_in: pd.DataFrame,
    known_movements_daily: pd.DataFrame,
    group_cols: Iterable[str] = (ENTITY_COL, CURRENCY_COL, MOVEMENT_COL),
) -> pd.DataFrame:
    """Measure how much realized D+1 cash is known by the forecast cutoff."""

    if realized_cash_in.empty:
        return pd.DataFrame()

    group_cols = [column for column in group_cols if column in realized_cash_in.columns]
    key_cols = group_cols + [SEQUENCE_ID_COLUMN, VALUE_DATE_COL]
    realized = realized_cash_in.copy()
    realized["CUTOFF_DATE"] = pd.to_datetime(realized[VALUE_DATE_COL]) - pd.Timedelta(days=1)

    known = known_movements_daily.copy()
    if not known.empty:
        known["CUTOFF_DATE"] = pd.to_datetime(known[VALUE_DATE_COL]) - pd.Timedelta(days=1)
        known["KNOWN_AT_CUTOFF_AMOUNT"] = known[KNOWN_AMOUNT_COLUMN].where(
            pd.to_datetime(known[TRADE_DATE_COL]) <= known["CUTOFF_DATE"],
            0.0,
        )
        known["KNOWN_AT_CUTOFF_COUNT"] = known[KNOWN_COUNT_COLUMN].where(
            pd.to_datetime(known[TRADE_DATE_COL]) <= known["CUTOFF_DATE"],
            0,
        )
        known["LATE_AFTER_CUTOFF_AMOUNT"] = known[KNOWN_AMOUNT_COLUMN].where(
            pd.to_datetime(known[TRADE_DATE_COL]) > known["CUTOFF_DATE"],
            0.0,
        )
        known["LATE_AFTER_CUTOFF_COUNT"] = known[KNOWN_COUNT_COLUMN].where(
            pd.to_datetime(known[TRADE_DATE_COL]) > known["CUTOFF_DATE"],
            0,
        )
        known["SAME_DAY_AMOUNT"] = known[KNOWN_AMOUNT_COLUMN].where(
            pd.to_datetime(known[TRADE_DATE_COL]) == pd.to_datetime(known[VALUE_DATE_COL]),
            0.0,
        )
        known["ADVANCE_KNOWN_AMOUNT"] = known[KNOWN_AMOUNT_COLUMN].where(
            pd.to_datetime(known[TRADE_DATE_COL]) < pd.to_datetime(known[VALUE_DATE_COL]),
            0.0,
        )
        known["AFTER_VALUE_AMOUNT"] = known[KNOWN_AMOUNT_COLUMN].where(
            pd.to_datetime(known[TRADE_DATE_COL]) > pd.to_datetime(known[VALUE_DATE_COL]),
            0.0,
        )
        known_daily = (
            known.groupby(key_cols, dropna=False, observed=True)
            .agg(
                KNOWN_TOTAL_AMOUNT=(KNOWN_AMOUNT_COLUMN, "sum"),
                KNOWN_TOTAL_COUNT=(KNOWN_COUNT_COLUMN, "sum"),
                KNOWN_AT_CUTOFF_AMOUNT=("KNOWN_AT_CUTOFF_AMOUNT", "sum"),
                KNOWN_AT_CUTOFF_COUNT=("KNOWN_AT_CUTOFF_COUNT", "sum"),
                LATE_AFTER_CUTOFF_AMOUNT=("LATE_AFTER_CUTOFF_AMOUNT", "sum"),
                LATE_AFTER_CUTOFF_COUNT=("LATE_AFTER_CUTOFF_COUNT", "sum"),
                SAME_DAY_AMOUNT=("SAME_DAY_AMOUNT", "sum"),
                ADVANCE_KNOWN_AMOUNT=("ADVANCE_KNOWN_AMOUNT", "sum"),
                AFTER_VALUE_AMOUNT=("AFTER_VALUE_AMOUNT", "sum"),
            )
            .reset_index()
        )
    else:
        known_daily = pd.DataFrame(columns=key_cols)

    daily = realized.merge(known_daily, on=key_cols, how="left")
    fill_columns = [
        "KNOWN_TOTAL_AMOUNT",
        "KNOWN_TOTAL_COUNT",
        "KNOWN_AT_CUTOFF_AMOUNT",
        "KNOWN_AT_CUTOFF_COUNT",
        "LATE_AFTER_CUTOFF_AMOUNT",
        "LATE_AFTER_CUTOFF_COUNT",
        "SAME_DAY_AMOUNT",
        "ADVANCE_KNOWN_AMOUNT",
        "AFTER_VALUE_AMOUNT",
    ]
    for column in fill_columns:
        if column not in daily.columns:
            daily[column] = 0.0
        daily[column] = daily[column].fillna(0.0)
    daily["ABS_TARGET_AMOUNT"] = daily[TARGET_AMOUNT_COLUMN].abs()
    daily["ABS_KNOWN_AT_CUTOFF_AMOUNT"] = daily["KNOWN_AT_CUTOFF_AMOUNT"].abs()
    daily["ABS_LATE_AFTER_CUTOFF_AMOUNT"] = daily["LATE_AFTER_CUTOFF_AMOUNT"].abs()

    summary = (
        daily.groupby(group_cols, dropna=False, observed=True)
        .agg(
            DAYS=(VALUE_DATE_COL, "nunique"),
            TARGET_AMOUNT=(TARGET_AMOUNT_COLUMN, "sum"),
            ABS_TARGET_AMOUNT=("ABS_TARGET_AMOUNT", "sum"),
            KNOWN_AT_CUTOFF_AMOUNT=("KNOWN_AT_CUTOFF_AMOUNT", "sum"),
            ABS_KNOWN_AT_CUTOFF_AMOUNT=("ABS_KNOWN_AT_CUTOFF_AMOUNT", "sum"),
            LATE_AFTER_CUTOFF_AMOUNT=("LATE_AFTER_CUTOFF_AMOUNT", "sum"),
            ABS_LATE_AFTER_CUTOFF_AMOUNT=("ABS_LATE_AFTER_CUTOFF_AMOUNT", "sum"),
            KNOWN_AT_CUTOFF_COUNT=("KNOWN_AT_CUTOFF_COUNT", "sum"),
            LATE_AFTER_CUTOFF_COUNT=("LATE_AFTER_CUTOFF_COUNT", "sum"),
            SAME_DAY_AMOUNT=("SAME_DAY_AMOUNT", "sum"),
            ADVANCE_KNOWN_AMOUNT=("ADVANCE_KNOWN_AMOUNT", "sum"),
            AFTER_VALUE_AMOUNT=("AFTER_VALUE_AMOUNT", "sum"),
        )
        .reset_index()
    )
    summary["KNOWN_COVERAGE_RATIO_ABS"] = _safe_divide(
        summary["ABS_KNOWN_AT_CUTOFF_AMOUNT"],
        summary["ABS_TARGET_AMOUNT"],
    )
    summary["LATE_AFTER_CUTOFF_RATIO_ABS"] = _safe_divide(
        summary["ABS_LATE_AFTER_CUTOFF_AMOUNT"],
        summary["ABS_TARGET_AMOUNT"],
    )
    return summary.sort_values("ABS_TARGET_AMOUNT", ascending=False).reset_index(drop=True)


def concentration_summary(
    realized_cash_in: pd.DataFrame,
    group_cols: Iterable[str] = (ENTITY_COL, CURRENCY_COL, MOVEMENT_COL),
) -> pd.DataFrame:
    """Build amount/count Pareto metrics while treating completed zero days correctly."""

    if realized_cash_in.empty:
        return pd.DataFrame()
    required = [VALUE_DATE_COL, TARGET_AMOUNT_COLUMN]
    if any(column not in realized_cash_in.columns for column in required):
        return pd.DataFrame()

    group_cols = [column for column in group_cols if column in realized_cash_in.columns]
    work = realized_cash_in.copy()
    work[TARGET_AMOUNT_COLUMN] = pd.to_numeric(work[TARGET_AMOUNT_COLUMN], errors="coerce").fillna(0.0)
    if OBSERVATION_COUNT_COLUMN in work.columns:
        work[OBSERVATION_COUNT_COLUMN] = pd.to_numeric(work[OBSERVATION_COUNT_COLUMN], errors="coerce").fillna(0.0)
        work["IS_ACTIVE_DAY"] = work[OBSERVATION_COUNT_COLUMN] > 0
    else:
        work["IS_ACTIVE_DAY"] = work[TARGET_AMOUNT_COLUMN] != 0
        work[OBSERVATION_COUNT_COLUMN] = work["IS_ACTIVE_DAY"].astype(int)
    work["ABS_TARGET_AMOUNT"] = work[TARGET_AMOUNT_COLUMN].abs()

    rows = []
    grouped = work.groupby(group_cols, dropna=False, observed=True) if group_cols else [((), work)]
    for keys, frame in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {column: value for column, value in zip(group_cols, keys)}
        active = frame.loc[frame["IS_ACTIVE_DAY"]]
        row.update(
            {
                "DAYS": int(frame[VALUE_DATE_COL].nunique(dropna=True)),
                "ACTIVE_DAYS": int(active[VALUE_DATE_COL].nunique(dropna=True)),
                "ZERO_DAYS": int(frame[VALUE_DATE_COL].nunique(dropna=True) - active[VALUE_DATE_COL].nunique(dropna=True)),
                "OBSERVATION_COUNT": float(frame[OBSERVATION_COUNT_COLUMN].sum()),
                "TARGET_AMOUNT": float(frame[TARGET_AMOUNT_COLUMN].sum()),
                "ABS_TARGET_AMOUNT": float(frame["ABS_TARGET_AMOUNT"].sum()),
                "AVG_ACTIVE_ABS_AMOUNT": float(active["ABS_TARGET_AMOUNT"].mean()) if not active.empty else 0.0,
            }
        )
        rows.append(row)

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    summary = summary.sort_values("ABS_TARGET_AMOUNT", ascending=False).reset_index(drop=True)
    total_abs = summary["ABS_TARGET_AMOUNT"].sum()
    total_count = summary["OBSERVATION_COUNT"].sum()
    summary["AMOUNT_SHARE"] = _safe_divide(summary["ABS_TARGET_AMOUNT"], total_abs)
    summary["CUMULATIVE_AMOUNT_SHARE"] = summary["AMOUNT_SHARE"].cumsum()
    summary["COUNT_SHARE"] = _safe_divide(summary["OBSERVATION_COUNT"], total_count)
    summary["AMOUNT_RANK"] = range(1, len(summary) + 1)
    return summary


def forecastability_diagnostics(
    realized_cash_in: pd.DataFrame,
    calendar_daily: pd.DataFrame,
    sequence_reference: pd.DataFrame,
) -> pd.DataFrame:
    """Compute sequence-level history, intermittency, and spike diagnostics."""

    if sequence_reference.empty or calendar_daily.empty:
        return pd.DataFrame()

    sequences = sequence_reference.copy()
    if SEQUENCE_ID_COLUMN in realized_cash_in.columns and OBSERVATION_COUNT_COLUMN in realized_cash_in.columns:
        observed_sequence_ids = realized_cash_in.loc[
            realized_cash_in[OBSERVATION_COUNT_COLUMN].fillna(0) > 0,
            SEQUENCE_ID_COLUMN,
        ].dropna().astype(str)
        if not observed_sequence_ids.empty:
            sequences = sequences.loc[sequences[SEQUENCE_ID_COLUMN].astype(str).isin(set(observed_sequence_ids))]

    if sequences.empty:
        return pd.DataFrame()

    calendar = calendar_daily[[DATE_COL]].dropna().copy()
    calendar["_merge_key"] = 1
    sequences = sequences.copy()
    sequences["_merge_key"] = 1
    panel = sequences.merge(calendar, on="_merge_key").drop(columns="_merge_key")
    realized = realized_cash_in.copy()
    panel = panel.merge(
        realized[
            [ENTITY_COL, CURRENCY_COL, MOVEMENT_COL, SEQUENCE_ID_COLUMN, VALUE_DATE_COL, TARGET_AMOUNT_COLUMN]
        ],
        left_on=[ENTITY_COL, CURRENCY_COL, MOVEMENT_COL, SEQUENCE_ID_COLUMN, DATE_COL],
        right_on=[ENTITY_COL, CURRENCY_COL, MOVEMENT_COL, SEQUENCE_ID_COLUMN, VALUE_DATE_COL],
        how="left",
    )
    panel[TARGET_AMOUNT_COLUMN] = panel[TARGET_AMOUNT_COLUMN].fillna(0.0)
    panel["IS_ACTIVE_DAY"] = panel[TARGET_AMOUNT_COLUMN] != 0
    panel["ABS_TARGET_AMOUNT"] = panel[TARGET_AMOUNT_COLUMN].abs()

    rows = []
    for keys, frame in panel.groupby([ENTITY_COL, CURRENCY_COL, MOVEMENT_COL, SEQUENCE_ID_COLUMN], dropna=False, observed=True):
        ordered = frame.sort_values(DATE_COL)
        active = ordered.loc[ordered["IS_ACTIVE_DAY"]]
        active_ratio = float(ordered["IS_ACTIVE_DAY"].mean()) if len(ordered) else 0.0
        non_zero_abs = active["ABS_TARGET_AMOUNT"]
        p99 = float(non_zero_abs.quantile(0.99)) if not non_zero_abs.empty else 0.0
        rows.append(
            {
                ENTITY_COL: keys[0],
                CURRENCY_COL: keys[1],
                MOVEMENT_COL: keys[2],
                SEQUENCE_ID_COLUMN: keys[3],
                "DAYS": len(ordered),
                "ACTIVE_DAYS": len(active),
                "ACTIVE_DAY_RATIO": active_ratio,
                "ZERO_DAYS": int((~ordered["IS_ACTIVE_DAY"]).sum()),
                "MAX_ZERO_RUN_DAYS": max_zero_run(ordered["IS_ACTIVE_DAY"]),
                "FIRST_ACTIVE_DATE": active[DATE_COL].min() if not active.empty else pd.NaT,
                "LAST_ACTIVE_DATE": active[DATE_COL].max() if not active.empty else pd.NaT,
                "TOTAL_AMOUNT": float(ordered[TARGET_AMOUNT_COLUMN].sum()),
                "ABS_TOTAL_AMOUNT": float(ordered["ABS_TARGET_AMOUNT"].sum()),
                "AVG_ACTIVE_ABS_AMOUNT": float(non_zero_abs.mean()) if not non_zero_abs.empty else 0.0,
                "STD_DAILY_AMOUNT": float(ordered[TARGET_AMOUNT_COLUMN].std(ddof=0)) if len(ordered) else 0.0,
                "P99_ACTIVE_ABS_AMOUNT": p99,
                "INTERMITTENCY_CLASS": intermittency_class(active_ratio),
            }
        )
    return pd.DataFrame(rows).sort_values("ABS_TOTAL_AMOUNT", ascending=False).reset_index(drop=True)


def max_zero_run(active_mask: pd.Series) -> int:
    """Return the longest consecutive run of inactive days."""

    max_run = 0
    current = 0
    for is_active in active_mask.fillna(False).astype(bool):
        if is_active:
            max_run = max(max_run, current)
            current = 0
        else:
            current += 1
    return max(max_run, current)


def intermittency_class(active_ratio: float) -> str:
    """Classify series sparsity for business-facing forecastability review."""

    if active_ratio == 0:
        return "no_activity"
    if active_ratio < 0.02:
        return "very_sparse"
    if active_ratio < 0.20:
        return "intermittent"
    return "regular"


def operational_timing_summary(
    silver_tables: dict[str, pd.DataFrame],
    ruleset: Ruleset | None = None,
    group_cols: Iterable[str] = (ENTITY_COL, MOVEMENT_TYPE_COL),
) -> pd.DataFrame:
    """Summarize only the business timing between Trade Date and Value Date."""

    if not silver_tables:
        return pd.DataFrame()
    work = normalize_table(pd.concat(silver_tables.values(), ignore_index=True, sort=False))
    if ruleset is not None and not work.empty:
        work = add_movement_scope(apply_ruleset_filters(work, ruleset), ruleset)

    if TRADE_DATE_COL not in work.columns or VALUE_DATE_COL not in work.columns:
        return pd.DataFrame()

    metric_col = "TRADE_TO_VALUE_DAYS"
    work[metric_col] = (
        pd.to_datetime(work[VALUE_DATE_COL], errors="coerce")
        - pd.to_datetime(work[TRADE_DATE_COL], errors="coerce")
    ).dt.days
    valid = work.loc[work[metric_col].notna()]
    if valid.empty:
        return pd.DataFrame()

    group_cols = [column for column in group_cols if column in valid.columns]
    rows = []
    grouped = valid.groupby(group_cols, dropna=False, observed=True) if group_cols else [((), valid)]
    for keys, frame in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {column: value for column, value in zip(group_cols, keys)}
        series = frame[metric_col].astype(float)
        row.update(
            {
                "TIMING_METRIC": metric_col,
                "ROWS": len(series),
                "MEAN_DAYS": float(series.mean()),
                "P05_DAYS": float(series.quantile(0.05)),
                "P50_DAYS": float(series.quantile(0.50)),
                "P95_DAYS": float(series.quantile(0.95)),
                "MIN_DAYS": float(series.min()),
                "MAX_DAYS": float(series.max()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def top_spike_days(
    realized_cash_in: pd.DataFrame,
    group_cols: Iterable[str] = (ENTITY_COL, CURRENCY_COL, MOVEMENT_COL),
    top_n: int = 50,
) -> pd.DataFrame:
    """Return the largest absolute realized amount days, excluding completed zero rows."""

    if realized_cash_in.empty or TARGET_AMOUNT_COLUMN not in realized_cash_in.columns:
        return pd.DataFrame()
    group_cols = [column for column in group_cols if column in realized_cash_in.columns]
    work = realized_cash_in.copy()
    work[TARGET_AMOUNT_COLUMN] = pd.to_numeric(work[TARGET_AMOUNT_COLUMN], errors="coerce").fillna(0.0)
    if OBSERVATION_COUNT_COLUMN in work.columns:
        active_mask = pd.to_numeric(work[OBSERVATION_COUNT_COLUMN], errors="coerce").fillna(0.0) > 0
    else:
        active_mask = work[TARGET_AMOUNT_COLUMN] != 0
    work = work.loc[active_mask].copy()
    if work.empty:
        return pd.DataFrame()
    work["ABS_TARGET_AMOUNT"] = work[TARGET_AMOUNT_COLUMN].abs()
    columns = group_cols + [VALUE_DATE_COL, TARGET_AMOUNT_COLUMN, "ABS_TARGET_AMOUNT"]
    if OBSERVATION_COUNT_COLUMN in work.columns:
        columns.append(OBSERVATION_COUNT_COLUMN)
    return work.sort_values("ABS_TARGET_AMOUNT", ascending=False)[columns].head(top_n).reset_index(drop=True)


def filter_by_entity(df: pd.DataFrame, entity: str | None) -> pd.DataFrame:
    """Filter a table to one entity when possible."""

    if entity is None or ENTITY_COL not in df.columns:
        return df.copy()
    return df.loc[df[ENTITY_COL].astype(str) == str(entity)].copy()


def filter_by_window(
    df: pd.DataFrame,
    date_col: str,
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
) -> pd.DataFrame:
    """Filter a table to an inclusive date window."""

    if df.empty or date_col not in df.columns:
        return df.copy()
    work = df.copy()
    dates = pd.to_datetime(work[date_col], errors="coerce")
    mask = pd.Series(True, index=work.index)
    if start_date is not None and pd.notna(start_date):
        mask &= dates >= pd.Timestamp(start_date)
    if end_date is not None and pd.notna(end_date):
        mask &= dates <= pd.Timestamp(end_date)
    return work.loc[mask].copy()


def window_bounds(
    tables: dict[str, pd.DataFrame],
    window: str,
    end_date: str | pd.Timestamp | None = None,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Resolve window labels such as full, 365d, 180d, or YYYY-MM-DD:YYYY-MM-DD."""

    min_date, max_date = gold_date_range(tables)
    if end_date is not None:
        max_date = pd.Timestamp(end_date)
    if pd.isna(min_date) or pd.isna(max_date) or window.lower() == "full":
        return None, None
    label = window.lower().strip()
    if ":" in label:
        start, end = label.split(":", 1)
        return pd.Timestamp(start) if start else None, pd.Timestamp(end) if end else None
    if label.isdigit():
        days = int(label)
        return pd.Timestamp(max_date) - pd.Timedelta(days=days - 1), pd.Timestamp(max_date)
    if label.endswith("d"):
        days = int(label[:-1])
        return pd.Timestamp(max_date) - pd.Timedelta(days=days - 1), pd.Timestamp(max_date)
    if label.endswith("m"):
        months = int(label[:-1])
        return pd.Timestamp(max_date) - pd.DateOffset(months=months), pd.Timestamp(max_date)
    if label.endswith("y"):
        years = int(label[:-1])
        return pd.Timestamp(max_date) - pd.DateOffset(years=years), pd.Timestamp(max_date)
    return None, None

def complete_daily_panel(
    df: pd.DataFrame,
    table_name: str,
    calendar_daily: pd.DataFrame,
    sequence_reference: pd.DataFrame | None = None,
    *,
    entity: str | None = None,
    start_date: pd.Timestamp | str | None = None,
    end_date: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Return a zero-filled daily panel at sequence grain using calendar_daily.

    Missing rows are interpreted as zero amount and zero count for the sequence
    defined by entity, currency, movement scope, and sequence id. For
    known_movements_daily this creates a Value Date panel for plotting and daily
    coverage summaries; Trade Date analyses should continue to use observed rows.
    """

    contract = TABLE_CONTRACTS.get(table_name)
    if not contract:
        return df.copy()
    date_col = contract["date_col"]
    amount_col = contract["amount_col"]
    count_col = contract["count_col"]
    if calendar_daily.empty or DATE_COL not in calendar_daily.columns:
        return filter_by_window(filter_by_entity(df, entity), date_col, pd.Timestamp(start_date) if start_date is not None else None, pd.Timestamp(end_date) if end_date is not None else None)

    sequence_source = sequence_reference if sequence_reference is not None and not sequence_reference.empty else df
    if sequence_source is None or sequence_source.empty:
        return filter_by_window(filter_by_entity(df, entity), date_col, pd.Timestamp(start_date) if start_date is not None else None, pd.Timestamp(end_date) if end_date is not None else None)

    required_sequence_cols = [column for column in DAILY_SEQUENCE_KEY if column in sequence_source.columns]
    if len(required_sequence_cols) < len(DAILY_SEQUENCE_KEY):
        return filter_by_window(filter_by_entity(df, entity), date_col, pd.Timestamp(start_date) if start_date is not None else None, pd.Timestamp(end_date) if end_date is not None else None)

    sequences = sequence_source[DAILY_SEQUENCE_KEY].drop_duplicates().copy()
    sequences = filter_by_entity(sequences, entity)
    if sequences.empty:
        return pd.DataFrame(columns=DAILY_SEQUENCE_KEY + [date_col, amount_col, count_col])

    calendar = calendar_daily[[DATE_COL]].dropna().drop_duplicates().rename(columns={DATE_COL: date_col})
    calendar[date_col] = pd.to_datetime(calendar[date_col], errors="coerce").dt.normalize()
    calendar = filter_by_window(
        calendar,
        date_col,
        pd.Timestamp(start_date) if start_date is not None else None,
        pd.Timestamp(end_date) if end_date is not None else None,
    )
    if calendar.empty:
        return pd.DataFrame(columns=DAILY_SEQUENCE_KEY + [date_col, amount_col, count_col])

    grid = sequences.merge(calendar, how="cross")
    observed = df.copy()
    observed = filter_by_entity(observed, entity)
    observed = filter_by_window(
        observed,
        date_col,
        pd.Timestamp(start_date) if start_date is not None else None,
        pd.Timestamp(end_date) if end_date is not None else None,
    )

    merge_cols = DAILY_SEQUENCE_KEY + [date_col]
    value_cols = [amount_col, count_col]
    if observed.empty or any(column not in observed.columns for column in merge_cols + value_cols):
        aggregated = pd.DataFrame(columns=merge_cols + value_cols)
    else:
        aggregated = (
            observed[merge_cols + value_cols]
            .assign(
                **{
                    amount_col: lambda frame: pd.to_numeric(frame[amount_col], errors="coerce").fillna(0.0),
                    count_col: lambda frame: pd.to_numeric(frame[count_col], errors="coerce").fillna(0.0),
                }
            )
            .groupby(merge_cols, dropna=False, observed=True)
            .agg({amount_col: "sum", count_col: "sum"})
            .reset_index()
        )

    panel = grid.merge(aggregated, on=merge_cols, how="left")
    panel[amount_col] = panel[amount_col].fillna(0.0)
    panel[count_col] = panel[count_col].fillna(0.0)
    return panel.sort_values(merge_cols).reset_index(drop=True)


def complete_gold_panels(
    gold_tables: dict[str, pd.DataFrame],
    *,
    entity: str | None = None,
    start_date: pd.Timestamp | str | None = None,
    end_date: pd.Timestamp | str | None = None,
) -> dict[str, pd.DataFrame]:
    """Create zero-filled daily panels for plottable Gold tables."""

    calendar = gold_tables.get("calendar_daily", pd.DataFrame())
    sequence_reference = filter_by_entity(gold_tables.get("sequence_reference", pd.DataFrame()), entity)
    return {
        "realized_cash_in": complete_daily_panel(
            gold_tables.get("realized_cash_in", pd.DataFrame()),
            "realized_cash_in",
            calendar,
            sequence_reference,
            entity=entity,
            start_date=start_date,
            end_date=end_date,
        ),
        "known_movements_daily": complete_daily_panel(
            gold_tables.get("known_movements_daily", pd.DataFrame()),
            "known_movements_daily",
            calendar,
            sequence_reference,
            entity=entity,
            start_date=start_date,
            end_date=end_date,
        ),
    }


def observed_gold_tables_for_entity(
    gold_tables: dict[str, pd.DataFrame],
    *,
    entity: str | None = None,
    start_date: pd.Timestamp | str | None = None,
    end_date: pd.Timestamp | str | None = None,
) -> dict[str, pd.DataFrame]:
    """Filter observed Gold rows by entity and date window without adding zero rows."""

    out: dict[str, pd.DataFrame] = {}
    for table_name, frame in gold_tables.items():
        filtered = filter_by_entity(frame, entity)
        if table_name in TABLE_CONTRACTS:
            filtered = filter_by_window(
                filtered,
                TABLE_CONTRACTS[table_name]["date_col"],
                pd.Timestamp(start_date) if start_date is not None else None,
                pd.Timestamp(end_date) if end_date is not None else None,
            )
        elif table_name == "calendar_daily":
            filtered = filter_by_window(
                filtered,
                DATE_COL,
                pd.Timestamp(start_date) if start_date is not None else None,
                pd.Timestamp(end_date) if end_date is not None else None,
            )
        out[table_name] = filtered
    return out



def select_movement_scopes(
    df: pd.DataFrame,
    amount_or_count_col: str,
    movement_scopes: list[str] | None = None,
    top_n: int = 10,
) -> list[str]:
    """Select explicit movement scopes or top movements by absolute signal."""

    if movement_scopes:
        return movement_scopes
    if df.empty or MOVEMENT_COL not in df.columns or amount_or_count_col not in df.columns:
        return []
    selected = (
        df.groupby(MOVEMENT_COL, dropna=False, observed=True)[amount_or_count_col]
        .apply(lambda s: float(s.abs().sum()))
        .sort_values(ascending=False)
        .head(top_n)
        .index.astype(str)
        .tolist()
    )
    return selected


def plot_daily_amount_by_movement(
    df: pd.DataFrame,
    table_name: str,
    entity: str = "all entities",
    movement_scopes: list[str] | None = None,
    top_n: int = 10,
    width: int = 1100,
    height: int = 620,
) -> go.Figure | None:
    """Build an interactive daily amount line chart by movement scope."""

    contract = TABLE_CONTRACTS.get(table_name)
    if not contract:
        return None
    date_col = contract["date_col"]
    amount_col = contract["amount_col"]
    if df.empty or date_col not in df.columns or amount_col not in df.columns or MOVEMENT_COL not in df.columns:
        return None

    work = df[[date_col, MOVEMENT_COL, amount_col]].copy()
    selected = select_movement_scopes(work, amount_col, movement_scopes, top_n)
    if selected:
        work = work.loc[work[MOVEMENT_COL].astype(str).isin(selected)]
    daily = (
        work.groupby([date_col, MOVEMENT_COL], dropna=False, observed=True)[amount_col]
        .sum()
        .reset_index()
        .sort_values(date_col)
    )
    if daily.empty:
        return None
    fig = px.line(
        daily,
        x=date_col,
        y=amount_col,
        color=MOVEMENT_COL,
        title=f"{entity} - {table_name}: daily amount by movement",
    )
    _standard_time_layout(fig, date_col, amount_col, MOVEMENT_COL, width, height)
    return fig


def plot_daily_count_by_movement(
    df: pd.DataFrame,
    table_name: str,
    entity: str = "all entities",
    movement_scopes: list[str] | None = None,
    top_n: int = 10,
    width: int = 1100,
    height: int = 620,
) -> go.Figure | None:
    """Build an interactive daily count line chart by movement scope."""

    contract = TABLE_CONTRACTS.get(table_name)
    if not contract:
        return None
    date_col = contract["date_col"]
    count_col = contract["count_col"]
    if df.empty or date_col not in df.columns or count_col not in df.columns or MOVEMENT_COL not in df.columns:
        return None

    work = df[[date_col, MOVEMENT_COL, count_col]].copy()
    selected = select_movement_scopes(work, count_col, movement_scopes, top_n)
    if selected:
        work = work.loc[work[MOVEMENT_COL].astype(str).isin(selected)]
    daily = (
        work.groupby([date_col, MOVEMENT_COL], dropna=False, observed=True)[count_col]
        .sum()
        .reset_index()
        .sort_values(date_col)
    )
    if daily.empty:
        return None
    fig = px.line(
        daily,
        x=date_col,
        y=count_col,
        color=MOVEMENT_COL,
        title=f"{entity} - {table_name}: daily count by movement",
    )
    _standard_time_layout(fig, date_col, count_col, MOVEMENT_COL, width, height)
    return fig


def plot_total_amount_by_movement(
    df: pd.DataFrame,
    table_name: str,
    entity: str = "all entities",
    movement_scopes: list[str] | None = None,
    top_n: int = 10,
    width: int = 1000,
    height: int = 560,
) -> go.Figure | None:
    """Build a total amount bar chart by movement scope."""

    contract = TABLE_CONTRACTS.get(table_name)
    if not contract:
        return None
    amount_col = contract["amount_col"]
    if df.empty or amount_col not in df.columns or MOVEMENT_COL not in df.columns:
        return None
    work = df[[MOVEMENT_COL, amount_col]].copy()
    selected = select_movement_scopes(work, amount_col, movement_scopes, top_n)
    if selected:
        work = work.loc[work[MOVEMENT_COL].astype(str).isin(selected)]
    summary = (
        work.groupby(MOVEMENT_COL, dropna=False, observed=True)[amount_col]
        .sum()
        .reset_index()
        .sort_values(amount_col, key=lambda s: s.abs(), ascending=False)
    )
    if summary.empty:
        return None
    fig = px.bar(summary, x=MOVEMENT_COL, y=amount_col, title=f"{entity} - {table_name}: total amount by movement")
    fig.update_layout(width=width, height=height, xaxis_tickangle=45)
    return fig


def plot_total_count_by_movement(
    df: pd.DataFrame,
    table_name: str,
    entity: str = "all entities",
    movement_scopes: list[str] | None = None,
    top_n: int = 10,
    width: int = 1000,
    height: int = 560,
) -> go.Figure | None:
    """Build a total count bar chart by movement scope."""

    contract = TABLE_CONTRACTS.get(table_name)
    if not contract:
        return None
    count_col = contract["count_col"]
    if df.empty or count_col not in df.columns or MOVEMENT_COL not in df.columns:
        return None
    work = df[[MOVEMENT_COL, count_col]].copy()
    selected = select_movement_scopes(work, count_col, movement_scopes, top_n)
    if selected:
        work = work.loc[work[MOVEMENT_COL].astype(str).isin(selected)]
    summary = (
        work.groupby(MOVEMENT_COL, dropna=False, observed=True)[count_col]
        .sum()
        .reset_index()
        .sort_values(count_col, ascending=False)
    )
    if summary.empty:
        return None
    fig = px.bar(summary, x=MOVEMENT_COL, y=count_col, title=f"{entity} - {table_name}: total count by movement")
    fig.update_layout(width=width, height=height, xaxis_tickangle=45)
    return fig


def plot_lag_bucket_heatmap(
    lag_summary: pd.DataFrame,
    entity: str = "all entities",
    value_col: str = "SOURCE_ROWS",
    width: int = 1100,
    height: int = 620,
    percentage_decimals: int = 1,
) -> go.Figure | None:
    """Build a movement by lag-bucket heatmap."""

    required_cols = {TRADE_VALUE_LAG_BUCKET_COL, MOVEMENT_COL, value_col}
    if lag_summary.empty or not required_cols.issubset(lag_summary.columns):
        return None

    pivot = lag_summary.pivot_table(
        index=MOVEMENT_COL,
        columns=TRADE_VALUE_LAG_BUCKET_COL,
        values=value_col,
        aggfunc="sum",
        fill_value=0,
        observed=True,
    ).reindex(columns=LAG_BUCKET_ORDER, fill_value=0)
    if pivot.empty:
        return None

    row_totals = pivot.sum(axis=1).replace(0, pd.NA)
    row_percent = pivot.div(row_totals, axis=0).mul(100).fillna(0.0)

    def _format_value(value: float) -> str:
        if pd.isna(value):
            return "0"
        numeric = float(value)
        if numeric.is_integer():
            return f"{int(numeric):,}"
        return f"{numeric:,.2f}"

    text = pivot.copy().astype(object)
    for row_label in pivot.index:
        for bucket in pivot.columns:
            count_label = _format_value(pivot.loc[row_label, bucket])
            pct_label = f"{row_percent.loc[row_label, bucket]:.{percentage_decimals}f}%"
            text.loc[row_label, bucket] = (
                f"<b>{count_label}</b><br>"
                f"<span style='font-size:10px'>{pct_label}</span>"
            )

    customdata = pd.concat(
        [
            pivot.stack().rename("raw_value"),
            row_percent.stack().rename("row_percent"),
        ],
        axis=1,
    ).to_numpy().reshape(pivot.shape[0], pivot.shape[1], 2)

    fig = go.Figure(
        data=go.Heatmap(
            z=row_percent.to_numpy(),
            x=row_percent.columns.tolist(),
            y=row_percent.index.astype(str).tolist(),
            text=text.to_numpy(),
            texttemplate="%{text}",
            textfont={"size": 12},
            customdata=customdata,
            colorscale="Blues",
            zmin=0,
            zmax=100,
            colorbar={"title": "Row share (%)"},
            hovertemplate=(
                "Movement: %{y}<br>"
                "Trade timing: %{x}<br>"
                f"{value_col}: %{{customdata[0]:,.0f}}<br>"
                "Row share: %{customdata[1]:.1f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title=f"{entity} - Trade Date vs Value Date timing ({value_col}, row-normalized color)",
        xaxis_title="Trade timing",
        yaxis_title="Movement",
        width=width,
        height=height,
    )
    fig.update_xaxes(side="bottom", tickangle=35)
    return fig


def plot_known_vs_realized_coverage(
    realized_cash_in: pd.DataFrame,
    known_movements_daily: pd.DataFrame,
    entity: str = "all entities",
    width: int = 1100,
    height: int = 620,
) -> go.Figure | None:
    """Plot daily realized amount and known-at-cutoff amount."""

    if realized_cash_in.empty:
        return None
    keys = [ENTITY_COL, CURRENCY_COL, MOVEMENT_COL, SEQUENCE_ID_COLUMN, VALUE_DATE_COL]
    realized = realized_cash_in.copy()
    realized["CUTOFF_DATE"] = realized[VALUE_DATE_COL] - pd.Timedelta(days=1)
    known = known_movements_daily.copy()
    if not known.empty:
        known["CUTOFF_DATE"] = known[VALUE_DATE_COL] - pd.Timedelta(days=1)
        known = known.loc[known[TRADE_DATE_COL] <= known["CUTOFF_DATE"]]
        known_daily = known.groupby(keys, dropna=False, observed=True)[KNOWN_AMOUNT_COLUMN].sum().reset_index()
    else:
        known_daily = pd.DataFrame(columns=keys + [KNOWN_AMOUNT_COLUMN])

    daily = realized.merge(known_daily, on=keys, how="left")
    daily[KNOWN_AMOUNT_COLUMN] = daily[KNOWN_AMOUNT_COLUMN].fillna(0.0)
    daily = (
        daily.groupby(VALUE_DATE_COL, dropna=False)
        .agg(
            TARGET_AMOUNT=(TARGET_AMOUNT_COLUMN, "sum"),
            KNOWN_AT_CUTOFF_AMOUNT=(KNOWN_AMOUNT_COLUMN, "sum"),
        )
        .reset_index()
        .melt(id_vars=VALUE_DATE_COL, var_name="SERIES", value_name="AMOUNT")
    )
    if daily.empty:
        return None
    fig = px.line(daily, x=VALUE_DATE_COL, y="AMOUNT", color="SERIES", title=f"{entity} - realized vs known at D+1 cutoff")
    _standard_time_layout(fig, VALUE_DATE_COL, "AMOUNT", "SERIES", width, height)
    return fig


def plot_monthly_trend(
    realized_cash_in: pd.DataFrame,
    entity: str = "all entities",
    top_n: int = 10,
    width: int = 1100,
    height: int = 620,
) -> go.Figure | None:
    """Plot monthly realized totals by movement."""

    if realized_cash_in.empty:
        return None
    work = realized_cash_in[[VALUE_DATE_COL, MOVEMENT_COL, TARGET_AMOUNT_COLUMN]].copy()
    selected = select_movement_scopes(work, TARGET_AMOUNT_COLUMN, top_n=top_n)
    if selected:
        work = work.loc[work[MOVEMENT_COL].astype(str).isin(selected)]
    work["MONTH"] = work[VALUE_DATE_COL].dt.to_period("M").dt.to_timestamp()
    monthly = work.groupby(["MONTH", MOVEMENT_COL], dropna=False, observed=True)[TARGET_AMOUNT_COLUMN].sum().reset_index()
    if monthly.empty:
        return None
    fig = px.line(monthly, x="MONTH", y=TARGET_AMOUNT_COLUMN, color=MOVEMENT_COL, title=f"{entity} - monthly realized trend")
    _standard_time_layout(fig, "MONTH", TARGET_AMOUNT_COLUMN, MOVEMENT_COL, width, height)
    return fig


def plot_weekday_profile(
    realized_cash_in: pd.DataFrame,
    entity: str = "all entities",
    width: int = 1000,
    height: int = 560,
) -> go.Figure | None:
    """Plot average absolute amount by weekday."""

    if realized_cash_in.empty:
        return None
    work = realized_cash_in[[VALUE_DATE_COL, MOVEMENT_COL, TARGET_AMOUNT_COLUMN]].copy()
    work["WEEKDAY"] = work[VALUE_DATE_COL].dt.day_name()
    work["WEEKDAY_NUM"] = work[VALUE_DATE_COL].dt.dayofweek
    work["ABS_TARGET_AMOUNT"] = work[TARGET_AMOUNT_COLUMN].abs()
    summary = (
        work.groupby(["WEEKDAY_NUM", "WEEKDAY"], dropna=False, observed=True)["ABS_TARGET_AMOUNT"]
        .mean()
        .reset_index()
        .sort_values("WEEKDAY_NUM")
    )
    if summary.empty:
        return None
    fig = px.bar(summary, x="WEEKDAY", y="ABS_TARGET_AMOUNT", title=f"{entity} - average absolute amount by weekday")
    fig.update_layout(width=width, height=height)
    return fig


def plot_top_spike_days(
    spike_days: pd.DataFrame,
    entity: str = "all entities",
    width: int = 1100,
    height: int = 620,
) -> go.Figure | None:
    """Plot largest spike days."""

    if spike_days.empty:
        return None
    work = spike_days.copy()
    work["LABEL"] = (
        work[VALUE_DATE_COL].dt.strftime("%Y-%m-%d")
        + " | "
        + work[MOVEMENT_COL].astype(str)
        + " | "
        + work[CURRENCY_COL].astype(str)
    )
    fig = px.bar(
        work.sort_values("ABS_TARGET_AMOUNT", ascending=True),
        x="ABS_TARGET_AMOUNT",
        y="LABEL",
        orientation="h",
        color=MOVEMENT_COL if MOVEMENT_COL in work.columns else None,
        title=f"{entity} - top absolute realized days",
    )
    fig.update_layout(width=width, height=height, yaxis_title="")
    return fig


def _rule_step(step_name: str, frame: pd.DataFrame) -> dict[str, object]:
    return {
        RULE_STEP_COL: step_name,
        "ROWS": len(frame),
        "SIGNED_AMOUNT": _sum_numeric(frame, "SIGNED_AMOUNT"),
        "ABS_SIGNED_AMOUNT": _sum_abs_numeric(frame, "SIGNED_AMOUNT"),
        "ENTITY_COUNT": _nunique(frame, ENTITY_COL),
        "CURRENCY_COUNT": _nunique(frame, CURRENCY_COL),
        "MOVEMENT_TYPE_COUNT": _nunique(frame, MOVEMENT_TYPE_COL),
    }


def _sum_numeric(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).sum())


def _sum_abs_numeric(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).abs().sum())


def _nunique(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(frame[column].nunique(dropna=True))


def _safe_divide(numerator: pd.Series | float, denominator: pd.Series | float) -> pd.Series | float:
    if isinstance(denominator, pd.Series):
        return numerator.divide(denominator.where(denominator != 0))
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _standard_time_layout(
    fig: go.Figure,
    x_title: str,
    y_title: str,
    legend_title: str,
    width: int,
    height: int,
) -> None:
    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
        legend_title_text=legend_title,
        width=width,
        height=height,
        hovermode="x unified",
    )
    fig.update_xaxes(rangeslider_visible=True)
