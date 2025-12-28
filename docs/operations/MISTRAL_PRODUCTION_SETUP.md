# Mistral-7B Production Setup on a Single Host

This document lists the exact steps and checks to deploy the canonical Mistral‑7B model on a single host and operate it
safely with `gpu_orchestrator`.

Prerequisites (host)

- NVIDIA drivers + CUDA installed and functional (verify via `nvidia-smi`).

- Conda environment `justnews-py312` available and `vllm` installed in that env.

- Sufficient disk space in `MODEL_STORE_ROOT` (>= 50GB for base model & snapshots).

- `systemd` available (system or user services supported).

1) Install model into ModelStore

- Ensure `MODEL_STORE_ROOT` is set in `/etc/justnews/global.env`.

- Run: `make modelstore-fetch-mistral` (this downloads HF snapshot into `MODEL_STORE_ROOT/base_models/models--mistralai--Mistral-7B-Instruct-v0.3/snapshots/<id>`)

2) Install systemd unit and start

- Run: `make vllm-install-and-start` (requires sudo). The unit executes vLLM using `conda run -n justnews-py312` so the canonical env is used.

- The agent startup script attempts to auto-bootstrap the canonical `justnews-py312` conda environment (idempotent) if it is not present and `AUTO_BOOTSTRAP_CONDA` is not set to `0` in `/etc/justnews/global.env`. You can run the bootstrap manually with `make env-bootstrap`.

- Verify with `make monitor-status` and `systemctl --user status vllm-mistral-7b.service`.

3) Run a smoke test

- Run `make vllm-smoke-test` to verify the endpoint responds.

4) Enable monitoring & logging

- Ensure `make monitor-install && make monitor-enable` has run (installs and starts GPU monitor service).

- Install logrotate: `make monitor-install-rotate` (requires sudo).

- Optionally configure a Pushgateway endpoint by setting `METRICS_PUSHGATEWAY_URL` in `/etc/justnews/global.env`.

5) Rolling restarts & upgrades

- To upgrade the model in ModelStore, stage a new snapshot under `snapshots/` and update `AGENT_MODEL_MAP.json` (change `model_store_version` and `approx_vram_mb` when needed). The orchestrator will not auto-switch running models without explicit operator action (use `/workers/pool` endpoints or update service unit).

6) Safety & resource tuning

- If you observe frequent OOMs: reduce `config/vllm_mistral_7b.yaml` `runtime.gpu_memory_util` and `model.max_batch_size` and restart the service.

- Tune `service.memory_max` and `service.cpu_quota` if host contention is observed.

Contact & support

- For driver-level faults (NVRM/Xid), collect `dmesg`, `journalctl -k`, `nvidia-smi -q -a`, and open a hardware support ticket.
