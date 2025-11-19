#!/usr/bin/env python3
"""
ChromaDB diagnose and setup script
Usage:
    python scripts/chroma_diagnose.py [--autocreate]

Attempts to discover ChromaDB endpoints, checks health, tenants and collections.
If --autocreate is provided, it will try to create a default tenant and a 'articles' collection via HTTP API best-effort.
"""
import argparse
import os
from pprint import pprint
from database.utils.chromadb_utils import discover_chroma_endpoints, get_root_info, create_tenant, ensure_collection_exists_using_http


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("CHROMADB_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CHROMADB_PORT", 3307)))
    parser.add_argument("--autocreate", action="store_true", help="Try to auto-create default tenant and articles collection via HTTP API")
    args = parser.parse_args()

    host = args.host
    port = args.port

    canonical_host = os.environ.get('CHROMADB_CANONICAL_HOST')
    canonical_port = os.environ.get('CHROMADB_CANONICAL_PORT')
    require_canonical = os.environ.get('CHROMADB_REQUIRE_CANONICAL', '1') == '1'
    if canonical_host and canonical_port:
        print(f"🔎 Diagnosing ChromaDB at {host}:{port} (canonical configured as {canonical_host}:{canonical_port})\n")
    else:
        print(f"🔎 Diagnosing ChromaDB at {host}:{port}\n")
    print("Root info:")
    pprint(get_root_info(host, port))

    print("\nEndpoint discovery: (may include endpoints that returned errors)")
    endpoints = discover_chroma_endpoints(host, port)
    pprint(endpoints)

    if args.autocreate:
        print("\nAttempting auto-create tenant and 'articles' collection (best-effort):")
        ok = create_tenant(host, port, tenant='default_tenant')
        print("Tenant create OK? ", ok)
        ok = ensure_collection_exists_using_http(host, port, collection_name='articles')
        print("Collection create OK? ", ok)

    print("\nDone. If connectivity issues persist check ChromaDB server logs and network/firewall rules.")

    # If require canonical is set and canonical values are configured, validate
    if require_canonical and canonical_host and canonical_port:
        from database.utils.chromadb_utils import validate_chroma_is_canonical
        try:
            validate_chroma_is_canonical(host, port, canonical_host, int(canonical_port), raise_on_fail=True)
            print("\nOK: This host/port matches canonical Chroma settings and appears to be a Chroma server.")
        except Exception as e:
            print(f"\nERROR: Chroma validation failed: {e}")
            raise SystemExit(1)


if __name__ == '__main__':
    main()
