from pathlib import Path
from typing import Dict, Any, Optional

from app.config import MODEL_FAST, MODEL_CODER, MODEL_VISION
from app.schemas import SystemAction, AnalysisResult
from app.database import (
    get_allowed_app,
    get_workspace,
    log_action,
    save_chat_message,
    create_pending_confirmation,
    resolve_pending_confirmation,
)
from app.services.ollama_service import (
    classify_intent,
    unload_all_models,
)
from app.services.os_executor import (
    execute_app,
    execute_workspace,
    is_valid_allowlist_key,
)
from app.services.dev_tools import (
    analyze_clipboard,
    suggest_commit_message,
    analyze_screen,
)
from app.services.voice_service import (
    speak_text_offline,
    unload_whisper_model,
)


async def handle_free_memory(speak_reply: bool = False) -> Dict[str, Any]:
    """Descarrega todos os modelos do Ollama e o modelo Whisper da RAM."""
    ollama_res = await unload_all_models()
    whisper_res = unload_whisper_model()
    reply = "Modelos descarregados e memória RAM liberada."
    if speak_reply:
        speak_text_offline(reply)

    return {
        "type": "action_result",
        "intent": "free_memory",
        "status": "success",
        "reply": reply,
        "details": {
            "ollama": ollama_res,
            "whisper": whisper_res,
        },
    }


async def handle_user_prompt(
    prompt: str,
    mode: str = MODEL_FAST,
    speak_reply: bool = False,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Orquestrador central do fluxo de comando do usuário:
    1. Salva a mensagem do usuário no histórico.
    2. Classifica a intenção via classify_intent (Task 07).
    3. Roteia de acordo com a intenção e regras estritas de segurança da Allowlist.
    4. Se for ação sensível, cria pending_confirmation e devolve confirmation_required.
    5. Se for ação autorizada direta, executa via os_executor (Task 08).
    6. Se solicitada fala (speak_reply), reproduz áudio via SAPI5 (Task 11).
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return {
            "type": "error",
            "message": "Comando vazio.",
            "reply": "Por favor, digite ou fale um comando.",
        }

    # 1. Classificação da Intenção (Fast-path ou Structured Output)
    action: SystemAction = await classify_intent(clean_prompt, model=mode)
    intent = action.intent
    target = action.target
    reply = action.reply

    # Salva no histórico do chat
    save_chat_message("user", mode, clean_prompt, intent=intent, db_path=db_path)

    # 2. Despacho por Intenção

    # CASO A: Ejeção de RAM
    if intent == "free_memory":
        res = await handle_free_memory(speak_reply=speak_reply)
        save_chat_message("assistant", mode, res["reply"], intent=intent, db_path=db_path)
        return res

    # CASO B: Clipboard (Smart Clipboard)
    if intent == "analyze_clipboard":
        clip_res: AnalysisResult = await analyze_clipboard()
        msg_reply = f"{reply}\n\n{clip_res.analysis}"
        save_chat_message("assistant", MODEL_CODER, msg_reply, intent=intent, db_path=db_path)
        if speak_reply:
            speak_text_offline(reply)
        return {
            "type": "action_result",
            "intent": intent,
            "status": clip_res.status,
            "reply": msg_reply,
            "details": clip_res.model_dump(),
        }

    # CASO C: Git Commit
    if intent == "generate_git_commit":
        repo_key = target or "x-assistant"
        commit_res = await suggest_commit_message(repo_key=repo_key)
        if commit_res["status"] == "success":
            msg_reply = f"{reply}\n\nMensagem sugerida:\n```\n{commit_res['commit_message']}\n```"
        else:
            msg_reply = f"{reply}\n\n{commit_res.get('message', 'Erro ao ler git diff.')}"

        save_chat_message("assistant", MODEL_FAST, msg_reply, intent=intent, db_path=db_path)
        if speak_reply:
            speak_text_offline(reply)
        return {
            "type": "action_result",
            "intent": intent,
            "status": commit_res["status"],
            "reply": msg_reply,
            "details": commit_res,
        }

    # CASO D: Análise de Tela / Print
    if intent == "analyze_screenshot":
        vision_res: AnalysisResult = await analyze_screen(prompt=clean_prompt)
        msg_reply = f"{reply}\n\n{vision_res.analysis}"
        save_chat_message("assistant", MODEL_VISION, msg_reply, intent=intent, db_path=db_path)
        if speak_reply:
            speak_text_offline(reply)
        return {
            "type": "action_result",
            "intent": intent,
            "status": vision_res.status,
            "reply": msg_reply,
            "details": vision_res.model_dump(),
        }

    # CASO E: Abertura de Aplicativo da Allowlist
    if intent == "open_app":
        if not target or not is_valid_allowlist_key(target):
            log_action("open_app", target or "NULL", "BLOCKED", "Target ausente ou formato inválido", db_path)
            blocked_reply = f"Acesso negado: aplicativo '{target}' não reconhecido na Allowlist."
            save_chat_message("assistant", mode, blocked_reply, intent=intent, db_path=db_path)
            return {
                "type": "action_result",
                "intent": intent,
                "status": "blocked",
                "reply": blocked_reply,
            }

        app_entry = get_allowed_app(target, db_path=db_path)
        if not app_entry:
            log_action("open_app", target, "BLOCKED", "Chave fora da Allowlist", db_path)
            blocked_reply = f"Acesso negado: '{target}' não está cadastrado na Allowlist de aplicativos."
            save_chat_message("assistant", mode, blocked_reply, intent=intent, db_path=db_path)
            return {
                "type": "action_result",
                "intent": intent,
                "status": "blocked",
                "reply": blocked_reply,
            }

        # Se for app marcado como sensível -> exige confirmação
        if app_entry.requires_confirmation:
            payload = {"action_type": "open_app", "target": app_entry.key}
            conf_id = create_pending_confirmation(
                intent="open_app",
                target=app_entry.key,
                payload=payload,
                reply=f"Confirmar abertura do aplicativo '{app_entry.name}'?",
                ttl_seconds=120,
                db_path=db_path,
            )
            conf_reply = f"A ação de abrir '{app_entry.name}' é sensível e aguarda sua confirmação."
            save_chat_message("assistant", mode, conf_reply, intent=intent, db_path=db_path)
            return {
                "type": "confirmation_required",
                "confirmation_id": conf_id,
                "intent": "open_app",
                "target": app_entry.key,
                "reply": conf_reply,
            }

        # Execução direta autorizada
        exec_res = execute_app(app_entry.key, db_path=db_path)
        save_chat_message("assistant", mode, exec_res["message"], intent=intent, db_path=db_path)
        if speak_reply and exec_res["status"] == "success":
            speak_text_offline(reply)
        return {
            "type": "action_result",
            "intent": intent,
            "status": exec_res["status"],
            "reply": exec_res["message"],
            "details": exec_res,
        }

    # CASO F: Execução de Workspace Composto
    if intent == "run_workspace":
        if not target or not is_valid_allowlist_key(target):
            log_action("run_workspace", target or "NULL", "BLOCKED", "Target ausente ou formato inválido", db_path)
            blocked_reply = f"Acesso negado: workspace '{target}' não reconhecido na Allowlist."
            save_chat_message("assistant", mode, blocked_reply, intent=intent, db_path=db_path)
            return {
                "type": "action_result",
                "intent": intent,
                "status": "blocked",
                "reply": blocked_reply,
            }

        ws_entry = get_workspace(target, db_path=db_path)
        if not ws_entry:
            log_action("run_workspace", target, "BLOCKED", "Chave fora da Allowlist", db_path)
            blocked_reply = f"Acesso negado: o workspace '{target}' não está cadastrado."
            save_chat_message("assistant", mode, blocked_reply, intent=intent, db_path=db_path)
            return {
                "type": "action_result",
                "intent": intent,
                "status": "blocked",
                "reply": blocked_reply,
            }

        # Qualquer workspace contendo terminal_cmd ou marcado como requires_confirmation exige confirmação
        has_terminal = any(s.type == "terminal_cmd" for s in ws_entry.steps)
        if ws_entry.requires_confirmation or has_terminal:
            payload = {"action_type": "run_workspace", "target": ws_entry.key}
            conf_id = create_pending_confirmation(
                intent="run_workspace",
                target=ws_entry.key,
                payload=payload,
                reply=f"Confirmar execução do workspace '{ws_entry.name}' ({len(ws_entry.steps)} passos)?",
                ttl_seconds=120,
                db_path=db_path,
            )
            conf_reply = f"O workspace '{ws_entry.name}' contém comandos de terminal e aguarda sua confirmação."
            save_chat_message("assistant", mode, conf_reply, intent=intent, db_path=db_path)
            return {
                "type": "confirmation_required",
                "confirmation_id": conf_id,
                "intent": "run_workspace",
                "target": ws_entry.key,
                "reply": conf_reply,
            }

        # Execução direta autorizada
        ws_res = execute_workspace(ws_entry.key, db_path=db_path)
        save_chat_message("assistant", mode, ws_res["message"], intent=intent, db_path=db_path)
        if speak_reply and ws_res["status"] == "success":
            speak_text_offline(reply)
        return {
            "type": "action_result",
            "intent": intent,
            "status": ws_res["status"],
            "reply": ws_res["message"],
            "details": ws_res,
        }

    # CASO G: Resposta de Chat / Conversa Geral
    save_chat_message("assistant", mode, reply, intent="chat_response", db_path=db_path)
    if speak_reply:
        speak_text_offline(reply)
    return {
        "type": "chat_response",
        "intent": "chat_response",
        "reply": reply,
    }


async def handle_confirmation(
    confirmation_id: str,
    approved: bool,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Resolve uma ação sensível pendente com garantia de uso único e expiração:
    - O cliente envia APENAS o ID da confirmação e a flag de aprovação.
    - O servidor executa ESTRITAMENTE o payload que ele mesmo gravou no SQLite.
    """
    status, payload = resolve_pending_confirmation(confirmation_id, approved=approved, db_path=db_path)

    if status == "NOT_FOUND":
        return {
            "type": "error",
            "status": "not_found",
            "message": "Confirmação não encontrada ou ID inválido.",
            "reply": "ID de confirmação inválido ou não encontrado.",
        }

    if status == "ALREADY_RESOLVED":
        return {
            "type": "error",
            "status": "already_resolved",
            "message": "Esta ação já foi resolvida anteriormente (uso único).",
            "reply": "Esta solicitação de confirmação já foi utilizada.",
        }

    if status == "EXPIRED":
        return {
            "type": "error",
            "status": "expired",
            "message": "O tempo limite de 2 minutos para confirmar esta ação expirou.",
            "reply": "Confirmação expirada por tempo limite.",
        }

    if not approved:
        target = payload.get("target", "-") if payload else "-"
        log_action("confirm_action", target, "CANCELLED", "Usuário rejeitou a ação", db_path)
        return {
            "type": "action_result",
            "status": "cancelled",
            "reply": "Ação cancelada pelo usuário.",
        }

    # Executa o payload guardado no servidor
    action_type = payload.get("action_type")
    target = payload.get("target")

    if action_type == "open_app":
        res = execute_app(target, db_path=db_path)
        log_action("confirm_action", target, "SUCCESS", "Aprovado pelo usuário", db_path)
        return {
            "type": "action_result",
            "intent": "open_app",
            "status": res["status"],
            "reply": f"Confirmado: {res['message']}",
            "details": res,
        }

    if action_type == "run_workspace":
        res = execute_workspace(target, db_path=db_path)
        log_action("confirm_action", target, "SUCCESS", "Aprovado pelo usuário", db_path)
        return {
            "type": "action_result",
            "intent": "run_workspace",
            "status": res["status"],
            "reply": f"Confirmado: {res['message']}",
            "details": res,
        }

    if action_type == "allowlist_mutation":
        from app.database import (
            upsert_allowed_app,
            delete_allowed_app,
            upsert_workspace,
            delete_workspace,
            upsert_git_repo,
            delete_git_repo,
        )
        from app.schemas import AppEntry, WorkspaceEntry, GitRepoEntry

        mutation = payload.get("mutation")
        data = payload.get("data", {})

        if mutation == "upsert_app":
            entry = AppEntry(**data)
            upsert_allowed_app(entry, db_path=db_path)
            log_action("update_allowlist_app", entry.key, "SUCCESS", "Aplicativo atualizado com confirmação", db_path)
            return {
                "type": "action_result",
                "intent": "allowlist_mutation",
                "status": "success",
                "reply": f"Aplicativo '{entry.name}' ({entry.key}) salvo na Allowlist com sucesso.",
            }

        if mutation == "delete_app":
            key = data.get("key", "")
            deleted = delete_allowed_app(key, db_path=db_path)
            log_action("delete_allowlist_app", key, "SUCCESS" if deleted else "NOT_FOUND", "Remoção de app confirmada", db_path)
            return {
                "type": "action_result",
                "intent": "allowlist_mutation",
                "status": "success" if deleted else "not_found",
                "reply": f"Aplicativo '{key}' removido da Allowlist." if deleted else f"Aplicativo '{key}' não encontrado.",
            }

        if mutation == "upsert_workspace":
            ws_entry = WorkspaceEntry(**data)
            upsert_workspace(ws_entry, db_path=db_path)
            log_action("update_allowlist_workspace", ws_entry.key, "SUCCESS", "Workspace atualizado com confirmação", db_path)
            return {
                "type": "action_result",
                "intent": "allowlist_mutation",
                "status": "success",
                "reply": f"Workspace '{ws_entry.name}' ({ws_entry.key}) salvo com sucesso.",
            }

        if mutation == "delete_workspace":
            key = data.get("key", "")
            deleted = delete_workspace(key, db_path=db_path)
            log_action("delete_allowlist_workspace", key, "SUCCESS" if deleted else "NOT_FOUND", "Remoção de workspace confirmada", db_path)
            return {
                "type": "action_result",
                "intent": "allowlist_mutation",
                "status": "success" if deleted else "not_found",
                "reply": f"Workspace '{key}' removido da Allowlist." if deleted else f"Workspace '{key}' não encontrado.",
            }

        if mutation == "upsert_git_repo":
            repo_entry = GitRepoEntry(**data)
            upsert_git_repo(repo_entry, db_path=db_path)
            log_action("update_allowlist_repo", repo_entry.key, "SUCCESS", "Repositório atualizado com confirmação", db_path)
            return {
                "type": "action_result",
                "intent": "allowlist_mutation",
                "status": "success",
                "reply": f"Repositório '{repo_entry.name}' ({repo_entry.key}) salvo com sucesso.",
            }

        if mutation == "delete_git_repo":
            key = data.get("key", "")
            deleted = delete_git_repo(key, db_path=db_path)
            log_action("delete_allowlist_repo", key, "SUCCESS" if deleted else "NOT_FOUND", "Remoção de repositório confirmada", db_path)
            return {
                "type": "action_result",
                "intent": "allowlist_mutation",
                "status": "success" if deleted else "not_found",
                "reply": f"Repositório '{key}' removido da Allowlist." if deleted else f"Repositório '{key}' não encontrado.",
            }

    return {
        "type": "error",
        "status": "unknown_action",
        "message": f"Tipo de ação desconhecido: '{action_type}'",
    }

