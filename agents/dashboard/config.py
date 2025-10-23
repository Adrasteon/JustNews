"""
Configuration file for the Dashboard Agent.
This file handles loading and saving settings to persist between sessions.
"""

import json
import os

CONFIG_FILE_PATH = "dashboard_config.json"

def load_config():
    """Load the configuration from a JSON file."""
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, encoding="utf-8") as file:
            return json.load(file)
    return {
    "dashboard_port": 8013,
        "mcp_bus_url": "http://localhost:8000",
        "log_level": "INFO"
    }

def save_config(config):
    """Save the configuration to a JSON file."""
    with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4)
