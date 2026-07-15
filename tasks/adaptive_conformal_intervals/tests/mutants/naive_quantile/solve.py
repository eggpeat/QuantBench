#!/usr/bin/env python3
from pathlib import Path
import sys

SRC = r'''import math, numpy as np

def calibration_split(n_samples, *, groups=None, times=None, calibration_fraction=.2, random_state=0):
    n=int(n_samples); k=int(math.ceil(n*float(calibration_fraction))); rng=np.random.default_rng(random_state)
    p=rng.permutation(n); return p[k:], p[:k]

def conformal_quantile(scores, alpha, sample_weight=None):
    # Deliberate mutant: ordinary interpolated quantile and ignores frequency weights.
    s=np.asarray(scores,dtype=float)
    return float(np.quantile(s, 1-float(alpha)))

def normalized_intervals(mu, scale, q, *, scale_floor=1e-12):
    m,s,qq=np.broadcast_arrays(np.asarray(mu,float),np.asarray(scale,float),np.asarray(q,float)); e=np.maximum(s,float(scale_floor)); return m-qq*e,m+qq*e
'''
RUN = r'''import json,sys
from pathlib import Path
import conformal

def main(root):
    root=Path(root); f=json.loads((root/'fixture.json').read_text()); tr,ca=conformal.calibration_split(f['n_samples'],calibration_fraction=f['calibration_fraction'],random_state=f['random_state']); q=conformal.conformal_quantile(f['scores'],f['alpha']); lo,hi=conformal.normalized_intervals(f['mu'],f['scale'],f['q']); (root/'outputs').mkdir(exist_ok=True); (root/'outputs'/'conformal.json').write_text(json.dumps({'train_indices':tr.tolist(),'calibration_indices':ca.tolist(),'quantile':q,'lower':lo.tolist(),'upper':hi.tolist()}))
if __name__=='__main__': main(sys.argv[1] if len(sys.argv)>1 else '.')
'''

def main(root):
    root=Path(root); root.mkdir(parents=True,exist_ok=True); (root/'conformal.py').write_text(SRC); (root/'run_task.py').write_text(RUN); sys.path.insert(0,str(root)); ns={'__name__':'x'}; exec(RUN,ns); ns['main'](root)
if __name__=='__main__': main(sys.argv[1] if len(sys.argv)>1 else '.')
