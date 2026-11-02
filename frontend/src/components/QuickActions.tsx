import { useState } from "react";
import {
  Camera,
  ClipboardCheck,
  FolderGit2,
  Layers,
  Play,
  Settings2,
  ShieldCheck,
  Sparkles,
  Terminal,
  Lock,
} from "lucide-react";
import { toast } from "sonner";
import type {
  AppEntry,
  AuditLogEntry,
  GitRepoEntry,
  WorkspaceEntry,
} from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface QuickActionsProps {
  apps: AppEntry[];
  workspaces: WorkspaceEntry[];
  repos: GitRepoEntry[];
  auditLogs: AuditLogEntry[];
  isGenerating: boolean;
  onTriggerCommand: (prompt: string) => Promise<void>;
  onAnalyzeClipboard: () => Promise<unknown>;
  onSuggestCommit: (repoKey?: string) => Promise<unknown>;
  onAnalyzeVision: () => Promise<unknown>;
  onOpenAllowlistModal: () => void;
}

export function QuickActions({
  apps,
  workspaces,
  repos,
  auditLogs,
  isGenerating,
  onTriggerCommand,
  onAnalyzeClipboard,
  onSuggestCommit,
  onAnalyzeVision,
  onOpenAllowlistModal,
}: QuickActionsProps) {
  const [selectedRepo, setSelectedRepo] = useState<string>(
    repos[0]?.key || "x-assistant"
  );

  const handleClipboard = async () => {
    await toast.promise(onAnalyzeClipboard(), {
      loading: "Lendo Clipboard e acionando especialista x-coder...",
      success: "Análise de Clipboard concluída!",
      error: (err) =>
        `Erro ao analisar Clipboard: ${
          err instanceof Error ? err.message : String(err)
        }`,
    });
  };

  const handleCommit = async () => {
    const targetRepo = selectedRepo || repos[0]?.key || "x-assistant";
    await toast.promise(onSuggestCommit(targetRepo), {
      loading: `Lendo git diff de '${targetRepo}' e gerando Conventional Commit...`,
      success: "Sugestão de commit gerada no painel de chat!",
      error: (err) =>
        `Erro ao ler git diff: ${
          err instanceof Error ? err.message : String(err)
        }`,
    });
  };

  const handleVision = async () => {
    await toast.promise(onAnalyzeVision(), {
      loading:
        "Capturando contexto visual (Clipboard / Tela) e acionando x-vision...",
      success: "Inspeção visual concluída!",
      error: (err) =>
        `Erro na inspeção visual: ${
          err instanceof Error ? err.message : String(err)
        }`,
    });
  };

  const handleLaunchItem = async (key: string, label: string, needsConfirm: boolean) => {
    if (needsConfirm) {
      toast.info(`'${label}' requer confirmação de segurança`, {
        description: "Confirme a execução no alerta exibido no painel principal.",
      });
    } else {
      toast.success(`Acionando '${label}'...`);
    }
    await onTriggerCommand(`abrir ${key}`);
  };

  return (
    <div className="flex flex-col gap-4">
      {/* 1. Card de Ferramentas Copiloto Dev & Workspaces */}
      <Card className="border-border bg-card/90 shadow-sm">
        <CardHeader className="pb-3 pt-4 px-4 flex flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/15 text-primary">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-sm font-semibold tracking-tight">
                Copiloto Dev &amp; Automação
              </CardTitle>
              <p className="text-[11px] text-muted-foreground">
                Canal isolado anti-prompt injection + Allowlist
              </p>
            </div>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={onOpenAllowlistModal}
            className="h-7 gap-1.5 text-xs border-border bg-secondary/70 hover:bg-accent cursor-pointer"
          >
            <Settings2 className="h-3.5 w-3.5 text-primary" />
            <span>Allowlist</span>
          </Button>
        </CardHeader>

        <CardContent className="px-4 pb-4 space-y-4">
          {/* Ferramentas Dev (Clipboard, Git Commit, Print Visão) */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Ferramentas de Desenvolvedor
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    disabled={isGenerating}
                    onClick={() => void handleClipboard()}
                    className="h-auto py-2.5 px-3 flex flex-col items-start gap-1 border-border/80 bg-background/60 hover:bg-accent hover:border-primary/40 text-left cursor-pointer"
                  >
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                      <ClipboardCheck className="h-3.5 w-3.5 text-primary" />
                      <span>Smart Clipboard</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground">
                      Analisar erro/código (x-coder)
                    </span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs text-xs">
                  Lê o texto copiado no Clipboard por um canal puramente textual
                  (sem risco de executar comandos) e sugere correção via{" "}
                  <code>x-coder</code>.
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    disabled={isGenerating}
                    onClick={() => void handleCommit()}
                    className="h-auto py-2.5 px-3 flex flex-col items-start gap-1 border-border/80 bg-background/60 hover:bg-accent hover:border-primary/40 text-left cursor-pointer"
                  >
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                      <FolderGit2 className="h-3.5 w-3.5 text-primary" />
                      <span>Gerar Commit</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground truncate max-w-full">
                      Diff de {selectedRepo || "x-assistant"} (x-fast)
                    </span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs text-xs">
                  Inspeciona <code>git status</code> e <code>git diff</code> do
                  repositório monitorado e gera uma mensagem Conventional
                  Commits.
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    disabled={isGenerating}
                    onClick={() => void handleVision()}
                    className="h-auto py-2.5 px-3 flex flex-col items-start gap-1 border-border/80 bg-background/60 hover:bg-accent hover:border-primary/40 text-left cursor-pointer"
                  >
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                      <Camera className="h-3.5 w-3.5 text-primary" />
                      <span>Inspecionar Tela</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground">
                      Recorte ou Tela (x-vision)
                    </span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs text-xs">
                  Usa imagem do Clipboard (<code>Win+Shift+S</code>) ou captura
                  a tela inteira automaticamente para análise visual via{" "}
                  <code>x-vision</code>.
                </TooltipContent>
              </Tooltip>
            </div>

            {repos.length > 1 && (
              <div className="flex items-center gap-2 pt-1">
                <span className="text-[11px] text-muted-foreground">
                  Repositório Git alvo:
                </span>
                <select
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  className="rounded-md border border-border bg-background px-2 py-0.5 text-xs text-foreground"
                >
                  {repos.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.name} ({r.key})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Workspaces Compostos */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Workspaces Compostos ({workspaces.length})
              </span>
            </div>

            {workspaces.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border p-3 text-center text-xs text-muted-foreground">
                Nenhum workspace cadastrado. Clique em &quot;Allowlist&quot; para criar.
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-2">
                {workspaces.map((ws) => (
                  <div
                    key={ws.key}
                    className="group flex items-center justify-between gap-2 rounded-lg border border-border/70 bg-background/60 px-3 py-2 hover:border-primary/40 transition-colors"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <Layers className="h-3.5 w-3.5 text-primary shrink-0" />
                        <span className="text-xs font-semibold text-foreground truncate">
                          {ws.name}
                        </span>
                        <Badge
                          variant="outline"
                          className="text-[10px] px-1.5 py-0 h-4 font-mono"
                        >
                          {ws.steps.length} passos
                        </Badge>
                        {ws.requires_confirmation && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge
                                variant="outline"
                                className="text-[10px] px-1.5 py-0 h-4 border-warning/40 bg-warning/10 text-warning"
                              >
                                <Lock className="h-2.5 w-2.5 mr-0.5" />
                                Confirmação
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent className="text-xs">
                              Contém comando de terminal ou foi marcado como sensível.
                            </TooltipContent>
                          </Tooltip>
                        )}
                      </div>
                      <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                        {ws.description}
                      </p>
                    </div>

                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={isGenerating}
                      onClick={() =>
                        void handleLaunchItem(
                          ws.key,
                          ws.name,
                          ws.requires_confirmation
                        )
                      }
                      className="h-7 px-2.5 text-xs gap-1 shrink-0 cursor-pointer hover:bg-primary hover:text-primary-foreground"
                    >
                      <Play className="h-3 w-3" />
                      Iniciar
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Aplicativos da Allowlist */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Aplicativos Homologados ({apps.length})
            </span>
            <div className="flex flex-wrap gap-1.5">
              {apps.map((app) => (
                <Button
                  key={app.key}
                  variant="outline"
                  size="sm"
                  disabled={isGenerating}
                  onClick={() =>
                    void handleLaunchItem(
                      app.key,
                      app.name,
                      app.requires_confirmation
                    )
                  }
                  className="h-7 px-2.5 text-xs gap-1.5 border-border/80 bg-background/60 hover:bg-accent hover:border-primary/40 cursor-pointer"
                >
                  <Terminal className="h-3 w-3 text-primary" />
                  <span>{app.name}</span>
                  {app.requires_confirmation && (
                    <Lock className="h-2.5 w-2.5 text-warning" />
                  )}
                </Button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 2. Mini-Feed de Auditoria em Tempo Real */}
      <Card className="border-border bg-card/90 shadow-sm">
        <CardHeader className="pb-2.5 pt-3.5 px-4 flex flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Feed de Auditoria SQLite ({auditLogs.length})
            </CardTitle>
          </div>
        </CardHeader>

        <CardContent className="px-4 pb-3.5">
          {auditLogs.length === 0 ? (
            <div className="py-4 text-center text-xs text-muted-foreground">
              Nenhuma ação de sistema auditada até o momento.
            </div>
          ) : (
            <div className="max-h-36 overflow-y-auto space-y-1.5 pr-1">
              {auditLogs.slice(0, 12).map((log) => (
                <div
                  key={log.id}
                  className="flex items-center justify-between gap-2 rounded-md border border-border/60 bg-background/50 px-2.5 py-1.5 text-[11px]"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Badge
                      variant="outline"
                      className={`text-[9px] px-1.5 py-0 h-4 shrink-0 font-mono ${
                        log.status === "SUCCESS"
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : log.status === "BLOCKED" || log.status === "ERROR"
                          ? "border-destructive/40 bg-destructive/10 text-destructive"
                          : "border-warning/40 bg-warning/10 text-warning"
                      }`}
                    >
                      {log.status}
                    </Badge>
                    <span className="font-mono font-medium text-foreground truncate">
                      {log.action_type}:{log.target_key}
                    </span>
                    {log.details && (
                      <span className="text-muted-foreground truncate hidden sm:inline">
                        — {log.details}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] font-mono text-muted-foreground shrink-0">
                    {log.timestamp.split("T")[1] || log.timestamp}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

