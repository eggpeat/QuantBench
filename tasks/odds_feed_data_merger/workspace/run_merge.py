#!/usr/bin/env python3
"""Run the odds feed data merger."""

import sys
from pathlib import Path
from merge_odds import main

if __name__ == "__main__":
    # If a workspace path is provided as a CLI argument, use it;
    # otherwise, default to None.
    workspace = sys.argv[1] if len(sys.argv) > 1 else None
    main(workspace)
