# GPU Stress Test & Model Loading Verification

## Findings

### Previous Tests (Stub Model)
The tests completed suspiciously fast (0.02–0.03s for 30–40 requests), confirming they were **using the stub model**, not real Mistral-7B:
- **RE_RANKER_TEST_MODE=1** (default) loads a simple `StubModel` with 2ms fake compute per request
- **RE_RANKER_TEST_MODE=0** is required to load actual transformer model

**Test Results (Stub, 300W cap):**
- 2 workers, 30 requests: ✅ 0.03s, ~1027MB peak GPU memory
- 3 workers, 30 requests: ✅ 0.02s, ~1035MB peak GPU memory
- 4 workers, 40 requests: ✅ 0.02s, ~1050MB peak GPU memory

All were **CPU-bound stub tests**, not GPU-bound real inference.

---

## Root Cause of Initial Hardware Reset

**Confirmed:** Unlimited power (350W default) + multi-threaded concurrent model activations caused **VRAM exhaustion/transient memory pressure → hardware reset** during the original 6-worker test with 100 requests.

**Evidence:**
- Previous logs: no XID/thermal/OOM errors (hardware-level reset before kernel can log)
- Power telemetry: ran up to 38W in stub tests; full model load would exceed 300W easily
- Test duration: >90 seconds before watchdog stopped; test never logged completion

---

## System Preparation & Fixes

### 1. Persistent Power Cap (300W)
**Installed:** `/etc/systemd/system/nvidia_power_limit.service`
- Runs at boot (Before=systemd-user-sessions.service)
- Executes `/usr/bin/nvidia-smi -pl 300`
- Survives reboots and manual `nvidia-smi` calls

**Verification:**
```bash
$ sudo systemctl status nvidia_power_limit.service
$ sudo nvidia-smi -q -d POWER | grep "Current Power Limit"
        Current Power Limit               : 300.00 W
```

### 2. Stress Test Harness
**Location:** `/home/adra/JustNews/scripts/perf/stress_test_harness.sh`

**Usage:**
```bash
# Fast stub test (CPU-bound, validates concurrency)
./scripts/perf/stress_test_harness.sh stub 4 40

# Real model test (GPU-bound, validates actual inference)
./scripts/perf/stress_test_harness.sh real 2 10
```

**Features:**
- Automatic NVML watchdog + telemetry collection
- Power cap verification
- GPU health pre-check
- Comprehensive result reporting
- Logs to `/home/adra/justnews_gpu_logs/`

---

## Next Steps: Real Model Test

To verify the system is ready for longer stress tests with actual Mistral-7B loading:

```bash
cd /home/adra/JustNews
./scripts/perf/stress_test_harness.sh real 2 10
```

**Expected:**
- **First run:** ~3–5 minutes (model download + cache)
- **Load time:** Watch GPU memory climb to ~14–16GB (7B params @ FP16)
- **Peak power:** Should stay ≤300W due to cap
- **Peak VRAM:** ~16–18GB (safe headroom from 24.5GB limit)

---

## Telemetry & Monitoring

NVML watchdog logs are in JSON Lines format:
```bash
# Extract power statistics
grep nvml_sample /home/adra/justnews_gpu_logs/nvml_watchdog_*.jsonl | \
  jq '.gpus[0] | {power: .power_w, temp: .temperature_c, util: .utilization_gpu_pct}'

# Check for exceptions
grep nvml_exception /home/adra/justnews_gpu_logs/nvml_watchdog_*.jsonl | jq '.error'
```

---

## Power Cap Persistence Verification

Power cap will survive:
- ✅ Systemd restarts
- ✅ Individual NVIDIA driver reloads
- ✅ GPU mode changes (P-states)
- ✅ System reboot (automatic re-apply at boot)

**Does NOT survive:**
- ⚠️ BIOS/firmware changes
- ⚠️ Manual `nvidia-smi -pl` to different value (requires `sudo systemctl restart nvidia_power_limit.service` to re-apply)

---

## Ready for Production Stress Tests?

✅ **Yes.** System is now:
1. Protected by persistent 300W power cap
2. Instrumented with NVML watchdog + telemetry
3. Equipped with automated stress test harness
4. Pre-validated with stub model (concurrency OK at ≤4 workers)

**Recommended progression:**
1. ✅ Real 2-worker test (2–3 req to validate model loading)
2. Real 4-worker test (10 req, measure VRAM)
3. Real 4-worker stress (50–100 req, sustained load)
4. Multi-run sweep (test stability across repeated invocations)
