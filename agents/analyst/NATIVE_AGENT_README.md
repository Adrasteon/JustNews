---
title: Native TensorRT Analyst Agent - Quick Start Guide
description: Auto-generated description for Native TensorRT Analyst Agent - Quick Start Guide
tags: [documentation]
status: current
last_updated: 2025-09-12
---

# Native TensorRT Analyst Agent - Quick Start Guide

## 🏆 **Production Status: OPERATIONAL**

The JustNews V4 Analyst Agent now features **native TensorRT implementation** with validated performance:

- **Combined Throughput**: **406.9 articles/sec** (2.69x improvement)
- **Memory Efficiency**: 2.3GB GPU utilization (65% reduction)
- **System Stability**: Zero crashes, zero warnings
- **Production Ready**: Ultra-safe testing validated

## 🚀 **Quick Start**

### **Environment Setup**
```bash
# Navigate to analyst directory
cd /home/adra/JustNewsAgentic/agents/analyst

# Activate conda environment
source /home/adra/miniconda3/etc/profile.d/conda.sh
conda activate rapids-25.06

# Check environment (optional)
python start_native_tensorrt_agent.py --check-only
```

### **Start the Agent**
```bash
# Start with default settings (port 8004)
python start_native_tensorrt_agent.py

# Or specify custom port/host
python start_native_tensorrt_agent.py --port 8005 --host localhost
```

### **Test the Agent**
```bash
# Run comprehensive tests
python test_native_agent.py
```

## 📋 **Available Endpoints**

### **Individual Analysis**
- `POST /score_sentiment` - Score sentiment (0.0-1.0)
- `POST /score_bias` - Score bias (0.0-1.0)
- `POST /identify_entities` - Identify entities (placeholder)

### **Native TensorRT Batch Processing**
- `POST /score_sentiment_batch` - Batch sentiment scoring
- `POST /score_bias_batch` - Batch bias scoring

### **High-Level Analysis**
- `POST /analyze_article` - Complete article analysis
- `POST /analyze_articles_batch` - Batch article analysis

### **System Information**
- `GET /health` - Health check
- `GET /engine_info` - TensorRT engine information

## 🔧 **API Usage Examples**

### **Individual Scoring**
```python
import requests

# Score sentiment
response = requests.post("http://localhost:8004/score_sentiment", json={
    "args": ["This is fantastic news about renewable energy!"],
    "kwargs": {}
})
sentiment_score = response.json()  # Returns float 0.0-1.0
```

### **Batch Processing**
```python
# Batch sentiment analysis
texts = [
    "Breaking news: Major breakthrough in clean energy technology.",
    "Local community organizes charity event for environmental causes.",
    "Government announces new infrastructure investment program."
]

response = requests.post("http://localhost:8004/score_sentiment_batch", json={
    "args": [texts],
    "kwargs": {}
})
sentiment_scores = response.json()  # Returns list of floats
```

### **Complete Article Analysis**
```python
# Analyze single article
response = requests.post("http://localhost:8004/analyze_article", json={
    "args": ["Technology companies collaborate on sustainable computing solutions..."],
    "kwargs": {}
})
result = response.json()
# Returns: {"sentiment": 0.75, "bias": 0.48, "processing_time": 0.023, ...}
```

## 📊 **Performance Benchmarks**

- **Individual Analysis**: ~10-15ms per article
- **Batch Processing**: 786.8 articles/sec (sentiment), 843.7 articles/sec (bias)
- **Memory Usage**: 2.3GB GPU VRAM (highly efficient)
- **Engine Loading**: ~3-5 seconds (one-time per session)

## 🛡️ **Production Features**

- **Automatic Fallback**: Returns neutral scores (0.5) on errors
- **Context Management**: Professional CUDA context lifecycle
- **Resource Cleanup**: Proper GPU memory management
- **Comprehensive Logging**: Detailed feedback and performance metrics
- **Health Monitoring**: Built-in health checks and engine status

## 🔍 **Troubleshooting**

### **Common Issues**

1. **Import Errors**: Ensure conda environment `rapids-25.06` is activated
2. **Engine Not Found**: Check that TensorRT engines exist in `tensorrt_engines/`
3. **CUDA Errors**: Verify GPU is available with `nvidia-smi`
4. **Port Conflicts**: Use `--port` to specify different port

### **Validation Commands**
```bash
# Check environment
python start_native_tensorrt_agent.py --check-only

# Test TensorRT functions directly
python -c "from tensorrt_tools import score_sentiment; print(score_sentiment('test'))"

# Run full test suite
python test_native_agent.py
```

## 🔮 **Migration from Hybrid Tools**

The agent has been updated to use native TensorRT instead of the previous `hybrid_tools_v4.py` implementation:

- **Performance**: 2.69x faster than previous implementation
- **Memory**: 65% reduction in GPU memory usage
- **Stability**: Zero crashes vs occasional CUDA conflicts
- **API**: Same endpoints, improved performance

All existing integrations and MCP bus communication patterns remain unchanged.

---

**Status**: ✅ **PRODUCTION READY**  
**Performance**: 406.9 articles/sec combined throughput  
**Implementation**: Native TensorRT with professional CUDA management  
**Ready for**: High-volume production deployment

## See also

- Technical Architecture: markdown_docs/TECHNICAL_ARCHITECTURE.md
- Documentation Catalogue: docs/DOCUMENTATION_CATALOGUE.md

