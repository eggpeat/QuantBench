#!/usr/bin/env python3
from pathlib import Path
import sys

SRC = r'''from dataclasses import dataclass
import numpy as np
@dataclass
class SelectionResult:
    selected_indices:list[int]
    selection_frequency:np.ndarray
    draw_thresholds:np.ndarray
    group_selected:list[object]
def select_fdr(X,y,*,q=.1,n_draws=10,random_state=0,feature_groups=None):
    # Deliberate mutant: ignores knockoff draws and simply returns marginal top-k.
    x=np.asarray(X,float); yy=np.asarray(y,float)
    if x.ndim!=2 or yy.ndim!=1 or len(yy)!=len(x): raise ValueError('invalid input')
    p=x.shape[1]; corr=[]
    for j in range(p):
        corr.append(abs(np.corrcoef(x[:,j],yy)[0,1]) if np.std(x[:,j]) else 0.)
    k=max(1,int(np.ceil(float(q)*p))); inds=np.argsort(corr)[-k:]; freq=np.zeros(p); freq[inds]=1.; groups=[]
    if feature_groups is not None:
        labels=list(feature_groups); chosen={labels[i] for i in inds}; inds=np.array([i for i,l in enumerate(labels) if l in chosen]); groups=[l for i,l in enumerate(labels) if l in chosen and l not in groups]
    return SelectionResult(sorted(int(i) for i in inds),freq,np.full(int(n_draws),np.inf),groups)
'''
RUN = r'''import json,sys
from pathlib import Path
import knockoffs
def main(root):
 root=Path(root);f=json.loads((root/'fixture.json').read_text());r=knockoffs.select_fdr(f['X'],f['y'],q=f['q'],n_draws=f['n_draws'],random_state=f['random_state'],feature_groups=f.get('feature_groups'));(root/'outputs').mkdir(exist_ok=True);(root/'outputs'/'knockoffs.json').write_text(json.dumps({'selected_indices':r.selected_indices,'selection_frequency':r.selection_frequency.tolist(),'draw_thresholds':r.draw_thresholds.tolist(),'group_selected':r.group_selected}))
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else '.')
'''
def main(root):
 root=Path(root);root.mkdir(parents=True,exist_ok=True);(root/'knockoffs.py').write_text(SRC);(root/'run_task.py').write_text(RUN);sys.path.insert(0,str(root));ns={'__name__':'x'};exec(RUN,ns);ns['main'](root)
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else '.')
