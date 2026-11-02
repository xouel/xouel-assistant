import os
import re
import sys
import json
import asyncio
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Header,
    UploadFile,
    File,
    Query,
    status,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    HOST,
    PORT,
    ALLOWED_ORIGINS,
    MODEL_FAST,
    MODEL_CODER,
    MODEL_VISION,
    FRONTEND_DIST_DIR,
)
from app.schemas import (
    ChatRequest,
    ConfirmActionRequest,
    ClipboardRequest,
    GitCommitRequest,
    VisionRequest,
    TTSRequest,
    AppEntry,
    WorkspaceEntry,
    GitRepoEntry,
    AuditLogEntry,
    WSMessage,
)
from app.database import (
    init_db,
    list_allowed_apps,
    list_workspaces,
    list_git_repos,
    get_audit_logs,
    get_chat_history,
    clear_chat_history,
    create_pending_confirmation,
)
from app.services.telemetry import warmup_telemetry, get_system_telemetry
from app.services.ollama_service import stream_chat_response
from app.services.dev_tools import (
    analyze_clipboard,
    suggest_commit_message,
    analyze_screen,
)
from app.services.voice_service import (
    speak_text_offline,
    transcribe_audio_file,
    unload_whisper_model,
)
from app.orchestrator import (
    handle_user_prompt,
    handle_confirmation,
    handle_free_memory,
)
from app.security import (
    get_or_create_local_token,
    get_local_token,
    verify_local_token,
    validate_ws_origin,
    authenticate_ws_token,
    check_port_available,
)


# ============================================================================
# LIFESPAN: INICIALIZAÇÃO SEGURA DO ASSISTENTE
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Inicialização atômica do X-Assistant:
    1. Cria esquema de tabelas e seeds SQLite caso seja a 1ª execução.
    2. Aquece o psutil para evitar leitura 0.0% na telemetria inicial.
    3. Gera ou carrega o token criptográfico em .local_token.
    """
    init_db()
    warmup_telemetry()
    token = get_or_create_local_token()
    print(f"[*] X-Assistant Backend inicializado em http://{HOST}:{PORT}")
    print(f"[*] Token local de segurança ativo ({len(token)} chars)")
    yield
    print("[*] Encerrando serviços do X-Assistant...")


# ============================================================================
# APLICAÇÃO FASTAPI E MIDDLEWARES
# ============================================================================

app = FastAPI(
    title="X-Assistant API",
    description="Motor Local de Automação, IA e Produtividade para Desenvolvedores",
    version="1.0.0",
    lifespan=lifespan,
)

# Proteção contra Host Header Injection (apenas localhost/127.0.0.1 e testserver do pytest)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "testserver"],
)

# CORS estrito para origens autorizadas da interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# 1. ROTAS DE SAÚDE E AUTENTICAÇÃO
# ============================================================================

@app.get("/api/health", tags=["Status"])
async def health_check():
    """Health check público para checagem rápida pelo launcher e scripts locais."""
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/auth/status", tags=["Segurança"], dependencies=[Depends(verify_local_token)])
async def auth_status():
    """Valida se o token enviado no header X-Local-Token está correto."""
    return {"status": "authenticated"}


# ============================================================================
# 2. ROTAS DO ORQUESTRADOR E SISTEMA (PROTEGIDAS)
# ============================================================================

@app.post("/api/chat", tags=["Orquestrador"], dependencies=[Depends(verify_local_token)])
async def api_chat(req: ChatRequest):
    """
    Roteia o comando do usuário pelo orquestrador central:
    Classifica a intenção -> Executa ação permitida -> Retorna resposta estruturada.
    """
    res = await handle_user_prompt(
        prompt=req.prompt,
        mode=req.mode,
        speak_reply=req.speak_reply,
    )
    return res


@app.post("/api/confirm", tags=["Segurança"], dependencies=[Depends(verify_local_token)])
async def api_confirm(req: ConfirmActionRequest):
    """
    Resolve uma ação sensível pendente (abertura de app sensível, workspace com terminal ou mutação de allowlist).
    O ID de confirmação tem uso único e expiração de 2 minutos.
    """
    res = await handle_confirmation(
        confirmation_id=req.confirmation_id,
        approved=req.approved,
    )
    return res


@app.get("/api/system/telemetry", tags=["Telemetria"], dependencies=[Depends(verify_local_token)])
async def api_telemetry():
    """Retorna o snapshot de uso de CPU, RAM e memória do Ollama em tempo real."""
    return await get_system_telemetry()


@app.post("/api/system/unload", tags=["Sistema"], dependencies=[Depends(verify_local_token)])
async def api_unload_memory():
    """Descarrega imediatamente todos os modelos do Ollama e Whisper da memória RAM."""
    return await handle_free_memory()


# ============================================================================
# 3. FERRAMENTAS DEV (ANTI-PROMPT INJECTION - CANAL SÓ-TEXTO)
# ============================================================================

@app.post("/api/devtools/clipboard", tags=["DevTools"], dependencies=[Depends(verify_local_token)])
async def api_clipboard(req: ClipboardRequest):
    """Lê com segurança o clipboard e aciona o especialista x-coder sem executar ações de sistema."""
    res = await analyze_clipboard(
        instruction=req.instruction,
        speak_reply=req.speak_reply,
    )
    return res.model_dump()


@app.post("/api/devtools/git-commit", tags=["DevTools"], dependencies=[Depends(verify_local_token)])
async def api_git_commit(req: GitCommitRequest):
    """Lê o git diff do repositório monitorado e sugere mensagem de commit convencional."""
    return await suggest_commit_message(
        repo_key=req.repo_key,
        custom_path=req.custom_path,
    )


@app.post("/api/devtools/vision", tags=["DevTools"], dependencies=[Depends(verify_local_token)])
async def api_vision(req: VisionRequest):
    """Captura e analisa a tela do usuário com o modelo de visão x-vision."""
    res = await analyze_screen(
        prompt=req.prompt,
        source_preference=req.source_preference,
        speak_reply=req.speak_reply,
    )
    return res.model_dump()


# ============================================================================
# 4. VOZ E ÁUDIO OFFLINE
# ============================================================================

@app.post("/api/voice/transcribe", tags=["Voz"], dependencies=[Depends(verify_local_token)])
async def api_transcribe(file: UploadFile = File(...)):
    """
    Recebe blob de áudio gravado no navegador (MediaRecorder) e transcreve via faster-whisper.
    """
    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        try:
            content = await file.read()
            tmp.write(content)
            tmp.flush()
        except Exception as exc:
            return {"status": "error", "message": f"Erro ao receber upload: {str(exc)}"}

    try:
        result = transcribe_audio_file(tmp_path)
        return result
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


@app.post("/api/voice/tts", tags=["Voz"], dependencies=[Depends(verify_local_token)])
async def api_tts(req: TTSRequest):
    """Enfileira texto para síntese de voz nativa SAPI5 (sem travar o servidor)."""
    speak_text_offline(req.text)
    return {"status": "queued", "text": req.text}


# ============================================================================
# 5. GERENCIAMENTO DA ALLOWLIST (MUTAÇÕES EXIGEM CONFIRMAÇÃO)
# ============================================================================

# --- Aplicativos ---

@app.get("/api/allowlist/apps", tags=["Allowlist"], dependencies=[Depends(verify_local_token)])
async def api_list_apps():
    """Lista todos os aplicativos cadastrados na Allowlist."""
    return [app.model_dump() for app in list_allowed_apps()]


@app.post("/api/allowlist/apps", tags=["Allowlist"], dependencies=[Depends(verify_local_token)])
async def api_upsert_app(entry: AppEntry):
    """
    Solicita inclusão/atualização de aplicativo na Allowlist.
    REGRA DE SEGURANÇA: Não altera diretamente. Retorna confirmation_required.
    """
    conf_id = create_pending_confirmation(
        intent="allowlist_mutation",
        target=entry.key,
        payload={
            "action_type": "allowlist_mutation",
            "mutation": "upsert_app",
            "data": entry.model_dump(),
        },
        reply=f"Confirmar cadastro/atualização do aplicativo '{entry.name}' ({entry.key})?",
    )
    return {
        "type": "confirmation_required",
        "confirmation_id": conf_id,
        "intent": "allowlist_mutation",
        "target": entry.key,
        "reply": f"A alteração da Allowlist para '{entry.name}' exige sua confirmação de segurança.",
    }


@app.delete("/api/allowlist/apps/{key}", tags=["Allowlist"], dependencies=[Depends(verify_local_token)])
async def api_delete_app(key: str):
    """
    Solicita exclusão de aplicativo da Allowlist.
    REGRA DE SEGURANÇA: Retorna confirmation_required.
    """
    conf_id = create_pending_confirmation(
        intent="allowlist_mutation",
        target=key,
        payload={
            "action_type": "allowlist_mutation",
            "mutation": "delete_app",
            "data": {"key": key},
        },
        reply=f"Confirmar exclusão do aplicativo '{key}' da Allowlist?",
    )
    return {
        "type": "confirmation_required",
        "confirmation_id": conf_id,
        "intent": "allowlist_mutation",
        "target": key,
        "reply": f"A exclusão de '{key}' da Allowlist exige sua confirmação de segurança.",
    }


# --- Workspaces Compostos ---

@app.get("/api/allowlist/workspaces", tags=["Allowlist"], dependencies=[Depends(verify_local_token)])
async def api_list_workspaces():
    """Lista todos os workspaces compostos cadastrados."""
    return [ws.model_dump() for ws in list_workspaces()]


@app.post("/api/allowlist/workspaces", tags=["Allowlist"], dependencies=[Depends(verify_local_token)])
async def api_upsert_workspace(entry: WorkspaceEntry):
    """
    Solicita criação/atualização de workspace composto.
    REGRA DE SEGURANÇA: Retorna confirmation_required.
    """
    conf_id = create_pending_confirmation(
        intent="allowlist_mutation",
        target=entry.key,
        payload={
            "action_type": "allowlist_mutation",
            "mutation": "upsert_workspace",
            "data": entry.model_dump(),
        },
        reply=f"Confirmar cadastro do workspace '{entry.name}' ({len(entry.steps)} passos)?",
    )
    return {
        "type": "confirmation_required",
        "confirmation_id": conf_id,
        "intent": "allowlist_mutation",
        "target": entry.key,
        "reply": f"O cadastro do workspace '{entry.name}' exige sua confirmação de segurança.",
    }


@app.delete("/api/allowlist/workspaces/{key}", tags=["Allowlist"], dependencies=[Depends(verify_local_token)])
async def api_delete_workspace(key: str):
    """Solicita remoção de workspace composto via confirmação."""
    conf_id = create_pending_confirmation(
        intent="allowlist_mutation",
        target=key,
        payload={
            "action_type": "allowlist_mutation",
            "mutation": "delete_workspace",
            "data": {"key": key},
        },
        reply=f"Confirmar exclusão do workspace '{key}'?",
    )
    return {
        "type": "confirmation_required",
        "confirmation_id": conf_id,
        "intent": "allowlist_mutation",
        "target": key,
        "reply": f"A exclusão do workspace '{key}' exige sua confirmação.",
    }


# --- Repositórios Git Monitorados ---

@app.get("/api/allowlist/repos", tags=["Allowlist"], dependencies=[Depends(verify_local_token)])
async def api_list_repos():
    """Lista os repositórios Git monitorados."""
    return [repo.model_dump() for repo in list_git_repos()]


@app.post("/api/allowlist/repos", tags=["Allowlist"], dependencies=[Depends(verify_local_token)])
async def api_upsert_repo(entry: GitRepoEntry):
    """Solicita inclusão de repositório via confirmação."""
    conf_id = create_pending_confirmation(
        intent="allowlist_mutation",
        target=entry.key,
        payload={
            "action_type": "allowlist_mutation",
            "mutation": "upsert_git_repo",
            "data": entry.model_dump(),
        },
        reply=f"Confirmar monitoramento do repositório '{entry.name}' ({entry.key})?",
    )
    return {
        "type": "confirmation_required",
        "confirmation_id": conf_id,
        "intent": "allowlist_mutation",
        "target": entry.key,
        "reply": f"O cadastro do repositório '{entry.name}' exige sua confirmação.",
    }


@app.delete("/api/allowlist/repos/{key}", tags=["Allowlist"], dependencies=[Depends(verify_local_token)])
async def api_delete_repo(key: str):
    """Solicita remoção de repositório monitorado via confirmação."""
    conf_id = create_pending_confirmation(
        intent="allowlist_mutation",
        target=key,
        payload={
            "action_type": "allowlist_mutation",
            "mutation": "delete_git_repo",
            "data": {"key": key},
        },
        reply=f"Confirmar remoção do repositório '{key}'?",
    )
    return {
        "type": "confirmation_required",
        "confirmation_id": conf_id,
        "intent": "allowlist_mutation",
        "target": key,
        "reply": f"A remoção do repositório '{key}' exige sua confirmação.",
    }


# ============================================================================
# 6. HISTÓRICO DE CHAT E AUDITORIA
# ============================================================================

@app.get("/api/audit-logs", tags=["Auditoria"], dependencies=[Depends(verify_local_token)])
async def api_audit_logs(limit: int = Query(50, ge=1, le=200)):
    """Retorna os registros de auditoria mais recentes."""
    return [entry.model_dump() for entry in get_audit_logs(limit=limit)]


@app.get("/api/chat-history", tags=["Histórico"], dependencies=[Depends(verify_local_token)])
async def api_chat_history(limit: int = Query(50, ge=1, le=200)):
    """Retorna as mensagens salvas no histórico de conversa."""
    return get_chat_history(limit=limit)


@app.delete("/api/chat-history", tags=["Histórico"], dependencies=[Depends(verify_local_token)])
async def api_clear_chat_history():
    """Limpa o histórico de mensagens salvas."""
    clear_chat_history()
    return {"status": "cleared", "message": "Histórico de conversa limpo com sucesso."}


# ============================================================================
# 7. WEBSOCKET EM TEMPO REAL (/ws)
# ============================================================================

async def _telemetry_background_worker(websocket: WebSocket):
    """
    Envia a telemetria do sistema imediatamente ao conectar e a cada 2 segundos.
    """
    while True:
        try:
            telemetry = await get_system_telemetry()
            msg = WSMessage(type="telemetry", data=telemetry)
            await websocket.send_text(msg.model_dump_json())
            await asyncio.sleep(2.0)
        except (WebSocketDisconnect, asyncio.CancelledError):
            break
        except Exception:
            await asyncio.sleep(2.0)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Canal bidirecional em tempo real:
    - Validação de Origin (apenas origens permitidas).
    - Handshake obrigatório: 1ª mensagem deve ter type="auth" e token válido em até 5 segundos.
    - Telemetria periódica em background (2s).
    - Streaming de resposta token-a-token para perguntas de chat e despacho de ações do sistema.
    """
    # 1. Validação de Origin
    origin = websocket.headers.get("origin")
    if not validate_ws_origin(origin):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # 2. Handshake de Autenticação (timeout de 5 segundos)
    try:
        raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        auth_payload = json.loads(raw_auth)
        auth_type = auth_payload.get("type")
        token = auth_payload.get("token") or (auth_payload.get("data") or {}).get("token")

        if auth_type != "auth" or not authenticate_ws_token(token):
            err_msg = WSMessage(type="error", text="Autenticação falhou: token inválido ou ausente.")
            await websocket.send_text(err_msg.model_dump_json())
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    except (asyncio.TimeoutError, Exception):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3. Notifica autenticação com sucesso
    ok_msg = WSMessage(type="auth_ok", text="Conexão autenticada com sucesso.")
    await websocket.send_text(ok_msg.model_dump_json())

    # 4. Inicia worker de telemetria em background
    telemetry_task = asyncio.create_task(_telemetry_background_worker(websocket))

    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                msg_dict = json.loads(raw_msg)
            except Exception:
                continue

            msg_type = msg_dict.get("type")

            # Tratamento de mensagem de chat do usuário
            if msg_type == "user_message":
                prompt = msg_dict.get("text") or msg_dict.get("prompt") or ""
                mode = msg_dict.get("mode") or MODEL_FAST
                speak = bool(msg_dict.get("speak", False))
                stream_enabled = bool(msg_dict.get("stream", False))

                # Orquestra intenção e execução
                res = await handle_user_prompt(prompt=prompt, mode=mode, speak_reply=speak)

                res_type = res.get("type")

                # Caso 1: Ação sensível exigindo confirmação do usuário
                if res_type == "confirmation_required":
                    await websocket.send_text(
                        WSMessage(
                            type="confirmation_required",
                            data=res,
                            text=res.get("reply", "Confirmação de segurança necessária."),
                        ).model_dump_json()
                    )

                # Caso 2: Conversa geral com streaming token a token solicitado
                elif res_type == "chat_response" and stream_enabled:
                    full_reply = ""
                    async for chunk in stream_chat_response(prompt, model=mode):
                        full_reply += chunk
                        await websocket.send_text(
                            WSMessage(type="token", token=chunk).model_dump_json()
                        )
                    await websocket.send_text(
                        WSMessage(type="done", text=full_reply).model_dump_json()
                    )

                # Caso 3: Resultado de ação direta ou resposta de chat padrão
                else:
                    await websocket.send_text(
                        WSMessage(
                            type="action_result",
                            data=res,
                            text=res.get("reply", ""),
                        ).model_dump_json()
                    )

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Encerramento limpo da tarefa de telemetria sem órfãos
        telemetry_task.cancel()
        try:
            await telemetry_task
        except asyncio.CancelledError:
            pass


# ============================================================================
# 8. SERVIDOR DE BUILD ESTÁTICO DO FRONT-END (MODO APP UNIFICADO)
# ============================================================================

_assets_dir = FRONTEND_DIST_DIR / "assets"
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend_index():
    """
    Serve o index.html compilado em frontend/dist injetando dinamicamente o
    token local (.local_token) em window.__X_LOCAL_TOKEN__.
    """
    index_file = FRONTEND_DIST_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse(
            content=(
                "<html><body style='background:#09090b;color:#fafafa;font-family:sans-serif;padding:2rem;'>"
                "<h2>X-Assistant Backend Online</h2>"
                "<p>Build do front-end não encontrado em <code>frontend/dist</code>. "
                "Execute <code>cd frontend &amp;&amp; npm run build</code>.</p>"
                "</body></html>"
            ),
            status_code=200,
        )

    raw_html = index_file.read_text(encoding="utf-8")
    token = get_local_token()
    token_script = f"window.__X_LOCAL_TOKEN__ = {json.dumps(token)};"

    if "window.__X_LOCAL_TOKEN__" in raw_html:
        injected_html = re.sub(
            r"window\.__X_LOCAL_TOKEN__\s*=\s*.*?;",
            lambda _: token_script,
            raw_html,
        )
    else:
        injected_html = raw_html.replace(
            "</head>",
            f"  <script>{token_script}</script>\n  </head>",
        )

    return HTMLResponse(
        content=injected_html,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


# ============================================================================
# ENTRY POINT DE INICIALIZAÇÃO COM VERIFICAÇÃO DE PORTA OCUPADA
# ============================================================================

def start():
    """Inicia o servidor FastAPI garantindo que a porta 8000 esteja livre."""
    available, pid, proc_name = check_port_available(PORT, HOST)
    if not available:
        print(
            f"\n[ERRO CRÍTICO] A porta {PORT} já está em uso pelo processo "
            f"PID {pid} ({proc_name}).\n"
            f"Finalize o processo ocupante ou altere a porta em 'backend/app/config.py'.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    start()
