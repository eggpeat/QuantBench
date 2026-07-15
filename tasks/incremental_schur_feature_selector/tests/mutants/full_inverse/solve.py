#!/usr/bin/env python3
from pathlib import Path
import numpy as np, json

SOURCE = r"""import numpy as np

def greedy_select(correlation, target_correlation, k, *, ridge=1e-8):
    R=np.asarray(correlation,dtype=float); r=np.asarray(target_correlation,dtype=float)
    chosen=[]; remaining=list(range(len(r)))
    for _ in range(k):
        scores=[]
        for j in remaining:
            S=np.asarray(chosen,dtype=int)
            if len(S):
                inv=np.linalg.inv(R[np.ix_(S,S)] + ridge*np.eye(len(S)))
                c=R[j,S]; den=R[j,j]+ridge-c@inv@c; num=r[j]-c@inv@r[S]
            else: den=R[j,j]+ridge; num=r[j]
            scores.append(num*num/max(den,1e-15))
        j=remaining[int(np.argmax(scores))]; chosen.append(j); remaining.remove(j)
    return chosen
"""

def main():
    ws=Path.cwd(); (ws/'selector.py').write_text(SOURCE)
    ns={}; exec(SOURCE,ns)
    with np.load(ws/'selector_input.npz') as d: R,r=d['correlation'],d['target_correlation']
    cfg=json.loads((ws/'selector_config.json').read_text()); out=ws/'outputs'; out.mkdir(exist_ok=True)
    (out/'selection.json').write_text(json.dumps({'selected_indices':ns['greedy_select'](R,r,cfg['k'],ridge=cfg['ridge'])}))
if __name__=='__main__': main()
