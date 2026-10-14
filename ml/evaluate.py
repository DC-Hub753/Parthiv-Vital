"""Evaluate a serialized model on a separate patient-disjoint CSV."""
import argparse, json
from pathlib import Path
import joblib, pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, confusion_matrix, precision_score, brier_score_loss
from prepare_dataset import FEATURES, validate_frame

def main():
 p=argparse.ArgumentParser(); p.add_argument("--artifact",required=True); p.add_argument("--input",required=True); p.add_argument("--threshold",type=float,default=.5); a=p.parse_args()
 frame=validate_frame(pd.read_csv(a.input)); model=joblib.load(a.artifact); prob=model.predict_proba(frame[FEATURES])[:,1]; y=frame.target; pred=(prob>=a.threshold).astype(int); tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
 result={"rows":len(frame),"roc_auc":float(roc_auc_score(y,prob)) if y.nunique()==2 else None,"pr_auc":float(average_precision_score(y,prob)) if y.nunique()==2 else None,"sensitivity":float(tp/(tp+fn)) if tp+fn else None,"specificity":float(tn/(tn+fp)) if tn+fp else None,"precision":float(precision_score(y,pred,zero_division=0)),"brier_score":float(brier_score_loss(y,prob)),"threshold":a.threshold,"clinical_performance_claim":False}
 print(json.dumps(result,indent=2))
if __name__=="__main__":main()
