import time
import wave
import struct
import math
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.voice_service import (
    list_available_tts_voices,
    speak_text_offline,
    unload_whisper_model,
    transcribe_audio_file,
)


@pytest.fixture
def synthetic_wav(tmp_path: Path):
    """Gera um arquivo WAV de 1 segundo de silêncio para testar o decodificador."""
    wav_path = tmp_path / "test_audio.wav"
    sample_rate = 16000
    num_samples = sample_rate * 1  # 1 segundo

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Escreve silêncio (amostras com valor zero)
        data = struct.pack(f"<{num_samples}h", *([0] * num_samples))
        wf.writeframes(data)

    return wav_path


def test_list_available_tts_voices():
    voices = list_available_tts_voices()
    assert len(voices) > 0
    # Verifica que a voz pt-BR foi detectada
    pt_voices = [v for v in voices if v["is_portuguese"]]
    assert len(pt_voices) >= 1
    assert any("maria" in v["description"].lower() for v in pt_voices)


def test_speak_text_offline_enqueues_safely():
    # Deve enfileirar sem levantar exceções
    speak_text_offline("Mensagem de teste do X-Assistant.")
    # Pequena pausa para a thread processar
    time.sleep(0.1)


def test_unload_whisper_model_when_empty():
    res = unload_whisper_model()
    assert res["status"] in ("unloaded", "already_empty")


def test_transcribe_audio_file_not_found():
    res = transcribe_audio_file(Path("arquivo_que_nao_existe_123.wav"))
    assert res["status"] == "error"
    assert "não encontrado" in res["message"]


def test_transcribe_audio_with_mocked_model(synthetic_wav):
    mock_model = MagicMock()
    mock_info = MagicMock()
    mock_info.language = "pt"
    mock_info.duration = 1.0

    mock_segment = MagicMock()
    mock_segment.text = "teste de fala"

    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    with patch("app.services.voice_service.get_or_load_whisper_model", return_value=mock_model):
        res = transcribe_audio_file(synthetic_wav, language="pt")
        assert res["status"] == "success"
        assert res["text"] == "teste de fala"
        assert res["language"] == "pt"

