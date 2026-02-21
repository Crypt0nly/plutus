"""Tests for configuration management."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from plutus.config import PlutusConfig, ModelConfig, GuardrailsConfig, _deep_merge


class TestConfig:
    def test_default_config(self):
        config = PlutusConfig()
        assert config.model.provider == "anthropic"
        assert config.guardrails.tier == "assistant"
        assert config.gateway.port == 7777

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "config.json"

            with patch("plutus.config.config_path", return_value=cfg_path):
                config = PlutusConfig()
                config.model.provider = "openai"
                config.model.model = "gpt-4o"
                config.guardrails.tier = "operator"
                config.save()

                loaded = PlutusConfig.load()
                assert loaded.model.provider == "openai"
                assert loaded.model.model == "gpt-4o"
                assert loaded.guardrails.tier == "operator"

    def test_deep_merge(self):
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        override = {"a": {"b": 10}, "e": 4}
        _deep_merge(base, override)
        assert base == {"a": {"b": 10, "c": 2}, "d": 3, "e": 4}

    def test_model_config_defaults(self):
        mc = ModelConfig()
        assert mc.temperature == 0.7
        assert mc.max_tokens == 4096
        assert mc.base_url is None

    def test_guardrails_config_defaults(self):
        gc = GuardrailsConfig()
        assert gc.tier == "assistant"
        assert gc.audit_enabled is True
        assert gc.max_concurrent_tools == 3
