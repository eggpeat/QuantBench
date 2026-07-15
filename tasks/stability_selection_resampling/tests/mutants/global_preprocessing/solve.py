#!/usr/bin/env python3
from pathlib import Path
import numpy as np, json
SOURCE = r"""from dataclasses import dataclass
import numpy as np
@dataclass(frozen=True)
class StabilityResult:
    selected_indices:list[int]; selected_features:list[str]; frequencies:np.ndarray; threshold:float; n_resamples:int
def stability_select(X,y,*,k,n_resamples=100,sample_fraction=.5,threshold=.8,sample_weight=None,groups=None,times=None,feature_names=None,random_state=0,n_jobs=1):
    X=np.asarray(X,float); y=np.asarray(y,float); n,p=X.shape
    # Incorrect mutant: imputes/scales once globally, leaking held-out rows.
    med=np.nanmedian(X,axis=0); Z=np.where(np.isnan(X),med,X); mu=Z.mean(0); sd=Z.std(0); Z=(Z-mu)/np.where(sd>0,sd,1)
    rng=np.random.default_rng(random_state); hits=np.zeros(p,int); size=max(1,int(np.ceil(n*sample_fraction)))
    for _ in range(n_resamples):
        idx=np.sort(rng.choice(n,size=size,replace=False)); z=Z[idx]; yy=y[idx]
        w=np.ones(size) if sample_weight is None else np.asarray(sample_weight)[idx]; yc=yy-np.average(yy,weights=w); zc=z-np.average(z,axis=0,weights=w); corr=np.abs(np.sum(w[:,None]*zc*yc[:,None],0)/np.sqrt(np.sum(w[:,None]*zc*zc,0)*np.sum(w*yc*yc)))
        for j in np.lexsort((np.arange(p),-np.nan_to_num(corr,nan=0)))[:k]: hits[j]+=1
    f=hits/n_resamples; sel=np.flatnonzero(f>=threshold).tolist(); names=[str(i) for i in range(p)] if feature_names is None else list(map(str,feature_names)); return StabilityResult(sel,[names[i] for i in sel],f,float(threshold),n_resamples)
"""
def main():
 ws=Path.cwd(); (ws/'stability.py').write_text(SOURCE); ns={}; exec(SOURCE,ns)
 with np.load(ws/'stability_input.npz') as d: X,y=d['X'],d['y']
 cfg=json.loads((ws/'stability_config.json').read_text()); res=ns['stability_select'](X,y,**cfg); out=ws/'outputs'; out.mkdir(exist_ok=True); (out/'stability.json').write_text(json.dumps({'selected_indices':res.selected_indices,'selected_features':res.selected_features,'frequencies':res.frequencies.tolist(),'threshold':res.threshold,'n_resamples':res.n_resamples}))
if __name__=='__main__': main()
