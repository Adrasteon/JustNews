#!/usr/bin/env python3
"""
Run fact check on article(s) via Analyst

Usage:
  python scripts/fact_check_article.py --text "Some article text"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.analyst.tools import generate_analysis_report


def main():
    parser = argparse.ArgumentParser(description='Run fact check on article text via Analyst')
    parser.add_argument('--text', required=True)
    parser.add_argument('--article-id', required=False)
    args = parser.parse_args()

    texts = [args.text]
    report = generate_analysis_report(texts, article_ids=[args.article_id] if args.article_id else None)
    print(report)


if __name__ == '__main__':
    main()
