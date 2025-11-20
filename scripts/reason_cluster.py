#!/usr/bin/env python3
"""
Run reasoning on a cluster using the Reasoning agent

Usage:
  python scripts/reason_cluster.py --cluster-id <cluster_id>
"""

import argparse
import requests
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description='Call Reasoning agent for cluster analysis')
    parser.add_argument('--cluster-id', required=True)
    parser.add_argument('--host', default='localhost:8008')
    args = parser.parse_args()

    url = f'http://{args.host}/reason'
    resp = requests.post(url, json={'cluster_id': args.cluster_id}, timeout=30)
    resp.raise_for_status()
    print(resp.json())


if __name__ == '__main__':
    main()
