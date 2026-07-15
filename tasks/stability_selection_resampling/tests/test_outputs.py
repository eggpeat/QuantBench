import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))


def load_candidate():
    path = WORKSPACE / "stability.py"
    spec = importlib.util.spec_from_file_location("candidate_stability", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def reference(X, y, *, k, n_resamples, sample_fraction, threshold, sample_weight=None, groups=None, times=None, feature_names=None, random_state=0):
    X = np.asarray(X, float); y = np.asarray(y, float); n, p = X.shape
    target = max(1, int(np.ceil(n * sample_fraction))); rng = np.random.default_rng(random_state); hits = np.zeros(p, int)
    for _ in range(n_resamples):
        if groups is not None:
            labels, inv = np.unique(groups, return_inverse=True); idxs=[]
            for gp in rng.permutation(len(labels)):
                rows=np.flatnonzero(inv == gp); idxs.extend(rows.tolist())
                if len(idxs) >= target: break
            idx=np.asarray(idxs)
        elif times is not None:
            order=np.argsort(times, kind='stable'); start=int(rng.integers(0,n-target+1)); idx=order[start:start+target]
        else:
            idx=np.sort(rng.choice(n,size=target,replace=False))
        z=X[idx].copy()
        for j in range(p):
            good=np.isfinite(z[:,j]);
            if good.any():
                z[~good,j]=np.median(z[good,j]); sd=z[:,j].std(); z[:,j]=(z[:,j]-z[:,j].mean())/(sd if sd>0 else 1)
            else: z[:,j]=0
        w=np.ones(idx.size) if sample_weight is None else np.asarray(sample_weight,float)[idx]
        yc=y[idx]-np.sum(w*y[idx])/w.sum(); zc=z-np.sum(w[:,None]*z,axis=0)/w.sum(); den=np.sqrt(np.sum(w[:,None]*zc*zc,axis=0)*np.sum(w*yc*yc)); corr=np.divide(np.sum(w[:,None]*zc*yc[:,None],axis=0),den,out=np.zeros(p),where=den>np.finfo(float).eps)
        hits[np.lexsort((np.arange(p),-np.abs(corr)))[:k]] += 1
    freq=hits/n_resamples; sel=np.flatnonzero(freq>=threshold).tolist(); names=[str(i) for i in range(p)] if feature_names is None else list(map(str,feature_names)); return sel,[names[i] for i in sel],freq


def test_public_cli_output():
    subprocess.run([sys.executable, str(WORKSPACE / 'stability.py')], cwd=WORKSPACE, check=True)
    actual=json.loads((WORKSPACE/'outputs'/'stability.json').read_text())
    with np.load(WORKSPACE/'stability_input.npz') as data:
        X, y = data['X'], data['y']
    mod = load_candidate()
    expected = mod.stability_select(
        X, y, k=3, n_resamples=100, sample_fraction=.5, threshold=.8,
        feature_names=[f'feature_{i}' for i in range(X.shape[1])], random_state=100,
    )
    assert actual['selected_indices'] == expected.selected_indices
    assert actual['selected_features'] == expected.selected_features
    np.testing.assert_allclose(actual['frequencies'], expected.frequencies)
    assert actual['threshold'] == expected.threshold == .8
    assert actual['n_resamples'] == expected.n_resamples == 100


def test_local_preprocessing_is_fit_inside_each_resample():
    m=load_candidate(); X=np.array([[1.0292004,-0.03349479],[-0.03809257,0.40874072],[np.nan,0.85508177],[-0.81682526,0.46027283],[np.nan,np.nan],[0.58179018,0.23198142],[np.nan,2.08797552],[0.73790539,np.nan]]); y=np.array([0.12573022,-0.13210486,0.64042265,0.10490012,-0.53566937,0.36159505,1.30400005,0.94708096])
    kwargs=dict(k=1,n_resamples=30,sample_fraction=.5,threshold=0.,random_state=7)
    got=m.stability_select(X,y,**kwargs); expected=reference(X,y,**kwargs)
    np.testing.assert_allclose(got.frequencies,expected[2]); assert not np.isclose(got.frequencies[0],0.2)
    np.testing.assert_allclose(got.frequencies,expected[2]); assert got.selected_indices==expected[0]


def test_weighted_pearson_and_tie_order():
    m=load_candidate(); X=np.array([[0.,0.,1.],[1.,1.,1.],[2.,2.,1.],[3.,3.,1.],[4.,4.,1.]],float); y=np.arange(5.,dtype=float); w=np.array([1.,2.,1.,3.,1.]);
    got=m.stability_select(X,y,k=2,n_resamples=4,sample_fraction=1.,threshold=1.,sample_weight=w,feature_names=['a','b','c'],random_state=11)
    assert got.selected_indices==[0,1] and got.selected_features==['a','b']; assert got.frequencies.tolist()==[1.,1.,0.]


def test_group_and_contiguous_time_modes_are_supported():
    m=load_candidate(); X=np.arange(48,dtype=float).reshape(12,4); y=np.sin(np.arange(12.))
    groups=np.repeat(np.arange(4),3); times=np.arange(12)
    grouped=m.stability_select(X,y,k=2,n_resamples=8,sample_fraction=.5,groups=groups,random_state=3)
    timed=m.stability_select(X,y,k=2,n_resamples=8,sample_fraction=.5,times=times,random_state=3)
    assert grouped.frequencies.shape==(4,) and timed.frequencies.shape==(4,)
    with np.testing.assert_raises(ValueError): m.stability_select(X,y,k=1,groups=groups,times=times)


def test_n_jobs_does_not_change_seeded_result():
    m=load_candidate(); rng=np.random.default_rng(1101); X=rng.normal(size=(60,6)); y=rng.normal(size=60); X[::9,2]=np.nan
    one=m.stability_select(X,y,k=3,n_resamples=20,random_state=22,n_jobs=1)
    many=m.stability_select(X,y,k=3,n_resamples=20,random_state=22,n_jobs=4)
    assert one.selected_indices==many.selected_indices and one.selected_features==many.selected_features
    np.testing.assert_array_equal(one.frequencies,many.frequencies)


def test_validation_rejects_bad_domains():
    m=load_candidate(); X=np.ones((5,2)); y=np.ones(5)
    for kwargs in [dict(k=0),dict(k=3),dict(k=1,n_resamples=0),dict(k=1,sample_fraction=0),dict(k=1,threshold=1.1),dict(k=1,n_jobs=0),dict(k=1,sample_weight=np.zeros(5)),dict(k=1,feature_names=['x','x'])]:
        with np.testing.assert_raises(ValueError): m.stability_select(X,y,**kwargs)
    bad=X.copy(); bad[0,0]=np.inf
    with np.testing.assert_raises(ValueError): m.stability_select(bad,y,k=1)
