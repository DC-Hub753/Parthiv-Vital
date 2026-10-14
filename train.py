"""Benchmark candidate classifiers with one patient-disjoint split protocol."""
from __future__ import annotations
import argparse, hashlib, json, time
from datetime import datetime, timezone
from pathlib import Path
import yaml, joblib, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, confusion_matrix, precision_score
from sklearn.model_selection import GroupShuffleSplit
from prepare_dataset import FEATURES, validate_frame
from model_registry import build_candidates, choose_candidate

def patient_split(frame, seed):
    groups=frame["patient_id"].astype(str).to_numpy(); idx=np.arange(len(frame))
    train_val,test=next(GroupShuffleSplit(n_splits=1,test_size=.15,random_state=seed).split(idx,frame.target,groups))
    rest=frame.iloc[train_val]
    train_rel,val_rel=next(GroupShuffleSplit(n_splits=1,test_size=.15/.85,random_state=seed+1).split(np.arange(len(rest)),rest.target,rest.patient_id.astype(str)))
    result=(rest.index.to_numpy()[train_rel],rest.index.to_numpy()[val_rel],frame.index.to_numpy()[test])
    groupsets=[set(frame.loc[ids,"patient_id"]) for ids in result]
    if any(groupsets[i]&groupsets[j] for i in range(3) for j in range(i+1,3)): raise ValueError("Patient leakage detected between splits")
    return result

def metric_or_none(fn,y,p):
    try:return float(fn(y,p))
    except ValueError:return None

def calculate_metrics(y, probs, threshold):
    pred=(probs>=threshold).astype(int); tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    return {"roc_auc":metric_or_none(roc_auc_score,y,probs),"pr_auc":metric_or_none(average_precision_score,y,probs),"sensitivity":float(tp/(tp+fn)) if tp+fn else None,"specificity":float(tn/(tn+fp)) if tn+fp else None,"precision":float(precision_score(y,pred,zero_division=0)),"brier_score":float(brier_score_loss(y,probs)),"threshold":float(threshold)}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",required=True); p.add_argument("--config",default="ml/config.yaml"); p.add_argument("--output-dir",default="ml/artifacts"); p.add_argument("--dataset-version",default="unverified-local-csv"); p.add_argument("--smoke-test",action="store_true")
    a=p.parse_args(); cfg=yaml.safe_load(Path(a.config).read_text()); seed=int(cfg["seed"]); frame=validate_frame(pd.read_csv(a.input))
    train_i,val_i,test_i=patient_split(frame,seed); X=frame[FEATURES]; y=frame.target; mc=cfg["model"]
    candidates=build_candidates(seed,mc); requested=mc.get("candidates",list(candidates)); candidates={k:v for k,v in candidates.items() if k in requested}
    if "logistic_regression" not in candidates: raise ValueError("Logistic regression baseline must be included")
    val_results={}; fitted={}
    for name,model in candidates.items():
        model.fit(X.loc[train_i],y.loc[train_i]); vp=model.predict_proba(X.loc[val_i])[:,1]
        val_results[name]=calculate_metrics(y.loc[val_i],vp,float(mc.get("threshold",.5))); fitted[name]=model
    selected=choose_candidate(val_results,mc.get("selection_metric","roc_auc"))
    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); report={}; dataset_hash=hashlib.sha256(Path(a.input).read_bytes()).hexdigest()
    for name,model in fitted.items():
        artifact=out/f"vitalguard_{name}.joblib"; joblib.dump(model,artifact)
        probe=X.loc[test_i].iloc[:min(100,len(test_i))]; start=time.perf_counter(); model.predict_proba(probe); latency=(time.perf_counter()-start)*1000/max(1,len(probe))
        test_prob=model.predict_proba(X.loc[test_i])[:,1]
        pred_file=out/f"test_predictions_{name}.csv"
        pd.DataFrame({"patient_id":frame.loc[test_i,"patient_id"].astype(str).to_numpy(),"target":y.loc[test_i].to_numpy(),"probability":test_prob}).to_csv(pred_file,index=False)
        report[name]={"validation_metrics":val_results[name],"test_metrics":calculate_metrics(y.loc[test_i],test_prob,float(mc.get("threshold",.5))),"artifact":artifact.name,"artifact_sha256":hashlib.sha256(artifact.read_bytes()).hexdigest(),"artifact_bytes":artifact.stat().st_size,"inference_ms_per_row_approx":latency,"test_predictions_file":pred_file.name,"test_predictions_sha256":hashlib.sha256(pred_file.read_bytes()).hexdigest()}
    manifest={"registry_version":"1","selected_candidate":selected,"selection_metric":mc.get("selection_metric","roc_auc"),"selection_source":"validation only; test set not used for selection","candidates":report,"baseline":"logistic_regression","dataset_sha256":dataset_hash,"dataset_version":a.dataset_version,"seed":seed,"features":FEATURES,"feature_version":cfg["feature_version"],"target_definition":cfg["target"],"split_strategy":"patient-group-disjoint train/validation/test","row_counts":{"total":len(frame),"train":len(train_i),"validation":len(val_i),"test":len(test_i)},"trained_at_utc":datetime.now(timezone.utc).isoformat(),"synthetic_smoke_test":bool(a.smoke_test),"clinical_training_verified":False,"clinical_model_selection_valid":False,"limitations":["Dataset provenance and clinical target were not independently verified.","Synthetic heuristic-label metrics are engineering smoke tests only.","Do not deploy a research artifact as a clinical model."]}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n"); print(json.dumps(manifest,indent=2))
if __name__=="__main__": main()
