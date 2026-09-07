"""Configuration tests only. No test in this file makes a network call or
spends a real Nebius credit: NebiusNemotronProvider.judge() is never invoked
here, only __init__, which just reads environment/constructor values and
validates them.
"""

import pytest

from relay_gate.judge import NebiusNemotronProvider


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setenv("NEBIUS_MODEL_ID", "nvidia/placeholder-for-test")
    with pytest.raises(RuntimeError, match="NEBIUS_API_KEY"):
        NebiusNemotronProvider()


def test_missing_model_id_raises(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-not-real")
    monkeypatch.delenv("NEBIUS_MODEL_ID", raising=False)
    with pytest.raises(RuntimeError, match="NEBIUS_MODEL_ID"):
        NebiusNemotronProvider()


def test_constructs_when_both_configured(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-not-real")
    monkeypatch.setenv("NEBIUS_MODEL_ID", "nvidia/placeholder-for-test")
    provider = NebiusNemotronProvider()
    assert provider.api_key == "test-key-not-real"
    assert provider.model_id == "nvidia/placeholder-for-test"


def test_constructor_args_override_environment(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "env-key")
    monkeypatch.setenv("NEBIUS_MODEL_ID", "env-model")
    provider = NebiusNemotronProvider(api_key="explicit-key", model_id="explicit-model")
    assert provider.api_key == "explicit-key"
    assert provider.model_id == "explicit-model"
