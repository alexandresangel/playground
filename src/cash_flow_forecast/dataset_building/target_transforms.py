from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.preprocessing import PowerTransformer


TARGET_TRANSFORM_NONE = "none"
TARGET_TRANSFORM_LOG1P = "log1p"
TARGET_TRANSFORM_BOX_COX = "box_cox"
TARGET_TRANSFORM_YEO_JOHNSON = "yeo_johnson"
TargetTransformName = Literal["none", "log1p", "box_cox", "yeo_johnson"]


@dataclass
class FittedTargetTransformer:
    """Fold-local target transformer used by dataset building and backtest inversion."""

    name: str
    shift: float = 0.0
    identity_fallback: bool = False
    power_transformer: PowerTransformer | None = None

    def transform_series(self, values: pd.Series, *, context: str = "target") -> pd.Series:
        numeric = _numeric_series(values)
        if self.name == TARGET_TRANSFORM_NONE or self.identity_fallback:
            return numeric
        if self.name == TARGET_TRANSFORM_LOG1P:
            _validate_log1p_domain(numeric)
            return numeric.map(math.log1p).astype(float)
        if self.name == TARGET_TRANSFORM_BOX_COX:
            shifted = numeric + self.shift
            _validate_box_cox_domain(shifted, context)
            return _transform_power_series(numeric, shifted, self.power_transformer)
        if self.name == TARGET_TRANSFORM_YEO_JOHNSON:
            return _transform_power_series(numeric, numeric, self.power_transformer)
        raise ValueError(f"Unsupported target transform: {self.name!r}")

    def inverse_series(self, values: pd.Series) -> pd.Series:
        numeric = _numeric_series(values)
        if self.name == TARGET_TRANSFORM_NONE or self.identity_fallback:
            return numeric
        if self.name == TARGET_TRANSFORM_LOG1P:
            return numeric.map(math.expm1).astype(float)
        if self.name == TARGET_TRANSFORM_BOX_COX:
            if self.power_transformer is None:
                raise ValueError("Box-Cox target transformer is not fitted.")
            restored = self.power_transformer.inverse_transform(_as_2d(numeric)).reshape(-1) - self.shift
            return pd.Series(restored, index=numeric.index, dtype="float64")
        if self.name == TARGET_TRANSFORM_YEO_JOHNSON:
            if self.power_transformer is None:
                raise ValueError("Yeo-Johnson target transformer is not fitted.")
            restored = self.power_transformer.inverse_transform(_as_2d(numeric)).reshape(-1)
            return pd.Series(restored, index=numeric.index, dtype="float64")
        raise ValueError(f"Unsupported target transform: {self.name!r}")


def fit_target_transformer(values: pd.Series, target_transform: str) -> FittedTargetTransformer:
    """Fit a target transformer from raw training target values."""

    name = str(target_transform)
    numeric = _numeric_series(values)
    if name in {TARGET_TRANSFORM_NONE, TARGET_TRANSFORM_LOG1P}:
        return FittedTargetTransformer(name=name)
    if name == TARGET_TRANSFORM_BOX_COX:
        if numeric.empty or numeric.nunique(dropna=False) <= 1:
            return FittedTargetTransformer(name=name, identity_fallback=True)
        shift = max(0.0, 1e-6 - float(numeric.min()))
        shifted = numeric + shift
        _validate_box_cox_domain(shifted, "Box-Cox training target")
        transformer = PowerTransformer(method="box-cox", standardize=False)
        try:
            transformer.fit(_as_2d(shifted))
        except ValueError as exc:
            if numeric.nunique(dropna=False) <= 1:
                return FittedTargetTransformer(name=name, identity_fallback=True)
            raise ValueError(f"Could not fit Box-Cox target transform: {exc}") from exc
        return FittedTargetTransformer(name=name, shift=shift, power_transformer=transformer)
    if name == TARGET_TRANSFORM_YEO_JOHNSON:
        if numeric.empty:
            return FittedTargetTransformer(name=name, identity_fallback=True)
        transformer = PowerTransformer(method="yeo-johnson", standardize=False)
        transformer.fit(_as_2d(numeric))
        return FittedTargetTransformer(name=name, power_transformer=transformer)
    raise ValueError(f"Unsupported target transform: {target_transform!r}")


def transform_target_series(
    values: pd.Series,
    target_transform: str,
    fitted_transformer: FittedTargetTransformer | None = None,
    *,
    context: str = "target",
) -> pd.Series:
    """Transform target amounts after point-in-time filtering and aggregation."""

    transformer = fitted_transformer or fit_target_transformer(pd.Series(dtype="float64"), target_transform)
    return transformer.transform_series(values, context=context)


def transform_target_amount(
    value: float,
    target_transform: str,
    fitted_transformer: FittedTargetTransformer | None = None,
    *,
    context: str = "target amount",
) -> float:
    """Transform one point-in-time safe, already-aggregated target amount."""

    return float(
        transform_target_series(
            pd.Series([value]),
            target_transform,
            fitted_transformer,
            context=context,
        ).iloc[0]
    )


def inverse_transform_target_series(
    values: pd.Series,
    target_transform: str,
    fitted_transformer: FittedTargetTransformer | None = None,
) -> pd.Series:
    """Return target-space values on the original cash amount scale."""

    transformer = fitted_transformer or fit_target_transformer(pd.Series(dtype="float64"), target_transform)
    return transformer.inverse_series(values)


def requires_fitted_target_transformer(target_transform: str) -> bool:
    return target_transform in {TARGET_TRANSFORM_BOX_COX, TARGET_TRANSFORM_YEO_JOHNSON}


def _numeric_series(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").fillna(0.0).astype(float)


def _as_2d(values: pd.Series) -> np.ndarray:
    return values.to_numpy(dtype="float64").reshape(-1, 1)


def _transform_power_series(
    original: pd.Series,
    values_for_transform: pd.Series,
    transformer: PowerTransformer | None,
) -> pd.Series:
    if transformer is None:
        raise ValueError("Target power transformer is not fitted.")
    transformed = transformer.transform(_as_2d(values_for_transform)).reshape(-1)
    return pd.Series(transformed, index=original.index, dtype="float64")


def _validate_log1p_domain(values: pd.Series) -> None:
    invalid = values < -1
    if invalid.any():
        minimum = float(values.min())
        raise ValueError(
            "target_transform='log1p' requires aggregated target amounts >= -1; "
            f"minimum observed value was {minimum}."
        )


def _validate_box_cox_domain(values: pd.Series, context: str) -> None:
    invalid = values <= 0.0
    if invalid.any():
        minimum = float(values.min())
        raise ValueError(
            "target_transform='box_cox' requires values to be positive after the fold shift; "
            f"{context} minimum after shift was {minimum}."
        )
