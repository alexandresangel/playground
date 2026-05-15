from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal
import numpy as np
import pandas as pd

from cash_flow_forecast.modeling.features import feature_frame, numeric_feature_columns


EstimatorRole = Literal["classifier", "regressor"]


class SupervisedRegressor:
    """Small tabular regressor protocol used by composite forecast models."""

    model_name: str

    def fit(self, frame: pd.DataFrame, target: pd.Series) -> "SupervisedRegressor":
        raise NotImplementedError

    def predict(self, frame: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    def model_info(self) -> dict[str, object]:
        raise NotImplementedError


class SupervisedClassifier:
    """Small binary classifier protocol used by composite forecast models."""

    model_name: str

    def fit(self, frame: pd.DataFrame, target: pd.Series) -> "SupervisedClassifier":
        raise NotImplementedError

    def predict_proba_positive(self, frame: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    def model_info(self) -> dict[str, object]:
        raise NotImplementedError


@dataclass(frozen=True)
class RegisteredSupervisedEstimator:
    role: EstimatorRole
    factory: Callable[..., SupervisedClassifier | SupervisedRegressor]


class _FeatureSelectingRegressor(SupervisedRegressor):
    model_name: str

    def __init__(self, **parameters: object) -> None:
        self.parameters = dict(self.default_parameters())
        self.parameters.update(parameters)
        self.feature_columns_: list[str] = []
        self.fallback_ = 0.0
        self.model_: object | None = None

    @staticmethod
    def default_parameters() -> dict[str, object]:
        return {}

    def fit(self, frame: pd.DataFrame, target: pd.Series) -> "_FeatureSelectingRegressor":
        numeric_target = pd.to_numeric(target, errors="coerce").fillna(0.0).astype(float)
        self.fallback_ = float(numeric_target.mean()) if not numeric_target.empty else 0.0
        self.feature_columns_ = numeric_feature_columns(frame)
        if frame.empty or not self.feature_columns_:
            return self
        self._fit_model(feature_frame(frame, self.feature_columns_), numeric_target)
        return self

    def predict(self, frame: pd.DataFrame) -> pd.Series:
        if self.model_ is None or not self.feature_columns_:
            return pd.Series(self.fallback_, index=frame.index, dtype="float64")
        return pd.Series(
            self._predict_model(feature_frame(frame, self.feature_columns_)),
            index=frame.index,
            dtype="float64",
        )

    def model_info(self) -> dict[str, object]:
        return {
            "model_name": self.model_name,
            "role": "regressor",
            "parameters": self.parameters,
        }

    def _fit_model(self, x_train: pd.DataFrame, y_train: pd.Series) -> None:
        raise NotImplementedError

    def _predict_model(self, x_inference: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError


class _FeatureSelectingClassifier(SupervisedClassifier):
    model_name: str

    def __init__(self, **parameters: object) -> None:
        self.parameters = dict(self.default_parameters())
        self.parameters.update(parameters)
        self.feature_columns_: list[str] = []
        self.fallback_probability_ = 0.0
        self.model_: object | None = None

    @staticmethod
    def default_parameters() -> dict[str, object]:
        return {}

    def fit(self, frame: pd.DataFrame, target: pd.Series) -> "_FeatureSelectingClassifier":
        binary_target = pd.to_numeric(target, errors="coerce").fillna(0).astype(int).clip(0, 1)
        self.fallback_probability_ = float(binary_target.mean()) if not binary_target.empty else 0.0
        self.feature_columns_ = numeric_feature_columns(frame)
        if frame.empty or not self.feature_columns_ or binary_target.nunique() < 2:
            return self
        self._fit_model(feature_frame(frame, self.feature_columns_), binary_target)
        return self

    def predict_proba_positive(self, frame: pd.DataFrame) -> pd.Series:
        if self.model_ is None or not self.feature_columns_:
            return pd.Series(self.fallback_probability_, index=frame.index, dtype="float64")
        return pd.Series(
            self._predict_positive_model(feature_frame(frame, self.feature_columns_)),
            index=frame.index,
            dtype="float64",
        ).clip(0.0, 1.0)

    def model_info(self) -> dict[str, object]:
        return {
            "model_name": self.model_name,
            "role": "classifier",
            "parameters": self.parameters,
        }

    def _fit_model(self, x_train: pd.DataFrame, y_train: pd.Series) -> None:
        raise NotImplementedError

    def _predict_positive_model(self, x_inference: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError


class LightGBMSupervisedRegressor(_FeatureSelectingRegressor):
    model_name = "lightgbm_regressor"

    @staticmethod
    def default_parameters() -> dict[str, object]:
        return {
            "n_estimators": 100,
            "num_leaves": 31,
            "learning_rate": 0.05,
            "random_state": 0,
            "n_jobs": 1,
            "verbosity": -1,
        }

    def _fit_model(self, x_train: pd.DataFrame, y_train: pd.Series) -> None:
        from lightgbm import LGBMRegressor

        try:
            self.model_ = LGBMRegressor(**self.parameters)
            self.model_.fit(x_train, y_train)
        except Exception as exc:
            self.model_ = None
            raise RuntimeError(
                "LightGBM supervised regressor failed to fit. Check the estimator parameters "
                "and training feature values."
            ) from exc

    def _predict_model(self, x_inference: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.model_.predict(x_inference), dtype=float)


class XGBoostSupervisedRegressor(_FeatureSelectingRegressor):
    model_name = "xgboost_regressor"

    @staticmethod
    def default_parameters() -> dict[str, object]:
        return {
            "n_estimators": 50,
            "max_depth": 3,
            "learning_rate": 0.05,
            "objective": "reg:squarederror",
            "random_state": 0,
            "n_jobs": 1,
            "verbosity": 0,
        }

    def _fit_model(self, x_train: pd.DataFrame, y_train: pd.Series) -> None:
        import xgboost as xgb

        try:
            self.model_ = xgb.train(
                params={
                    "max_depth": self.parameters["max_depth"],
                    "eta": self.parameters["learning_rate"],
                    "objective": self.parameters["objective"],
                    "seed": self.parameters["random_state"],
                    "nthread": self.parameters["n_jobs"],
                    "verbosity": self.parameters["verbosity"],
                },
                dtrain=xgb.DMatrix(x_train, label=y_train),
                num_boost_round=int(self.parameters["n_estimators"]),
            )
        except Exception as exc:
            self.model_ = None
            raise RuntimeError(
                "XGBoost supervised regressor failed to fit. Check the estimator parameters "
                "and training feature values."
            ) from exc

    def _predict_model(self, x_inference: pd.DataFrame) -> np.ndarray:
        import xgboost as xgb

        return np.asarray(self.model_.predict(xgb.DMatrix(x_inference)), dtype=float)


class SklearnRidgeSupervisedRegressor(_FeatureSelectingRegressor):
    model_name = "sklearn_ridge_regressor"

    @staticmethod
    def default_parameters() -> dict[str, object]:
        return {"alpha": 1.0}

    def _fit_model(self, x_train: pd.DataFrame, y_train: pd.Series) -> None:
        from sklearn.linear_model import Ridge

        try:
            self.model_ = Ridge(**self.parameters)
            self.model_.fit(x_train, y_train)
        except Exception as exc:
            self.model_ = None
            raise RuntimeError(
                "Ridge supervised regressor failed to fit. Check the estimator parameters "
                "and training feature values."
            ) from exc

    def _predict_model(self, x_inference: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.model_.predict(x_inference), dtype=float)


class LightGBMSupervisedClassifier(_FeatureSelectingClassifier):
    model_name = "lightgbm_classifier"

    @staticmethod
    def default_parameters() -> dict[str, object]:
        return {
            "n_estimators": 100,
            "num_leaves": 31,
            "learning_rate": 0.05,
            "random_state": 0,
            "n_jobs": 1,
            "verbosity": -1,
        }

    def _fit_model(self, x_train: pd.DataFrame, y_train: pd.Series) -> None:
        from lightgbm import LGBMClassifier

        try:
            self.model_ = LGBMClassifier(**self.parameters)
            self.model_.fit(x_train, y_train)
        except Exception as exc:
            self.model_ = None
            raise RuntimeError(
                "LightGBM supervised classifier failed to fit. Check the estimator parameters "
                "and training feature values."
            ) from exc

    def _predict_positive_model(self, x_inference: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.model_.predict_proba(x_inference)[:, 1], dtype=float)


class XGBoostSupervisedClassifier(_FeatureSelectingClassifier):
    model_name = "xgboost_classifier"

    @staticmethod
    def default_parameters() -> dict[str, object]:
        return {
            "n_estimators": 50,
            "max_depth": 3,
            "learning_rate": 0.05,
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "random_state": 0,
            "n_jobs": 1,
            "verbosity": 0,
        }

    def _fit_model(self, x_train: pd.DataFrame, y_train: pd.Series) -> None:
        from xgboost import XGBClassifier

        try:
            self.model_ = XGBClassifier(**self.parameters)
            self.model_.fit(x_train, y_train)
        except Exception as exc:
            self.model_ = None
            raise RuntimeError(
                "XGBoost supervised classifier failed to fit. Check the estimator parameters "
                "and training feature values."
            ) from exc

    def _predict_positive_model(self, x_inference: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.model_.predict_proba(x_inference)[:, 1], dtype=float)


class SklearnLogisticSupervisedClassifier(_FeatureSelectingClassifier):
    model_name = "sklearn_logistic_classifier"

    @staticmethod
    def default_parameters() -> dict[str, object]:
        return {
            "max_iter": 1000,
            "class_weight": "balanced",
            "random_state": 0,
        }

    def _fit_model(self, x_train: pd.DataFrame, y_train: pd.Series) -> None:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        try:
            self.model_ = make_pipeline(
                StandardScaler(),
                LogisticRegression(**self.parameters),
            )
            self.model_.fit(x_train, y_train)
        except Exception as exc:
            self.model_ = None
            raise RuntimeError(
                "Logistic supervised classifier failed to fit. Check the estimator parameters "
                "and training feature values."
            ) from exc

    def _predict_positive_model(self, x_inference: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.model_.predict_proba(x_inference)[:, 1], dtype=float)


SUPERVISED_REGISTRY: dict[str, RegisteredSupervisedEstimator] = {
    "lightgbm_regressor": RegisteredSupervisedEstimator(
        role="regressor",
        factory=LightGBMSupervisedRegressor,
    ),
    "xgboost_regressor": RegisteredSupervisedEstimator(
        role="regressor",
        factory=XGBoostSupervisedRegressor,
    ),
    "sklearn_ridge_regressor": RegisteredSupervisedEstimator(
        role="regressor",
        factory=SklearnRidgeSupervisedRegressor,
    ),
    "lightgbm_classifier": RegisteredSupervisedEstimator(
        role="classifier",
        factory=LightGBMSupervisedClassifier,
    ),
    "xgboost_classifier": RegisteredSupervisedEstimator(
        role="classifier",
        factory=XGBoostSupervisedClassifier,
    ),
    "sklearn_logistic_classifier": RegisteredSupervisedEstimator(
        role="classifier",
        factory=SklearnLogisticSupervisedClassifier,
    ),
}


def create_supervised_regressor(name: str, parameters: dict[str, object] | None = None) -> SupervisedRegressor:
    registered = _registered_supervised_estimator(name)
    if registered.role != "regressor":
        raise ValueError(f"Supervised estimator {name!r} is not a regressor.")
    return registered.factory(**(parameters or {}))


def create_supervised_classifier(name: str, parameters: dict[str, object] | None = None) -> SupervisedClassifier:
    registered = _registered_supervised_estimator(name)
    if registered.role != "classifier":
        raise ValueError(f"Supervised estimator {name!r} is not a classifier.")
    return registered.factory(**(parameters or {}))


def supervised_estimator_role(name: str) -> EstimatorRole:
    return _registered_supervised_estimator(name).role


def available_supervised_estimator_names(role: EstimatorRole | None = None) -> list[str]:
    return [
        name
        for name, registered in SUPERVISED_REGISTRY.items()
        if role is None or registered.role == role
    ]


def _registered_supervised_estimator(name: str) -> RegisteredSupervisedEstimator:
    try:
        return SUPERVISED_REGISTRY[name]
    except KeyError as exc:
        options = ", ".join(sorted(SUPERVISED_REGISTRY))
        raise ValueError(f"Unknown supervised estimator {name!r}. Available estimators: {options}.") from exc
