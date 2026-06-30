import json
from unittest.mock import patch
from dct.core.config import Config, DEFAULTS


def test_config_load_success(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"history_limit": 50, "temperature": 0.5})
    )

    config = Config(str(config_file))

    assert config.get("history_limit") == 50
    assert config.get("temperature") == 0.5
    # Check default fallback for missing key
    assert config.get("max_agent_turns") == 12


def test_config_load_file_not_found(tmp_path):
    config_file = tmp_path / "config.json"
    config = Config(str(config_file))

    assert config.get("history_limit") == DEFAULTS["history_limit"]
    assert config.get("temperature") == DEFAULTS["temperature"]


def test_config_load_json_decode_error(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{malformed: json,}")

    config = Config(str(config_file))

    assert config.get("history_limit") == DEFAULTS["history_limit"]
    assert config.get("temperature") == DEFAULTS["temperature"]


def test_config_save(tmp_path):
    config_file = tmp_path / "config.json"
    config = Config(str(config_file))

    config.set("history_limit", 200)
    config.save()

    assert config_file.exists()
    saved_data = json.loads(config_file.read_text())
    assert saved_data["history_limit"] == 200


@patch("dct.core.config.open")
def test_config_generic_exception(mock_open, tmp_path, caplog):
    # Make open raise a generic exception to trigger the exception block in _load
    # Note os.makedirs is outside the try block, so we patch open instead
    mock_open.side_effect = Exception("Generic error")

    config_file = tmp_path / "config.json"
    config = Config(str(config_file))

    # Should fallback to defaults instead of crashing
    assert config.get("history_limit") == DEFAULTS["history_limit"]
    assert "Failed to load config from" in caplog.text


@patch("dct.core.config.json.dump")
def test_config_save_generic_exception(mock_json_dump, tmp_path, caplog):
    mock_json_dump.side_effect = Exception("Generic save error")
    config_file = tmp_path / "config.json"
    config = Config(str(config_file))

    config.save()
    assert "Failed to save config to" in caplog.text

def test_config_getitem_setitem(tmp_path):
    config_file = tmp_path / "config.json"
    config = Config(str(config_file))

    config["test_key"] = "test_value"
    assert config["test_key"] == "test_value"
