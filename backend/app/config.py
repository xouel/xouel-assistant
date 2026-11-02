import os
from pathlib import Path

# Resolução dinâmica e robusta de caminhos do monorepo
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
ROOT_DIR = BACKEND_DIR.parent

# Caminhos de persistência, segurança e build do front-end
DB_PATH = BACKEND_DIR / "assistant.db"
TOKEN_PATH = BACKEND_DIR / ".local_token"
CAPTURES_DIR = BACKEND_DIR / "captures"
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"

# Configurações de Rede (Restrito estritamente a localhost)
HOST = "127.0.0.1"
PORT = 8000
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Nomes dos Modelos Locais (Perfis compilados no Ollama)
MODEL_FAST = "x-fast"
MODEL_CODER = "x-coder"
MODEL_VISION = "x-vision"

# Mapeamento de fallback para o caso de modelos base
MODEL_ALIASES = {
    MODEL_FAST: "qwen2.5:3b-instruct",
    MODEL_CODER: "qwen2.5-coder:7b-instruct",
    MODEL_VISION: "gemma3:4b",
}

# Sementes Iniciais da Allowlist de Aplicativos (salvas no SQLite na 1ª execução)
# Regra de Ouro: caminhos e executáveis fixos, sem interpolação não validada
DEFAULT_ALLOWED_APPS = {
    "vscode": {
        "name": "Visual Studio Code",
        "executable_path": r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
        "args": "",
        "requires_confirmation": False,
    },
    "terminal": {
        "name": "Windows Terminal",
        "executable_path": "wt.exe",
        "args": "",
        "requires_confirmation": False,
    },
    "explorer": {
        "name": "Windows Explorer",
        "executable_path": "explorer.exe",
        "args": "",
        "requires_confirmation": False,
    },
    "calc": {
        "name": "Calculadora do Windows",
        "executable_path": "calc.exe",
        "args": "",
        "requires_confirmation": False,
    },
    "notepad": {
        "name": "Bloco de Notas",
        "executable_path": "notepad.exe",
        "args": "",
        "requires_confirmation": False,
    },
    "taskmgr": {
        "name": "Gerenciador de Tarefas",
        "executable_path": "taskmgr.exe",
        "args": "",
        "requires_confirmation": True,  # Ação sensível de sistema
    },
}

# Sementes Iniciais de Workspaces Compostos
DEFAULT_WORKSPACES = {
    "dev_web": {
        "name": "Workspace Dev Web",
        "description": "Inicia VS Code, Terminal e abre o navegador local em 5173",
        "requires_confirmation": False,
        "steps": [
            {"type": "app", "target": "vscode", "working_dir": None},
            {"type": "app", "target": "terminal", "working_dir": None},
            {"type": "url", "target": "http://localhost:5173", "working_dir": None},
        ],
    },
    "dev_assistant": {
        "name": "Projeto X-Assistant",
        "description": "Abre o diretório do X-Assistant no VS Code e roda 'git status' no terminal",
        "requires_confirmation": True,  # Contém comando de terminal -> exige confirmação
        "steps": [
            {
                "type": "vscode_project",
                "target": str(ROOT_DIR),
                "working_dir": str(ROOT_DIR),
            },
            {
                "type": "terminal_cmd",
                "target": "git status",
                "working_dir": str(ROOT_DIR),
            },
        ],
    },
    "foco_estudo": {
        "name": "Modo Estudo e Documentação",
        "description": "Abre editor e documentação oficial do Python",
        "requires_confirmation": False,
        "steps": [
            {"type": "app", "target": "vscode", "working_dir": None},
            {"type": "url", "target": "https://docs.python.org/3/", "working_dir": None},
        ],
    },
}

# Sementes Iniciais de Repositórios Git Monitorados
DEFAULT_GIT_REPOS = {
    "x-assistant": {
        "name": "Repositório Principal X-Assistant",
        "repo_path": str(ROOT_DIR),
    }
}

