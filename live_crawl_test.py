#!/usr/bin/env python3
"""
Live Crawl Test: 100 sites × 40 articles = 4,000 articles total
Tests the full crawling pipeline with our enhancements
"""

import asyncio
import sys
import time
from collections import defaultdict
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.crawler.crawler_engine import CrawlerEngine


async def run_crawl_test():
    """Run comprehensive crawl test with 100 sites × 40 articles each"""

    print("🚀 JustNews Live Crawl Test")
    print("=" * 50)
    print("Testing: 100 sites × 40 articles each = 4,000 articles total")
    print()

    # Define test sites - mix of major news sources
    test_sites = [
        "bbc.co.uk",
        "nytimes.com",
        "theguardian.com",
        "washingtonpost.com",
        "aljazeera.com",
        "dw.com",
        "france24.com",
        "abc.net.au",
        "scmp.com",
        "indiatoday.in",
        "theverge.com",
        "wired.com",
        "vice.com",
        "lemonde.fr",
        "corriere.it",
        "asahi.com",
        "globo.com",
        "folha.uol.com.br",
        "ledevoir.com",
        "channel4.com",
        # Additional 20 sites for higher load testing
        "reuters.com",
        "apnews.com",
        "bloomberg.com",
        "cnn.com",
        "foxnews.com",
        "nbcnews.com",
        "cbsnews.com",
        "npr.org",
        "pbs.org",
        "politico.com",
        "axios.com",
        "huffpost.com",
        "msnbc.com",
        "usatoday.com",
        "latimes.com",
        "chicago.suntimes.com",
        "nypost.com",
        "newsweek.com",
        "time.com",
        "forbes.com",
        # Additional 10 sites for maximum load testing
        "wsj.com",
        "ft.com",
        "economist.com",
        "slate.com",
        "salon.com",
        "motherjones.com",
        "prospect.org",
        "jacobinmag.com",
        "thenation.com",
        "newyorker.com",
        # Additional 50 sites for extreme load testing
        "guardian.co.uk",
        "telegraph.co.uk",
        "independent.co.uk",
        "dailymail.co.uk",
        "mirror.co.uk",
        "sky.com",
        "itv.com",
        "standard.co.uk",
        "metro.co.uk",
        "express.co.uk",
        "sun.co.uk",
        "huffingtonpost.co.uk",
        "buzzfeed.com",
        "businessinsider.com",
        "cnbc.com",
        "marketwatch.com",
        "yahoo.com",
        "msn.com",
        "aol.com",
        "drudgereport.com",
        "breitbart.com",
        "dailywire.com",
        "theblaze.com",
        "newsmax.com",
        "oann.com",
        "epochtimes.com",
        "gatewaypundit.com",
        "townhall.com",
        "pjmedia.com",
        "redstate.com",
        "twitchy.com",
        "weaselzippers.us",
        "thefederalist.com",
        "dailycaller.com",
        "ijr.com",
        "westernjournal.com",
        "libertyheadlines.com",
        "100percentfedup.com",
        "conservativereview.com",
        "truthrevolt.org",
        "allenwestrepublic.com",
        "madworldnews.com",
        "shoebat.com",
        "christianpost.com",
        "faithwire.com",
        "relevantmagazine.com",
        "sojourners.org",
        "patheos.com",
        "beliefnet.com",
        "catholicnewsagency.com",
        "ncronline.org",
        "cruxnow.com",
        "angelusnews.com",
    ]

    print(f"📋 Selected {len(test_sites)} test sites:")
    for i, site in enumerate(test_sites, 1):
        print(f"  {i:2d}. {site}")
    print()

    # Initialize crawler engine
    print("🔧 Initializing crawler engine...")
    start_time = time.time()

    try:
        async with CrawlerEngine() as crawler:
            init_time = time.time() - start_time
            print(f"⚙️  Init time: {init_time:.1f}s")
            print()

            # Run the crawl
            print("📰 Starting unified crawl...")
            crawl_start = time.time()

            result = await crawler.run_unified_crawl(
                domains=test_sites,
                max_articles_per_site=40,
                concurrent_sites=10,  # Increased concurrency for extreme load testing
            )

            crawl_time = time.time() - crawl_start
            total_time = time.time() - start_time

            # Analyze results
            print("\n" + "=" * 60)
            print("📊 CRAWL RESULTS SUMMARY")
            print("=" * 60)

            sites_crawled = result.get("sites_crawled", 0)
            total_ingested = result.get("total_articles", 0)
            total_candidates = result.get("total_ingest_candidates", total_ingested)
            duplicates = result.get("duplicates_skipped", 0)
            errors = result.get("ingestion_errors", 0)

            print(f"⏱️  Total time: {total_time:.1f}s")
            print(f"🚀 Crawl time: {crawl_time:.1f}s")
            print(f"⚙️  Init time: {init_time:.1f}s")
            print()

            print(f"📊 Sites processed: {sites_crawled}/{len(test_sites)}")
            print(f"✅ Articles ingested: {total_ingested}")
            if total_candidates != total_ingested:
                print(f"🧪 Ingest candidates processed: {total_candidates}")
            print(f"🔄 Duplicates skipped: {duplicates}")
            print(f"❌ Errors: {errors}")
            print()

            if total_ingested > 0:
                articles_per_second = total_ingested / crawl_time
                print(f"📈 Performance: {articles_per_second:.2f} articles/second")
                print(
                    f"⏱️  Average time per article: {crawl_time / total_ingested:.1f}s"
                )
                print()

            # Site-by-site breakdown
            print("📋 SITE-BY-SITE BREAKDOWN:")
            print("-" * 40)

            site_breakdown = result.get("site_breakdown", {})
            site_candidates = result.get("site_candidate_breakdown", {})
            site_duplicates = result.get("site_duplicate_breakdown", {})
            site_errors = result.get("site_error_breakdown", {})

            for site in test_sites:
                ingested = site_breakdown.get(site, 0)
                candidates = site_candidates.get(site, 0)
                duplicate_count = site_duplicates.get(site, 0)
                error_count = site_errors.get(site, 0)

                status = "✅" if ingested > 0 else "❌" if candidates == 0 else "⚠️"
                print(
                    f"{status} {site:<20} candidates={candidates:2d} ingested={ingested:2d} "
                    f"duplicates={duplicate_count:2d} errors={error_count:2d}"
                )

            articles = result.get("articles", []) or []
            modal_dismissals = defaultdict(int)
            cookie_consents = defaultdict(int)
            paywall_article_counts = defaultdict(int)

            for article in articles:
                domain = article.get("domain") or article.get("source_name")
                if not domain:
                    continue
                metadata = article.get("extraction_metadata", {}) or {}
                modal_info = metadata.get("modal_handler", {}) or {}
                if modal_info.get("modal_detected"):
                    modal_dismissals[domain] += 1
                cookie_consents[domain] += modal_info.get("consent_cookies", 0)
                if article.get("paywall_flag"):
                    paywall_article_counts[domain] += 1

            total_modal_dismissals = sum(modal_dismissals.values())
            total_cookie_consents = sum(cookie_consents.values())
            modal_dismissals_positive = {
                site: count for site, count in modal_dismissals.items() if count > 0
            }
            cookie_consents_positive = {
                site: count for site, count in cookie_consents.items() if count > 0
            }

            site_paywall_breakdown = result.get("site_paywall_breakdown", {}) or {}
            if not site_paywall_breakdown and paywall_article_counts:
                site_paywall_breakdown = dict(paywall_article_counts)

            aggregated_paywalls = result.get("total_paywalls_detected")
            if aggregated_paywalls is None:
                aggregated_paywalls = sum(site_paywall_breakdown.values())
            if aggregated_paywalls == 0:
                aggregated_paywalls = sum(paywall_article_counts.values())

            paywalled_site_list = (
                set(site_paywall_breakdown.keys())
                if site_paywall_breakdown
                else set(paywall_article_counts.keys())
            )
            total_paywalled_sites = len(paywalled_site_list)

            print()
            print("🛡️  DEFENSIVE MEASURES SUMMARY:")
            print("-" * 40)
            print(f"  Paywall encounters: {aggregated_paywalls}")
            print(f"  Paywalled sites encountered: {total_paywalled_sites}")
            print(f"  Modal dismissals performed: {total_modal_dismissals}")
            print(f"  Cookie consents cleared: {total_cookie_consents}")

            if site_paywall_breakdown:
                print("  Paywall encounters by site:")
                for site, count in sorted(
                    site_paywall_breakdown.items(), key=lambda item: (-item[1], item[0])
                ):
                    print(f"    {site}: {count}")
            elif paywalled_site_list:
                print("  Paywalled site list:")
                for site in sorted(paywalled_site_list):
                    print(f"    {site}")

            if modal_dismissals_positive:
                print("  Modal dismissals by site:")
                for site, count in sorted(
                    modal_dismissals_positive.items(),
                    key=lambda item: (-item[1], item[0]),
                ):
                    print(f"    {site}: {count}")

            if cookie_consents_positive:
                print("  Cookie consents by site:")
                for site, count in sorted(
                    cookie_consents_positive.items(),
                    key=lambda item: (-item[1], item[0]),
                ):
                    print(f"    {site}: {count}")

            print()
            print("🎯 TEST OBJECTIVES ASSESSMENT:")
            print("-" * 40)

            # Assess success criteria
            success_criteria = {
                "Sites with articles": sites_crawled
                >= 70,  # At least 70% success rate (70/100)
                "Total articles": total_ingested
                >= 1000,  # At least 1,000 articles (25% of potential 4,000)
                "Average per site": total_ingested / sites_crawled >= 10.0
                if sites_crawled > 0
                else False,
                "Low error rate": errors / max(total_candidates, 1) < 0.5,
            }

            all_passed = True
            for criterion, passed in success_criteria.items():
                status = "✅ PASS" if passed else "❌ FAIL"
                print(f"  {status}: {criterion}")
                if not passed:
                    all_passed = False

            print()
            if all_passed:
                print("🎉 OVERALL RESULT: SUCCESS!")
                print("   The crawler is working well with our enhancements!")
            else:
                print("⚠️  OVERALL RESULT: PARTIAL SUCCESS")
                print("   Some improvements may be needed.")

            # Strategy breakdown
            strategy_breakdown = result.get("strategy_breakdown", {})
            if strategy_breakdown:
                print()
                print("🎲 CRAWLING STRATEGIES USED:")
                print("-" * 30)
                for strategy, count in strategy_breakdown.items():
                    if count > 0:
                        print(f"  {strategy}: {count} sites")

    except Exception as e:
        print(f"❌ Crawl test failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_crawl_test())
