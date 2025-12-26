#!/usr/bin/env python3
"""
Fact-Check Cluster Script

Run comprehensive fact-checking on a cluster of articles via Analyst integration.
Displays per-article fact-check results and cluster-level summary.

Usage:
    python scripts/fact_check_cluster.py --cluster-id <cluster_id>
    python scripts/fact_check_cluster.py --article-ids <id1> <id2> <id3>
    python scripts/fact_check_cluster.py --texts "Article 1 text" "Article 2 text"
    python scripts/fact_check_cluster.py --cluster-id <id> --verbose
"""

import argparse
import json
import sys
import textwrap
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.analyst.analyst_engine import AnalystEngine
from common.observability import get_logger

logger = get_logger(__name__)


def fact_check_cluster(
    texts: list[str],
    article_ids: list[str] | None = None,
    cluster_id: str | None = None,
    verbose: bool = False,
) -> dict:
    """
    Run fact-checking on a cluster via Analyst integration.

    Args:
        texts: List of article texts
        article_ids: Optional article IDs
        cluster_id: Optional cluster ID
        verbose: Show detailed trace output

    Returns:
        Analysis report dict with source_fact_checks and cluster_fact_check_summary
    """
    engine = AnalystEngine()

    logger.info(f"Running fact-check for {len(texts)} articles (cluster: {cluster_id})")

    report = engine.generate_analysis_report(
        texts=texts,
        article_ids=article_ids,
        cluster_id=cluster_id,
        enable_fact_check=True,
    )

    return report


def display_results(report: dict, verbose: bool = False):
    """Display fact-check results in human-readable format."""
    print("\n" + "=" * 80)
    print("FACT-CHECK RESULTS")
    print("=" * 80)

    if "error" in report:
        print(f"\n❌ Error: {report['error']}")
        return

    # Cluster summary
    cluster_id = report.get("cluster_id", "unknown")
    articles_count = report.get("articles_count", 0)
    summary = report.get("cluster_fact_check_summary", {})

    print(f"\nCluster ID: {cluster_id}")
    print(f"Articles Analyzed: {articles_count}")

    if summary:
        print("\n" + "-" * 80)
        print("CLUSTER SUMMARY")
        print("-" * 80)
        print(f"Total Checked: {summary.get('total_articles_checked', 0)}")
        print(f"Passed: {summary.get('passed_count', 0)}")
        print(f"Failed: {summary.get('failed_count', 0)}")
        print(f"Needs Review: {summary.get('needs_review_count', 0)}")
        print(f"Average Score: {summary.get('average_overall_score', 0.0):.3f}")
        print(f"Percent Verified: {summary.get('percent_verified', 0.0):.1f}%")

        flagged = summary.get("articles_flagged", [])
        if flagged:
            print(f"\n⚠️  Flagged Articles: {', '.join(flagged)}")

    # Per-article results
    source_fact_checks = report.get("source_fact_checks", [])
    if source_fact_checks:
        print("\n" + "-" * 80)
        print("PER-ARTICLE FACT-CHECK RESULTS")
        print("-" * 80)

        for i, sfc in enumerate(source_fact_checks, 1):
            article_id = sfc.get("article_id", "unknown")
            status = sfc.get("fact_check_status", "unknown")
            overall_score = sfc.get("overall_score", 0.0)
            credibility = sfc.get("credibility_score")

            # Status emoji
            status_emoji = {
                "passed": "✅",
                "failed": "❌",
                "needs_review": "⚠️",
                "pending": "⏳",
            }.get(status, "❓")

            print(f"\n{i}. Article: {article_id}")
            print(f"   Status: {status_emoji} {status.upper()}")
            print(f"   Overall Score: {overall_score:.3f}")
            if credibility is not None:
                print(f"   Credibility: {credibility:.3f}")

            # Claim verdicts
            claim_verdicts = sfc.get("claim_verdicts", [])
            if claim_verdicts:
                print(f"   Claims Verified: {len(claim_verdicts)}")
                if verbose:
                    for j, cv in enumerate(
                        claim_verdicts[:5], 1
                    ):  # Show first 5 claims
                        print(f'      {j}. "{cv.get("claim_text", "")[:60]}..."')
                        print(
                            f"         Verdict: {cv.get('verdict')} (confidence: {cv.get('confidence', 0.0):.2f})"
                        )

            # Detailed trace (verbose mode)
            if verbose:
                trace = sfc.get("fact_check_trace", {})
                if trace:
                    print("   Fact-Check Trace:")
                    print(f"      Claims Analyzed: {trace.get('claims_analyzed', 0)}")

                    fact_verification = trace.get("fact_verification", {})
                    if fact_verification:
                        print(
                            f"      Verification Score: {fact_verification.get('verification_score', 0.0):.3f}"
                        )
                        print(
                            f"      Classification: {fact_verification.get('classification', 'unknown')}"
                        )

                    contradictions = trace.get("contradictions", {})
                    if contradictions and contradictions.get("contradictions_found"):
                        print(
                            f"      ⚠️  Contradictions Found: {contradictions.get('count', 0)}"
                        )

    print("\n" + "=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run fact-checking on article cluster via Analyst integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              # Fact-check specific texts
              python scripts/fact_check_cluster.py --texts "Article 1 text" "Article 2 text"

              # Fact-check with article IDs
              python scripts/fact_check_cluster.py --texts "Text 1" "Text 2" --article-ids "art1" "art2"

              # Verbose output with detailed trace
              python scripts/fact_check_cluster.py --texts "Text" --verbose

              # Save results to JSON
              python scripts/fact_check_cluster.py --texts "Text" --output results.json
            """
        ),
    )

    parser.add_argument("--texts", nargs="+", help="Article texts to fact-check")
    parser.add_argument(
        "--article-ids",
        nargs="+",
        help="Article IDs (optional, must match --texts count)",
    )
    parser.add_argument("--cluster-id", type=str, help="Cluster ID for grouping")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed fact-check trace output",
    )
    parser.add_argument("--output", "-o", type=str, help="Save results to JSON file")

    args = parser.parse_args()

    # Validate inputs
    if not args.texts:
        parser.error("--texts is required")

    if args.article_ids and len(args.article_ids) != len(args.texts):
        parser.error("--article-ids count must match --texts count")

    # Run fact-check
    try:
        report = fact_check_cluster(
            texts=args.texts,
            article_ids=args.article_ids,
            cluster_id=args.cluster_id,
            verbose=args.verbose,
        )

        # Display results
        display_results(report, verbose=args.verbose)

        # Save to file if requested
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(json.dumps(report, indent=2))
            print(f"Results saved to: {output_path}")

    except Exception as e:
        logger.error(f"Fact-check failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
