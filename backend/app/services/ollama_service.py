import re
from typing import AsyncGenerator, List, Dict, Any, Optional
import httpx
import ollama

from app.config import MODEL_FAST, MODEL_CODER, MODEL_VISION, MODEL_ALIASES
from app.schemas import SystemAction, AnalysisResult, ModelMode
from app.database import list_allowed_apps, list_workspaces, list_git_repos
from app.services.telemetry import get_loaded_ollama_models


# ============================================================================
# EXCEÇÕES TIPADAS
# ============================================================================

class OllamaOfflineError(Exception):
    """Lançada quando o daemon local do Ollama não está em execução."""
    def __init__(self, message: str = "O Ollama não está em execução. Abra o aplicativo do Ollama ou inicie o serviço no Windows."):
        super().__init__(message)


class ModelNotFoundError(Exception):
    """Lançada quando o modelo solicitado ainda não foi baixado/compilado."""
    def __init__(self, model_name: str):
        super().__init__(
            f"O modelo '{model_name}' não foi encontrado no Ollama. "
            f"Execute 'scripts\\setup_models.bat' ou 'ollama pull {model_name}' para instalá-lo."
        )
        self.model_name = model_name


def get_async_client() -> ollama.AsyncClient:
    """
    Retorna uma instância do AsyncClient vinculada ao event loop em execução.
    Evita o erro clássico 'Event loop is closed' entre requisições assíncronas e testes pytest.
    """
    return ollama.AsyncClient(host="http://127.0.0.1:11434")


# ============================================================================
# RESOLUÇÃO RESILIENTE DE MODELOS E DESCARGA DE RAM
# ============================================================================

async def is_ollama_online() -> bool:
    """Verifica se o servidor do Ollama está respondendo em :11434."""
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get("http://127.0.0.1:11434/")
            return resp.status_code == 200
    except Exception:
        return False


async def resolve_model_name(preferred: ModelMode) -> str:
    """
    Verifica se o alias customizado ('x-fast', 'x-coder', 'x-vision') existe.
    Se ainda não tiver sido compilado, faz fallback transparente para o modelo base.
    """
    if not await is_ollama_online():
        raise OllamaOfflineError()

    try:
        client = get_async_client()
        models_resp = await client.list()
        raw_list = getattr(models_resp, "models", None) or models_resp.get("models", [])
        installed = []
        for m in raw_list:
            name = getattr(m, "model", None) or getattr(m, "name", None) or m.get("model") or m.get("name", "")
            if name:
                installed.append(name.split(":")[0])

        if preferred in installed:
            return preferred

        base_name = MODEL_ALIASES.get(preferred, preferred).split(":")[0]
        if base_name in installed:
            return MODEL_ALIASES.get(preferred, preferred)

        raise ModelNotFoundError(preferred)
    except (OllamaOfflineError, ModelNotFoundError):
        raise
    except Exception as exc:
        raise OllamaOfflineError(f"Erro ao consultar o Ollama: {str(exc)}")


async def unload_all_models() -> Dict[str, Any]:
    """
    Ejeta todos os modelos ativos da memória RAM do Windows (keep_alive=0).
    Utilizado pelo botão 'Ejetar RAM' do Bento Box.
    """
    if not await is_ollama_online():
        return {"status": "offline", "message": "Ollama está offline. Nenhum modelo na memória."}

    active_models = await get_loaded_ollama_models()
    candidates = set(active_models + list(MODEL_ALIASES.keys()) + list(MODEL_ALIASES.values()))

    unloaded = []
    client = get_async_client()
    for model_name in candidates:
        try:
            await client.generate(model=model_name, prompt="", keep_alive=0)
            unloaded.append(model_name)
        except Exception:
            pass

    return {
        "status": "success",
        "unloaded_models": unloaded,
        "message": "Memória RAM do motor Ollama liberada com sucesso (keep_alive: 0).",
    }


# ============================================================================
# CLASSIFICADOR DE INTENÇÕES (FAST-PATH DETERMINÍSTICO + OLLAMA STRUCTURED)
# ============================================================================

def _build_router_system_prompt() -> str:
    """Monta o prompt do classificador com base estrita nas tabelas da Allowlist."""
    apps = [f"'{a.key}' ({a.name})" for a in list_allowed_apps()]
    workspaces = [f"'{w.key}' ({w.name})" for w in list_workspaces()]
    repos = [f"'{r.key}' ({r.name})" for r in list_git_repos()]

    return (
        "Você é o classificador de intenções do X-Assistant no Windows.\n"
        "Sua ÚNICA tarefa é analisar o pedido do usuário e responder em JSON válido seguindo estritamente o schema SystemAction.\n"
        f"- Apps permitidos na Allowlist (intent='open_app'): {', '.join(apps)}\n"
        f"- Workspaces permitidos (intent='run_workspace'): {', '.join(workspaces)}\n"
        f"- Repositórios Git (intent='generate_git_commit'): {', '.join(repos)}\n"
        "- Pedidos para analisar/corrigir texto copiado ou área de transferência: intent='analyze_clipboard'.\n"
        "- Pedidos para analisar print de tela, imagem ou erro visual: intent='analyze_screenshot'.\n"
        "- Pedidos para limpar memória, ejetar modelo ou liberar RAM: intent='free_memory'.\n"
        "- Perguntas gerais, dúvidas de programação ou conversa: intent='chat_response', target=null.\n"
        "- REGRA CRÍTICA DE SEGURANÇA: 'target' deve ser APENAS uma chave exata listada acima ou null. NUNCA invente comandos ou caminhos do Windows."
    )


def fast_path_intent_parser(prompt: str) -> Optional[SystemAction]:
    """
    Roteador determinístico ultra-rápido (~0 ms).
    Resolve comandos óbvios e diretos sem precisar esperar a inferência do LLM.
    """
    text = prompt.lower().strip()

    # 1. Ejeção de RAM
    if any(k in text for k in ["liberar ram", "limpar ram", "ejetar ram", "descarregar modelo", "free memory"]):
        return SystemAction(
            intent="free_memory",
            target=None,
            requires_confirmation=False,
            reply="Liberando os modelos da memória RAM imediatamente.",
        )

    # 2. Clipboard
    if any(k in text for k in ["analisar clipboard", "analise o clipboard", "corrigir clipboard", "área de transferência", "area de transferencia"]):
        return SystemAction(
            intent="analyze_clipboard",
            target=None,
            requires_confirmation=False,
            reply="Analisando o conteúdo copiado na área de transferência com o módulo especialista.",
        )

    # 3. Print / Tela
    if any(k in text for k in ["analisar tela", "analise a tela", "analisar print", "olhe minha tela", "screenshot"]):
        return SystemAction(
            intent="analyze_screenshot",
            target=None,
            requires_confirmation=False,
            reply="Inspecionando captura visual com o módulo de visão.",
        )

    # 4. Git Commit
    if any(k in text for k in ["gerar commit", "gere um commit", "commit do git", "git commit"]):
        repos = list_git_repos()
        default_repo = repos[0].key if repos else "x-assistant"
        return SystemAction(
            intent="generate_git_commit",
            target=default_repo,
            requires_confirmation=False,
            reply=f"Lendo as alterações locais do repositório '{default_repo}' para sugerir a mensagem de commit.",
        )

    # 5. Workspaces por nome ou chave
    if any(w in text for w in ["workspace", "ambiente", "iniciar projeto", "rodar workspace", "abrir workspace"]):
        for ws in list_workspaces():
            if ws.key.lower() in text or ws.name.lower() in text:
                return SystemAction(
                    intent="run_workspace",
                    target=ws.key,
                    requires_confirmation=ws.requires_confirmation,
                    reply=f"Iniciando o workspace '{ws.name}'.",
                )

    # 6. Abertura direta de Apps autorizados ("abrir vscode", "iniciar calculadora", etc.)
    open_match = re.search(r"\b(abrir|abra|iniciar|inicie|executar|rode|open)\b", text)
    if open_match:
        for app in list_allowed_apps():
            if app.key.lower() in text or app.name.lower() in text:
                return SystemAction(
                    intent="open_app",
                    target=app.key,
                    requires_confirmation=app.requires_confirmation,
                    reply=f"Abrindo {app.name}.",
                )
        for ws in list_workspaces():
            if ws.key.lower() in text:
                return SystemAction(
                    intent="run_workspace",
                    target=ws.key,
                    requires_confirmation=ws.requires_confirmation,
                    reply=f"Iniciando o workspace {ws.name}.",
                )

    return None


async def classify_intent(prompt: str, model: ModelMode = MODEL_FAST) -> SystemAction:
    """
    Classifica a intenção do usuário em um contrato SystemAction.
    1. Executa o roteador determinístico (~0 ms).
    2. Se não casar, consulta o modelo Ollama com Structured Outputs (format=schema).
    IMPORTANTE: Esta função APENAS classifica. Ela NÃO executa nada no Windows.
    """
    # 1. Atalho ultra-rápido
    fast_result = fast_path_intent_parser(prompt)
    if fast_result is not None:
        return fast_result

    # 2. Resolução do modelo e chamada assíncrona
    resolved_model = await resolve_model_name(model)
    messages = [
        {"role": "system", "content": _build_router_system_prompt()},
        {"role": "user", "content": prompt},
    ]

    try:
        client = get_async_client()
        response = await client.chat(
            model=resolved_model,
            messages=messages,
            format=SystemAction.model_json_schema(),
            keep_alive="5m",
        )
        content = response["message"]["content"]
        return SystemAction.model_validate_json(content)
    except Exception as exc:
        # Fallback de conversa amigável se a inferência falhar
        return SystemAction(
            intent="chat_response",
            target=None,
            requires_confirmation=False,
            reply=f"Não foi possível classificar via {resolved_model}: {str(exc)}",
        )


# ============================================================================
# CHAT EM STREAMING (PARA CONVERSAS TÉCNICAS E PERGUNTAS LIVRES)
# ============================================================================

async def stream_chat_response(
    prompt: str,
    model: ModelMode = MODEL_FAST,
    history: Optional[List[Dict[str, str]]] = None,
) -> AsyncGenerator[str, None]:
    """
    Gera resposta token-a-token via streaming assíncrono para ser transmitida pelo WebSocket.
    """
    resolved_model = await resolve_model_name(model)
    messages: List[Dict[str, Any]] = []

    if history:
        for msg in history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": prompt})

    try:
        client = get_async_client()
        stream = await client.chat(
            model=resolved_model,
            messages=messages,
            stream=True,
            keep_alive="5m",
        )
        async for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
    except Exception as exc:
        yield f"\n⚠️ [Erro durante o streaming com {resolved_model}: {str(exc)}]"


# ============================================================================
# CAMINHO SEPARADO SÓ-TEXTO (ANTI PROMPT INJECTION - DEV TOOLS E VISÃO)
# ============================================================================

async def analyze_text(
    system_prompt: str,
    content_to_analyze: str,
    model: ModelMode = MODEL_CODER,
) -> str:
    """
    Caminho estritamente textual para Clipboard e Git Diff.
    NÃO usa schema de ação do sistema. A resposta gerada é puramente textual.
    """
    resolved_model = await resolve_model_name(model)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content_to_analyze},
    ]
    client = get_async_client()
    response = await client.chat(
        model=resolved_model,
        messages=messages,
        keep_alive="5m",
    )
    return response["message"]["content"]


async def analyze_image(
    system_prompt: str,
    user_prompt: str,
    image_path: str,
    model: ModelMode = MODEL_VISION,
) -> str:
    """
    Caminho estritamente textual para análise de telas e prints.
    NÃO usa schema de ação do sistema.
    """
    resolved_model = await resolve_model_name(model)
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": user_prompt,
            "images": [image_path],
        },
    ]
    client = get_async_client()
    response = await client.chat(
        model=resolved_model,
        messages=messages,
        keep_alive="5m",
    )
    return response["message"]["content"]

