"""Interpretable transaction baselines and graph-enhanced comparators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.evaluation.splits import BASELINE_FEATURES, GRAPH_FEATURES


@dataclass
class FittedModel:
    name: str
    estimator: Any
    features: tuple[str, ...]

    def probabilities(self, frame: pd.DataFrame) -> np.ndarray:
        return self.estimator.predict_proba(frame.loc[:, self.features])[:, 1]


def _logistic(seed: int) -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=1_000,
                    random_state=seed,
                ),
            ),
        ]
    )


def _forest(seed: int) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=120,
        max_depth=9,
        min_samples_leaf=4,
        class_weight="balanced_subsample",
        random_state=seed,
        n_jobs=1,
    )


def fit_comparison_models(train: pd.DataFrame, seed: int = 42) -> dict[str, FittedModel]:
    """Fit LR/RF on identical rows with flat and graph-enhanced features."""
    if train["label"].nunique() < 2:
        raise ValueError("training split needs both positive and negative examples")
    feature_sets = {
        "baseline": tuple(BASELINE_FEATURES),
        "graph_enhanced": tuple(BASELINE_FEATURES + GRAPH_FEATURES),
    }
    fitted: dict[str, FittedModel] = {}
    for variant, features in feature_sets.items():
        for family, estimator in (
            ("logistic_regression", _logistic(seed)),
            ("random_forest", _forest(seed)),
        ):
            name = f"{variant}_{family}"
            estimator.fit(train.loc[:, features], train["label"])
            fitted[name] = FittedModel(name, estimator, features)
    return fitted
