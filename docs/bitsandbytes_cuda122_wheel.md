# Custom bitsandbytes CUDA 12.2 Wheel

This note documents how we produced the CUDA‑enabled `bitsandbytes` wheel that now
lives under `.build/bitsandbytes/dist/bitsandbytes-0.49.0.dev0-cp312-cp312-linux_x86_64.whl`.
It captures the full environment recipe, every error we hit, and the fixes you can
apply if future rebuilds encounter the same issues.

## Why we needed a custom build

- Upstream `bitsandbytes` wheels currently publish CUDA binaries for 12.1, 12.2, 12.3,
  and 12.8+, but **not** for the exact combination we run locally (PyTorch reports
  CUDA 12.4 while the driver stack exposes CUDA 12.2 runtime bits).
- All attempts to run int8 inference with the stock wheels ended in nvlink
  "`Uncompress failed`" errors during device linking.
- Rebuilding from source with a CUDA 12.2 toolchain avoids the nvlink crash and lets
  us pin `BNB_CUDA_VERSION=122` at runtime so the correct binary is loaded.

## Environment recipe

```bash
# Fresh toolchain with NVIDIA's CUDA 12.2.2 label
conda create -n bnb122lab -c "nvidia/label/cuda-12.2.2" -c defaults -y \
   python=3.12 cuda-toolkit=12.2.2 cuda-nvcc=12.2.140 cmake ninja pip

# Ensure nvcc uses a supported host compiler (nvcc 12.2 requires GCC <=12)
conda install -n bnb122lab -c conda-forge -y gcc_linux-64=12.3.0 gxx_linux-64=12.3.0
```

Key binaries live under `/home/adra/miniconda3/envs/bnb122lab/bin/` and we refer to
this path as `CUDA_HOME` in the commands below.

## Build steps

1. **Clean the source tree** (we build from the vendored bitsandbytes sources
   at `.build/bitsandbytes/`).
   ```bash
   cd /home/adra/JustNews/.build/bitsandbytes
   rm -rf _skbuild build dist bitsandbytes.egg-info manual_build
   ```

2. **Invoke `python -m build --wheel`** via `conda run` while forcing CMake to use
   the CUDA 12.2 toolchain and the GCC 12.3 host compiler shipped inside the
   `bnb122lab` environment:
   ```bash
   conda run -n bnb122lab \
     env \
       CUDA_HOME=/home/adra/miniconda3/envs/bnb122lab \
       CUDA_VERSION=12.2 \
       CUDACXX=/home/adra/miniconda3/envs/bnb122lab/bin/nvcc \
       CC=/home/adra/miniconda3/envs/bnb122lab/bin/x86_64-conda-linux-gnu-gcc \
       CXX=/home/adra/miniconda3/envs/bnb122lab/bin/x86_64-conda-linux-gnu-g++ \
       CUDAHOSTCXX=/home/adra/miniconda3/envs/bnb122lab/bin/x86_64-conda-linux-gnu-g++ \
       FORCE_CMAKE=1 \
       CMAKE_ARGS="-DCOMPUTE_BACKEND=cuda -DCUDA_VERSION=122 -DCOMPUTE_CAPABILITY=86 -DCMAKE_CUDA_HOST_COMPILER=/home/adra/miniconda3/envs/bnb122lab/bin/x86_64-conda-linux-gnu-g++" \
     python -m build --wheel
   ```
   The build drops the wheel into `dist/` and also produces the shared library
   `bitsandbytes/libbitsandbytes_cuda122.so` we ship inside the package.

3. **Install into the runtime env** (after copying the wheel to the repo root):
   ```bash
  conda run -n ${CANONICAL_ENV:-justnews-py312} pip install -U \
     /home/adra/JustNews/.build/bitsandbytes/dist/bitsandbytes-0.49.0.dev0-cp312-cp312-linux_x86_64.whl
   ```

4. **Runtime toggle**: export `BNB_CUDA_VERSION=122` (now part of `global.env`) so
   bitsandbytes picks `libbitsandbytes_cuda122.so` even though PyTorch advertises
   CUDA 12.4. Leaving the variable empty will make the runtime look for a 12.4
   binary instead and crash.

## Troubleshooting log

| Symptom | Root cause | Fix |
| --- | --- | --- |
| `You've specified CUDA version 122 however the CUDA compiler found is 120.` | CMake picked `/usr/bin/nvcc` (12.0). | Set `CUDACXX` and `CUDA_HOME` to the CUDA 12.2 toolkit inside `bnb122lab`. |
| `#error -- unsupported GNU version! gcc versions later than 12 are not supported!` | System GCC 13.3 was selected as the host compiler. | Install `gcc_linux-64=12.3.0 gxx_linux-64=12.3.0` in the build env and export `CC`, `CXX`, and `CUDAHOSTCXX` to those binaries. |
| Hundreds of `_Float32` / `_Float64` undefined errors after adding `--allow-unsupported-compiler`. | Still compiling with GCC 13, which lacks the headers expected by nvcc when the unsupported compiler flag is active. | Same fix as above: force the Conda GCC 12 toolchain and drop the `--allow-unsupported-compiler` workaround. |
| nvlink `Uncompress failed` during `cmake_device_link`. | Stock wheel (CUDA 12.4) mismatched the runtime driver and produced invalid fatbins. | Rebuild the wheel with a matching CUDA toolkit (12.2) and point bitsandbytes to it via `BNB_CUDA_VERSION=122`. |

## Verification checklist

1. **NVCC sanity check**
   ```bash
   conda run -n bnb122lab nvcc --version  # should print release 12.2, V12.2.140
   ```
2. **Diagnostics after install**
   ```bash
  conda run -n ${CANONICAL_ENV:-justnews-py312} env BNB_CUDA_VERSION=122 python -m bitsandbytes
   ```
   Expect the tool to print "SUCCESS!" and explicitly state that it is loading
   `libbitsandbytes_cuda122.so`.
3. **Performance smoke test** – run the real-model perf helper:
   ```bash
   RE_RANKER_TEST_MODE=0 RE_RANKER_MODEL=mistralai/Mistral-7B-Instruct-v0.3 \
  BNB_CUDA_VERSION=122 \
  conda run -n ${CANONICAL_ENV:-justnews-py312} python scripts/perf/simulate_concurrent_inference.py \
     --requests 20 --sweep --sweep-max 2 --model mistralai/Mistral-7B-Instruct-v0.3
   ```

## Operational tips

- Keep `BNB_CUDA_VERSION=122` in every service environment until we either upgrade
  the system CUDA stack or rebuild the wheel for a new toolkit.
- Use `BNB_DISABLE=1` (supported by `scripts/perf/simulate_concurrent_inference.py`
  and our agent loaders) to force a float16 path when you need a quick comparison
  or when bitsandbytes is temporarily unavailable.
- When regenerating the wheel for a new bitsandbytes release, re-run the exact
  commands above but bump the source checkout version under `.build/bitsandbytes`
  and re-test the diagnostics before publishing.
- Store the wheel artifact (or checksum) somewhere durable if other hosts need to
  reinstall it; otherwise repeat this recipe verbatim on the target machine.

## Automated rebuild (CI / reproducibility)

We also provide a lightweight automation helper that reproduces the build across
multiple CUDA targets and uploads the resulting wheel as an artifact.

- Script: `.build/bitsandbytes/build_wheels.sh` — a small, documented helper that supports
   building via docker (nvidia/cuda images) or using a local `conda` build environment.

- CI: `.github/workflows/build-bnb-wheels.yml` — GitHub Actions workflow intended for
   self-hosted GPU runners. It runs the build script in a matrix across CUDA targets
   (e.g. 122, 124, 128) and uploads the produced wheel as an artifact so the team can
   cache or pin it for reproducible installs.

## How CI & other workflows will pick up the wheel

Our CI workflows (including `orchestrator-only-tests.yml` and the full `pytest.yml`) now
attempt to install a prebuilt bnb wheel automatically before falling back to pip installs.

- CI finds the latest `bitsandbytes-wheel-<short-cuda>` artifact produced by
   `.github/workflows/build-bnb-wheels.yml` and installs the wheel from that artifact.
- If no artifact is available the workflow will continue and fall back to `pip install -r requirements.txt`.

This keeps CI fast and repeatable when an approved wheel exists, while still being resilient when a wheel isn't available.

Publishing artifacts:

- The build workflow uploads wheels as GitHub Actions artifacts for later reuse.

Notes: The workflow expects runners with GPU access (or access to nvidia-docker) and
is therefore scoped to self-hosted infrastructure. Use the workflow dispatch entrypoint
to trigger ad-hoc rebuilds, or schedule it (the workflow includes a weekly schedule).

