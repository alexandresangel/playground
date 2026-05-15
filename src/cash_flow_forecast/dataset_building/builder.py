from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

from cash_flow_forecast.contracts.builders import (
    DatasetBuildRequest,
    DatasetBuildResult,
    DatasetManifest,
    GoldBuildResult,
    RollingWindowFeatureConfig,
)
from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.data_layers.gold.builder import (
    DATE_COLUMN,
    KNOWN_AMOUNT_COLUMN,
    KNOWN_COUNT_COLUMN,
    SEQUENCE_ID_COLUMN,
    TARGET_AMOUNT_COLUMN,
)
from cash_flow_forecast.dataset_building.target_transforms import (
    FittedTargetTransformer,
    TARGET_TRANSFORM_BOX_COX,
    TARGET_TRANSFORM_LOG1P,
    TARGET_TRANSFORM_NONE,
    TARGET_TRANSFORM_YEO_JOHNSON,
    fit_target_transformer,
    inverse_transform_target_series,
    requires_fitted_target_transformer,
    transform_target_amount,
    transform_target_series,
)


FORECAST_HORIZON_DAYS = 1
CALENDAR_COLUMNS = ["DAY_OF_WEEK", "DAY_OF_MONTH", "IS_MONTH_END", "IS_MONTH_START", "IS_WEEKEND"]
FEATURE_POLICY = "TRADE_DATE <= CUTOFF_DATE"
TRAINING_LABEL_POLICY = "TRADE_DATE <= EVALUATION_CUTOFF"
FINAL_LABEL_POLICY = "final realized VALUE_DATE totals"


@dataclass
class DatasetContext:
    """Reusable one-sequence state for live point-in-time dataset assembly."""

    label_panel: pd.DataFrame
    sequence_known: pd.DataFrame
    all_known: pd.DataFrame
    sequence_row: pd.Series
    calendar_daily: pd.DataFrame


class DatasetBuilder:
    """Assemble live point-in-time datasets from reusable Gold outputs."""

    def build(self, request: DatasetBuildRequest) -> DatasetBuildResult:
        """Build a D+1 dataset for exactly one sequence and one dataset kind."""

        request = self._request_with_target_transformer(request)
        context = self._build_context(request)
        dataframe = self._build_frame(request, context)
        feature_columns = [
            column
            for column in dataframe.columns
            if column not in self._id_columns(request) + [TARGET_AMOUNT_COLUMN]
        ]
        manifest = DatasetManifest(
            dataset_kind=request.dataset.kind,
            ruleset_id=request.ruleset.ruleset_id,
            cutoff_dates=request.cutoff_dates,
            forecast_horizon_days=FORECAST_HORIZON_DAYS,
            sequence_id=request.sequence_id,
            label_as_of_date=request.label_as_of_date,
            feature_policy=FEATURE_POLICY,
            training_label_policy=TRAINING_LABEL_POLICY if request.label_as_of_date else FINAL_LABEL_POLICY,
            history_window_days=request.dataset.history_window_days,
            target_transform=request.dataset.target_transform,
            row_count=len(dataframe),
            sequence_count=1 if not dataframe.empty else 0,
            feature_columns=feature_columns,
            source_tables=[
                "realized_cash_in",
                "known_movements_daily",
                "sequence_reference",
                "calendar_daily",
            ],
        )
        return DatasetBuildResult(dataframe=dataframe, manifest=manifest)

    def _request_with_target_transformer(self, request: DatasetBuildRequest) -> DatasetBuildRequest:
        if request.target_transformer is not None:
            return request
        if not requires_fitted_target_transformer(request.dataset.target_transform):
            transformer = fit_target_transformer(pd.Series(dtype="float64"), request.dataset.target_transform)
            return request.model_copy(update={"target_transformer": transformer})

        raw_dataset = request.dataset.model_copy(update={"target_transform": TARGET_TRANSFORM_NONE})
        raw_request = request.model_copy(
            update={
                "dataset": raw_dataset,
                "target_transformer": fit_target_transformer(
                    pd.Series(dtype="float64"),
                    TARGET_TRANSFORM_NONE,
                ),
            }
        )
        raw_context = self._build_context(raw_request)
        raw_frame = self._build_frame(raw_request, raw_context)
        raw_target = (
            raw_frame[TARGET_AMOUNT_COLUMN]
            if TARGET_AMOUNT_COLUMN in raw_frame.columns
            else pd.Series(dtype="float64")
        )
        transformer = fit_target_transformer(raw_target, request.dataset.target_transform)
        return request.model_copy(update={"target_transformer": transformer})

    def _build_frame(self, request: DatasetBuildRequest, context: DatasetContext) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        cutoff_dates = [pd.Timestamp(cutoff).normalize() for cutoff in request.cutoff_dates]

        for cutoff_date in cutoff_dates:
            forecast_date = cutoff_date + pd.Timedelta(days=FORECAST_HORIZON_DAYS)
            target_row = context.label_panel.loc[context.label_panel[DATE_COLUMN] == forecast_date]
            if target_row.empty:
                continue

            try:
                available_panel = (
                    self._available_target_panel(
                        context.sequence_known,
                        context.calendar_daily,
                        request,
                        cutoff_date,
                    )
                    if self._needs_target_history_panel(request)
                    else pd.DataFrame(columns=[DATE_COLUMN, TARGET_AMOUNT_COLUMN])
                )
                row = self._base_row(request, context, cutoff_date, forecast_date, target_row.iloc[0])
            except ValueError as exc:
                raise ValueError(
                    f"Failed to transform target values for cutoff={cutoff_date.date()} "
                    f"with target_transform={request.dataset.target_transform!r}: {exc}"
                ) from exc
            row.update(self._features_for_kind(request, context, available_panel, cutoff_date, forecast_date))
            rows.append(row)

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values("CUTOFF_DATE", ignore_index=True)

    def _base_row(
        self,
        request: DatasetBuildRequest,
        context: DatasetContext,
        cutoff_date: pd.Timestamp,
        forecast_date: pd.Timestamp,
        target_row: pd.Series,
    ) -> dict[str, object]:
        sequence_columns = request.ruleset.sequence_columns + [SEQUENCE_ID_COLUMN]
        row = {column: context.sequence_row[column] for column in sequence_columns}
        row["CUTOFF_DATE"] = cutoff_date
        row["FORECAST_DATE"] = forecast_date
        row[TARGET_AMOUNT_COLUMN] = transform_target_amount(
            float(target_row[TARGET_AMOUNT_COLUMN]),
            request.dataset.target_transform,
            request.target_transformer,
            context="row target amount",
        )
        return row

    def _features_for_kind(
        self,
        request: DatasetBuildRequest,
        context: DatasetContext,
        available_panel: pd.DataFrame,
        cutoff_date: pd.Timestamp,
        forecast_date: pd.Timestamp,
    ) -> dict[str, object]:
        if request.dataset.kind is DatasetKind.TIME_SERIES:
            return self._time_series_features(request, available_panel, cutoff_date, forecast_date)
        return self._tabular_features(request, context, available_panel, cutoff_date, forecast_date)

    def _time_series_features(
        self,
        request: DatasetBuildRequest,
        available_panel: pd.DataFrame,
        cutoff_date: pd.Timestamp,
        forecast_date: pd.Timestamp,
    ) -> dict[str, object]:
        features = request.dataset.features
        return {
            **self._target_lag_features(available_panel, features.target_lags, forecast_date),
            **self._rolling_features(request, available_panel, features.rolling_windows, cutoff_date),
        }

    def _tabular_features(
        self,
        request: DatasetBuildRequest,
        context: DatasetContext,
        available_panel: pd.DataFrame,
        cutoff_date: pd.Timestamp,
        forecast_date: pd.Timestamp,
    ) -> dict[str, object]:
        features = request.dataset.features
        row_features: dict[str, object] = {}
        if features.calendar:
            row_features.update(self._calendar_features(context.label_panel, forecast_date))
        row_features.update(self._target_lag_features(available_panel, features.target_lags, forecast_date))
        rolling_features = self._rolling_features(request, available_panel, features.rolling_windows, cutoff_date)
        row_features.update(rolling_features)
        if features.known_d1:
            known_features = self._known_state_features(request, context.sequence_known, cutoff_date, forecast_date)
            row_features.update(known_features)
        if features.cross_movement_known.enabled:
            row_features.update(self._cross_movement_known_features(request, context, cutoff_date, forecast_date))
        return row_features

    @staticmethod
    def _needs_target_history_panel(request: DatasetBuildRequest) -> bool:
        features = request.dataset.features
        return bool(features.target_lags or features.rolling_windows)

    def _calendar_features(self, label_panel: pd.DataFrame, forecast_date: pd.Timestamp) -> dict[str, object]:
        target_row = label_panel.loc[label_panel[DATE_COLUMN] == forecast_date]
        if target_row.empty:
            return {}
        return {column: target_row.iloc[0][column] for column in CALENDAR_COLUMNS}

    def _target_lag_features(
        self,
        available_panel: pd.DataFrame,
        lags: list[int],
        forecast_date: pd.Timestamp,
    ) -> dict[str, float]:
        return {
            f"TARGET_LAG_{lag}": self._target_for_date(available_panel, forecast_date - pd.Timedelta(days=lag))
            for lag in lags
        }

    def _rolling_features(
        self,
        request: DatasetBuildRequest,
        available_panel: pd.DataFrame,
        rolling_windows: list[RollingWindowFeatureConfig],
        cutoff_date: pd.Timestamp,
    ) -> dict[str, float]:
        history_start = cutoff_date - pd.Timedelta(days=request.dataset.history_window_days - 1)
        history = available_panel.loc[
            (available_panel[DATE_COLUMN] >= history_start)
            & (available_panel[DATE_COLUMN] <= cutoff_date)
        ]
        result: dict[str, float] = {}
        for window in rolling_windows:
            # available_panel is already in target-modeling space, so mean/std stay
            # consistent with TARGET_AMOUNT and lags when a transform is enabled.
            values = history.tail(window.days)[TARGET_AMOUNT_COLUMN]
            for aggregation in window.aggregations:
                if aggregation == "mean":
                    result[f"TARGET_ROLLING_MEAN_{window.days}"] = float(values.mean()) if not values.empty else 0.0
                elif aggregation == "std":
                    result[f"TARGET_STD_{window.days}"] = float(values.std(ddof=0)) if not values.empty else 0.0
                elif aggregation == "non_zero_ratio":
                    result[f"TARGET_NON_ZERO_RATIO_{window.days}"] = (
                        float((values != 0).mean()) if not values.empty else 0.0
                    )
                else:
                    raise ValueError(f"Unsupported rolling aggregation: {aggregation!r}")
        return result

    def _known_state_features(
        self,
        request: DatasetBuildRequest,
        sequence_known: pd.DataFrame,
        cutoff_date: pd.Timestamp,
        forecast_date: pd.Timestamp,
    ) -> dict[str, float]:
        filtered = self._known_for_forecast_date(request, sequence_known, cutoff_date, forecast_date)
        return self._known_amount_count_features(filtered, prefix="KNOWN", request=request)

    def _cross_movement_known_features(
        self,
        request: DatasetBuildRequest,
        context: DatasetContext,
        cutoff_date: pd.Timestamp,
        forecast_date: pd.Timestamp,
    ) -> dict[str, float]:
        if context.all_known.empty:
            return self._known_amount_count_features(
                context.all_known,
                prefix="CROSS_MOVEMENT_KNOWN",
                request=request,
            )

        entity_column = request.ruleset.entity_column
        currency_column = request.ruleset.currency_column
        movement_column = request.ruleset.movement_scope_column
        other_known = context.all_known.loc[
            (context.all_known[entity_column] == context.sequence_row[entity_column])
            & (context.all_known[currency_column] == context.sequence_row[currency_column])
            & (context.all_known[movement_column] != context.sequence_row[movement_column])
        ]
        filtered = self._known_for_forecast_date(request, other_known, cutoff_date, forecast_date)
        return self._known_amount_count_features(filtered, prefix="CROSS_MOVEMENT_KNOWN", request=request)

    def _known_for_forecast_date(
        self,
        request: DatasetBuildRequest,
        known: pd.DataFrame,
        cutoff_date: pd.Timestamp,
        forecast_date: pd.Timestamp,
    ) -> pd.DataFrame:
        if known.empty:
            return known
        return known.loc[
            (known[request.ruleset.truth_date_column] == forecast_date)
            & (known[request.ruleset.availability_date_column] <= cutoff_date)
        ]

    def _known_amount_count_features(
        self,
        known: pd.DataFrame,
        prefix: str,
        request: DatasetBuildRequest,
    ) -> dict[str, float]:
        amount = float(known[KNOWN_AMOUNT_COLUMN].sum()) if not known.empty else 0.0
        count = int(known[KNOWN_COUNT_COLUMN].sum()) if not known.empty else 0
        return {
            f"{prefix}_AMOUNT_D1": transform_target_amount(
                amount,
                request.dataset.target_transform,
                request.target_transformer,
                context=f"{prefix}_AMOUNT_D1",
            ),
            f"{prefix}_COUNT_D1": count,
        }

    def _available_target_panel(
        self,
        sequence_known: pd.DataFrame,
        calendar_daily: pd.DataFrame,
        request: DatasetBuildRequest,
        cutoff_date: pd.Timestamp,
    ) -> pd.DataFrame:
        calendar = calendar_daily[[DATE_COLUMN]].copy()
        if sequence_known.empty:
            panel = calendar
            panel[TARGET_AMOUNT_COLUMN] = 0.0
            panel[TARGET_AMOUNT_COLUMN] = transform_target_series(
                panel[TARGET_AMOUNT_COLUMN],
                request.dataset.target_transform,
                request.target_transformer,
                context="available target panel",
            )
            return panel

        available = sequence_known.loc[
            sequence_known[request.ruleset.availability_date_column] <= cutoff_date
        ]
        target_by_date = (
            available.groupby(request.ruleset.truth_date_column, dropna=False, observed=True)[KNOWN_AMOUNT_COLUMN]
            .sum()
            .reset_index()
            .rename(
                columns={
                    request.ruleset.truth_date_column: DATE_COLUMN,
                    KNOWN_AMOUNT_COLUMN: TARGET_AMOUNT_COLUMN,
                }
            )
        )
        panel = calendar.merge(target_by_date, on=DATE_COLUMN, how="left")
        panel[TARGET_AMOUNT_COLUMN] = panel[TARGET_AMOUNT_COLUMN].fillna(0.0).astype(float)
        panel[TARGET_AMOUNT_COLUMN] = transform_target_series(
            panel[TARGET_AMOUNT_COLUMN],
            request.dataset.target_transform,
            request.target_transformer,
            context="available target panel",
        )
        return panel

    def _build_context(self, request: DatasetBuildRequest) -> DatasetContext:
        gold = request.gold_outputs
        sequence_row = self._sequence_row(gold.sequence_reference, request)
        calendar_daily = self._normalized_calendar(gold.calendar_daily)
        all_known = self._normalized_known(gold.known_movements_daily, request)
        sequence_known = all_known.loc[all_known[SEQUENCE_ID_COLUMN].astype(str) == request.sequence_id].copy()
        label_panel = self._build_dense_label_panel(
            gold,
            request,
            sequence_row,
            sequence_known,
            calendar_daily,
        )
        return DatasetContext(
            label_panel=label_panel,
            sequence_known=sequence_known,
            all_known=all_known,
            sequence_row=sequence_row,
            calendar_daily=calendar_daily,
        )

    def _sequence_row(self, sequence_reference: pd.DataFrame, request: DatasetBuildRequest) -> pd.Series:
        matches = sequence_reference.loc[
            sequence_reference[SEQUENCE_ID_COLUMN].astype(str) == request.sequence_id
        ]
        matches = matches.drop_duplicates(subset=[SEQUENCE_ID_COLUMN])
        if len(matches) != 1:
            raise ValueError(
                f"Dataset build expected exactly one {SEQUENCE_ID_COLUMN}={request.sequence_id!r}, "
                f"got {len(matches)}."
            )
        return matches.iloc[0]

    def _normalized_calendar(self, calendar_daily: pd.DataFrame) -> pd.DataFrame:
        calendar = calendar_daily.copy()
        calendar[DATE_COLUMN] = pd.to_datetime(calendar[DATE_COLUMN]).dt.normalize()
        return calendar.sort_values(DATE_COLUMN).reset_index(drop=True)

    def _normalized_known(
        self,
        known_movements_daily: pd.DataFrame,
        request: DatasetBuildRequest,
    ) -> pd.DataFrame:
        known = known_movements_daily.copy()
        if known.empty:
            return known
        for column in [request.ruleset.truth_date_column, request.ruleset.availability_date_column]:
            known[column] = pd.to_datetime(known[column]).dt.normalize()
        return known.sort_values(
            [request.ruleset.availability_date_column, request.ruleset.truth_date_column],
            ignore_index=True,
        )

    def _build_dense_label_panel(
        self,
        gold: GoldBuildResult,
        request: DatasetBuildRequest,
        sequence_row: pd.Series,
        sequence_known: pd.DataFrame,
        calendar_daily: pd.DataFrame,
    ) -> pd.DataFrame:
        panel = pd.DataFrame({DATE_COLUMN: calendar_daily[DATE_COLUMN]})
        for column in CALENDAR_COLUMNS:
            panel[column] = calendar_daily[column]

        if request.label_as_of_date is None:
            observed = self._final_targets(gold, request)
        else:
            observed = self._labels_as_of(sequence_known, request)

        panel = panel.merge(observed, on=DATE_COLUMN, how="left")
        panel[TARGET_AMOUNT_COLUMN] = panel[TARGET_AMOUNT_COLUMN].fillna(0.0).astype(float)
        for column in request.ruleset.sequence_columns + [SEQUENCE_ID_COLUMN]:
            panel[column] = sequence_row[column]
        return panel.sort_values(DATE_COLUMN).reset_index(drop=True)

    def _final_targets(self, gold: GoldBuildResult, request: DatasetBuildRequest) -> pd.DataFrame:
        realized = gold.realized_cash_in.loc[
            gold.realized_cash_in[SEQUENCE_ID_COLUMN].astype(str) == request.sequence_id
        ].copy()
        if realized.empty:
            return pd.DataFrame(columns=[DATE_COLUMN, TARGET_AMOUNT_COLUMN])
        realized[request.ruleset.truth_date_column] = pd.to_datetime(
            realized[request.ruleset.truth_date_column]
        ).dt.normalize()
        return (
            realized.groupby(request.ruleset.truth_date_column, dropna=False, observed=True)[TARGET_AMOUNT_COLUMN]
            .sum()
            .reset_index()
            .rename(columns={request.ruleset.truth_date_column: DATE_COLUMN})
        )

    def _labels_as_of(
        self,
        sequence_known: pd.DataFrame,
        request: DatasetBuildRequest,
    ) -> pd.DataFrame:
        if sequence_known.empty:
            return pd.DataFrame(columns=[DATE_COLUMN, TARGET_AMOUNT_COLUMN])
        label_as_of_date = pd.Timestamp(request.label_as_of_date).normalize()
        available = sequence_known.loc[
            sequence_known[request.ruleset.availability_date_column] <= label_as_of_date
        ]
        if available.empty:
            return pd.DataFrame(columns=[DATE_COLUMN, TARGET_AMOUNT_COLUMN])
        return (
            available.groupby(request.ruleset.truth_date_column, dropna=False, observed=True)[KNOWN_AMOUNT_COLUMN]
            .sum()
            .reset_index()
            .rename(
                columns={
                    request.ruleset.truth_date_column: DATE_COLUMN,
                    KNOWN_AMOUNT_COLUMN: TARGET_AMOUNT_COLUMN,
                }
            )
        )

    def _id_columns(self, request: DatasetBuildRequest) -> list[str]:
        return [
            SEQUENCE_ID_COLUMN,
            "CUTOFF_DATE",
            "FORECAST_DATE",
            request.ruleset.entity_column,
            request.ruleset.currency_column,
            request.ruleset.movement_scope_column,
        ]

    @staticmethod
    def _target_for_date(target_panel: pd.DataFrame, target_date: pd.Timestamp) -> float:
        row = target_panel.loc[target_panel[DATE_COLUMN] == target_date]
        if row.empty:
            return 0.0
        return float(row.iloc[0][TARGET_AMOUNT_COLUMN])
