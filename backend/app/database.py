import json
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from app.config import (
    DB_PATH,
    DEFAULT_ALLOWED_APPS,
    DEFAULT_WORKSPACES,
    DEFAULT_GIT_REPOS,
)
from app.schemas import (
    AppEntry,
    WorkspaceEntry,
    WorkspaceStep,
    GitRepoEntry,
    AuditLogEntry,
)


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Retorna uma nova conexão SQLite curta.
    Configurações:
    - check_same_thread=False: permite que chamadas do threadpool abram conexões isoladas.
    - row_factory=sqlite3.Row: permite acesso como dicionário e por índice.
    - journal_mode=WAL: alta concorrência de leitura e escrita no Windows sem locks.
    """
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """
    Inicializa o esquema de tabelas e popula os dados iniciais (Seed on Startup)
    caso o banco esteja sendo executado pela primeira vez.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Tabela de Aplicativos Permitidos na Allowlist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS allowed_apps (
                key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                executable_path TEXT NOT NULL,
                args TEXT DEFAULT '',
                requires_confirmation INTEGER DEFAULT 0
            )
        """)

        # 2. Tabela de Workspaces Compostos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                requires_confirmation INTEGER DEFAULT 0,
                steps_json TEXT NOT NULL
            )
        """)

        # 3. Tabela de Repositórios Git Monitorados
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS git_repos (
                key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                repo_path TEXT NOT NULL
            )
        """)

        # 4. Tabela de Auditoria de Ações do Sistema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target_key TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT DEFAULT ''
            )
        """)

        # 5. Tabela de Histórico de Mensagens do Chat
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL,
                model_used TEXT NOT NULL,
                content TEXT NOT NULL,
                intent TEXT DEFAULT 'chat_response'
            )
        """)

        # 6. Tabela de Confirmações Pendentes de Segurança
        # ID aleatório criptográfico, uso único e expiração temporal
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_confirmations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                intent TEXT NOT NULL,
                target TEXT NOT NULL,
                reply TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING'
            )
        """)

        # SEED ON STARTUP: Executado apenas se a tabela estiver vazia
        cursor.execute("SELECT COUNT(*) as count FROM allowed_apps")
        if cursor.fetchone()["count"] == 0:
            for key, data in DEFAULT_ALLOWED_APPS.items():
                cursor.execute(
                    """
                    INSERT INTO allowed_apps (key, name, executable_path, args, requires_confirmation)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        data["name"],
                        data["executable_path"],
                        data.get("args", ""),
                        1 if data.get("requires_confirmation", False) else 0,
                    ),
                )

        cursor.execute("SELECT COUNT(*) as count FROM workspaces")
        if cursor.fetchone()["count"] == 0:
            for key, data in DEFAULT_WORKSPACES.items():
                cursor.execute(
                    """
                    INSERT INTO workspaces (key, name, description, requires_confirmation, steps_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        data["name"],
                        data.get("description", ""),
                        1 if data.get("requires_confirmation", False) else 0,
                        json.dumps(data["steps"], ensure_ascii=False),
                    ),
                )

        cursor.execute("SELECT COUNT(*) as count FROM git_repos")
        if cursor.fetchone()["count"] == 0:
            for key, data in DEFAULT_GIT_REPOS.items():
                cursor.execute(
                    """
                    INSERT INTO git_repos (key, name, repo_path)
                    VALUES (?, ?, ?)
                    """,
                    (key, data["name"], data["repo_path"]),
                )

        conn.commit()


# ============================================================================
# AUDITORIA E HISTÓRICO
# ============================================================================

def log_action(
    action_type: str,
    target_key: str,
    status: str,
    details: str = "",
    db_path: Optional[Path] = None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (timestamp, action_type, target_key, status, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (now, action_type, target_key or "-", status, details),
        )
        conn.commit()


def get_audit_logs(limit: int = 50, db_path: Optional[Path] = None) -> List[AuditLogEntry]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, timestamp, action_type, target_key, status, details FROM audit_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [AuditLogEntry(**dict(r)) for r in rows]


def save_chat_message(
    role: str,
    model_used: str,
    content: str,
    intent: str = "chat_response",
    db_path: Optional[Path] = None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO chat_history (timestamp, role, model_used, content, intent)
            VALUES (?, ?, ?, ?, ?)
            """,
            (now, role, model_used, content, intent),
        )
        conn.commit()


def get_chat_history(limit: int = 50, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, timestamp, role, model_used, content, intent FROM chat_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def clear_chat_history(db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM chat_history")
        conn.commit()


# ============================================================================
# ALLOWLIST CRUD (APPS, WORKSPACES, GIT REPOS)
# ============================================================================

def list_allowed_apps(db_path: Optional[Path] = None) -> List[AppEntry]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM allowed_apps ORDER BY key").fetchall()
        return [
            AppEntry(
                key=r["key"],
                name=r["name"],
                executable_path=r["executable_path"],
                args=r["args"] or "",
                requires_confirmation=bool(r["requires_confirmation"]),
            )
            for r in rows
        ]


def get_allowed_app(key: str, db_path: Optional[Path] = None) -> Optional[AppEntry]:
    with get_connection(db_path) as conn:
        r = conn.execute("SELECT * FROM allowed_apps WHERE LOWER(key) = LOWER(?)", (key.strip(),)).fetchone()
        if not r:
            return None
        return AppEntry(
            key=r["key"],
            name=r["name"],
            executable_path=r["executable_path"],
            args=r["args"] or "",
            requires_confirmation=bool(r["requires_confirmation"]),
        )


def upsert_allowed_app(entry: AppEntry, db_path: Optional[Path] = None) -> None:
    clean_key = entry.key.lower().strip()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO allowed_apps (key, name, executable_path, args, requires_confirmation)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                name=excluded.name,
                executable_path=excluded.executable_path,
                args=excluded.args,
                requires_confirmation=excluded.requires_confirmation
            """,
            (
                clean_key,
                entry.name.strip(),
                entry.executable_path.strip(),
                entry.args.strip(),
                1 if entry.requires_confirmation else 0,
            ),
        )
        conn.commit()


def delete_allowed_app(key: str, db_path: Optional[Path] = None) -> bool:
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM allowed_apps WHERE LOWER(key) = LOWER(?)", (key.strip(),))
        conn.commit()
        return cur.rowcount > 0


def list_workspaces(db_path: Optional[Path] = None) -> List[WorkspaceEntry]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM workspaces ORDER BY key").fetchall()
        result = []
        for r in rows:
            raw_steps = json.loads(r["steps_json"])
            steps = [WorkspaceStep(**s) for s in raw_steps]
            result.append(
                WorkspaceEntry(
                    key=r["key"],
                    name=r["name"],
                    description=r["description"] or "",
                    requires_confirmation=bool(r["requires_confirmation"]),
                    steps=steps,
                )
            )
        return result


def get_workspace(key: str, db_path: Optional[Path] = None) -> Optional[WorkspaceEntry]:
    with get_connection(db_path) as conn:
        r = conn.execute("SELECT * FROM workspaces WHERE LOWER(key) = LOWER(?)", (key.strip(),)).fetchone()
        if not r:
            return None
        steps = [WorkspaceStep(**s) for s in json.loads(r["steps_json"])]
        return WorkspaceEntry(
            key=r["key"],
            name=r["name"],
            description=r["description"] or "",
            requires_confirmation=bool(r["requires_confirmation"]),
            steps=steps,
        )


def upsert_workspace(entry: WorkspaceEntry, db_path: Optional[Path] = None) -> None:
    clean_key = entry.key.lower().strip()
    steps_json = json.dumps([s.model_dump() for s in entry.steps], ensure_ascii=False)
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO workspaces (key, name, description, requires_confirmation, steps_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                requires_confirmation=excluded.requires_confirmation,
                steps_json=excluded.steps_json
            """,
            (
                clean_key,
                entry.name.strip(),
                entry.description.strip(),
                1 if entry.requires_confirmation else 0,
                steps_json,
            ),
        )
        conn.commit()


def delete_workspace(key: str, db_path: Optional[Path] = None) -> bool:
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM workspaces WHERE LOWER(key) = LOWER(?)", (key.strip(),))
        conn.commit()
        return cur.rowcount > 0


def list_git_repos(db_path: Optional[Path] = None) -> List[GitRepoEntry]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM git_repos ORDER BY key").fetchall()
        return [GitRepoEntry(key=r["key"], name=r["name"], repo_path=r["repo_path"]) for r in rows]


def get_git_repo(key: str, db_path: Optional[Path] = None) -> Optional[GitRepoEntry]:
    with get_connection(db_path) as conn:
        r = conn.execute("SELECT * FROM git_repos WHERE LOWER(key) = LOWER(?)", (key.strip(),)).fetchone()
        if not r:
            return None
        return GitRepoEntry(key=r["key"], name=r["name"], repo_path=r["repo_path"])


def upsert_git_repo(entry: GitRepoEntry, db_path: Optional[Path] = None) -> None:
    clean_key = entry.key.lower().strip()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO git_repos (key, name, repo_path)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                name=excluded.name,
                repo_path=excluded.repo_path
            """,
            (clean_key, entry.name.strip(), entry.repo_path.strip()),
        )
        conn.commit()


def delete_git_repo(key: str, db_path: Optional[Path] = None) -> bool:
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM git_repos WHERE LOWER(key) = LOWER(?)", (key.strip(),))
        conn.commit()
        return cur.rowcount > 0


# ============================================================================
# GERENCIAMENTO SEGURO DE CONFIRMAÇÕES (PENDING_CONFIRMATIONS)
# ============================================================================

def create_pending_confirmation(
    intent: str,
    target: str,
    payload: Dict[str, Any],
    reply: str,
    ttl_seconds: int = 120,
    db_path: Optional[Path] = None,
) -> str:
    """
    Gera um registro de confirmação com ID criptográfico aleatório e tempo de expiração.
    O payload da ação é guardado NO SERVIDOR. O cliente recebe apenas o ID.
    """
    conf_id = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
    payload_str = json.dumps(payload, ensure_ascii=False)

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO pending_confirmations (id, created_at, expires_at, intent, target, reply, payload_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            (
                conf_id,
                now.isoformat(),
                expires_at,
                intent,
                target,
                reply,
                payload_str,
            ),
        )
        conn.commit()

    return conf_id


def resolve_pending_confirmation(
    confirmation_id: str,
    approved: bool,
    db_path: Optional[Path] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Resolve uma confirmação pendente de forma atômica e segura.
    Retorna uma tupla (resultado, payload_original):
    - ("APPROVED", payload): Aprovado dentro do prazo.
    - ("CANCELLED", payload): Cancelado pelo usuário.
    - ("EXPIRED", None): O prazo de validade expirou.
    - ("NOT_FOUND_OR_RESOLVED", None): ID inexistente ou já resolvido anteriormente (uso único).
    """
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM pending_confirmations WHERE id = ?",
            (confirmation_id.strip(),),
        ).fetchone()

        if not row:
            return "NOT_FOUND", None

        if row["status"] != "PENDING":
            return "ALREADY_RESOLVED", None

        # Checa expiração temporal
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromisoformat(row["expires_at"])
        if now > expires_at:
            conn.execute(
                "UPDATE pending_confirmations SET status = 'EXPIRED' WHERE id = ?",
                (confirmation_id,),
            )
            conn.commit()
            return "EXPIRED", None

        # Resolve
        new_status = "APPROVED" if approved else "CANCELLED"
        conn.execute(
            "UPDATE pending_confirmations SET status = ? WHERE id = ?",
            (new_status, confirmation_id),
        )
        conn.commit()
        payload = json.loads(row["payload_json"])
        return new_status, payload

