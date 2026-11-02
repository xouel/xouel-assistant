import pytest
from app.schemas import SystemAction
from app.services.ollama_service import (
    fast_path_intent_parser,
    classify_intent,
    stream_chat_response,
    unload_all_models,
    is_ollama_online,
)


def test_fast_path_deterministic():
    # 1. Ejeção de RAM
    res = fast_path_intent_parser("assistente, favor liberar ram agora")
    assert res is not None
    assert res.intent == "free_memory"

    # 2. Abertura de App
    res = fast_path_intent_parser("abrir calculadora")
    assert res is not None
    assert res.intent == "open_app"
    assert res.target == "calc"

    # 3. Workspace
    res = fast_path_intent_parser("iniciar workspace dev_web")
    assert res is not None
    assert res.intent == "run_workspace"
    assert res.target == "dev_web"

    # 4. Clipboard
    res = fast_path_intent_parser("analise o clipboard")
    assert res is not None
    assert res.intent == "analyze_clipboard"

    # 5. Git Commit
    res = fast_path_intent_parser("gerar commit do git")
    assert res is not None
    assert res.intent == "generate_git_commit"

    # 6. Pergunta aberta deve retornar None para cair no LLM
    res = fast_path_intent_parser("O que é um closure em Python?")
    assert res is None


@pytest.mark.anyio
async def test_ollama_is_online():
    online = await is_ollama_online()
    assert online is True


@pytest.mark.anyio
async def test_classify_intent_via_llm():
    # Pergunta livre -> LLM deve classificar como chat_response
    action = await classify_intent("O que é uma função assíncrona no Python?")
    assert isinstance(action, SystemAction)
    assert action.intent == "chat_response"
    assert len(action.reply) > 0


@pytest.mark.anyio
async def test_stream_chat_response():
    chunks = []
    async for chunk in stream_chat_response("Diga apenas a palavra 'Teste'"):
        chunks.append(chunk)
    full_text = "".join(chunks)
    assert len(full_text) > 0


@pytest.mark.anyio
async def test_unload_all_models():
    res = await unload_all_models()
    assert res["status"] in ("success", "offline")

