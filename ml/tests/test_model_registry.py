import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model_registry import build_candidates, choose_candidate

def test_registry_always_includes_logistic_regression_baseline():
 candidates=build_candidates(42,{"max_iter":100,"include_xgboost":False})
 assert "logistic_regression" in candidates and "random_forest" in candidates

def test_candidate_selection_uses_validation_metric_and_baseline_tiebreak():
 results={"logistic_regression":{"roc_auc":0.8},"random_forest":{"roc_auc":0.8}}
 assert choose_candidate(results,"roc_auc")=="logistic_regression"
 results["random_forest"]["roc_auc"]=0.9
 assert choose_candidate(results,"roc_auc")=="random_forest"

def test_candidate_selection_fails_if_metric_missing():
 import pytest
 with pytest.raises(ValueError): choose_candidate({"logistic_regression":{"roc_auc":None}},"roc_auc")
