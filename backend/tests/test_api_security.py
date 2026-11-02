import json
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.config import TOKEN_PATH
from app.security import get_local_token, get_or_create_local_token
from app.database import init_db


@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    """Garante que o banco de dados e o token estejam inicializados para os testes."""
    init_db()
    get_or_create_local_token()


@pytest.fixture
def auth_headers():
    token = get_local_token()
    return {"X-Local-Token": token}


def test_health_endpoint_is_public():
    """O health check deve responder 200 sem necessidade de token."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_missing_token_returns_401():
    """Requisição a endpoint protegido sem header X-Local-Token deve retornar 401."""
    client = TestClient(app)
    response = client.get("/api/system/telemetry")
    assert response.status_code == 401
    assert "não autorizado" in response.json()["detail"].lower()


def test_invalid_token_returns_401():
    """Requisição a endpoint protegido com token falso deve retornar 401."""
    client = TestClient(app)
    response = client.get(
        "/api/system/telemetry",
        headers={"X-Local-Token": "token_falso_invalido_123"},
    )
    assert response.status_code == 401
    assert "inválido" in response.json()["detail"].lower()


def test_valid_token_allows_access(auth_headers):
    """Requisição com token correto no header deve retornar 200 e dados válidos."""
    client = TestClient(app)
    response = client.get("/api/system/telemetry", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "cpu_percent" in data
    assert "ram_total_gb" in data
    assert "is_dual_channel" in data
    assert "memory_mode_label" in data


def test_trusted_host_blocks_unauthorized_host(auth_headers):
    """TrustedHostMiddleware deve recusar cabeçalhos Host não autorizados com 400."""
    client = TestClient(app)
    # Envia Host malicioso
    response = client.get("/api/health", headers={"Host": "malicious-site.com"})
    assert response.status_code == 400


def test_allowlist_mutation_requires_confirmation_and_resolves(auth_headers):
    """
    REGRA CRÍTICA DE SEGURANÇA:
    Qualquer alteração na Allowlist via API NÃO grava direto;
    devolve 'confirmation_required' com ID seguro para posterior aprovação.
    """
    client = TestClient(app)

    new_app = {
        "key": "app_teste_seguro",
        "name": "App de Teste Seguro",
        "executable_path": "calc.exe",
        "args": "",
        "requires_confirmation": False,
    }

    # 1. Tenta cadastrar via POST
    post_res = client.post("/api/allowlist/apps", json=new_app, headers=auth_headers)
    assert post_res.status_code == 200
    data = post_res.json()

    assert data["type"] == "confirmation_required"
    assert "confirmation_id" in data
    conf_id = data["confirmation_id"]
    assert len(conf_id) > 10

    # 2. Verifica se o app ainda NÃO foi salvo na Allowlist
    list_res = client.get("/api/allowlist/apps", headers=auth_headers)
    apps = list_res.json()
    assert not any(a["key"] == "app_teste_seguro" for a in apps)

    # 3. Resolve a confirmação aprovando a ação
    confirm_payload = {
        "confirmation_id": conf_id,
        "approved": True,
    }
    confirm_res = client.post("/api/confirm", json=confirm_payload, headers=auth_headers)
    assert confirm_res.status_code == 200
    conf_data = confirm_res.json()
    assert conf_data["status"] == "success"
    assert "salvo na Allowlist" in conf_data["reply"]

    # 4. Agora o app DEVE estar presente na Allowlist
    list_res_after = client.get("/api/allowlist/apps", headers=auth_headers)
    apps_after = list_res_after.json()
    assert any(a["key"] == "app_teste_seguro" for a in apps_after)

    # 5. Solicita remoção via DELETE
    del_res = client.delete("/api/allowlist/apps/app_teste_seguro", headers=auth_headers)
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["type"] == "confirmation_required"
    del_conf_id = del_data["confirmation_id"]

    # 6. Aprova a exclusão
    confirm_del = client.post(
        "/api/confirm",
        json={"confirmation_id": del_conf_id, "approved": True},
        headers=auth_headers,
    )
    assert confirm_del.status_code == 200

    # 7. Confirma que foi removido
    list_res_final = client.get("/api/allowlist/apps", headers=auth_headers)
    assert not any(a["key"] == "app_teste_seguro" for a in list_res_final.json())


def test_websocket_rejects_unauthorized_origin():
    """Conexão WebSocket com Origin desconhecido/externo deve ser rejeitada."""
    client = TestClient(app)
    try:
        with client.websocket_connect("/ws", headers={"Origin": "http://evil-site.com"}) as ws:
            pytest.fail("Conexão deveria ter sido recusada por Origin malicioso.")
    except Exception:
        # Starlette fecha a conexão com política violada
        pass


def test_websocket_rejects_unauthorized_token():
    """Conexão WebSocket com token inválido na 1ª mensagem deve ser rejeitada."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # Envia auth com token errado
        bad_auth = {"type": "auth", "token": "token_errado_invalido"}
        ws.send_text(json.dumps(bad_auth))

        raw_resp = ws.receive_text()
        resp = json.loads(raw_resp)
        assert resp["type"] == "error"
        assert "inválido" in resp["text"].lower()


def test_websocket_successful_handshake_and_flow():
    """
    Fluxo completo do WebSocket:
    1. Conecta.
    2. Envia mensagem de auth com o token legítimo.
    3. Recebe auth_ok.
    4. Envia mensagem de usuário e recebe a resposta estruturada.
    """
    token = get_local_token()
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        # 1. Envia auth
        auth_msg = {"type": "auth", "token": token}
        ws.send_text(json.dumps(auth_msg))

        raw_auth_resp = ws.receive_text()
        auth_resp = json.loads(raw_auth_resp)
        assert auth_resp["type"] == "auth_ok"

        # 2. Envia mensagem rápida de comando
        user_msg = {
            "type": "user_message",
            "text": "calc",
            "mode": "x-fast",
            "stream": False,
        }
        ws.send_text(json.dumps(user_msg))

        raw_reply = ws.receive_text()
        reply_data = json.loads(raw_reply)
        assert reply_data["type"] in ("action_result", "confirmation_required", "telemetry")


def test_root_serves_frontend_with_injected_token():
    """
    A rota raiz '/' deve servir o index.html do build estático injetando
    o token local em window.__X_LOCAL_TOKEN__.
    """
    token = get_local_token()
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert f'window.__X_LOCAL_TOKEN__ = "{token}";' in response.text
