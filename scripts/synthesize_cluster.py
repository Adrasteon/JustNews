#!/usr/bin/env python3
"""
Synthesize cluster helper script

Usage:
  python scripts/synthesize_cluster.py --cluster-id <cluster_id>
"""

import argparse
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))



def main():
    parser = argparse.ArgumentParser(description='Synthesize a cluster of articles via the Synthesizer agent')
    parser.add_argument('--cluster-id', required=True, help='Cluster id')
    parser.add_argument('--publish', action='store_true', help='Attempt to publish if gates pass')
    parser.add_argument('--host', default='localhost:8005')
    args = parser.parse_args()

    payload = {
        'articles': [],
        'cluster_id': args.cluster_id,
        'max_clusters': 1,
        'context': 'news',
        'publish': args.publish
    }

    url = f'http://{args.host}/synthesize_and_publish'

    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    print(resp.json())


if __name__ == '__main__':
    main()
