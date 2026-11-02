import pytest
from pathlib import Path
from app.database import init_db, get_audit_logs, upsert_allowed_app
from app.schemas import AppEntry
from app.services.os_executor import (
    is_valid_allowlist_key,
    resolve_executable_path,
    execute_app,
    execute_workspace,
)


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_os_executor.db"
    init_db(db_file)
    return db_file


def test_is_valid_allowlist_key():
    # Chaves válidas
    assert is_valid_allowlist_key("vscode") is True
    assert is_valid_allowlist_key("dev_web") is True
    assert is_valid_allowlist_key("git-status") is True
    assert is_valid_allowlist_key("calc123") is True

    # Tentativas de injeção e caminhos de arquivo bloqueados
    assert is_valid_allowlist_key("calc & del /f") is False
    assert is_valid_allowlist_key("C:\\Windows\\System32\\cmd.exe") is False
    assert is_valid_allowlist_key("../etc/passwd") is False
    assert is_valid_allowlist_key("app; rm -rf") is False
    assert is_valid_allowlist_key("app | dir") is False
    assert is_valid_allowlist_key("") is False
    assert is_valid_allowlist_key(None) is False


def test_execute_app_blocked_for_unknown_key(temp_db):
    res = execute_app("app_inexistente_123", db_path=temp_db)
    assert res["status"] == "blocked"
    assert "Acesso negado" in res["message"]

    # Valida registro de auditoria
    logs = get_audit_logs(limit=1, db_path=temp_db)
    assert len(logs) == 1
    assert logs[0].status == "BLOCKED"
    assert logs[0].target_key == "app_inexistente_123"


def test_execute_app_blocked_for_injection_attempts(temp_db):
    malicious_inputs = [
        "calc & notepad.exe",
        "C:\\Windows\\System32\\cmd.exe",
        "; whoami",
        "calc | tasklist",
    ]
    for bad_input in malicious_inputs:
        res = execute_app(bad_input, db_path=temp_db)
        assert res["status"] == "blocked"


def test_execute_app_error_for_missing_executable_on_disk(temp_db):
    fake_app = AppEntry(
        key="fakeapp",
        name="Fake Application",
        executable_path=r"C:\Windows\System32\arquivo_que_com_certeza_nao_existe_xyz123.exe",
        args="",
        requires_confirmation=False,
    )
    upsert_allowed_app(fake_app, temp_db)

    res = execute_app("fakeapp", db_path=temp_db)
    assert res["status"] == "error"
    assert "Não foi possível localizar o executável" in res["message"]

    logs = get_audit_logs(limit=1, db_path=temp_db)
    assert len(logs) == 1
    assert logs[0].status == "ERROR"


def test_execute_app_success_with_dry_run(temp_db):
    # 'calc' está nos seeds da allowlist e existe no Windows
    res = execute_app("calc", db_path=temp_db, dry_run=True)
    assert res["status"] == "success"
    assert "[DRY_RUN]" in res["message"]
    assert "cmd" in res
    assert len(res["cmd"]) > 0

    logs = get_audit_logs(limit=1, db_path=temp_db)
    assert len(logs) == 1
    assert logs[0].status == "SUCCESS"
    assert logs[0].target_key == "calc"


def test_execute_workspace_blocked_and_success(temp_db):
    # 1. Workspace inexistente
    res_fake = execute_workspace("ws_desconhecido", db_path=temp_db)
    assert res_fake["status"] == "blocked"

    # 2. Workspace válido com dry_run
    res_ok = execute_workspace("dev_web", db_path=temp_db, dry_run=True)
    assert res_ok["status"] in ("success", "partial")
    assert len(res_ok["executed_steps"]) > 0

    logs = get_audit_logs(limit=2, db_path=temp_db)
    assert logs[0].action_type == "run_workspace"
    assert logs[0].target_key == "dev_web"

