import time
import pytest
from pathlib import Path
from app.schemas import AppEntry, WorkspaceEntry, WorkspaceStep, GitRepoEntry
from app.database import (
    init_db,
    list_allowed_apps,
    get_allowed_app,
    upsert_allowed_app,
    delete_allowed_app,
    list_workspaces,
    get_workspace,
    upsert_workspace,
    delete_workspace,
    list_git_repos,
    get_git_repo,
    upsert_git_repo,
    delete_git_repo,
    log_action,
    get_audit_logs,
    save_chat_message,
    get_chat_history,
    clear_chat_history,
    create_pending_confirmation,
    resolve_pending_confirmation,
)


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_assistant.db"
    init_db(db_file)
    return db_file


def test_seed_on_startup(temp_db):
    apps = list_allowed_apps(temp_db)
    workspaces = list_workspaces(temp_db)
    repos = list_git_repos(temp_db)

    # Verifica os seeds do config.py
    assert len(apps) >= 6
    app_keys = [a.key for a in apps]
    assert "vscode" in app_keys
    assert "terminal" in app_keys
    assert "calc" in app_keys

    assert len(workspaces) >= 3
    ws_keys = [w.key for w in workspaces]
    assert "dev_web" in ws_keys
    assert "dev_assistant" in ws_keys

    assert len(repos) >= 1
    assert repos[0].key == "x-assistant"


def test_seed_idempotency(temp_db):
    # Roda init_db uma segunda vez e garante que os dados não duplicam
    init_db(temp_db)
    apps = list_allowed_apps(temp_db)
    assert len(apps) >= 6


def test_allowed_apps_crud(temp_db):
    # Upsert novo app
    novo_app = AppEntry(
        key="spotify",
        name="Spotify Music",
        executable_path="spotify.exe",
        args="",
        requires_confirmation=False,
    )
    upsert_allowed_app(novo_app, temp_db)

    # Busca (case-insensitive)
    app = get_allowed_app("SPOTIFY", temp_db)
    assert app is not None
    assert app.name == "Spotify Music"

    # Atualiza app existente
    novo_app.args = "--minimized"
    upsert_allowed_app(novo_app, temp_db)
    app_atualizado = get_allowed_app("spotify", temp_db)
    assert app_atualizado.args == "--minimized"

    # Deleta app
    deleted = delete_allowed_app("spotify", temp_db)
    assert deleted is True
    assert get_allowed_app("spotify", temp_db) is None


def test_workspaces_crud(temp_db):
    ws = WorkspaceEntry(
        key="test_ws",
        name="Test Workspace",
        description="Workspace de teste",
        requires_confirmation=True,
        steps=[
            WorkspaceStep(type="app", target="calc"),
            WorkspaceStep(type="url", target="https://google.com"),
        ],
    )
    upsert_workspace(ws, temp_db)

    res = get_workspace("test_ws", temp_db)
    assert res is not None
    assert len(res.steps) == 2
    assert res.steps[0].type == "app"
    assert res.steps[1].target == "https://google.com"

    deleted = delete_workspace("test_ws", temp_db)
    assert deleted is True
    assert get_workspace("test_ws", temp_db) is None


def test_audit_logs_and_chat_history(temp_db):
    log_action("open_app", "calc", "SUCCESS", "Calculadora aberta", temp_db)
    log_action("run_command", "cmd.exe", "BLOCKED", "Tentativa fora da allowlist", temp_db)

    logs = get_audit_logs(limit=10, db_path=temp_db)
    assert len(logs) == 2
    assert logs[0].status == "BLOCKED"  # Mais recente primeiro
    assert logs[1].status == "SUCCESS"

    save_chat_message("user", "x-fast", "Olá assistente", "chat_response", temp_db)
    save_chat_message("assistant", "x-fast", "Olá! Como posso ajudar?", "chat_response", temp_db)

    history = get_chat_history(limit=10, db_path=temp_db)
    assert len(history) == 2
    assert history[0]["role"] == "user"

    clear_chat_history(temp_db)
    assert len(get_chat_history(limit=10, db_path=temp_db)) == 0


def test_pending_confirmations_security_lifecycle(temp_db):
    payload = {"type": "terminal_cmd", "cmd": "git push"}
    
    # 1. Cria confirmação com token aleatório
    conf_id = create_pending_confirmation(
        intent="run_workspace",
        target="dev_assistant",
        payload=payload,
        reply="Deseja confirmar a execução do comando?",
        ttl_seconds=120,
        db_path=temp_db,
    )
    assert isinstance(conf_id, str)
    assert len(conf_id) >= 16  # ID criptográfico, não número sequencial

    # 2. Aprova dentro do prazo
    status, res_payload = resolve_pending_confirmation(conf_id, approved=True, db_path=temp_db)
    assert status == "APPROVED"
    assert res_payload == payload

    # 3. Tentativa de reuso (USO ÚNICO): deve ser rejeitada
    status_reuse, res_payload_reuse = resolve_pending_confirmation(conf_id, approved=True, db_path=temp_db)
    assert status_reuse == "ALREADY_RESOLVED"
    assert res_payload_reuse is None

    # 4. ID inexistente
    status_fake, _ = resolve_pending_confirmation("token_inexistente_123", approved=True, db_path=temp_db)
    assert status_fake == "NOT_FOUND"

    # 5. Expiração temporal (TTL)
    expired_id = create_pending_confirmation(
        intent="run_workspace",
        target="sensivel",
        payload={"secret": 123},
        reply="Confirmar?",
        ttl_seconds=-10,  # Já criado expirado no passado
        db_path=temp_db,
    )
    status_exp, res_exp = resolve_pending_confirmation(expired_id, approved=True, db_path=temp_db)
    assert status_exp == "EXPIRED"
    assert res_exp is None

