import pytest
from app.services.telemetry import (
    warmup_telemetry,
    get_ollama_processes_memory,
    get_loaded_ollama_models,
    get_system_telemetry,
)


def test_warmup_telemetry():
    # Deve rodar sem levantar exceções
    warmup_telemetry()


def test_ollama_processes_memory():
    rss, count = get_ollama_processes_memory()
    assert isinstance(rss, int)
    assert isinstance(count, int)
    assert rss >= 0
    assert count >= 0


@pytest.mark.anyio
async def test_loaded_ollama_models():
    models = await get_loaded_ollama_models()
    assert isinstance(models, list)
    # Se houver modelo carregado, deve ser uma string
    for m in models:
        assert isinstance(m, str)


@pytest.mark.anyio
async def test_get_system_telemetry():
    t = await get_system_telemetry()
    assert "cpu_percent" in t
    assert "ram_total_gb" in t
    assert "ram_used_gb" in t
    assert "ram_free_gb" in t
    assert "ram_percent" in t
    assert "ollama_ram_mb" in t
    assert "active_models" in t
    assert "is_dual_channel" in t
    assert "memory_mode_label" in t

    assert t["ram_total_gb"] > 0
    assert 0 <= t["ram_percent"] <= 100
    assert 0 <= t["cpu_percent"] <= 100

