import os
import sys
import time
import shutil
import ctypes
from ctypes import wintypes
import threading
import subprocess
from pathlib import Path
from typing import Optional, List

# ============================================================================
# 1. RESOLUÇÃO DE CAMINHOS E REDIRECIONAMENTO SEGURO PARA PYTHONW.EXE
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

LOG_FILE_PATH = BACKEND_DIR / "launcher.log"

# Quando executado via pythonw.exe (sem console), sys.stdout/stderr são None.
# Redirecionamos para launcher.log para que o Uvicorn não falhe ao logar.
if sys.stdout is None or sys.stderr is None:
    log_stream = open(LOG_FILE_PATH, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log_stream
    if sys.stderr is None:
        sys.stderr = log_stream

import httpx
import uvicorn
import win32gui
import win32con

from app.config import HOST, PORT
from app.security import check_port_available
from app.main import app

# ============================================================================
# 2. CONSTANTES WIN32 PARA ATALHO GLOBAL E FOCO DE JANELA
# ============================================================================

user32 = ctypes.windll.user32

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
VK_X = ord("X")
VK_MENU = 0x12  # Tecla Alt
KEYEVENTF_KEYUP = 0x0002
WM_HOTKEY = 0x0312

HOTKEY_CANDIDATES = [
    (1, "Ctrl + Alt + X", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_X),
    (2, "Ctrl + Shift + X", MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_X),
    (3, "Ctrl + Shift + Espaço", MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_SPACE),
    (4, "Ctrl + Alt + Espaço", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_SPACE),
]

MB_OK = 0x00000000
MB_ICONERROR = 0x00000010
MB_ICONWARNING = 0x00000030

APP_URL = f"http://{HOST}:{PORT}"
WINDOW_TITLE_MARKER = "X-Assistant"


def show_message_box(title: str, message: str, icon: int = MB_ICONERROR) -> None:
    """Exibe caixa de diálogo nativa do Windows (útil quando rodando sem terminal em pythonw)."""
    try:
        user32.MessageBoxW(None, message, title, MB_OK | icon)
    except Exception:
        print(f"[{title}] {message}")


# ============================================================================
# 3. GERENCIAMENTO DA JANELA EDGE (--app) E FOCO WIN32
# ============================================================================

def resolve_edge_executable() -> Optional[str]:
    """Localiza o executável oficial do Microsoft Edge no Windows."""
    which_edge = shutil.which("msedge") or shutil.which("msedge.exe")
    if which_edge:
        return which_edge

    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def find_assistant_hwnd() -> Optional[int]:
    """
    Procura o HWND da janela do X-Assistant entre as janelas visíveis do Windows.
    Ignora janelas de editor/IDE (como VS Code editando arquivos do projeto).
    """
    matched_hwnds: List[int] = []

    def _enum_cb(hwnd: int, _extra: object) -> bool:
        if win32gui.IsWindowVisible(hwnd):
            title = (win32gui.GetWindowText(hwnd) or "").lower()
            if WINDOW_TITLE_MARKER.lower() in title and "visual studio code" not in title:
                matched_hwnds.append(hwnd)
        return True

    try:
        win32gui.EnumWindows(_enum_cb, None)
    except Exception:
        pass

    return matched_hwnds[0] if matched_hwnds else None


def launch_edge_app() -> None:
    """Abre a interface do X-Assistant em modo aplicativo dedicado do Microsoft Edge (--app)."""
    edge_exe = resolve_edge_executable()
    try:
        if edge_exe and os.path.isfile(edge_exe):
            subprocess.Popen([edge_exe, f"--app={APP_URL}"])
            return
    except Exception as exc:
        print(f"[Launcher] Falha ao abrir Edge: {exc}")

    # Fallback para navegador padrão
    try:
        import webbrowser
        webbrowser.open(APP_URL)
    except Exception as exc:
        print(f"[Launcher] Falha no fallback do navegador: {exc}")
        os.startfile(APP_URL)


def bring_hwnd_to_front(hwnd: int) -> None:
    """
    Traz a janela do X-Assistant para a frente mesmo que outro app (ex: VS Code)
    esteja em tela cheia, contornando a restrição do SetForegroundWindow via keybd_event(Alt).
    """
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

        # Simula um pulso neutro na tecla Alt para liberar o Foreground Lock do Windows
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

        win32gui.SetForegroundWindow(hwnd)
    except Exception as exc:
        print(f"[Launcher] Aviso ao focar janela: {exc}")


def focus_or_open_assistant_window() -> str:
    """
    Se a janela do X-Assistant já estiver aberta, restaura e traz para frente.
    Se tiver sido fechada pelo usuário, reabre o Edge em modo --app.
    """
    hwnd = find_assistant_hwnd()
    if hwnd is not None:
        bring_hwnd_to_front(hwnd)
        return "focused"

    launch_edge_app()
    return "launched"


# ============================================================================
# 4. CHECAGEM DE PRÉ-REQUISITOS (PORTA 8000 E MOTOR OLLAMA)
# ============================================================================

def is_backend_already_healthy() -> bool:
    """Verifica se o servidor do X-Assistant já está respondendo em 127.0.0.1:8000."""
    try:
        resp = httpx.get(f"{APP_URL}/api/health", timeout=1.2)
        return resp.status_code == 200 and resp.json().get("status") == "ok"
    except Exception:
        return False


def ensure_ollama_running() -> bool:
    """
    Verifica se o Ollama responde em :11434.
    Se estiver fechado, tenta iniciar o daemon em background sem bloquear o assistente.
    """
    try:
        resp = httpx.get("http://127.0.0.1:11434/", timeout=1.2)
        if resp.status_code == 200:
            return True
    except Exception:
        pass

    print("[Launcher] Ollama não detectado em :11434. Tentando iniciar em segundo plano...")
    ollama_app = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama app.exe")
    ollama_cli = shutil.which("ollama")

    try:
        if os.path.isfile(ollama_app):
            subprocess.Popen([ollama_app], close_fds=True)
            return True
        if ollama_cli:
            subprocess.Popen(
                [ollama_cli, "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )
            return True
    except Exception as exc:
        print(f"[Launcher] Não foi possível iniciar o Ollama automaticamente: {exc}")

    return False


# ============================================================================
# 5. INICIALIZAÇÃO DO UVICORN EM THREAD DEDICADA E LOOP DE HOTKEY
# ============================================================================

def start_backend_thread() -> uvicorn.Server:
    """Inicia o servidor FastAPI/Uvicorn em uma thread daemon dentro do mesmo processo."""
    config = uvicorn.Config(
        app=app,
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config=config)
    thread = threading.Thread(target=server.run, name="XAssistantUvicornThread", daemon=True)
    thread.start()
    return server


def wait_for_backend_ready(timeout_sec: float = 10.0) -> bool:
    """Aguarda o endpoint /api/health responder antes de abrir a janela do Edge."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if is_backend_already_healthy():
            return True
        time.sleep(0.2)
    return False


def main() -> int:
    check_only = "--check-only" in sys.argv
    no_browser = "--no-browser" in sys.argv

    # 1. Verifica disponibilidade da porta 8000
    available, pid, proc_name = check_port_available(PORT, HOST)
    if not available:
        if is_backend_already_healthy():
            print("[Launcher] X-Assistant já está em execução. Focando janela...")
            if not check_only and not no_browser:
                focus_or_open_assistant_window()
            return 0

        err_msg = (
            f"A porta {PORT} já está ocupada pelo processo PID {pid} ({proc_name}).\n\n"
            f"Finalize o processo ocupante no Gerenciador de Tarefas antes de iniciar o X-Assistant."
        )
        print(f"[ERRO] {err_msg}", file=sys.stderr)
        if not check_only:
            show_message_box("X-Assistant — Porta 8000 Ocupada", err_msg, MB_ICONERROR)
        return 1

    # 2. Verifica / inicia o Ollama (não fatal se desligado)
    ollama_ok = ensure_ollama_running()
    print(f"[Launcher] Status inicial do Ollama: {'Online / Iniciado' if ollama_ok else 'Offline'}")

    # 3. Sobe o Uvicorn na thread daemon
    server = start_backend_thread()
    if not wait_for_backend_ready(timeout_sec=10.0):
        err_msg = "O servidor FastAPI não respondeu em http://127.0.0.1:8000 dentro do tempo limite."
        print(f"[ERRO] {err_msg}", file=sys.stderr)
        if not check_only:
            show_message_box("X-Assistant — Falha na Inicialização", err_msg, MB_ICONERROR)
        return 1

    print(f"[Launcher] Backend online em {APP_URL}")

    # 4. Registra atalhos globais (Ctrl+Alt+Espaço primário + fallbacks caso ocupado por outro app)
    registered_ids: List[int] = []
    registered_labels: List[str] = []
    for hk_id, hk_label, hk_mod, hk_vk in HOTKEY_CANDIDATES:
        if user32.RegisterHotKey(None, hk_id, hk_mod, hk_vk):
            registered_ids.append(hk_id)
            registered_labels.append(hk_label)
        else:
            print(f"[Launcher] Nota: '{hk_label}' já ocupado por outro processo no Windows (Win32 1409).")

    if registered_labels:
        print(f"[Launcher] Atalhos globais ativos: {', '.join(registered_labels)}")
    else:
        print("[Launcher] Aviso: Nenhum atalho global pôde ser registrado.")

    # Modo de teste automatizado de bancada (--check-only)
    if check_only:
        for hk_id in registered_ids:
            user32.UnregisterHotKey(None, hk_id)
        server.should_exit = True
        print("[Launcher] Check-only concluído com sucesso (OK).")
        return 0

    # 5. Abre a janela dedicada do Edge (--app)
    if not no_browser:
        focus_or_open_assistant_window()

    # 6. Loop nativo de mensagens do Windows (0.0% de CPU em repouso)
    msg = wintypes.MSG()
    try:
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = wintypes.BOOL

        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
            if msg.message == WM_HOTKEY and msg.wParam in registered_ids:
                action = focus_or_open_assistant_window()
                print(f"[Launcher] Hotkey global (#{msg.wParam}) acionada -> {action}")
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except KeyboardInterrupt:
        print("\n[Launcher] Encerrando X-Assistant...")
    finally:
        for hk_id in registered_ids:
            user32.UnregisterHotKey(None, hk_id)
        server.should_exit = True

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            show_message_box(
                "X-Assistant — Erro Fatal",
                f"Falha ao iniciar:\n\n{exc}\n\nConsulte backend/launcher.log",
                MB_ICONERROR,
            )
        except Exception:
            pass
        sys.exit(1)
