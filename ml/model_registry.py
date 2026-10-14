"""Shared candidate registry for reproducible offline benchmarks.

XGBoost is optional. This registry never fetches data or chooses a clinical model.
"""
from __future__ import annotations
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def build_candidates(seed: int, config: dict):
    candidates = {
        "logistic_regression": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=int(config.get("max_iter", 1200)), class_weight="balanced", random_state=seed)),
        ]),
        "random_forest": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("classifier", RandomForestClassifier(n_estimators=int(config.get("rf_estimators", 200)), min_samples_leaf=int(config.get("rf_min_samples_leaf", 2)), class_weight="balanced", random_state=seed, n_jobs=1)),
        ]),
    }
    if config.get("include_xgboost", True):
        try:
            from xgboost import XGBClassifier
            candidates["xgboost"] = Pipeline([
                ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                ("classifier", XGBClassifier(n_estimators=int(config.get("xgb_estimators", 150)), max_depth=int(config.get("xgb_max_depth", 3)), learning_rate=float(config.get("xgb_learning_rate", 0.05)), subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0, random_state=seed, n_jobs=1, eval_metric="logloss")),
            ])
        except ImportError:
            pass
    return candidates


def choose_candidate(validation_results: dict, metric: str = "roc_auc") -> str:
    """Select by a predeclared validation metric; stable tie-break prefers baseline."""
    baseline = "logistic_regression"
    usable = [(name, result.get(metric)) for name, result in validation_results.items() if result.get(metric) is not None]
    if not usable:
        raise ValueError(f"No candidates have a valid validation {metric}")
    usable.sort(key=lambda item: (item[1], item[0] == baseline, item[0]), reverse=True)
    return usable[0][0]
