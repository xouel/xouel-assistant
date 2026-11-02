from datetime import datetime
from typing import Literal, Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field


# ============================================================================
# 1. CONTRATOS DO CLASSIFICADOR DE INTENÇÕES (STRUCTURED OUTPUTS)
# ============================================================================

IntentType = Literal[
    "chat_response",       # Conversa livre / pergunta técnica geral
    "open_app",            # Abrir um aplicativo cadastrado na Allowlist
    "run_workspace",       # Executar um workspace composto pré-aprovado
    "analyze_clipboard",   # Acionar leitura segura do Clipboard via x-coder
    "generate_git_commit", # Ler git diff e sugerir mensagem via x-fast
    "analyze_screenshot",  # Inspecionar captura visual via x-vision
    "free_memory",         # Ejetar modelos da memória RAM imediatamente
]

ModelMode = Literal["x-fast", "x-coder", "x-vision"]

class SystemAction(BaseModel):
    """
    Contrato estrito enviado ao parâmetro format do Ollama.
    O LLM é obrigado a responder estritamente neste formato JSON.
    Regra de Segurança: 'target' aceita apenas chaves cadastradas na Allowlist.
    """
    intent: IntentType = Field(
        ...,
        description="Classificação objetiva da intenção do comando do usuário."
    )
    target: Optional[str] = Field(
        None,
        description="Chave exata cadastrada na Allowlist (ex: 'vscode', 'terminal', 'dev_web', 'x-assistant'). NUNCA caminhos livres."
    )
    requires_confirmation: bool = Field(
        False,
        description="True caso a ação envolva comandos de terminal ou alteração de estado do sistema."
    )
    reply: str = Field(
        ...,
        description="Resposta curta, direta e amigável em português (pt-BR) para exibição e síntese de voz TTS."
    )


# ============================================================================
# 2. CONTRATOS SEPARADOS PARA FERRAMENTAS DEV (ANTI PROMPT INJECTION)
# ============================================================================

class AnalysisResult(BaseModel):
    """
    Contrato puramente textual para saídas de Clipboard, Git Diff e Visão.
    GARANTIA DE SEGURANÇA: Não possui campos de execução de sistema.
    O conteúdo externo copiado/visto NUNCA pode se tornar uma ação de sistema.
    """
    status: Literal["success", "empty", "error"]
    model_used: str
    preview: Optional[str] = None
    analysis: str = Field(..., description="Texto descritivo ou correção de código gerada pelo especialista.")
    details: Optional[Dict[str, Any]] = None


# ============================================================================
# 3. CONTRATOS DE ENTIDADES DA ALLOWLIST (PERSISTIDAS NO SQLITE)
# ============================================================================

StepType = Literal["app", "url", "vscode_project", "terminal_cmd"]

class WorkspaceStep(BaseModel):
    type: StepType = Field(
        ...,
        description="Tipo do passo: 'app' (chave), 'url' (endereço web), 'vscode_project' (pasta) ou 'terminal_cmd' (comando fixo)."
    )
    target: str = Field(..., description="Chave do aplicativo, URL ou comando homologado no seed.")
    working_dir: Optional[str] = Field(None, description="Diretório de execução opcional.")

class AppEntry(BaseModel):
    key: str = Field(..., description="Chave identificadora única sem espaços (ex: 'vscode')")
    name: str = Field(..., description="Nome amigável exibido na interface")
    executable_path: str = Field(..., description="Caminho do executável ou comando do sistema")
    args: str = ""
    requires_confirmation: bool = False

class WorkspaceEntry(BaseModel):
    key: str = Field(..., description="Chave identificadora única do workspace (ex: 'dev_web')")
    name: str
    description: str = ""
    requires_confirmation: bool = False
    steps: List[WorkspaceStep]

class GitRepoEntry(BaseModel):
    key: str
    name: str
    repo_path: str

class AuditLogEntry(BaseModel):
    id: int
    timestamp: str
    action_type: str
    target_key: str
    status: Literal["SUCCESS", "BLOCKED", "ERROR", "PENDING_CONFIRMATION"]
    details: str = ""

class ConfirmationRecord(BaseModel):
    id: str = Field(..., description="Token aleatório seguro (secrets.token_urlsafe)")
    created_at: str
    expires_at: str
    intent: str
    target: str
    payload_json: str
    status: Literal["PENDING", "APPROVED", "CANCELLED", "EXPIRED"]


# ============================================================================
# 4. CONTRATOS DE REQUISIÇÕES REST (API)
# ============================================================================

class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Texto digitado ou transcrito pelo usuário")
    mode: ModelMode = "x-fast"
    speak_reply: bool = False

class ConfirmActionRequest(BaseModel):
    confirmation_id: str = Field(..., description="ID seguro gerado pelo servidor em pending_confirmations")
    approved: bool

class ClipboardRequest(BaseModel):
    instruction: str = "Analise o trecho a seguir. Se for um erro ou exceção, explique a causa em até 2 frases e forneça o código corrigido:"
    speak_reply: bool = False

class GitCommitRequest(BaseModel):
    repo_key: str = "x-assistant"
    custom_path: Optional[str] = None

class VisionRequest(BaseModel):
    prompt: str = "Inspecione esta imagem. Identifique mensagens de erro, problemas visuais de UI ou descreva os elementos com clareza:"
    source_preference: Literal["auto", "clipboard", "fullscreen"] = "auto"
    speak_reply: bool = False

class TTSRequest(BaseModel):
    text: str = Field(..., max_length=500)


# ============================================================================
# 5. PROTOCOLO TIPADO DO WEBSOCKET (/ws)
# ============================================================================

WSMessageType = Literal[
    "auth",                   # Cliente enviando token para autenticar
    "auth_ok",                # Servidor confirmando autenticação
    "telemetry",              # Servidor enviando métricas de CPU/RAM/Ollama
    "user_message",           # Cliente enviando comando/prompt de chat
    "token",                  # Servidor enviando chunk de texto em streaming
    "done",                   # Servidor sinalizando fim de geração de texto
    "action_result",          # Servidor informando resultado de uma execução de ação
    "confirmation_required",  # Servidor solicitando confirmação de ação sensível
    "error",                  # Servidor notificando erro tratado
]

class WSMessage(BaseModel):
    """
    Envelope padronizado para todas as trocas de mensagens no WebSocket.
    O discriminador 'type' permite que cliente e servidor façam parsing seguro.
    """
    type: WSMessageType
    data: Optional[Dict[str, Any]] = None
    text: Optional[str] = None
    token: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

