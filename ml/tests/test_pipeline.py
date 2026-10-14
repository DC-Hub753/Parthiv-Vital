import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_dataset import FEATURES, DatasetValidationError, validate_frame
from train import patient_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import joblib

def sample(n=60):
 rng=np.random.default_rng(4); d={"patient_id":[f"p{i}" for i in range(n)]}
 for f in FEATURES: d[f]=rng.uniform(20,90,n)
 d["spo2"]=rng.uniform(90,100,n); d["systolic_bp"]=rng.uniform(100,150,n); d["diastolic_bp"]=rng.uniform(60,90,n); d["temperature"]=rng.uniform(36,38,n); d["respiratory_rate"]=rng.uniform(8,30,n); d["target"]=[i%2 for i in range(n)]
 return pd.DataFrame(d)
def test_validates_and_preserves_feature_order():
 d=validate_frame(sample()); assert list(d[FEATURES].columns)==FEATURES
@pytest.mark.parametrize("bad",[np.nan,np.inf])
def test_rejects_missing_or_nonfinite(bad):
 d=sample(); d.loc[0,"spo2"]=bad
 with pytest.raises(DatasetValidationError): validate_frame(d)
def test_rejects_invalid_units_or_values():
 d=sample(); d.loc[0,"temperature"]=100
 with pytest.raises(DatasetValidationError): validate_frame(d)
def test_patient_split_has_no_overlap():
 d=sample(100); a,b,c=patient_split(d,2026); sets=[set(d.loc[x,"patient_id"]) for x in (a,b,c)]
 assert not sets[0]&sets[1] and not sets[0]&sets[2] and not sets[1]&sets[2]
def test_serialization_round_trip_predictions(tmp_path):
 d=validate_frame(sample()); model=Pipeline([("scale",StandardScaler()),("clf",LogisticRegression(random_state=1))]).fit(d[FEATURES],d.target)
 before=model.predict_proba(d[FEATURES])[:,1]; path=tmp_path/"model.joblib"; joblib.dump(model,path); after=joblib.load(path).predict_proba(d[FEATURES])[:,1]
 np.testing.assert_allclose(before,after,rtol=0,atol=1e-12)
