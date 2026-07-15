#!/usr/bin/env python3
"""Incremental feature materializer starter."""
import argparse


def materialize(events, output):
    raise NotImplementedError("implement incremental materialization")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    materialize(args.events, args.output)


if __name__ == "__main__":
    main()
