---
title: NewsReader Agent - Production-Validated Configuration
description: Auto-generated description for NewsReader Agent - Production-Validated Configuration
tags: [documentation]
status: current
last_updated: 2025-09-12
---

# NewsReader Agent - Production-Validated Configuration

## 🚨 **CRITICAL UPDATE: GPU Crash Resolution - August 13, 2025**

**MAJOR BREAKTHROUGH**: All PC crashes resolved through proper configuration identification and correction.

### **Root Cause Analysis**
The crashes were **NOT caused by GPU memory exhaustion** but by:
1. **Incorrect quantization method**: Using `torch_dtype=torch.int8` instead of `BitsAndBytesConfig`
2. **Improper LLaVA conversation formatting**: Wrong image input structure
3. **SystemD environment issues**: Missing CUDA variables (resolved)

### **✅ Production-Validated Solution**
- **Correct Method**: `BitsAndBytesConfig` with `load_in_8bit=True`
- **Memory Usage**: Stable 6.85GB GPU allocation (well within 25GB limits)
- **Crash Testing**: 100% success rate including critical 5th image analysis
- **Documentation**: Complete setup guide in `markdown_docs/development_reports/Using-The-GPU-Correctly.md`

## 📁 Directory Organization

### **Main Agent Files** (Top Level)
- `newsreader_v2_true_engine.py` - **Production engine with crash-resolved configuration** ⭐
- `main_v2.py` - **Active FastAPI service** (crash-resolved, systemd-compatible) ⭐
- `tools.py` - Agent tool implementations with proper V2 engine integration
- `requirements.txt` - Python dependencies

### **📂 `/main_options/`** - Alternative Implementations
Contains variant newsreader implementations for different use cases:
- `advanced_quantized_llava.py` - Advanced quantization with memory optimization
- `llava_newsreader_agent.py` - Standard LLaVA implementation
- `quantized_llava_newsreader_agent.py` - INT8 quantized version
- `optimized_llava_test.py` - Performance testing implementation
- **`practical_newsreader_solution.py`** - Practical INT8 approach with dual model fallback

### **📂 `/documentation/`** - Technical Documentation
- `IMPLEMENTATION_SUMMARY.md` - Implementation overview and decisions
- `INT8_QUANTIZATION_RATIONALE.md` - Quantization strategy documentation
- `LIFESPAN_MIGRATION.md` - Migration and lifecycle documentation

### **📂 `/archive/`** - Development Artifacts
- `*.log` - Agent execution logs
- `*.png` - Screenshot outputs and test results
- `*.sh` - Development shell scripts
- Previous development versions

## 🎯 **Current Production Implementation**

**File**: `newsreader_v2_true_engine.py` + `main_v2.py`  
**Status**: ✅ **Production-validated, crash-resolved** 
**Features**:
- **Crash-Safe Configuration**: Proper `BitsAndBytesConfig` quantization method
- **Conservative Memory Limits**: 8GB maximum GPU usage (crash-safe mode)
- **Correct LLaVA Format**: Proper conversation structure with separate image/text inputs
- **SystemD Compatible**: Correct environment variables and service configuration
- **Memory Monitoring**: Real-time GPU and system memory tracking

### **Production Performance Metrics**
```
✅ Validated Operation (August 13, 2025):
- GPU Memory: 6.85GB allocated, 7.36GB reserved
- System Memory: 24.8% usage (~7.3GB of 31GB)
- Model Loading: ~14 seconds (with quantization)
- Analysis Speed: ~7-8 seconds per image
- Crash Rate: 0% (previously 100% at 5th image)
```

## 🔧 **Development Workflow**

### Adding New Implementations
1. Develop new variants in `/main_options/`
2. Test thoroughly with validation scripts
3. When ready for production, copy to `newsreader_agent.py`
4. Archive previous version to `/main_options/`

### **NEW: Practical Solution Implementation** 
**File**: `main_options/practical_newsreader_solution.py`

The practical approach implements user insight on INT8 quantization:
- ✅ **Dual Model Fallback**: LLaVA-1.5-7B → BLIP-2 if needed
- ✅ **Smart Memory Management**: Proper model sizing instead of forcing large models to fit
- ✅ **Production Ready**: FastAPI endpoints, health checks, memory monitoring
- ✅ **Quantization First**: INT8 optimization as primary approach, not afterthought
- ✅ **Zero Warnings**: Clean model loading with BitsAndBytesConfig

### Documentation Updates
- Technical documentation → `/documentation/`
- Development logs and outputs → `/archive/`
- Keep main directory clean with only active files

## 📊 **Performance Metrics**
- **Model**: LLaVA-1.5-7B with INT8 quantization
- **GPU Memory**: 6.8GB stable utilization
- **Processing**: Screenshot analysis + DOM extraction
- **Reliability**: Zero crashes with proper modal handling

---

*Last Updated: August 2, 2025*  
*Organization: Clean structure for production deployment and development*

## See also

- Technical Architecture: markdown_docs/TECHNICAL_ARCHITECTURE.md
- Documentation Catalogue: docs/DOCUMENTATION_CATALOGUE.md

