# Vendor Patches

## Google RPC Namespace Patch

Purpose: Remove the deprecated `pkg_resources.declare_namespace` call from the `google.rpc` package that ships with
`googleapis-common-protos`. The upstream module still relies on Setuptools' legacy namespace helper, which emits a
runtime deprecation warning on Python 3.12 and later.

### What we changed

- The installed module `google/rpc/__init__.py` is rewritten to use the
standard-library `pkgutil.extend_path` helper. This avoids importing `pkg_resources` entirely and eliminates the warning
during startup.

- `googleapis-common-protos>=1.59.1` is pinned in `requirements.txt` and
`environment.yml` to keep the dependency explicit.

- A helper script `scripts/vendor_patches/apply_google_rpc_namespace_patch.py`
automates rewriting the installed file.

### Reapplying after environment rebuild

Whenever the Python environment is rebuilt (new conda env, dependency upgrade, CI image refresh, etc.), rerun:

```bash
conda run --name ${CANONICAL_ENV:-justnews-py312} python scripts/vendor_patches/apply_google_rpc_namespace_patch.py

```

Use `--dry-run` to verify whether the patch needs to be applied. The script is idempotent and safe to re-execute.

### Upstream tracking

- Upstream package: `googleapis-common-protos`

- Patch availability: pending upstream migration away from `pkg_resources`.
Remove this vendor patch once the upstream module adopts implicit namespace packages.

### Conda / conda-forge

If your CI / platform requires a python `protobuf` wheel compatible with Python 3.12, consider providing a conda recipe
so conda-forge can build and distribute a matching package. This repository includes an example recipe at
`conda/recipes/protobuf` which is intended as a starting point for a `conda- forge/staged-recipes` PR. See
`conda/README.md` for usage and local build instructions.
