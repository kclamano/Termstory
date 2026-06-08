import os
import json
import pytest
from unittest.mock import patch, mock_open

from termstory.config import load_config, save_config, get_config_path

def test_load_config_corrupted_file(tmp_path):
    # Mock get_config_path to point to our tmp_path
    config_file = tmp_path / "config.json"
    
    # Write corrupted JSON
    config_file.write_text("{corrupted_json: [")
    
    with patch("termstory.config.get_config_path", return_value=str(config_file)):
        config = load_config()
        
        # It should fallback to defaults
        assert config["ai_enabled"] is False
        assert config["active_provider"] == "disabled"
        assert config["providers"]["groq"]["model_name"] == "llama-3.1-8b-instant"

def test_load_config_missing_file(tmp_path):
    config_file = tmp_path / "config.json"
    
    with patch("termstory.config.get_config_path", return_value=str(config_file)):
        config = load_config()
        
        assert config["ai_enabled"] is False
        assert config["active_provider"] == "disabled"

def test_save_config_error_handling(tmp_path):
    # If open fails, save_config should not raise an exception
    with patch("termstory.config.get_config_path", return_value="/invalid/path/that/does/not/exist/config.json"):
        save_config({"test": "data"})  # Should silently pass
