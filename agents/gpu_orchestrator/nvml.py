import pynvml

# NVML State Manager
_NVML_HANDLE_CACHE = {}


def initialize_nvml():
    """Initialize NVML and populate handle cache."""
    pynvml.nvmlInit()
    device_count = pynvml.nvmlDeviceGetCount()
    for i in range(device_count):
        _NVML_HANDLE_CACHE[i] = pynvml.nvmlDeviceGetHandleByIndex(i)


def get_nvml_handle(index):
    """Retrieve NVML handle for a given index."""
    return _NVML_HANDLE_CACHE.get(index)


def shutdown_nvml():
    """Shutdown NVML and clear handle cache."""
    pynvml.nvmlShutdown()
    _NVML_HANDLE_CACHE.clear()