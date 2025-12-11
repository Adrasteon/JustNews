# Ready to Test: GPU Stress Test System Status

## ✅ System Status Check

```bash
# Power cap verification
$ sudo nvidia-smi -q -d POWER | grep "Current Power Limit"
        Current Power Limit               : 300.00 W

# Systemd service status
$ sudo systemctl status nvidia_power_limit.service --no-pager | grep Active
   Active: active (exited)

# GPU health
$ nvidia-smi --query-gpu=name,temp.gpu,power.draw --format=csv,noheader,nounits
NVIDIA RTX 3090, 28, 18.01

# Log directory
$ ls -lh /home/adra/justnews_gpu_logs/
Total: 11M with 14 log files (recent tests: 2w, 3w, 4w stub tests successful)
```

---

## 🚀 Quick Start: Run a Real Model Test

To validate the system with **actual Mistral-7B model loading**:

```bash
cd /home/adra/JustNews

# Real model test (2 workers, 10 requests)
# First run: ~3–5 min (model download), subsequent: ~30–60 sec
./scripts/perf/stress_test_harness.sh real 2 10
```

Expected output:
- Model downloads to `~/.cache/huggingface/hub/` (first run only)
- GPU memory climbs to ~16GB (from VRAM pool of 24.5GB)
- Power draw stays ≤300W (cap enforced)
- Test completes with summary statistics

---

## 📊 What Gets Logged

Each test creates:
1. **`nvml_watchdog_<name>.jsonl`** — NVML telemetry (0.1s samples, JSON Lines format)
2. **`nvml_watchdog_<name>.stdout.log`** — Watchdog stdout
3. Test output in harness terminal

### Extract Statistics

```bash
# Get power/temp/memory stats for last test
LATEST=$(ls -t /home/adra/justnews_gpu_logs/nvml_watchdog_*.jsonl | head -1)
grep nvml_sample "$LATEST" | \
  jq '{power: .gpus[0].power_w, temp: .gpus[0].temperature_c, mem_mb: .gpus[0].memory_used_mb}' | \
  jq -s '{
    power_avg: (map(.power) | add / length),
    power_max: (map(.power) | max),
    temp_max: (map(.temp) | max),
    mem_max_mb: (map(.mem_mb) | max)
  }'
```

---

## 🔄 Test Progression

After confirming real-2w-10 works:

```bash
# Real 2 workers, 20 requests (longer test)
./scripts/perf/stress_test_harness.sh real 2 20

# Real 4 workers, 10 requests (high concurrency)
./scripts/perf/stress_test_harness.sh real 4 10

# Real 4 workers, 50+ requests (sustained stress)
./scripts/perf/stress_test_harness.sh real 4 50
```

---

## 🛡️ Power Cap Details

**Applied:** `/etc/systemd/system/nvidia_power_limit.service`

```ini
[Unit]
Description=NVIDIA Power Limit (300W)
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/nvidia-smi -pl 300
Restart=no

[Install]
WantedBy=multi-user.target
```

- Persistent across reboots ✅
- Applied automatically at boot
- Current limit verified as **300.00 W**
- Prevents hardware resets from power exhaustion

---

## ⚠️ If Test Fails

Check:
1. **Power cap:** `sudo nvidia-smi -pl 300` (manual re-apply if needed)
2. **Watchdog logs:** `tail -f /home/adra/justnews_gpu_logs/nvml_watchdog_*.jsonl`
3. **GPU health:** `nvidia-smi dmon` (watch for thermal throttle, power throttle)
4. **Disk space:** `df -h /home/adra/justnews_gpu_logs/` (logs grow ~2–3MB per 10-min test)

---

## 📝 Environment

- **Conda:** `/home/adra/miniconda3/envs/justnews-py312`
- **Model:** `mistralai/Mistral-7B-Instruct-v0.3` (INT8, 7B params)
- **GPU:** NVIDIA RTX 3090 (24.5GB VRAM, 300W cap)
- **Framework:** Transformers + Bitsandbytes (INT8 quantization)

---

## ✨ Ready to Proceed?

All infrastructure is operational. The system is protected from the power exhaustion issue that caused the initial hardware reset. You can safely proceed with real model stress testing.

**Next command:** `cd /home/adra/JustNews && ./scripts/perf/stress_test_harness.sh real 2 10`
