import os
import pytest
from typer.testing import CliRunner
from termstory.cli import app
from termstory.hermes_obs import modify_config_yaml, modify_env_file

def test_modify_config_yaml_fresh(tmp_path):
    config_file = tmp_path / "config.yaml"
    
    # 1. Enable from scratch (file doesn't exist)
    assert modify_config_yaml(str(config_file), enable=True) is True
    content = config_file.read_text()
    assert "plugins:" in content
    assert "observability/nemo_relay" in content
    
    # 2. Enable again (no change)
    assert modify_config_yaml(str(config_file), enable=True) is False
    
    # 3. Disable (should completely empty/remove config)
    assert modify_config_yaml(str(config_file), enable=False) is True
    assert config_file.read_text() == ""
    
    # 4. Disable again (no change)
    assert modify_config_yaml(str(config_file), enable=False) is False

def test_modify_config_yaml_existing_no_plugins(tmp_path):
    config_file = tmp_path / "config.yaml"
    orig_content = "model:\n  default: deepseek\n"
    config_file.write_text(orig_content)
    
    # Enable
    assert modify_config_yaml(str(config_file), enable=True) is True
    content = config_file.read_text()
    assert "model:" in content
    assert "observability/nemo_relay" in content
    
    # Disable
    assert modify_config_yaml(str(config_file), enable=False) is True
    # Should restore back to original
    assert config_file.read_text() == orig_content

def test_modify_config_yaml_existing_plugins_no_enabled(tmp_path):
    config_file = tmp_path / "config.yaml"
    orig_content = "plugins:\n  debug: true\n"
    config_file.write_text(orig_content)
    
    # Enable
    assert modify_config_yaml(str(config_file), enable=True) is True
    content = config_file.read_text()
    assert "debug: true" in content
    assert "observability/nemo_relay" in content
    
    # Disable
    assert modify_config_yaml(str(config_file), enable=False) is True
    assert config_file.read_text() == orig_content

def test_modify_config_yaml_existing_with_other_plugins(tmp_path):
    config_file = tmp_path / "config.yaml"
    orig_content = "plugins:\n  enabled:\n    - spotify\n"
    config_file.write_text(orig_content)
    
    # Enable
    assert modify_config_yaml(str(config_file), enable=True) is True
    content = config_file.read_text()
    assert "spotify" in content
    assert "observability/nemo_relay" in content
    
    # Disable
    assert modify_config_yaml(str(config_file), enable=False) is True
    assert config_file.read_text() == orig_content

def test_modify_env_file(tmp_path):
    env_file = tmp_path / ".env"
    
    # 1. Enable from scratch
    assert modify_env_file(str(env_file), enable=True) is True
    content = env_file.read_text()
    assert "HERMES_NEMO_RELAY_ATOF_ENABLED=true" in content
    assert "HERMES_NEMO_RELAY_ATIF_ENABLED=true" in content
    
    # 2. Enable again (no change)
    assert modify_env_file(str(env_file), enable=True) is False
    
    # 3. Disable (should remove lines)
    assert modify_env_file(str(env_file), enable=False) is True
    assert env_file.read_text().strip() == ""

def test_modify_env_file_existing(tmp_path):
    env_file = tmp_path / ".env"
    orig_content = "SOME_KEY=123\nHERMES_NEMO_RELAY_ATOF_ENABLED=false\nOTHER_KEY=456\n"
    env_file.write_text(orig_content)
    
    # Enable
    assert modify_env_file(str(env_file), enable=True) is True
    content = env_file.read_text()
    assert "HERMES_NEMO_RELAY_ATOF_ENABLED=true" in content
    assert "HERMES_NEMO_RELAY_ATIF_ENABLED=true" in content
    assert "SOME_KEY=123" in content
    
    # Disable
    assert modify_env_file(str(env_file), enable=False) is True
    content = env_file.read_text()
    assert "HERMES_NEMO_RELAY" not in content
    assert "SOME_KEY=123" in content
    assert "OTHER_KEY=456" in content

def test_cli_obs_enable_disable(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    config_file = tmp_path / "config.yaml"
    
    def mock_expanduser(path):
        if path == "~/.hermes/.env":
            return str(env_file)
        if path == "~/.hermes/config.yaml":
            return str(config_file)
        return path
        
    monkeypatch.setattr(os.path, "expanduser", mock_expanduser)
    
    runner = CliRunner()
    
    # 1. Test enable
    result = runner.invoke(app, ["obs"], input="y\n")
    assert result.exit_code == 0
    assert "enabled" in result.stdout.lower()
    assert env_file.exists()
    assert config_file.exists()
    
    assert "HERMES_NEMO_RELAY_ATOF_ENABLED=true" in env_file.read_text()
    assert "observability/nemo_relay" in config_file.read_text()
    
    # 2. Test disable
    result = runner.invoke(app, ["obs"], input="n\n")
    assert result.exit_code == 0
    assert "disabled" in result.stdout.lower()
    
    assert "HERMES_NEMO_RELAY" not in env_file.read_text()
    assert "observability/nemo_relay" not in config_file.read_text()
