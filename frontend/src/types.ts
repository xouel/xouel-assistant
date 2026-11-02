// ============================================================================
// 1. CONTRATOS DO CLASSIFICADOR DE INTENÇÕES E MODELOS
// ============================================================================

export type IntentType =
  | "chat_response"
  | "open_app"
  | "run_workspace"
  | "analyze_clipboard"
  | "generate_git_commit"
  | "analyze_screenshot"
  | "free_memory"
  | "allowlist_mutation";

export type ModelMode = "x-fast" | "x-coder" | "x-vision";

export interface SystemAction {
  intent: IntentType;
  target?: string | null;
  requires_confirmation: boolean;
  reply: string;
}

export interface AnalysisResult {
  status: "success" | "empty" | "error";
  model_used: string;
  preview?: string | null;
  analysis: string;
  details?: Record<string, unknown> | null;
}

// ============================================================================
// 2. ENTIDADES DA ALLOWLIST E AUDITORIA (SQLITE)
// ============================================================================

export type StepType = "app" | "url" | "vscode_project" | "terminal_cmd";

export interface WorkspaceStep {
  type: StepType;
  target: string;
  working_dir?: string | null;
}

export interface AppEntry {
  key: string;
  name: string;
  executable_path: string;
  args: string;
  requires_confirmation: boolean;
}

export interface WorkspaceEntry {
  key: string;
  name: string;
  description: string;
  requires_confirmation: boolean;
  steps: WorkspaceStep[];
}

export interface GitRepoEntry {
  key: string;
  name: string;
  repo_path: string;
}

export type AuditStatus =
  | "SUCCESS"
  | "BLOCKED"
  | "ERROR"
  | "PENDING_CONFIRMATION"
  | "CANCELLED"
  | "NOT_FOUND";

export interface AuditLogEntry {
  id: number;
  timestamp: string;
  action_type: string;
  target_key: string;
  status: AuditStatus;
  details: string;
}

// ============================================================================
// 3. TELEMETRIA DE HARDWARE (i3-1215U + 20 GB FLEX MODE)
// ============================================================================

export interface SystemTelemetry {
  cpu_percent: number;
  ram_total_gb: number;
  ram_used_gb: number;
  ram_free_gb: number;
  ram_percent: number;
  ollama_ram_mb: number;
  ollama_ram_gb: number;
  ollama_processes_count: number;
  active_models: string[];
  active_model_label: string;
  is_dual_channel: boolean;
  memory_mode_label: string;
}

// ============================================================================
// 4. CONFIRMAÇÕES DE SEGURANÇA E MENSAGENS DE CHAT
// ============================================================================

export interface PendingConfirmation {
  confirmation_id: string;
  intent: string;
  target: string;
  reply: string;
  timestamp: string;
}

export interface ChatMessage {
  id: string;
  timestamp: string;
  role: "user" | "assistant" | "system";
  model_used: string;
  content: string;
  intent?: string;
  isStreaming?: boolean;
  status?: string;
  details?: Record<string, unknown>;
}

// ============================================================================
// 5. PROTOCOLO TIPADO DO WEBSOCKET (/ws)
// ============================================================================

export type WSMessageType =
  | "auth"
  | "auth_ok"
  | "telemetry"
  | "user_message"
  | "token"
  | "done"
  | "action_result"
  | "confirmation_required"
  | "error";

export interface WSMessage {
  type: WSMessageType;
  data?: Record<string, unknown> | null;
  text?: string | null;
  token?: string | null;
  timestamp?: string;
}

export type ConnectionStatus =
  | "connecting"
  | "authenticating"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "auth_error";

