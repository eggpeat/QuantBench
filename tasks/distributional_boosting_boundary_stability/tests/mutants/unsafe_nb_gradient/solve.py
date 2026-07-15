#!/usr/bin/env python3
"""Intentional mutant: uses overflow-prone p*(y - n*(1-p)/p)."""
from pathlib import Path
SOURCE='''import numpy as np
from scipy.special import digamma,expit
MIN_EXPONENT=float(np.log(np.float32(1e-32))); MAX_EXPONENT=float(np.log(np.finfo("float32").max)-1.0); DIAG_FLOOR=np.float32(1e-30)
def gradient_and_hessian(y,log_n,logit_p,*,natural_gradient=True):
 if not natural_gradient: raise NotImplementedError()
 y=np.asarray(y,dtype=np.float64); a=np.asarray(log_n,dtype=np.float64); b=np.asarray(logit_p,dtype=np.float64)
 if y.ndim!=1 or a.shape!=y.shape or b.shape!=y.shape or np.any(~np.isfinite(y)) or np.any(~np.isfinite(a)) or np.any(~np.isfinite(b)) or np.any(y<0) or np.any(y!=np.floor(y)): raise ValueError("invalid input")
 n=np.exp(np.clip(a,MIN_EXPONENT,MAX_EXPONENT)); p=expit(np.clip(b,MIN_EXPONENT,MAX_EXPONENT)); raw0=-n*(digamma(y+n)-digamma(n)+np.log(p))
 # MUTATION: float32 intermediate overflows at p -> 0.
 n32=n.astype(np.float32); p32=p.astype(np.float32); raw1=p32*(y.astype(np.float32)-n32*(1-p32)/p32)
 f0=np.maximum(np.asarray(n*p/(p+1),dtype=np.float32),DIAG_FLOOR).astype(np.float64); f1=np.maximum(np.asarray(n*(1-p),dtype=np.float32),DIAG_FLOOR).astype(np.float64)
 return np.column_stack([raw0/f0,raw1/f1]).astype(np.float32),np.ones((y.size,2),dtype=np.float32)
'''
def main():
 Path("negative_binomial.py").write_text(SOURCE,encoding="utf-8")
 import subprocess,sys
 if Path("run_negative_binomial.py").exists(): subprocess.run([sys.executable,"run_negative_binomial.py"],check=True)
if __name__=="__main__": main()
