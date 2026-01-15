## JustNews Test Resource Management - Quick Reference

### 🎯 Problem Solved
- **Before**: 2,140 Python processes → RAM exhaustion → VS Code crash
- **After**: ~100 processes, controlled parallelism, 63GB total memory

---

### 🚀 Quick Start

**Run all tests (recommended):**
```bash
./scripts/run_live_tests.sh
```

**Common scenarios:**
```bash
# GPU tests only
./scripts/run_live_tests.sh --gpu

# With coverage
./scripts/run_live_tests.sh --cov

# Fast mode (skip slow tests)
./scripts/run_live_tests.sh --fast

# Debug mode (sequential)
./scripts/run_live_tests.sh --sequential -vv

# Custom worker count
./scripts/run_live_tests.sh -n 4
```

---

### 📊 Resource Configuration

| Resource | Value | Why |
|----------|-------|-----|
| **RAM** | 31 GB | System hardware |
| **Swap** | 32 GB | Upgraded from 8GB |
| **Workers** | 6 | Balanced speed/safety |
| **Process Limit** | 1000 | Prevents runaway spawning |
| **Total Memory** | 63 GB | Safe for parallel tests |

---

### ⚙️ Settings Changed

**pytest.ini:**
```ini
addopts = -n 6 --dist worksteal --maxfail=3
```

**conftest.py:**
- ✅ Process limit: 1000 max
- ✅ Session-scoped fixtures

**tests/database/conftest.py:**
- ✅ `mock_embedding_model` → session scope
- ✅ `mock_chromadb_client_session` → session scope

**requirements.txt:**
- ✅ Added `pytest-xdist>=3.5.0`

---

### 🔍 Monitor Resources

**During test run:**
```bash
watch -n 1 'ps aux | grep python | wc -l'  # Process count
watch -n 1 'free -h'                       # Memory usage
```

**Check for OOM events:**
```bash
sudo dmesg -T | grep -i "out of memory" | tail -20
```

---

### 🎛️ Tuning Options

**Conservative (slower, safer):**
```bash
./scripts/run_live_tests.sh -n 4
```

**Aggressive (faster, more RAM):**
```bash
./scripts/run_live_tests.sh -n 8
```

**Debug (slowest, minimal RAM):**
```bash
./scripts/run_live_tests.sh --sequential
```

---

### ⚠️ If Tests Still Crash

1. **Reduce workers:**
   ```bash
   ./scripts/run_live_tests.sh -n 2
   ```

2. **Check services are running:**
   ```bash
   systemctl status justnews-*
   ```

3. **Monitor memory during run:**
   ```bash
   watch -n 1 'free -h'
   ```

4. **Run subset of tests:**
   ```bash
   ./scripts/run_live_tests.sh -k "test_specific"
   ```

---

### 📈 Expected Performance

| Workers | Speed | RAM Peak | Duration | Safety |
|---------|-------|----------|----------|--------|
| 2 | 4x | 10 GB | 15-20 min | ⭐⭐⭐⭐⭐ |
| 4 | 6-8x | 12-15 GB | 8-15 min | ⭐⭐⭐⭐ |
| 6 | 8-10x | 15-20 GB | 5-10 min | ⭐⭐⭐ |
| 8 | 12-15x | 20-25 GB | 4-7 min | ⭐⭐ |

---

### ✅ Verification

**Check all fixes are active:**
```bash
bash /tmp/verify_fixes.sh
```

**Should show:**
- ✅ Swap: 32G
- ✅ pytest -n 6 in config
- ✅ Process limit in conftest
- ✅ Session-scoped fixtures
- ✅ Test runner exists

---

### 📚 Full Documentation

See [`docs/test-resource-management.md`](test-resource-management.md) for complete details.

---

### 🆘 Emergency Stop

If tests are consuming too much RAM:

```bash
# Stop all Python test processes
pkill -9 -f pytest

# Monitor cleanup
watch -n 1 'ps aux | grep python | wc -l'
```

---

**Last Updated**: January 14, 2026  
**Issue Reference**: OOM event at 15:18:30 (2,140 processes spawned)  
**Status**: ✅ Resolved with controlled parallelism
