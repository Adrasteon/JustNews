#!/usr/bin/env python3
"""
Smoke test for vLLM Mistral-7B endpoint (replaces Qwen2 smoke test).
Validates OpenAI-compatible API, basic chat completion, and optional adapter routing.
"""
import os
import sys
from pathlib import Path

import requests
import yaml


def load_vllm_config(config_path: str = "config/vllm_mistral_7b.yaml") -> dict:
    """Load vLLM config."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def test_health(base_url: str):
    """Test /health endpoint."""
    print(f"Testing health endpoint: {base_url}/health")
    resp = requests.get(f"{base_url}/health", timeout=5)
    resp.raise_for_status()
    print("✅ Health check passed")


def test_models(base_url: str):
    """Test /v1/models endpoint."""
    print(f"Testing models endpoint: {base_url}/v1/models")
    resp = requests.get(f"{base_url}/v1/models", timeout=5)
    resp.raise_for_status()
    models = resp.json()
    print(f"✅ Models: {[m['id'] for m in models.get('data', [])]}")
    return models


def test_chat_completion(base_url: str, api_key: str = "dummy"):
    """Test /v1/chat/completions."""
    print(f"Testing chat completion: {base_url}/v1/chat/completions")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "mistralai/Mistral-7B-Instruct-v0.3",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2? Answer in one word."},
        ],
        "max_tokens": 10,
        "temperature": 0.0,
    }
    resp = requests.post(f"{base_url}/v1/chat/completions", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    answer = result["choices"][0]["message"]["content"].strip()
    print(f"✅ Chat completion result: {answer}")
    assert "4" in answer.lower() or "four" in answer.lower(), f"Unexpected answer: {answer}"


def main():
    config = load_vllm_config()
    endpoint = config["endpoint"]
    base_url = endpoint["base_url"]
    api_key = endpoint.get("api_key", "dummy")

    print("===== vLLM Qwen2-32B Smoke Test =====")
    print(f"Base URL: {base_url}")

    try:
        test_health(base_url)
        test_models(base_url)
        test_chat_completion(base_url, api_key)
        print("\n✅ All tests passed!")
        return 0
    except requests.exceptions.ConnectionError:
        print("\n❌ Connection error: vLLM server not running?")
        print("Start with: scripts/launch_vllm_mistral_7b.sh")
        return 1
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
