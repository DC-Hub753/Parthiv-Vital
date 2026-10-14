"""Recalculate metrics from saved held-out predictions or a separate labeled CSV."""
import argparse, hashlib, json
from pathlib import Path
import joblib, pandas as pd, numpy as np
from sklearn.metrics import roc_auc_score, average_precision_score, confusion_matrix, precision_score, brier_score_loss
from prepare_dataset import FEATURES, validate_frame

def calibration_ece(y,prob,bins=10):
 y=np.asarray(y); prob=np.asarray(prob); edges=np.linspace(0.0,1.0,bins+1); total=max(1,len(prob)); error=0.0
 for i in range(bins):
  mask=(prob>=edges[i]) & ((prob<edges[i+1]) if i<bins-1 else (prob<=edges[i+1]))
  if mask.any(): error+=float(mask.sum())/total*abs(float(np.mean(y[mask]))-float(np.mean(prob[mask])))
 return error
def calculate(y,prob,threshold):
 y=np.asarray(y); prob=np.asarray(prob)
 pred=(prob>=threshold).astype(int); tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
 return {"roc_auc":float(roc_auc_score(y,prob)) if len(set(y))==2 else None,"pr_auc":float(average_precision_score(y,prob)) if len(set(y))==2 else None,"sensitivity":float(tp/(tp+fn)) if tp+fn else None,"specificity":float(tn/(tn+fp)) if tn+fp else None,"precision":float(precision_score(y,pred,zero_division=0)),"brier_score":float(brier_score_loss(y,prob)),"calibration_ece_10_bins":calibration_ece(y,prob),"threshold":float(threshold)}
def main():
 p=argparse.ArgumentParser(); p.add_argument("--artifact"); p.add_argument("--input"); p.add_argument("--predictions-file"); p.add_argument("--threshold",type=float,default=.5); p.add_argument("--output",default=""); a=p.parse_args()
 if a.predictions_file:
  frame=pd.read_csv(a.predictions_file)
  if not {"target","probability"}.issubset(frame.columns): raise SystemExit("Predictions file must contain target and probability columns")
  y=pd.to_numeric(frame["target"],errors="raise").to_numpy(); prob=pd.to_numeric(frame["probability"],errors="raise").to_numpy()
  if len(y)==0 or not np.isfinite(prob).all() or not np.isin(y,[0,1]).all() or ((prob<0)|(prob>1)).any(): raise SystemExit("Invalid saved target/probability values")
 else:
  if not a.artifact or not a.input: raise SystemExit("Provide --predictions-file or both --artifact and --input")
  frame=validate_frame(pd.read_csv(a.input)); model=joblib.load(a.artifact); prob=model.predict_proba(frame[FEATURES])[:,1]; y=frame.target.to_numpy()
 result={"rows":len(y),"metrics":calculate(y,prob,a.threshold),"prediction_sha256":hashlib.sha256(np.asarray(prob).tobytes()).hexdigest(),"clinical_performance_claim":False}
 text=json.dumps(result,indent=2); print(text)
 if a.output: Path(a.output).write_text(text+"\n")
if __name__=="__main__":main()
