ChromaDB Setup and Troubleshooting
=================================

This document helps you configure and troubleshoot ChromaDB for the JustNews stack.

1) Environment variables
-------------------------
- Set CHROMADB_HOST and CHROMADB_PORT to point to your ChromaDB server. For example:

    export CHROMADB_HOST=localhost
    export CHROMADB_PORT=3307

- Optional: Set CHROMADB_TENANT if your Chroma server uses multi-tenancy. Default: `default_tenant`.
    export CHROMADB_TENANT=default_tenant

- Optional: Allow the system to try to create the default tenant during startup (best-effort):
    export CHROMADB_AUTO_CREATE_TENANT=1

2) Diagnose & auto-provision
----------------------------
Run the included diagnostic script to discover endpoints, test connectivity, and optionally try to create the default tenant and `articles` collection (best-effort, not guaranteed on all server versions):

    PYTHONPATH=. conda run -n justnews-v2-py312-fix python scripts/chroma_diagnose.py --autocreate

If the script reports that the root endpoint appears to be another service (for example `MCP Bus Agent`) you likely have the wrong host or port configured — update `CHROMADB_HOST` or `CHROMADB_PORT` accordingly.

3) Common issues
----------------
- Wrong port: If `CHROMADB_PORT` points to `8000` or another agent such as the MCP Bus, Chroma clients may fail to connect or list collections; your logs may show root endpoints or versions for a different service.

- Tenant missing: If a server requires a tenant but it doesn't exist, some Chroma endpoints may return an error like `Could not connect to tenant default_tenant`. Use the script `--autocreate` attempt to create the default tenant (if your server supports tenant creation via HTTP).

- API versions: Different Chroma server versions use different API versions; the client attempts `heartbeat()`, and if that fails, `list_collections()` as an alternate connectivity probe.

4) Logs and diagnostics
-----------------------
- To see the server type root info: use `curl -s http://CHROMADB_HOST:CHROMADB_PORT/` which should show a JSON with a server name/version.
- To list collections via Python client:
    import chromadb
    client = chromadb.HttpClient(host='CHROMADB_HOST', port=CHROMADB_PORT, tenant='default_tenant')
    print([c.name for c in client.list_collections()])

5) Notes
--------
- Our code now respects `CHROMADB_TENANT` and will optionally try to auto-create a default tenant and `articles` collection if `CHROMADB_AUTO_CREATE_TENANT` is set to 1.
- If you use `system_config.json` and want to override, set environment variables: `CHROMADB_HOST` and `CHROMADB_PORT`. Environment variables will take precedence over `system_config.json` values.

If you still face issues after following these steps, share the outputs of `python scripts/chroma_diagnose.py --autocreate` and the memory agent logs for further debugging.
