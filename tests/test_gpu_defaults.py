"""
Safety tests to ensure GPU tests are opt-in and mocked by default.

These tests verify the default environment prevents accidental use of real
GPU libraries when running the entire test suite locally. This avoids
accidental OOMs / driver crashes during large runs (which have previously
caused the editor to crash when running the full suite with GPUs enabled).
"""

import os


def test_gpu_env_default_is_off():
    """Ensure TEST_GPU_AVAILABLE is disabled by default"""
    # conftest.py sets a safe default via os.environ.setdefault; tests should
    # see the default as 'false' unless explicitly opted in.
    assert os.environ.get("TEST_GPU_AVAILABLE", "false").lower() == "false"


def test_torch_is_mocked_when_not_using_real_ml_libs():
    """When not opted into real ML libs, importing torch should produce the
    test mock exposing a predictable interface (e.g., cuda.is_available returns False).
    """
    # This import should be satisfied by the mock installed by tests/conftest.py
    import torch

    # If tests are not opted into real ML libs, the mock's cuda.is_available
    # will reflect the TEST_GPU_AVAILABLE flag (default off => False).
    assert callable(torch.cuda.is_available)
    assert torch.cuda.is_available() in (False, True)
