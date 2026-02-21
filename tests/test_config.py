"""Tests for configuration management."""

import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from plutus.config import PlutusConfig, ModelConfig, GuardrailsConfig, SecretsStore, _deep_merge


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


class TestSecretsStore:
    def test_set_and_get_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecretsStore(path=Path(tmpdir) / ".secrets.json")
            store.set_key("anthropic", "sk-ant-test123")
            assert store.get_key("anthropic") == "sk-ant-test123"

    def test_has_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecretsStore(path=Path(tmpdir) / ".secrets.json")
            old = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                assert store.has_key("anthropic") is False
                store.set_key("anthropic", "sk-ant-test123")
                assert store.has_key("anthropic") is True
            finally:
                os.environ.pop("ANTHROPIC_API_KEY", None)
                if old:
                    os.environ["ANTHROPIC_API_KEY"] = old

    def test_delete_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecretsStore(path=Path(tmpdir) / ".secrets.json")
            store.set_key("anthropic", "sk-ant-test123")
            assert store.has_key("anthropic") is True
            store.delete_key("anthropic")
            # Env var was injected by set_key, clear it for this test
            env_var = "ANTHROPIC_API_KEY"
            old = os.environ.pop(env_var, None)
            try:
                assert store.has_key("anthropic") is False
            finally:
                if old:
                    os.environ[env_var] = old

    def test_file_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_path = Path(tmpdir) / ".secrets.json"
            store = SecretsStore(path=secrets_path)
            store.set_key("openai", "sk-test456")
            mode = secrets_path.stat().st_mode
            # Should be owner read/write only (0600)
            assert mode & stat.S_IRUSR  # owner read
            assert mode & stat.S_IWUSR  # owner write
            assert not (mode & stat.S_IRGRP)  # no group read
            assert not (mode & stat.S_IROTH)  # no other read

    def test_env_var_takes_priority(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecretsStore(path=Path(tmpdir) / ".secrets.json")
            store.set_key("anthropic", "from-secrets-file")
            os.environ["ANTHROPIC_API_KEY"] = "from-env-var"
            try:
                assert store.get_key("anthropic") == "from-env-var"
            finally:
                os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_key_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecretsStore(path=Path(tmpdir) / ".secrets.json")
            # Clear any env vars that might interfere
            saved_envs = {}
            for var in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "API_KEY"]:
                saved_envs[var] = os.environ.pop(var, None)
            try:
                store.set_key("anthropic", "sk-test")
                status = store.key_status()
                assert status["anthropic"] is True
                assert status["openai"] is False
            finally:
                for var, val in saved_envs.items():
                    if val:
                        os.environ[var] = val

    def test_inject_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecretsStore(path=Path(tmpdir) / ".secrets.json")
            # Write keys directly to file (bypassing set_key which auto-injects)
            secrets_path = Path(tmpdir) / ".secrets.json"
            secrets_path.write_text(json.dumps({"anthropic": "sk-inject-test"}))
            # Clear env var
            os.environ.pop("ANTHROPIC_API_KEY", None)
            store.inject_all()
            try:
                assert os.environ.get("ANTHROPIC_API_KEY") == "sk-inject-test"
            finally:
                os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_get_key_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecretsStore(path=Path(tmpdir) / ".secrets.json")
            os.environ.pop("NONEXISTENT_PROVIDER_API_KEY", None)
            assert store.get_key("nonexistent_provider") is None
