import json
import pytest
from pydantic import ValidationError
from app.schemas import SystemAction, AnalysisResult, WSMessage, AppEntry, WorkspaceEntry, WorkspaceStep


def test_system_action_valid():
    raw = {
        "intent": "open_app",
        "target": "vscode",
        "requires_confirmation": False,
        "reply": "Abrindo o VS Code para você."
    }
    action = SystemAction.model_validate(raw)
    assert action.intent == "open_app"
    assert action.target == "vscode"
    assert action.requires_confirmation is False
    assert action.reply == "Abrindo o VS Code para você."


def test_system_action_invalid_intent_rejected():
    raw = {
        "intent": "executar_script_malicioso",
        "target": "cmd.exe",
        "reply": "Ok"
    }
    with pytest.raises(ValidationError) as exc_info:
        SystemAction.model_validate(raw)
    assert "Input should be" in str(exc_info.value)


def test_system_action_missing_required_reply_rejected():
    raw = {
        "intent": "open_app",
        "target": "calc"
    }
    with pytest.raises(ValidationError):
        SystemAction.model_validate(raw)


def test_analysis_result_pure_text():
    res = AnalysisResult(
        status="success",
        model_used="x-coder",
        preview="def foo(): ...",
        analysis="O erro ocorre devido a uma divisão por zero. Correção sugerida: validar o divisor."
    )
    assert res.status == "success"
    assert "divisão por zero" in res.analysis
    # Garante que não possui campos de ação do sistema
    assert not hasattr(res, "target")
    assert not hasattr(res, "requires_confirmation")


def test_ws_message_envelope():
    msg = WSMessage(
        type="telemetry",
        data={"cpu_percent": 15.2, "ram_used_gb": 6.4, "active_model": "x-fast"}
    )
    dumped = msg.model_dump()
    assert dumped["type"] == "telemetry"
    assert dumped["data"]["cpu_percent"] == 15.2


def test_json_schema_for_ollama():
    schema = SystemAction.model_json_schema()
    assert "properties" in schema
    assert "intent" in schema["properties"]
    assert "target" in schema["properties"]
    assert "reply" in schema["properties"]
    
    # Valida que o Ollama receberá a lista fechada de intenções
    intents = schema["properties"]["intent"]["enum"]
    assert "open_app" in intents
    assert "run_workspace" in intents
    assert "free_memory" in intents
    assert "chat_response" in intents


if __name__ == "__main__":
    test_system_action_valid()
    test_system_action_invalid_intent_rejected()
    test_system_action_missing_required_reply_rejected()
    test_analysis_result_pure_text()
    test_ws_message_envelope()
    test_json_schema_for_ollama()
    print(" Todos os 6 testes de contratos Pydantic passaram com sucesso!")

