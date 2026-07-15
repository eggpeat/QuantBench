#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import negative_binomial


def main() -> None:
    root = Path(__file__).resolve().parent
    with (root / "input.json").open(encoding="utf-8") as fh:
        d = json.load(fh)
    grad, hess = negative_binomial.gradient_and_hessian(d["y"], d["log_n"], d["logit_p"])
    payload = {
        "gradient": np.asarray(grad, dtype=np.float32).tolist(),
        "hessian": np.asarray(hess, dtype=np.float32).tolist(),
        "finite": bool(np.all(np.isfinite(grad)) and np.all(np.isfinite(hess))),
    }
    out = root / "outputs" / "gradients.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True, indent=2)
        fh.write("\n")

if __name__ == "__main__":
    main()
