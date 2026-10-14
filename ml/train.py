"""Train a versioned baseline from an explicit validated CSV."""
from __future__ import annotations
import argparse, hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
import yaml
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import joblib
from prepare_dataset import FEATURES, validate_frame


def patient_split(frame, seed):
    groups=frame["patient_id"].astype(str).to_numpy()
    idx=np.arange(len(frame))
    train_val, test = next(GroupShuffleSplit(n_splits=1,test_size=.15,random_state=seed).split(idx,frame.target,groups))
    rest=frame.iloc[train_val]
    tr_rel, val_rel = next(GroupShuffleSplit(n_splits=1,test_size=.15/.85,random_state=seed+1).split(np.arange(len(rest)),rest.target,rest.patient_id.astype(str)))
    train_idx=rest.index.to_numpy()[tr_rel]; val_idx=rest.index.to_numpy()[val_rel]; test_idx=frame.index.to_numpy()[test]
    groupsets=[set(frame.loc[ids,"patient_id"]) for ids in (train_idx,val_idx,test_idx)]
    if any(groupsets[i]&groupsets[j] for i in range(3) for j in range(i+1,3)): raise ValueError("Patient leakage detected between splits")
    return train_idx,val_idx,test_idx

def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",required=True); p.add_argument("--config",default="ml/config.yaml"); p.add_argument("--output-dir",default="ml/artifacts"); p.add_argument("--dataset-version",default="unverified-local-csv"); p.add_argument("--smoke-test",action="store_true")
    a=p.parse_args(); cfg=yaml.safe_load(Path(a.config).read_text()); seed=int(cfg["seed"])
    frame=validate_frame(pd.read_csv(a.input)); train_i,val_i,test_i=patient_split(frame,seed)
    X=frame[FEATURES]; y=frame.target
    pipe=Pipeline([("imputer",SimpleImputer(strategy="median",add_indicator=True)),("scale",StandardScaler()),("classifier",LogisticRegression(max_iter=int(cfg["model"]["max_iter"]),class_weight="balanced",random_state=seed))])
    pipe.fit(X.loc[train_i],y.loc[train_i]); valp=pipe.predict_proba(X.loc[val_i])[:,1]
    testp=pipe.predict_proba(X.loc[test_i])[:,1]; yt=y.loc[test_i]
    def metric(fn, labels, probs):
        try:return float(fn(labels,probs))
        except ValueError:return None
    threshold=float(cfg["model"].get("threshold",.5)); pred=(testp>=threshold).astype(int)
    from sklearn.metrics import confusion_matrix, precision_score, recall_score
    tn,fp,fn, tp=confusion_matrix(yt,pred,labels=[0,1]).ravel()
    metrics={"roc_auc":metric(roc_auc_score,yt,testp),"pr_auc":metric(average_precision_score,yt,testp),"sensitivity":float(tp/(tp+fn)) if tp+fn else None,"specificity":float(tn/(tn+fp)) if tn+fp else None,"precision":float(precision_score(yt,pred,zero_division=0)),"brier_score":float(np.mean((testp-yt.to_numpy())**2)),"threshold":threshold,"test_rows":len(test_i),"validation_rows":len(val_i)}
    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    artifact=out/"vitalguard_logreg.joblib"; joblib.dump(pipe,artifact)
    digest=hashlib.sha256(Path(a.input).read_bytes()).hexdigest()
    manifest={"artifact":artifact.name,"artifact_sha256":hashlib.sha256(artifact.read_bytes()).hexdigest(),"dataset_sha256":digest,"dataset_version":a.dataset_version,"seed":seed,"features":FEATURES,"feature_version":cfg["feature_version"],"target_definition":cfg["target"],"split_strategy":"patient-group-disjoint train/validation/test; test held out from fitting","threshold_source":"config fixed before test evaluation; do not tune on test","trained_at_utc":datetime.now(timezone.utc).isoformat(),"synthetic_smoke_test":bool(a.smoke_test),"clinical_training_verified":False,"metrics":metrics,"row_counts":{"total":len(frame),"train":len(train_i),"validation":len(val_i),"test":len(test_i)}}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps(manifest,indent=2))
if __name__ == "__main__": main()
