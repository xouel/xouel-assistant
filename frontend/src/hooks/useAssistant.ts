import { useState, useEffect, useRef, useCallback } from "react";
import type {
  ModelMode,
  SystemTelemetry,
  ChatMessage,
  PendingConfirmation,
  AppEntry,
  WorkspaceEntry,
  GitRepoEntry,
  AuditLogEntry,
  WSMessage,
  ConnectionStatus,
  AnalysisResult,
} from "@/types";

const API_BASE_URL = "http://127.0.0.1:8000";
const WS_URL = "ws://127.0.0.1:8000/ws";

export function getLocalToken(): string {
  if (typeof window !== "undefined" && window.__X_LOCAL_TOKEN__) {
    return window.__X_LOCAL_TOKEN__;
  }
  if (typeof __DEV_LOCAL_TOKEN__ !== "undefined" && __DEV_LOCAL_TOKEN__) {
    return __DEV_LOCAL_TOKEN__;
  }
  return "";
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getLocalToken();
  const headers = new Headers(options.headers || {});
  headers.set("X-Local-Token", token);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`;
    try {
      const errJson = await response.json();
      errorDetail = errJson.detail || errJson.message || errorDetail;
    } catch {
      // Ignora erro de parse caso não seja JSON
    }
    throw new Error(errorDetail);
  }

  return response.json() as Promise<T>;
}

export function useAssistant() {
  // Estado da conexão WebSocket e reconexão com backoff
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("connecting");
  const [reconnectAttempt, setReconnectAttempt] = useState<number>(0);
  const [lastError, setLastError] = useState<string | null>(null);

  // Estado de Telemetria em tempo real
  const [telemetry, setTelemetry] = useState<SystemTelemetry | null>(null);
  const [lastTelemetryAt, setLastTelemetryAt] = useState<string | null>(null);

  // Estado de Chat, Modelos e Confirmações Pendentes
  const [mode, setMode] = useState<ModelMode>("x-fast");
  const [speakReply, setSpeakReply] = useState<boolean>(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [pendingConfirmations, setPendingConfirmations] = useState<
    PendingConfirmation[]
  >([]);

  // Estado da Allowlist e Auditoria
  const [apps, setApps] = useState<AppEntry[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceEntry[]>([]);
  const [repos, setRepos] = useState<GitRepoEntry[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);

  // Refs para controle do ciclo de vida do WebSocket sem closures obsoletas
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const unmountedRef = useRef<boolean>(false);
  const statusRef = useRef<ConnectionStatus>("connecting");
  const attemptRef = useRef<number>(0);
  const activeModeRef = useRef<ModelMode>(mode);

  useEffect(() => {
    activeModeRef.current = mode;
  }, [mode]);

  const updateStatus = useCallback((next: ConnectionStatus) => {
    statusRef.current = next;
    setConnectionStatus(next);
  }, []);

  // ==========================================================================
  // HIDRATAÇÃO E SINCRONIZAÇÃO DE DADOS REST
  // ==========================================================================

  const refreshAllowlistAndLogs = useCallback(async () => {
    try {
      const [appsData, wsData, reposData, logsData] = await Promise.all([
        apiRequest<AppEntry[]>("/api/allowlist/apps"),
        apiRequest<WorkspaceEntry[]>("/api/allowlist/workspaces"),
        apiRequest<GitRepoEntry[]>("/api/allowlist/repos"),
        apiRequest<AuditLogEntry[]>("/api/audit-logs?limit=30"),
      ]);
      setApps(appsData);
      setWorkspaces(wsData);
      setRepos(reposData);
      setAuditLogs(logsData);
    } catch (err) {
      console.warn("[useAssistant] Falha ao sincronizar allowlist/logs:", err);
    }
  }, []);

  const loadInitialHistory = useCallback(async () => {
    try {
      const history = await apiRequest<
        Array<{
          id: number;
          timestamp: string;
          role: "user" | "assistant";
          model_used: string;
          content: string;
          intent?: string;
        }>
      >("/api/chat-history?limit=40");

      setMessages((prev) => {
        if (prev.length > 0) return prev;
        return history.map((item) => ({
          id: `hist-${item.id}`,
          timestamp: item.timestamp,
          role: item.role,
          model_used: item.model_used,
          content: item.content,
          intent: item.intent,
        }));
      });
    } catch (err) {
      console.warn("[useAssistant] Falha ao carregar histórico:", err);
    }
  }, []);

  // ==========================================================================
  // REGISTRO DE CONFIRMAÇÕES PENDENTES
  // ==========================================================================

  const enqueueConfirmation = useCallback(
    (payload: {
      confirmation_id: string;
      intent?: string;
      target?: string;
      reply?: string;
    }) => {
      const item: PendingConfirmation = {
        confirmation_id: payload.confirmation_id,
        intent: payload.intent || "system_action",
        target: payload.target || "-",
        reply:
          payload.reply ||
          "Esta ação é sensível e exige sua confirmação explícita.",
        timestamp: new Date().toISOString(),
      };

      setPendingConfirmations((prev) => {
        if (prev.some((c) => c.confirmation_id === item.confirmation_id)) {
          return prev;
        }
        return [item, ...prev];
      });
    },
    []
  );

  // ==========================================================================
  // CONEXÃO WEBSOCKET, HANDSHAKE E RECONEXÃO COM BACKOFF EXPONENCIAL
  // ==========================================================================

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const connectWebSocket = useCallback(() => {
    if (unmountedRef.current) return;
    clearReconnectTimer();

    // Fecha instância anterior se ainda existir
    if (wsRef.current) {
      try {
        wsRef.current.onclose = null;
        wsRef.current.close();
      } catch {
        // Ignora erro no fechamento
      }
      wsRef.current = null;
    }

    const token = getLocalToken();
    if (!token) {
      updateStatus("auth_error");
      setLastError(
        "Token local (.local_token) não encontrado. Inicie o backend primeiro e recarregue a página."
      );
      return;
    }

    updateStatus(attemptRef.current > 0 ? "reconnecting" : "connecting");

    let ws: WebSocket;
    try {
      ws = new WebSocket(WS_URL);
      wsRef.current = ws;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLastError(`Erro ao criar WebSocket: ${msg}`);
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      if (unmountedRef.current) return;
      updateStatus("authenticating");
      ws.send(
        JSON.stringify({
          type: "auth",
          token,
        })
      );
    };

    ws.onmessage = (event: MessageEvent) => {
      if (unmountedRef.current) return;
      let msg: WSMessage;
      try {
        msg = JSON.parse(event.data) as WSMessage;
      } catch {
        return;
      }

      switch (msg.type) {
        case "auth_ok": {
          attemptRef.current = 0;
          setReconnectAttempt(0);
          setLastError(null);
          updateStatus("connected");
          void refreshAllowlistAndLogs();
          void loadInitialHistory();
          break;
        }

        case "telemetry": {
          if (msg.data) {
            setTelemetry(msg.data as unknown as SystemTelemetry);
            setLastTelemetryAt(
              msg.timestamp || new Date().toLocaleTimeString("pt-BR")
            );
          }
          break;
        }

        case "token": {
          const chunk = msg.token || "";
          if (!chunk) break;
          setIsGenerating(true);
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant" && last.isStreaming) {
              const updated: ChatMessage = {
                ...last,
                content: last.content + chunk,
              };
              return [...prev.slice(0, -1), updated];
            }
            const streamMsg: ChatMessage = {
              id: `stream-${Date.now()}`,
              timestamp: new Date().toISOString(),
              role: "assistant",
              model_used: activeModeRef.current,
              content: chunk,
              intent: "chat_response",
              isStreaming: true,
            };
            return [...prev, streamMsg];
          });
          break;
        }

        case "done": {
          setIsGenerating(false);
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant" && last.isStreaming) {
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  content: msg.text || last.content,
                  isStreaming: false,
                },
              ];
            }
            if (msg.text) {
              return [
                ...prev,
                {
                  id: `done-${Date.now()}`,
                  timestamp: new Date().toISOString(),
                  role: "assistant",
                  model_used: activeModeRef.current,
                  content: msg.text,
                  intent: "chat_response",
                  isStreaming: false,
                },
              ];
            }
            return prev;
          });
          break;
        }

        case "action_result": {
          setIsGenerating(false);
          const payload = msg.data || {};
          const replyText =
            msg.text ||
            (payload.reply as string) ||
            "Ação executada pelo assistente.";
          const intent = (payload.intent as string) || "action_result";
          const status = (payload.status as string) || "success";

          setMessages((prev) => [
            ...prev,
            {
              id: `act-${Date.now()}`,
              timestamp: msg.timestamp || new Date().toISOString(),
              role: "assistant",
              model_used: activeModeRef.current,
              content: replyText,
              intent,
              status,
              details: payload,
            },
          ]);

          void refreshAllowlistAndLogs();
          break;
        }

        case "confirmation_required": {
          setIsGenerating(false);
          const payload = msg.data || {};
          const confId = payload.confirmation_id as string | undefined;
          const replyText =
            msg.text ||
            (payload.reply as string) ||
            "Confirmação de segurança necessária.";

          if (confId) {
            enqueueConfirmation({
              confirmation_id: confId,
              intent: (payload.intent as string) || "system_action",
              target: (payload.target as string) || "-",
              reply: replyText,
            });
          }

          setMessages((prev) => [
            ...prev,
            {
              id: `conf-${Date.now()}`,
              timestamp: msg.timestamp || new Date().toISOString(),
              role: "assistant",
              model_used: activeModeRef.current,
              content: `⚠️ ${replyText}`,
              intent: (payload.intent as string) || "confirmation_required",
              status: "pending_confirmation",
              details: payload,
            },
          ]);
          break;
        }

        case "error": {
          setIsGenerating(false);
          const errText = msg.text || "Erro reportado pelo servidor.";
          setLastError(errText);
          if (statusRef.current === "authenticating") {
            updateStatus("auth_error");
          }
          break;
        }
      }
    };

    ws.onerror = () => {
      // O evento onclose lidará com a reconexão com backoff
    };

    ws.onclose = () => {
      if (unmountedRef.current) return;
      if (statusRef.current === "auth_error") {
        return;
      }
      scheduleReconnect();
    };
  }, [
    clearReconnectTimer,
    enqueueConfirmation,
    loadInitialHistory,
    refreshAllowlistAndLogs,
    updateStatus,
  ]);

  const scheduleReconnect = useCallback(() => {
    if (unmountedRef.current) return;
    clearReconnectTimer();

    const nextAttempt = attemptRef.current + 1;
    attemptRef.current = nextAttempt;
    setReconnectAttempt(nextAttempt);
    updateStatus("reconnecting");

    // Backoff exponencial suave: 1s -> 1.5s -> 2.25s -> 3.3s ... teto de 8s
    const delayMs = Math.min(Math.round(1000 * Math.pow(1.5, nextAttempt - 1)), 8000);
    reconnectTimerRef.current = window.setTimeout(() => {
      connectWebSocket();
    }, delayMs);
  }, [clearReconnectTimer, connectWebSocket, updateStatus]);

  const reconnectNow = useCallback(() => {
    attemptRef.current = 0;
    setReconnectAttempt(0);
    setLastError(null);
    connectWebSocket();
  }, [connectWebSocket]);

  useEffect(() => {
    unmountedRef.current = false;
    connectWebSocket();

    return () => {
      unmountedRef.current = true;
      clearReconnectTimer();
      if (wsRef.current) {
        try {
          wsRef.current.onclose = null;
          wsRef.current.close();
        } catch {
          // Ignora
        }
      }
    };
  }, [connectWebSocket, clearReconnectTimer]);

  // ==========================================================================
  // AÇÕES DO ASSISTENTE (CHAT, CONFIRMAÇÃO, DEV TOOLS, VOZ E ALLOWLIST)
  // ==========================================================================

  const sendMessage = useCallback(
    async (
      prompt: string,
      options?: { mode?: ModelMode; speak?: boolean; stream?: boolean }
    ) => {
      const clean = prompt.trim();
      if (!clean) return;

      const selectedMode = options?.mode || mode;
      const selectedSpeak = options?.speak ?? speakReply;
      const selectedStream = options?.stream ?? true;

      const userMsg: ChatMessage = {
        id: `usr-${Date.now()}`,
        timestamp: new Date().toISOString(),
        role: "user",
        model_used: selectedMode,
        content: clean,
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsGenerating(true);
      setLastError(null);

      // Caminho primário: WebSocket autenticado
      if (
        wsRef.current &&
        wsRef.current.readyState === WebSocket.OPEN &&
        statusRef.current === "connected"
      ) {
        wsRef.current.send(
          JSON.stringify({
            type: "user_message",
            text: clean,
            mode: selectedMode,
            speak: selectedSpeak,
            stream: selectedStream,
          })
        );
        return;
      }

      // Fallback REST caso o WebSocket esteja reconectando
      try {
        const res = await apiRequest<Record<string, unknown>>("/api/chat", {
          method: "POST",
          body: JSON.stringify({
            prompt: clean,
            mode: selectedMode,
            speak_reply: selectedSpeak,
          }),
        });

        if (res.type === "confirmation_required" && res.confirmation_id) {
          enqueueConfirmation({
            confirmation_id: String(res.confirmation_id),
            intent: String(res.intent || "system_action"),
            target: String(res.target || "-"),
            reply: String(res.reply || "Confirmação necessária."),
          });
        }

        setMessages((prev) => [
          ...prev,
          {
            id: `rest-${Date.now()}`,
            timestamp: new Date().toISOString(),
            role: "assistant",
            model_used: selectedMode,
            content: String(res.reply || "Comando processado."),
            intent: String(res.intent || "chat_response"),
            status: String(res.status || "success"),
            details: res,
          },
        ]);
        void refreshAllowlistAndLogs();
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setLastError(msg);
      } finally {
        setIsGenerating(false);
      }
    },
    [mode, speakReply, enqueueConfirmation, refreshAllowlistAndLogs]
  );

  const confirmAction = useCallback(
    async (confirmationId: string, approved: boolean) => {
      try {
        const res = await apiRequest<Record<string, unknown>>("/api/confirm", {
          method: "POST",
          body: JSON.stringify({
            confirmation_id: confirmationId,
            approved,
          }),
        });

        setPendingConfirmations((prev) =>
          prev.filter((c) => c.confirmation_id !== confirmationId)
        );

        const replyText = String(
          res.reply ||
            res.message ||
            (approved ? "Ação confirmada." : "Ação cancelada.")
        );

        setMessages((prev) => [
          ...prev,
          {
            id: `conf-res-${Date.now()}`,
            timestamp: new Date().toISOString(),
            role: "assistant",
            model_used: mode,
            content: replyText,
            intent: String(res.intent || "confirm_action"),
            status: String(res.status || "success"),
            details: res,
          },
        ]);

        await refreshAllowlistAndLogs();
        return res;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setLastError(msg);
        throw err;
      }
    },
    [mode, refreshAllowlistAndLogs]
  );

  const freeMemory = useCallback(async () => {
    try {
      const res = await apiRequest<Record<string, unknown>>(
        "/api/system/unload",
        {
          method: "POST",
        }
      );
      const freshTelemetry = await apiRequest<SystemTelemetry>(
        "/api/system/telemetry"
      );
      setTelemetry(freshTelemetry);
      setMessages((prev) => [
        ...prev,
        {
          id: `mem-${Date.now()}`,
          timestamp: new Date().toISOString(),
          role: "assistant",
          model_used: "system",
          content: String(res.reply || "Memória RAM liberada com sucesso."),
          intent: "free_memory",
          status: "success",
        },
      ]);
      return res;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLastError(msg);
      throw err;
    }
  }, []);

  const runClipboardAnalysis = useCallback(
    async (instruction?: string) => {
      setIsGenerating(true);
      try {
        const res = await apiRequest<AnalysisResult>(
          "/api/devtools/clipboard",
          {
            method: "POST",
            body: JSON.stringify({
              instruction:
                instruction ||
                "Analise o trecho a seguir. Se for um erro ou exceção, explique a causa em até 2 frases e forneça o código corrigido:",
              speak_reply: speakReply,
            }),
          }
        );
        setMessages((prev) => [
          ...prev,
          {
            id: `clip-${Date.now()}`,
            timestamp: new Date().toISOString(),
            role: "assistant",
            model_used: res.model_used || "x-coder",
            content: res.analysis,
            intent: "analyze_clipboard",
            status: res.status,
            details: res as unknown as Record<string, unknown>,
          },
        ]);
        return res;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setLastError(msg);
        throw err;
      } finally {
        setIsGenerating(false);
      }
    },
    [speakReply]
  );

  const runGitCommitSuggestion = useCallback(
    async (repoKey = "x-assistant") => {
      setIsGenerating(true);
      try {
        const res = await apiRequest<Record<string, unknown>>(
          "/api/devtools/git-commit",
          {
            method: "POST",
            body: JSON.stringify({ repo_key: repoKey }),
          }
        );
        const content =
          res.status === "success"
            ? `Sugestão de Commit (${repoKey}):\n\`\`\`\n${res.commit_message}\n\`\`\``
            : String(res.message || "Nenhuma alteração detectada no repositório.");

        setMessages((prev) => [
          ...prev,
          {
            id: `git-${Date.now()}`,
            timestamp: new Date().toISOString(),
            role: "assistant",
            model_used: "x-fast",
            content,
            intent: "generate_git_commit",
            status: String(res.status || "info"),
            details: res,
          },
        ]);
        return res;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setLastError(msg);
        throw err;
      } finally {
        setIsGenerating(false);
      }
    },
    []
  );

  const runVisionAnalysis = useCallback(
    async (
      prompt?: string,
      sourcePreference: "auto" | "clipboard" | "fullscreen" = "auto"
    ) => {
      setIsGenerating(true);
      try {
        const res = await apiRequest<AnalysisResult>("/api/devtools/vision", {
          method: "POST",
          body: JSON.stringify({
            prompt:
              prompt ||
              "Inspecione esta imagem. Identifique mensagens de erro, problemas visuais de UI ou descreva os elementos com clareza:",
            source_preference: sourcePreference,
            speak_reply: speakReply,
          }),
        });
        setMessages((prev) => [
          ...prev,
          {
            id: `vis-${Date.now()}`,
            timestamp: new Date().toISOString(),
            role: "assistant",
            model_used: res.model_used || "x-vision",
            content: res.analysis,
            intent: "analyze_screenshot",
            status: res.status,
            details: res as unknown as Record<string, unknown>,
          },
        ]);
        return res;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setLastError(msg);
        throw err;
      } finally {
        setIsGenerating(false);
      }
    },
    [speakReply]
  );

  const transcribeAudio = useCallback(async (audioBlob: Blob) => {
    const formData = new FormData();
    formData.append("file", audioBlob, "ptt_recording.webm");
    const res = await apiRequest<{
      status: string;
      text?: string;
      message?: string;
      duration?: number;
    }>("/api/voice/transcribe", {
      method: "POST",
      body: formData,
    });
    if (res.status !== "success") {
      throw new Error(res.message || "Falha ao transcrever áudio.");
    }
    return res.text || "";
  }, []);

  // Mutações da Allowlist (todas geram confirmation_required no servidor)
  const requestAllowlistMutation = useCallback(
    async (
      endpoint: string,
      method: "POST" | "DELETE",
      body?: unknown
    ): Promise<PendingConfirmation | null> => {
      const res = await apiRequest<{
        type: string;
        confirmation_id: string;
        intent: string;
        target: string;
        reply: string;
      }>(endpoint, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });

      if (res.type === "confirmation_required" && res.confirmation_id) {
        enqueueConfirmation(res);
        return {
          confirmation_id: res.confirmation_id,
          intent: res.intent,
          target: res.target,
          reply: res.reply,
          timestamp: new Date().toISOString(),
        };
      }
      return null;
    },
    [enqueueConfirmation]
  );

  const clearHistory = useCallback(async () => {
    await apiRequest("/api/chat-history", { method: "DELETE" });
    setMessages([]);
  }, []);

  return {
    // Conexão e Diagnóstico
    connectionStatus,
    reconnectAttempt,
    lastError,
    reconnectNow,

    // Telemetria de Hardware
    telemetry,
    lastTelemetryAt,
    freeMemory,

    // Chat, Modelos e Voz
    mode,
    setMode,
    speakReply,
    setSpeakReply,
    messages,
    isGenerating,
    sendMessage,
    clearHistory,
    transcribeAudio,

    // Confirmações de Segurança
    pendingConfirmations,
    confirmAction,

    // Ferramentas Dev
    runClipboardAnalysis,
    runGitCommitSuggestion,
    runVisionAnalysis,

    // Allowlist e Auditoria
    apps,
    workspaces,
    repos,
    auditLogs,
    refreshAllowlistAndLogs,
    requestAllowlistMutation,
  };
}

