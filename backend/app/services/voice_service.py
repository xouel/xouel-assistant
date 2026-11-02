import os
import sys
import gc
import queue
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

# Garante que as DLLs nativas do CTranslate2 (libiomp5md, msvcp140) sejam localizadas no Windows
_ct2_dir = Path(sys.prefix) / "Lib" / "site-packages" / "ctranslate2"
if _ct2_dir.exists() and hasattr(os, "add_dll_directory"):
    try:
        os.add_dll_directory(str(_ct2_dir))
    except Exception:
        pass


# ============================================================================
# 1. SÍNTESE DE VOZ OFFLINE (SAPI5 NATIVO DO WINDOWS VIA DEDICATED THREAD)
# ============================================================================

_tts_queue: "queue.Queue[Optional[str]]" = queue.Queue()
_tts_thread: Optional[threading.Thread] = None
_tts_lock = threading.Lock()


def _tts_worker_loop():
    """
    Worker em thread dedicada com inicialização segura de COM (pythoncom.CoInitialize).
    Garante que as chamadas SAPI5 não concorram com as threads do FastAPI.
    """
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    speaker = None
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        
        # Procura e seleciona a voz em português (ex: Microsoft Maria)
        voices = speaker.GetVoices()
        for i in range(voices.Count):
            desc = voices.Item(i).GetDescription()
            if "portuguese" in desc.lower() or "brazil" in desc.lower() or "maria" in desc.lower():
                speaker.Voice = voices.Item(i)
                break

        while True:
            text = _tts_queue.get()
            if text is None:  # Sinal de encerramento
                break
            if text.strip():
                try:
                    # Limpa quebras de linha e limita tamanho para resposta falada concisa
                    clean_text = text.replace("\n", " ").strip()[:350]
                    # 0 = Flags normais síncronos na thread dedicada do worker
                    speaker.Speak(clean_text, 0)
                except Exception:
                    pass
            _tts_queue.task_done()

    except Exception:
        pass
    finally:
        del speaker
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _ensure_tts_worker_running():
    global _tts_thread
    with _tts_lock:
        if _tts_thread is None or not _tts_thread.is_alive():
            _tts_thread = threading.Thread(target=_tts_worker_loop, name="XAssistant-TTS", daemon=True)
            _tts_thread.start()


def speak_text_offline(text: str) -> None:
    """
    Enfileira uma mensagem para ser falada pelo sintetizador nativo do Windows em background.
    Custo de RAM praticamente zero e sem bloquear a aplicação.
    """
    if not text or not text.strip():
        return
    _ensure_tts_worker_running()
    _tts_queue.put(text)


def list_available_tts_voices() -> List[Dict[str, Any]]:
    """Lista as vozes SAPI5 instaladas no Windows com liberação limpa de ponteiros COM."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    voices = speaker.GetVoices()
    result = []
    for i in range(voices.Count):
        v = voices.Item(i)
        desc = v.GetDescription()
        is_pt = "portuguese" in desc.lower() or "brazil" in desc.lower() or "maria" in desc.lower()
        result.append({
            "index": i,
            "description": desc,
            "is_portuguese": is_pt,
        })
        del v
    del voices
    del speaker
    gc.collect()
    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass
    return result


# ============================================================================
# 2. TRANSCRIÇÃO DE VOZ OFFLINE (FASTER-WHISPER COM LAZY LOADING)
# ============================================================================

_whisper_model = None
_whisper_model_name = "base"  # Padrão recomendado: robusto em pt-BR e consome ~250 MB
_whisper_lock = threading.Lock()


def get_or_load_whisper_model(model_size: str = "base"):
    """
    Lazy loading: carrega o modelo Whisper na CPU apenas quando o primeiro áudio for recebido.
    Utiliza 4 threads (número medido na Task 01) e quantização int8 para mínima pegada de RAM.
    """
    global _whisper_model, _whisper_model_name
    with _whisper_lock:
        if _whisper_model is None or _whisper_model_name != model_size:
            from faster_whisper import WhisperModel
            _whisper_model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
            )
            _whisper_model_name = model_size
        return _whisper_model


def unload_whisper_model() -> Dict[str, Any]:
    """
    Descarrega o modelo Whisper da RAM sob demanda (botão 'Ejetar RAM').
    """
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is not None:
            del _whisper_model
            _whisper_model = None
            gc.collect()
            return {"status": "unloaded", "message": "Modelo Whisper liberado da memória."}
    return {"status": "already_empty", "message": "Nenhum modelo Whisper carregado na RAM."}


def transcribe_audio_file(
    audio_path: Path,
    language: str = "pt",
    model_size: str = "base",
) -> Dict[str, Any]:
    """
    Transcreve um arquivo de áudio (.webm, .wav, .mp3, etc.) usando faster-whisper.
    O PyAV embutido decodifica streams do navegador (MediaRecorder) sem depender de ffmpeg externo.
    """
    if not audio_path.exists():
        return {"status": "error", "message": f"Arquivo de áudio não encontrado: '{audio_path}'"}

    try:
        model = get_or_load_whisper_model(model_size=model_size)
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=1,
            vad_filter=True,  # Filtro de silêncio (Voice Activity Detection)
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return {
            "status": "success",
            "text": text,
            "language": info.language,
            "duration": round(info.duration, 2),
            "model_used": model_size,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Erro na transcrição de áudio: {str(exc)}",
        }
