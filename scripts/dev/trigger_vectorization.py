#!/usr/bin/env python3
"""
Trigger vectorization for articles missing from ChromaDB.
Calls the memory agent service to reindex specific article IDs.
"""
import requests
import sys

def get_missing_article_ids():
    """Returns list of article IDs that need vectorization (2863-3062)"""
    # Based on parity check: MariaDB has 3062, Chroma has 2862
    # Missing IDs are 2863-3062 (200 articles)
    return list(range(2863, 3063))

def trigger_vectorization_via_memory_agent(article_ids):
    """
    Trigger vectorization by fetching and re-saving articles via memory agent.
    Since we can't directly access the DB, we'll need to use the memory agent's
    get_article and save_article endpoints.
    """
    memory_agent_url = "http://localhost:8007"
    
    success_count = 0
    error_count = 0
    
    print(f"Attempting to vectorize {len(article_ids)} articles...")
    print(f"Article ID range: {min(article_ids)} - {max(article_ids)}")
    
    for article_id in article_ids:
        try:
            # Try to get the article
            get_response = requests.post(
                f"{memory_agent_url}/get_article",
                json={"article_id": article_id},
                timeout=10
            )
            
            if get_response.status_code == 200:
                article_data = get_response.json()
                
                if article_data and article_data.get("content"):
                    # Re-save to trigger vectorization
                    # Note: This might not work if save_article checks for duplicates
                    print(f"✓ Article {article_id}: Retrieved, attempting vectorization...")
                    # We can't actually re-save without triggering duplicate detection
                    # This approach won't work
                else:
                    print(f"✗ Article {article_id}: No content returned")
                    error_count += 1
            else:
                print(f"✗ Article {article_id}: Failed to retrieve (status {get_response.status_code})")
                error_count += 1
                
        except Exception as e:
            print(f"✗ Article {article_id}: Error - {e}")
            error_count += 1
    
    print(f"\nCompleted: {success_count} successful, {error_count} errors")
    return error_count == 0

if __name__ == "__main__":
    print("=" * 60)
    print("ChromaDB Vectorization Trigger")
    print("=" * 60)
    print()
    
    print("Note: This script cannot directly trigger vectorization")
    print("because the save_article function has duplicate detection.")
    print()
    print("The issue is that articles were saved to MariaDB but")
    print("ChromaDB vectorization failed silently.")
    print()
    print("Solution: The memory agent needs to be fixed to ensure")
    print("ChromaDB collection is properly initialized, OR we need")
    print("a dedicated reindex endpoint in the memory agent.")
    print()
    print("Missing article IDs: 2863-3062 (200 articles)")
    sys.exit(1)
