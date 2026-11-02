import os
import re
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from app.database import (
    get_allowed_app,
    get_workspace,
    log_action,
)


# ============================================================================
# VALIDADORES DE SEGURANÇA
# ============================================================================

# Permite apenas identificadores alfanuméricos simples e underscores (sem barras ou metacaracteres de shell)
KEY_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


def is_valid_allowlist_key(key: Optional[str]) -> bool:
    """Garante que a chave não contém barras, pipes, & ou caracteres de injeção."""
    if not key or not isinstance(key, str):
        return False
    return bool(KEY_REGEX.match(key.strip()))


def resolve_executable_path(raw_path: str) -> Optional[Path]:
    """
    Expande variáveis de ambiente do Windows (%LOCALAPPDATA%, etc.) e resolve o caminho.
    Se for um comando do PATH (ex: wt.exe, calc.exe, notepad.exe), localiza via shutil.which.
    """
    expanded = os.path.expandvars(raw_path.strip())

    # 1. Se for um caminho absoluto ou relativo que existe
    direct_path = Path(expanded)
    if direct_path.is_file():
        return direct_path.resolve()

    # 2. Se for um comando disponível no PATH do Windows
    which_path = shutil.which(expanded)
    if which_path:
        return Path(which_path).resolve()

    # 3. Fallbacks comuns do Windows (System32 para calc, notepad, wt, etc.)
    system32 = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32"
    sys_path = system32 / expanded
    if sys_path.is_file():
        return sys_path.resolve()

    return None


# ============================================================================
# EXECUTOR DE APLICATIVOS (ESTRITAMENTE VIA ALLOWLIST)
# ============================================================================

def execute_app(
    target_key: str,
    db_path: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Executa um aplicativo validado estritamente pela Allowlist do SQLite.
    REGRA DE SEGURANÇA:
    - target_key é validada contra injeção de shell.
    - O comando nunca usa shell=True.
    - Registra em audit_logs (SUCCESS, BLOCKED ou ERROR).
    """
    # 1. Validação estrutural da chave
    if not is_valid_allowlist_key(target_key):
        details = f"Chave inválida ou tentativa de injeção: '{target_key}'"
        log_action("open_app", target_key or "NULL", "BLOCKED", details, db_path)
        return {
            "status": "blocked",
            "message": f"Acesso negado: formato de chave inválido '{target_key}'.",
            "details": details,
        }

    clean_key = target_key.lower().strip()

    # 2. Consulta no banco da Allowlist
    app_entry = get_allowed_app(clean_key, db_path=db_path)
    if not app_entry:
        details = f"Chave '{clean_key}' não está cadastrada na Allowlist do sistema."
        log_action("open_app", clean_key, "BLOCKED", details, db_path)
        return {
            "status": "blocked",
            "message": f"Acesso negado: o aplicativo '{clean_key}' não está na Allowlist.",
            "details": details,
        }

    # 3. Resolução segura do executável
    resolved_exe = resolve_executable_path(app_entry.executable_path)
    if not resolved_exe:
        details = f"Executável não encontrado no disco: '{app_entry.executable_path}'"
        log_action("open_app", app_entry.key, "ERROR", details, db_path)
        return {
            "status": "error",
            "message": f"Não foi possível localizar o executável de '{app_entry.name}'.",
            "details": details,
        }

    # 4. Construção da lista de argumentos (Sem shell=True!)
    cmd_args = [str(resolved_exe)]
    if app_entry.args:
        # Divide argumentos respeitando espaços sem invocar shell
        for arg in app_entry.args.split():
            cmd_args.append(os.path.expandvars(arg))

    # 5. Execução do Processo
    if dry_run:
        log_action("open_app", app_entry.key, "SUCCESS", f"[DRY_RUN] {cmd_args}", db_path)
        return {
            "status": "success",
            "message": f"[DRY_RUN] Aplicativo '{app_entry.name}' pronto para execução.",
            "cmd": cmd_args,
        }

    try:
        # Cria o processo em background sem bloquear a aplicação
        subprocess.Popen(cmd_args)
        log_action("open_app", app_entry.key, "SUCCESS", str(resolved_exe), db_path)
        return {
            "status": "success",
            "message": f"Aplicativo '{app_entry.name}' iniciado com sucesso.",
            "executable": str(resolved_exe),
        }
    except Exception as exc:
        details = f"Falha ao executar Popen: {str(exc)}"
        log_action("open_app", app_entry.key, "ERROR", details, db_path)
        return {
            "status": "error",
            "message": f"Erro ao iniciar '{app_entry.name}': {str(exc)}",
            "details": details,
        }


# ============================================================================
# EXECUTOR DE WORKSPACES COMPOSTOS
# ============================================================================

def execute_workspace(
    workspace_key: str,
    db_path: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Executa os passos encadeados de um Workspace composto da Allowlist:
    - 'app': abre aplicativo autorizado via execute_app
    - 'url': abre endereço web validado no navegador padrão
    - 'vscode_project': abre uma pasta no VS Code homologado
    - 'terminal_cmd': abre o Windows Terminal com comando fixo da Allowlist
    """
    if not is_valid_allowlist_key(workspace_key):
        details = f"Chave de workspace inválida: '{workspace_key}'"
        log_action("run_workspace", workspace_key or "NULL", "BLOCKED", details, db_path)
        return {
            "status": "blocked",
            "message": f"Acesso negado: chave de workspace inválida '{workspace_key}'.",
        }

    clean_key = workspace_key.lower().strip()
    ws = get_workspace(clean_key, db_path=db_path)
    if not ws:
        details = f"Workspace '{clean_key}' não encontrado na Allowlist."
        log_action("run_workspace", clean_key, "BLOCKED", details, db_path)
        return {
            "status": "blocked",
            "message": f"Acesso negado: Workspace '{clean_key}' não cadastrado.",
        }

    executed_steps: List[str] = []
    errors: List[str] = []

    for idx, step in enumerate(ws.steps, start=1):
        try:
            # 1. Passo: Aplicativo
            if step.type == "app":
                res = execute_app(step.target, db_path=db_path, dry_run=dry_run)
                if res["status"] == "success":
                    executed_steps.append(f"Passo {idx} (App): {step.target}")
                else:
                    errors.append(f"Passo {idx} (App {step.target}): {res['message']}")

            # 2. Passo: URL no Navegador
            elif step.type == "url":
                parsed = urlparse(step.target)
                if parsed.scheme not in ("http", "https"):
                    errors.append(f"Passo {idx} (URL): esquema não seguro '{step.target}'")
                    continue
                if not dry_run:
                    webbrowser.open(step.target)
                executed_steps.append(f"Passo {idx} (URL): {step.target}")

            # 3. Passo: Abrir pasta de Projeto no VS Code
            elif step.type == "vscode_project":
                project_dir = Path(os.path.expandvars(step.target)).resolve()
                if not project_dir.is_dir():
                    errors.append(f"Passo {idx} (Projeto): diretório '{project_dir}' não existe no disco.")
                    continue

                vscode_entry = get_allowed_app("vscode", db_path=db_path)
                vscode_raw = vscode_entry.executable_path if vscode_entry else "code.cmd"
                vscode_bin = resolve_executable_path(vscode_raw) or shutil.which("code")

                if not vscode_bin:
                    errors.append(f"Passo {idx} (Projeto): executável do VS Code não encontrado.")
                    continue

                cmd_args = [str(vscode_bin), str(project_dir)]
                if not dry_run:
                    subprocess.Popen(cmd_args)
                executed_steps.append(f"Passo {idx} (VS Code): {project_dir}")

            # 4. Passo: Comando no Terminal
            elif step.type == "terminal_cmd":
                work_dir = Path(os.path.expandvars(step.working_dir or ".")).resolve()
                if not work_dir.is_dir():
                    errors.append(f"Passo {idx} (Terminal): diretório de trabalho '{work_dir}' não existe.")
                    continue

                # Localiza o Windows Terminal (wt.exe) ou usa cmd.exe como fallback
                wt_bin = resolve_executable_path("wt.exe")
                if wt_bin:
                    term_args = [str(wt_bin), "-d", str(work_dir), "cmd.exe", "/k", step.target]
                else:
                    term_args = ["cmd.exe", "/k", f"cd /d {work_dir} && {step.target}"]

                if not dry_run:
                    subprocess.Popen(term_args)
                executed_steps.append(f"Passo {idx} (Terminal em {work_dir.name}): {step.target}")

        except Exception as exc:
            errors.append(f"Passo {idx} ({step.type}): {str(exc)}")

    status = "SUCCESS" if not errors else ("PARTIAL" if executed_steps else "ERROR")
    summary = f"Executados: {len(executed_steps)}; Erros: {len(errors)}"
    log_action("run_workspace", ws.key, status, summary, db_path)

    return {
        "status": "success" if status == "SUCCESS" else ("partial" if status == "PARTIAL" else "error"),
        "workspace": ws.name,
        "executed_steps": executed_steps,
        "errors": errors,
        "message": f"Workspace '{ws.name}' concluído com {len(executed_steps)} passo(s).",
    }

