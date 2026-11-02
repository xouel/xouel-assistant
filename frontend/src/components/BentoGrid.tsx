import { useState } from "react";
import {
  RefreshCw,
  Settings2,
  Sparkles,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useAssistant } from "@/hooks/useAssistant";
import { TelemetryCard } from "@/components/TelemetryCard";
import { QuickActions } from "@/components/QuickActions";
import { ChatPanel } from "@/components/ChatPanel";
import { AllowlistModal } from "@/components/AllowlistModal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function BentoGrid() {
  const {
    connectionStatus,
    reconnectAttempt,
    lastError,
    reconnectNow,
    telemetry,
    lastTelemetryAt,
    freeMemory,
    mode,
    setMode,
    speakReply,
    setSpeakReply,
    messages,
    isGenerating,
    sendMessage,
    clearHistory,
    transcribeAudio,
    pendingConfirmations,
    confirmAction,
    runClipboardAnalysis,
    runGitCommitSuggestion,
    runVisionAnalysis,
    apps,
    workspaces,
    repos,
    auditLogs,
    requestAllowlistMutation,
  } = useAssistant();

  const [isAllowlistOpen, setIsAllowlistOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background text-foreground p-3 sm:p-5">
      <div className="max-w-7xl mx-auto space-y-4">
        {/* Top Header Bento Bar */}
        <header className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/90 px-4 py-3 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/15 text-primary border border-primary/25">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm sm:text-base font-bold tracking-tight text-foreground">
                  X-Assistant
                </h1>
                <Badge
                  variant="outline"
                  className="text-[10px] px-1.5 py-0 h-4 font-mono border-primary/30 text-primary hidden sm:inline-flex"
                >
                  v1.0 • Local AI
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground">
                i3-1215U • 20 GB Flex Mode •{" "}
                <kbd className="font-mono text-[10px] text-foreground">
                  Ctrl+Shift+Espaço
                </kbd>{" "}
                /{" "}
                <kbd className="font-mono text-[10px] text-foreground">
                  Ctrl+Alt+X
                </kbd>{" "}
                Focar •{" "}
                <kbd className="font-mono text-[10px] text-foreground">
                  Ctrl+Espaço
                </kbd>{" "}
                Voz PTT
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Status do WebSocket */}
            <div
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium border ${
                connectionStatus === "connected"
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : connectionStatus === "reconnecting" ||
                    connectionStatus === "connecting" ||
                    connectionStatus === "authenticating"
                  ? "border-warning/40 bg-warning/10 text-warning"
                  : "border-destructive/40 bg-destructive/10 text-destructive"
              }`}
            >
              {connectionStatus === "connected" ? (
                <>
                  <Wifi className="h-3 w-3" />
                  <span>Online (/ws)</span>
                </>
              ) : connectionStatus === "reconnecting" ? (
                <>
                  <RefreshCw className="h-3 w-3 animate-spin" />
                  <span>Reconectando (#{reconnectAttempt})</span>
                </>
              ) : (
                <>
                  <WifiOff className="h-3 w-3" />
                  <span>{connectionStatus}</span>
                </>
              )}
            </div>

            {connectionStatus !== "connected" && (
              <Button
                variant="outline"
                size="sm"
                onClick={reconnectNow}
                className="h-7 px-2.5 text-xs gap-1 cursor-pointer"
              >
                <RefreshCw className="h-3 w-3" />
                Reconectar
              </Button>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsAllowlistOpen(true)}
              className="h-7 px-2.5 text-xs gap-1.5 border-border bg-secondary/70 hover:bg-accent cursor-pointer"
            >
              <Settings2 className="h-3.5 w-3.5 text-primary" />
              <span className="hidden sm:inline">Configurar Allowlist</span>
            </Button>
          </div>
        </header>

        {/* Layout Bento Box Principal (12 Colunas) */}
        <main className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          {/* Coluna Esquerda (5 Colunas): Telemetria + Ações Rápidas + Auditoria */}
          <div className="lg:col-span-5 flex flex-col gap-4">
            <TelemetryCard
              telemetry={telemetry}
              lastTelemetryAt={lastTelemetryAt}
              onFreeMemory={freeMemory}
            />

            <QuickActions
              apps={apps}
              workspaces={workspaces}
              repos={repos}
              auditLogs={auditLogs}
              isGenerating={isGenerating}
              onTriggerCommand={(cmd) =>
                sendMessage(cmd, {
                  mode: "x-fast",
                  speak: speakReply,
                  stream: false,
                })
              }
              onAnalyzeClipboard={() => runClipboardAnalysis()}
              onSuggestCommit={(repoKey) => runGitCommitSuggestion(repoKey)}
              onAnalyzeVision={() => runVisionAnalysis()}
              onOpenAllowlistModal={() => setIsAllowlistOpen(true)}
            />
          </div>

          {/* Coluna Direita (7 Colunas): Chat Streaming, Voz Push-to-Talk e Confirmações */}
          <div className="lg:col-span-7">
            <ChatPanel
              mode={mode}
              onSelectMode={setMode}
              speakReply={speakReply}
              onToggleSpeakReply={setSpeakReply}
              messages={messages}
              isGenerating={isGenerating}
              lastError={lastError}
              pendingConfirmations={pendingConfirmations}
              onSendMessage={sendMessage}
              onConfirmAction={confirmAction}
              onClearHistory={clearHistory}
              onTranscribeAudio={transcribeAudio}
            />
          </div>
        </main>

        {/* Modal de Gerenciamento Seguro da Allowlist */}
        <AllowlistModal
          open={isAllowlistOpen}
          onOpenChange={setIsAllowlistOpen}
          apps={apps}
          workspaces={workspaces}
          repos={repos}
          pendingConfirmations={pendingConfirmations}
          onRequestMutation={requestAllowlistMutation}
          onConfirmAction={confirmAction}
        />
      </div>
    </div>
  );
}

