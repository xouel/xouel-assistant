import os
import time
import ctypes
from ctypes import wintypes
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import pyperclip
from PIL import Image, ImageGrab

try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

from app.config import ROOT_DIR, CAPTURES_DIR, MODEL_FAST, MODEL_CODER, MODEL_VISION
from app.schemas import AnalysisResult
from app.database import get_git_repo, list_git_repos, log_action
from app.services.ollama_service import analyze_text, analyze_image


# ============================================================================
# 1. SMART CLIPBOARD (ANÁLISE SEGURA DE TEXTO / ERROS / CÓDIGO)
# ============================================================================

def get_clipboard_text(max_chars: int = 6000) -> Optional[str]:
    """
    Lê o texto da área de transferência do Windows com proteção de tamanho.
    Retorna None se estiver vazio ou se não for texto legível.
    """
    try:
        content = pyperclip.paste()
        if not content or not content.strip():
            return None
        return content.strip()[:max_chars]
    except Exception:
        return None


async def analyze_clipboard(
    instruction: str = "Analise o trecho a seguir. Se for um erro ou exceção, explique a causa em até 2 frases e forneça o código corrigido:",
    max_chars: int = 6000,
) -> AnalysisResult:
    """
    Lê o texto do Clipboard e envia para o modelo especialista x-coder.
    GARANTIA DE SEGURANÇA (Anti Prompt-Injection):
    - Usa analyze_text() (caminho só-texto).
    - Não utiliza SystemAction nem passa pelo executor do sistema operacional.
    """
    copied_text = get_clipboard_text(max_chars=max_chars)
    if not copied_text:
        return AnalysisResult(
            status="empty",
            model_used=MODEL_CODER,
            preview=None,
            analysis="A área de transferência (Clipboard) está vazia ou não contém texto legível.",
        )

    preview = copied_text[:180] + ("..." if len(copied_text) > 180 else "")
    system_prompt = (
        "Você é o especialista em código e depuração do X-Assistant.\n"
        "Analise o texto recebido em português (pt-BR).\n"
        "Seja enxuto, direto e mostre a solução de código corrigida quando aplicável."
    )
    user_prompt = f"{instruction}\n\n```\n{copied_text}\n```"

    try:
        reply = await analyze_text(
            system_prompt=system_prompt,
            content_to_analyze=user_prompt,
            model=MODEL_CODER,
        )
        log_action("analyze_clipboard", "x-coder", "SUCCESS", f"{len(copied_text)} chars")
        return AnalysisResult(
            status="success",
            model_used=MODEL_CODER,
            preview=preview,
            analysis=reply.strip(),
        )
    except Exception as exc:
        log_action("analyze_clipboard", "x-coder", "ERROR", str(exc))
        return AnalysisResult(
            status="error",
            model_used=MODEL_CODER,
            preview=preview,
            analysis=f"Erro ao analisar o Clipboard com o modelo de código: {str(exc)}",
        )


# ============================================================================
# 2. GIT DIFF & CONVENTIONAL COMMITS INTELIGENTE
# ============================================================================

def build_limited_diff(
    repo_path: Path,
    max_chars: int = 4000,
) -> Tuple[str, str]:
    """
    Extrai o diff do repositório Git de forma compacta e com encoding UTF-8 seguro no Windows:
    1. Tenta diff staged (--staged) com estatísticas (--stat).
    2. Se não houver staged, tenta diff da working tree (--stat).
    3. Usa '-U1' (apenas 1 linha de contexto) para economizar 50% dos tokens da janela da IA.
    4. Trunca com aviso explícito se ultrapassar o orçamento max_chars.
    Retorna (diff_formatado, tipo_origem).
    """
    if not repo_path.is_dir() or not (repo_path / ".git").exists():
        raise ValueError(f"O caminho '{repo_path}' não é um repositório Git válido.")

    # 1. Verifica alterações em stage (--staged)
    # -c core.quotepath=false garante que o Git não escape caracteres acentuados (ex: ç, ã) em octal
    stat_cmd = ["git", "-C", str(repo_path), "-c", "core.quotepath=false", "diff", "--staged", "--stat"]
    stat_out = subprocess.run(
        stat_cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()

    diff_source = "staged"
    diff_args = ["git", "-C", str(repo_path), "-c", "core.quotepath=false", "diff", "--staged", "-U1"]

    if not stat_out:
        # 2. Se não houver staged, busca na working tree
        stat_cmd = ["git", "-C", str(repo_path), "-c", "core.quotepath=false", "diff", "--stat"]
        stat_out = subprocess.run(
            stat_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
        diff_source = "unstaged"
        diff_args = ["git", "-C", str(repo_path), "-c", "core.quotepath=false", "diff", "-U1"]

    if not stat_out:
        # 3. Verifica se há arquivos untracked
        status_out = subprocess.run(
            ["git", "-C", str(repo_path), "-c", "core.quotepath=false", "status", "--short"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
        if not status_out:
            return "", "empty"
        return f"Arquivos não rastreados:\n{status_out}", "untracked"

    # Pega o conteúdo detalhado dos hunks compactos (-U1)
    diff_out = subprocess.run(
        diff_args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()

    combined = f"Estatísticas de alterações:\n{stat_out}\n\nDiff detalhado:\n{diff_out}"
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n[... diff truncado para preservar a janela de contexto da IA ...]"

    return combined, diff_source


async def suggest_commit_message(
    repo_key: str = "x-assistant",
    custom_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lê as alterações do repositório Git homologado e consulta o modelo x-fast
    para gerar uma mensagem semântica no formato Conventional Commits.
    """
    target_path = Path(custom_path) if custom_path else None
    if not target_path:
        repo_entry = get_git_repo(repo_key)
        if not repo_entry:
            repos = list_git_repos()
            repo_entry = repos[0] if repos else None
        if not repo_entry:
            return {
                "status": "error",
                "message": f"Nenhum repositório Git com a chave '{repo_key}' encontrado na Allowlist.",
            }
        target_path = Path(repo_entry.repo_path)

    try:
        diff_content, diff_source = build_limited_diff(target_path)
    except Exception as exc:
        log_action("generate_git_commit", repo_key, "ERROR", str(exc))
        return {
            "status": "error",
            "message": f"Erro ao acessar repositório Git em '{target_path}': {str(exc)}",
        }

    if diff_source == "empty":
        return {
            "status": "empty",
            "message": f"Nenhuma alteração pendente encontrada no repositório '{target_path.name}'.",
        }

    system_prompt = (
        "Você é o copiloto de Git do X-Assistant.\n"
        "Sua tarefa é analisar o diff e gerar uma mensagem no padrão Conventional Commits em português (pt-BR).\n"
        "Regras estritas:\n"
        "1. Primeira linha: <tipo>(<escopo opcional>): <descrição curta em minúsculas (máx 72 caracteres)>\n"
        "   Exemplos de tipo: feat, fix, refactor, docs, chore, test.\n"
        "2. Pule uma linha e adicione até 3 bullet points objetivos detalhando as alterações principais se necessário.\n"
        "3. Não gere introduções, explicações ou cumprimentos. Forneça APENAS a mensagem do commit."
    )

    try:
        commit_msg = await analyze_text(
            system_prompt=system_prompt,
            content_to_analyze=diff_content,
            model=MODEL_FAST,
        )
        log_action("generate_git_commit", repo_key, "SUCCESS", f"{diff_source} ({len(diff_content)} chars)")
        return {
            "status": "success",
            "repo_name": target_path.name,
            "diff_source": diff_source,
            "commit_message": commit_msg.strip(),
            "diff_preview": diff_content[:250],
        }
    except Exception as exc:
        log_action("generate_git_commit", repo_key, "ERROR", str(exc))
        return {
            "status": "error",
            "message": f"Erro ao gerar commit com o modelo '{MODEL_FAST}': {str(exc)}",
        }


# ============================================================================
# 3. VISÃO COMPUTACIONAL (CLIPBOARD FIRST + FALLBACK TELA INTEIRA)
# ============================================================================

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _capture_fullscreen_gdi() -> Image.Image:
    """
    Captura resiliente da tela inteira usando diretamente a API GDI do Windows (user32/gdi32).
    Elimina o erro 'OSError: screen grab failed' do Pillow quando executado em sessões híbridas.
    """
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)

    hdesktop = user32.GetDesktopWindow()
    hdc_screen = user32.GetDC(hdesktop)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)

    gdi32.SelectObject(hdc_mem, hbmp)
    # 0x00CC0020 = SRCCOPY
    gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, 0x00CC0020)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h  # top-down DIB
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    buffer = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buffer, ctypes.byref(bmi), 0)

    img = Image.frombuffer("RGBA", (w, h), buffer, "raw", "BGRA", 0, 1)
    img = img.convert("RGB")

    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hdesktop, hdc_screen)
    return img


def _find_assistant_window() -> Optional[int]:
    """Localiza o handle (HWND) da janela do X-Assistant se estiver aberta no Windows."""
    if not HAS_WIN32:
        return None

    target_hwnd = None

    def enum_cb(hwnd, _):
        nonlocal target_hwnd
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "X-Assistant" in title or "xouel-assistant" in title:
                target_hwnd = hwnd

    try:
        win32gui.EnumWindows(enum_cb, None)
    except Exception:
        pass
    return target_hwnd


def capture_visual_context(
    source_preference: str = "auto",
    hide_window: bool = True,
) -> Tuple[Path, str]:
    """
    Captura imagem priorizando o Clipboard do usuário (Win+Shift+S) e com fallback
    inteligente para o monitor principal.
    CENÁRIOS TRATADOS:
    1. Recorte de bitmap no Clipboard (Win + Shift + S).
    2. Arquivo de imagem copiado no Windows Explorer (lista de caminhos).
    3. Fallback para tela inteira (minimizando temporariamente a janela do assistente).
    Retorna (caminho_arquivo_png, tipo_origem).
    """
    target_img_path = CAPTURES_DIR / "latest_capture.png"

    # 1. Tenta capturar do Clipboard (se preferência for 'auto' ou 'clipboard')
    if source_preference in ("auto", "clipboard"):
        try:
            clip_data = ImageGrab.grabclipboard()

            # Cenário 1: É um bitmap recortado diretamente na tela
            if isinstance(clip_data, Image.Image):
                clip_data.save(target_img_path, format="PNG")
                return target_img_path, "clipboard_crop"

            # Cenário 2: É uma lista de arquivos copiados no Explorer
            if isinstance(clip_data, list):
                for item in clip_data:
                    item_path = Path(str(item))
                    if item_path.is_file() and item_path.suffix.lower() in IMAGE_EXTENSIONS:
                        with Image.open(item_path) as img:
                            img.save(target_img_path, format="PNG")
                        return target_img_path, "clipboard_file"

        except Exception:
            pass

        # Se o usuário exigiu explicitamente apenas clipboard e não encontrou:
        if source_preference == "clipboard":
            raise ValueError("Nenhuma imagem ou arquivo de imagem encontrado na área de transferência (Clipboard).")

    # 2. Fallback: Captura da tela inteira (monitor principal)
    hwnd = _find_assistant_window() if hide_window else None
    try:
        # Se a janela do assistente estiver em primeiro plano, minimiza para não estragar o print
        if hwnd and HAS_WIN32:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            time.sleep(0.3)  # Pausa necessária para a animação do Windows completar

        try:
            screen_img = ImageGrab.grab(all_screens=False)
        except Exception:
            screen_img = _capture_fullscreen_gdi()

        screen_img.save(target_img_path, format="PNG")

    finally:
        # Restaura a janela do assistente após tirar o print
        if hwnd and HAS_WIN32:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass

    return target_img_path, "fullscreen"


async def analyze_screen(
    prompt: str = "Inspecione esta imagem. Identifique mensagens de erro, problemas visuais de UI ou descreva os elementos com clareza:",
    source_preference: str = "auto",
    hide_window: bool = True,
) -> AnalysisResult:
    """
    Captura o contexto visual e envia para o modelo multimodal x-vision (gemma3:4b).
    GARANTIA DE SEGURANÇA (Anti Prompt-Injection):
    - Usa analyze_image() (caminho só-texto).
    - Retorna estritamente o schema AnalysisResult sem campos de execução.
    """
    try:
        img_path, capture_source = capture_visual_context(
            source_preference=source_preference,
            hide_window=hide_window,
        )
    except Exception as exc:
        return AnalysisResult(
            status="error",
            model_used=MODEL_VISION,
            preview=None,
            analysis=f"Falha ao capturar imagem para análise visual: {str(exc)}",
        )

    system_prompt = (
        "Você é o especialista visual (x-vision) do X-Assistant no Windows.\n"
        "Sua tarefa é inspecionar capturas de tela e interfaces em português (pt-BR):\n"
        "1. Se houver janelas de erro, traces de terminal ou falhas, transcreva os detalhes e sugira a correção.\n"
        "2. Se for uma interface de usuário, avalie layout, consistência e alinhamentos de forma objetiva."
    )

    try:
        reply = await analyze_image(
            system_prompt=system_prompt,
            user_prompt=prompt,
            image_path=str(img_path),
            model=MODEL_VISION,
        )
        log_action("analyze_screenshot", MODEL_VISION, "SUCCESS", capture_source)
        return AnalysisResult(
            status="success",
            model_used=MODEL_VISION,
            preview=f"Captura realizada via '{capture_source}' ({img_path.name})",
            analysis=reply.strip(),
            details={"capture_source": capture_source, "image_path": str(img_path)},
        )
    except Exception as exc:
        log_action("analyze_screenshot", MODEL_VISION, "ERROR", str(exc))
        return AnalysisResult(
            status="error",
            model_used=MODEL_VISION,
            preview=f"Captura realizada via '{capture_source}' ({img_path.name})",
            analysis=f"Erro ao processar imagem no modelo '{MODEL_VISION}': {str(exc)}",
            details={"capture_source": capture_source, "image_path": str(img_path)},
        )


