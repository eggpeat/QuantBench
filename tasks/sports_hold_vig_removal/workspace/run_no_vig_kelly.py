#!/usr/bin/env python3
import sys
from pathlib import Path
import no_vig_kelly


def main():
    workspace_path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent
    no_vig_kelly.main(workspace_path)


if __name__ == "__main__":
    main()
