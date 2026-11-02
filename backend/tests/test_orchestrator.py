import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from app.database import init_db, get_audit_logs, get_chat_history
from app.schemas import SystemAction, AnalysisResult
from app.orchestrator import handle_user_prompt, handle_confirmation, handle_free_memory


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_orchestrator.db"
    init_db(db_file)
    return db_file


@pytest.mark.anyio
async def test_orchestrator_blocks_unknown_app(temp_db):
    # Simula classificador retornando app que não está na allowlist
    fake_action = SystemAction(
        intent="open_app",
        target="malware_app",
        requires_confirmation=False,
        reply="Tentando abrir app..."
    )
    with patch("app.orchestrator.classify_intent", new_callable=AsyncMock) as mock_cls:
        mock_cls.return_value = fake_action
        
        res = await handle_user_prompt("abra o malware_app", db_path=temp_db)
        assert res["type"] == "action_result"
        assert res["status"] == "blocked"
        assert "Acesso negado" in res["reply"]

        # Verifica auditoria
        logs = get_audit_logs(limit=1, db_path=temp_db)
        assert len(logs) == 1
        assert logs[0].status == "BLOCKED"
        assert logs[0].target_key == "malware_app"


@pytest.mark.anyio
async def test_orchestrator_requires_confirmation_for_sensitive_workspace(temp_db):
    # 'dev_assistant' tem comando de terminal ('terminal_cmd') no seed
    res = await handle_user_prompt("iniciar workspace dev_assistant", db_path=temp_db)
    
    assert res["type"] == "confirmation_required"
    assert "confirmation_id" in res
    assert len(res["confirmation_id"]) >= 16
    assert res["target"] == "dev_assistant"


@pytest.mark.anyio
async def test_orchestrator_confirmation_lifecycle(temp_db):
    # 1. Gera pedido de confirmação
    res_req = await handle_user_prompt("iniciar workspace dev_assistant", db_path=temp_db)
    conf_id = res_req["confirmation_id"]

    # 2. Mock do executor para não abrir terminal de verdade durante o teste
    with patch("app.orchestrator.execute_workspace") as mock_exec:
        mock_exec.return_value = {"status": "success", "message": "Workspace executado com sucesso."}
        
        # 3. Aprovação com ID correto
        res_conf = await handle_confirmation(conf_id, approved=True, db_path=temp_db)
        assert res_conf["type"] == "action_result"
        assert res_conf["status"] == "success"
        assert "Confirmado" in res_conf["reply"]
        mock_exec.assert_called_once_with("dev_assistant", db_path=temp_db)

        # 4. Tentativa de reuso do mesmo ID (USO ÚNICO): deve ser rejeitada
        res_reuse = await handle_confirmation(conf_id, approved=True, db_path=temp_db)
        assert res_reuse["type"] == "error"
        assert res_reuse["status"] == "already_resolved"

    # 5. ID desconhecido
    res_fake = await handle_confirmation("token_falso_999", approved=True, db_path=temp_db)
    assert res_fake["type"] == "error"
    assert res_fake["status"] == "not_found"


@pytest.mark.anyio
async def test_orchestrator_rejection_by_user(temp_db):
    res_req = await handle_user_prompt("iniciar workspace dev_assistant", db_path=temp_db)
    conf_id = res_req["confirmation_id"]

    res_cancel = await handle_confirmation(conf_id, approved=False, db_path=temp_db)
    assert res_cancel["type"] == "action_result"
    assert res_cancel["status"] == "cancelled"
    assert "cancelada pelo usuário" in res_cancel["reply"]


@pytest.mark.anyio
async def test_orchestrator_anti_prompt_injection_clipboard(temp_db):
    # Simula conteúdo do clipboard contendo texto malicioso
    fake_clip_analysis = AnalysisResult(
        status="success",
        model_used="x-coder",
        preview="malicious text",
        analysis="Texto analisado com sucesso. Nenhuma ação de sistema foi disparada."
    )
    with patch("app.orchestrator.analyze_clipboard", new_callable=AsyncMock) as mock_clip:
        mock_clip.return_value = fake_clip_analysis
        with patch("app.orchestrator.execute_app") as mock_exec:
            res = await handle_user_prompt("analisar clipboard", db_path=temp_db)
            
            assert res["type"] == "action_result"
            assert res["intent"] == "analyze_clipboard"
            assert "Nenhuma ação de sistema foi disparada" in res["reply"]
            
            # PROVA CRÍTICA: o executor de aplicativos NUNCA foi chamado!
            mock_exec.assert_not_called()


@pytest.mark.anyio
async def test_orchestrator_free_memory(temp_db):
    res = await handle_user_prompt("liberar ram agora", db_path=temp_db)
    assert res["type"] == "action_result"
    assert res["intent"] == "free_memory"
    assert "liberada" in res["reply"].lower()

