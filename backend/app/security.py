import os
import socket
import secrets
from pathlib import Path
from typing import Optional, Tuple
import psutil
from fastapi import Header, HTTPException, status

from app.config import TOKEN_PATH, ALLOWED_ORIGINS

_CACHED_TOKEN: Optional[str] = None


def get_or_create_local_token(token_file: Optional[Path] = None) -> str:
    """
    Carrega ou cria atomicamente o token secreto do assistente em .local_token.
    O token é uma string segura de 32 bytes URL-safe (secrets.token_urlsafe).
    """
    global _CACHED_TOKEN
    target_path = token_file or TOKEN_PATH

    if target_path.exists():
        try:
            content = target_path.read_text(encoding="utf-8").strip()
            if content:
                _CACHED_TOKEN = content
                return _CACHED_TOKEN
        except Exception:
            pass

    # Gera um novo token seguro
    token = secrets.token_urlsafe(32)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(token, encoding="utf-8")
    _CACHED_TOKEN = token
    return token


def get_local_token() -> str:
    """Retorna o token ativo em memória ou carrega do disco."""
    global _CACHED_TOKEN
    if _CACHED_TOKEN is None:
        _CACHED_TOKEN = get_or_create_local_token()
    return _CACHED_TOKEN


def verify_local_token(
    x_local_token: Optional[str] = Header(None, alias="X-Local-Token")
) -> str:
    """
    Dependência de segurança FastAPI para endpoints REST.
    Exige o cabeçalho 'X-Local-Token' idêntico ao gravado em .local_token.
    Usa comparação em tempo constante (secrets.compare_digest) para evitar timing attacks.
    """
    expected = get_local_token()
    if not x_local_token or not secrets.compare_digest(x_local_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acesso não autorizado: token local ausente ou inválido no header 'X-Local-Token'.",
        )
    return x_local_token


def validate_ws_origin(origin: Optional[str]) -> bool:
    """
    Valida a origem de conexões WebSocket (/ws).
    - Origens None/vazias são permitidas (clientes CLI, scripts python, desktop apps).
    - Origem 'null' é permitida (execução local em WebView ou Edge app file://).
    - Origens em ALLOWED_ORIGINS ou localhost/127.0.0.1 são permitidas.
    - Qualquer origem externa (ex: http://evil.com) é estritamente bloqueada.
    """
    if not origin or origin == "null":
        return True

    clean_origin = origin.lower().rstrip("/")

    # Lista explícita configurada
    allowed_clean = [o.lower().rstrip("/") for o in ALLOWED_ORIGINS]
    if clean_origin in allowed_clean:
        return True

    # Permite portas de desenvolvimento locais
    if clean_origin.startswith("http://localhost:") or clean_origin.startswith("http://127.0.0.1:"):
        return True

    return False


def authenticate_ws_token(token: Optional[str]) -> bool:
    """
    Autentica o token enviado na primeira mensagem do WebSocket.
    Usa comparação em tempo constante (secrets.compare_digest).
    """
    if not token or not isinstance(token, str):
        return False
    expected = get_local_token()
    return secrets.compare_digest(token.strip(), expected)


def check_port_available(port: int = 8000, host: str = "127.0.0.1") -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Verifica se a porta informada está livre para bind no Windows.
    Se estiver ocupada, localiza o processo responsável via psutil e retorna:
    (is_available, pid, process_name)
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        res = sock.connect_ex((host, port))
        if res != 0:
            # Conexão recusada -> porta livre!
            return True, None, None

    # Porta está em uso: tenta identificar o processo
    pid = None
    proc_name = None
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port:
                pid = conn.pid
                if pid:
                    try:
                        p = psutil.Process(pid)
                        proc_name = p.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        proc_name = "Desconhecido / Protegido"
                break
    except Exception:
        pass

    return False, pid, proc_name

