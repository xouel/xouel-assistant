import { useState } from "react";
import {
  CheckCircle2,
  FolderGit2,
  Layers,
  Plus,
  ShieldAlert,
  Terminal,
  Trash2,
  XCircle,
  Edit3,
} from "lucide-react";
import { toast } from "sonner";
import type {
  AppEntry,
  GitRepoEntry,
  PendingConfirmation,
  StepType,
  WorkspaceEntry,
  WorkspaceStep,
} from "@/types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface AllowlistModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  apps: AppEntry[];
  workspaces: WorkspaceEntry[];
  repos: GitRepoEntry[];
  pendingConfirmations: PendingConfirmation[];
  onRequestMutation: (
    endpoint: string,
    method: "POST" | "DELETE",
    body?: unknown
  ) => Promise<PendingConfirmation | null>;
  onConfirmAction: (confirmationId: string, approved: boolean) => Promise<unknown>;
}

export function AllowlistModal({
  open,
  onOpenChange,
  apps,
  workspaces,
  repos,
  pendingConfirmations,
  onRequestMutation,
  onConfirmAction,
}: AllowlistModalProps) {
  // --- Estado do formulário de Aplicativo ---
  const [appKey, setAppKey] = useState("");
  const [appName, setAppName] = useState("");
  const [appPath, setAppPath] = useState("");
  const [appArgs, setAppArgs] = useState("");
  const [appConfirm, setAppConfirm] = useState(false);

  // --- Estado do formulário de Workspace ---
  const [wsKey, setWsKey] = useState("");
  const [wsName, setWsName] = useState("");
  const [wsDesc, setWsDesc] = useState("");
  const [wsConfirm, setWsConfirm] = useState(false);
  const [wsSteps, setWsSteps] = useState<WorkspaceStep[]>([
    { type: "app", target: "vscode", working_dir: null },
  ]);

  // --- Estado do formulário de Repositório Git ---
  const [repoKey, setRepoKey] = useState("");
  const [repoName, setRepoName] = useState("");
  const [repoPath, setRepoPath] = useState("");

  // Helpers para o formulário de Aplicativos
  const handleSubmitApp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!appKey.trim() || !appName.trim() || !appPath.trim()) {
      toast.warning("Preencha chave, nome e caminho do executável.");
      return;
    }

    const payload: AppEntry = {
      key: appKey.trim().toLowerCase(),
      name: appName.trim(),
      executable_path: appPath.trim(),
      args: appArgs.trim(),
      requires_confirmation: appConfirm,
    };

    try {
      const conf = await onRequestMutation("/api/allowlist/apps", "POST", payload);
      if (conf) {
        toast.info("Confirmação gerada pelo servidor", {
          description: `Aprove a alteração (${conf.confirmation_id.slice(0, 8)}...) no card acima para gravar no SQLite.`,
        });
      }
      setAppKey("");
      setAppName("");
      setAppPath("");
      setAppArgs("");
      setAppConfirm(false);
    } catch (err) {
      toast.error(
        `Erro ao solicitar cadastro: ${
          err instanceof Error ? err.message : String(err)
        }`
      );
    }
  };

  const handleDeleteApp = async (key: string) => {
    try {
      const conf = await onRequestMutation(
        `/api/allowlist/apps/${encodeURIComponent(key)}`,
        "DELETE"
      );
      if (conf) {
        toast.info(`Confirme a remoção de '${key}' no card de segurança.`);
      }
    } catch (err) {
      toast.error(
        `Erro ao solicitar exclusão: ${
          err instanceof Error ? err.message : String(err)
        }`
      );
    }
  };

  // Helpers para o formulário de Workspaces
  const handleAddStep = () => {
    setWsSteps((prev) => [
      ...prev,
      { type: "app", target: "terminal", working_dir: null },
    ]);
  };

  const handleUpdateStep = (
    index: number,
    field: keyof WorkspaceStep,
    value: string
  ) => {
    setWsSteps((prev) =>
      prev.map((step, idx) =>
        idx === index
          ? {
              ...step,
              [field]:
                field === "working_dir" ? (value.trim() ? value : null) : value,
            }
          : step
      )
    );
  };

  const handleRemoveStep = (index: number) => {
    setWsSteps((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleSubmitWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!wsKey.trim() || !wsName.trim() || wsSteps.length === 0) {
      toast.warning("Preencha chave, nome e pelo menos 1 passo.");
      return;
    }

    const payload: WorkspaceEntry = {
      key: wsKey.trim().toLowerCase(),
      name: wsName.trim(),
      description: wsDesc.trim(),
      requires_confirmation:
        wsConfirm || wsSteps.some((s) => s.type === "terminal_cmd"),
      steps: wsSteps,
    };

    try {
      const conf = await onRequestMutation(
        "/api/allowlist/workspaces",
        "POST",
        payload
      );
      if (conf) {
        toast.info("Confirmação gerada pelo servidor", {
          description: "Aprove o cadastro do workspace no card de confirmação.",
        });
      }
      setWsKey("");
      setWsName("");
      setWsDesc("");
      setWsConfirm(false);
    } catch (err) {
      toast.error(
        `Erro ao solicitar workspace: ${
          err instanceof Error ? err.message : String(err)
        }`
      );
    }
  };

  const handleDeleteWorkspace = async (key: string) => {
    try {
      const conf = await onRequestMutation(
        `/api/allowlist/workspaces/${encodeURIComponent(key)}`,
        "DELETE"
      );
      if (conf) {
        toast.info(`Confirme a remoção do workspace '${key}' acima.`);
      }
    } catch (err) {
      toast.error(
        `Erro ao solicitar exclusão: ${
          err instanceof Error ? err.message : String(err)
        }`
      );
    }
  };

  // Helpers para o formulário de Repositórios Git
  const handleSubmitRepo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoKey.trim() || !repoName.trim() || !repoPath.trim()) {
      toast.warning("Preencha chave, nome e caminho absoluto do repositório.");
      return;
    }

    const payload: GitRepoEntry = {
      key: repoKey.trim().toLowerCase(),
      name: repoName.trim(),
      repo_path: repoPath.trim(),
    };

    try {
      const conf = await onRequestMutation("/api/allowlist/repos", "POST", payload);
      if (conf) {
        toast.info("Confirmação gerada pelo servidor", {
          description: "Aprove o cadastro do repositório no card de confirmação.",
        });
      }
      setRepoKey("");
      setRepoName("");
      setRepoPath("");
    } catch (err) {
      toast.error(
        `Erro ao solicitar repositório: ${
          err instanceof Error ? err.message : String(err)
        }`
      );
    }
  };

  const handleDeleteRepo = async (key: string) => {
    try {
      const conf = await onRequestMutation(
        `/api/allowlist/repos/${encodeURIComponent(key)}`,
        "DELETE"
      );
      if (conf) {
        toast.info(`Confirme a remoção do repositório '${key}' acima.`);
      }
    } catch (err) {
      toast.error(
        `Erro ao solicitar exclusão: ${
          err instanceof Error ? err.message : String(err)
        }`
      );
    }
  };

  const handleResolveConfirmation = async (id: string, approved: boolean) => {
    await toast.promise(onConfirmAction(id, approved), {
      loading: approved
        ? "Aplicando alteração na Allowlist (SQLite)..."
        : "Cancelando alteração...",
      success: approved
        ? "Allowlist atualizada e auditada com sucesso!"
        : "Alteração cancelada.",
      error: (err) =>
        `Erro ao resolver confirmação: ${
          err instanceof Error ? err.message : String(err)
        }`,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[88vh] overflow-y-auto bg-card border-border text-foreground">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold">
            Gerenciador de Allowlist &amp; Workspaces (SQLite)
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Toda adição, edição ou exclusão gera um token de confirmação de uso
            único no servidor antes de alterar o banco de dados.
          </DialogDescription>
        </DialogHeader>

        {/* Cards de Confirmação Pendentes dentro do Modal */}
        {pendingConfirmations.length > 0 && (
          <div className="space-y-2 my-1">
            {pendingConfirmations.map((conf) => (
              <div
                key={conf.confirmation_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/50 bg-warning/10 p-3"
              >
                <div className="flex items-start gap-2.5 min-w-0">
                  <ShieldAlert className="h-4 w-4 text-warning shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                      <span>Confirmação de Segurança</span>
                      <Badge
                        variant="outline"
                        className="text-[10px] px-1.5 py-0 h-4 font-mono border-warning/40 text-warning"
                      >
                        ID: {conf.confirmation_id.slice(0, 10)}...
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {conf.reply}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <Button
                    size="sm"
                    onClick={() =>
                      void handleResolveConfirmation(conf.confirmation_id, true)
                    }
                    className="h-7 px-2.5 text-xs gap-1 bg-primary text-primary-foreground cursor-pointer"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Aprovar
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void handleResolveConfirmation(
                        conf.confirmation_id,
                        false
                      )
                    }
                    className="h-7 px-2.5 text-xs gap-1 border-border hover:bg-destructive/15 hover:text-destructive cursor-pointer"
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    Cancelar
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        <Tabs defaultValue="apps" className="w-full">
          <TabsList className="grid w-full grid-cols-3 bg-background/80 border border-border">
            <TabsTrigger value="apps" className="text-xs gap-1.5 cursor-pointer">
              <Terminal className="h-3.5 w-3.5" />
              Apps ({apps.length})
            </TabsTrigger>
            <TabsTrigger
              value="workspaces"
              className="text-xs gap-1.5 cursor-pointer"
            >
              <Layers className="h-3.5 w-3.5" />
              Workspaces ({workspaces.length})
            </TabsTrigger>
            <TabsTrigger value="repos" className="text-xs gap-1.5 cursor-pointer">
              <FolderGit2 className="h-3.5 w-3.5" />
              Git Repos ({repos.length})
            </TabsTrigger>
          </TabsList>

          {/* ABA 1: APLICATIVOS */}
          <TabsContent value="apps" className="space-y-4 pt-3">
            <form
              onSubmit={(e) => void handleSubmitApp(e)}
              className="rounded-xl border border-border bg-background/50 p-3.5 space-y-3"
            >
              <div className="text-xs font-semibold text-foreground">
                Adicionar / Atualizar Aplicativo
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <div className="space-y-1">
                  <label className="text-[11px] text-muted-foreground">
                    Chave única (sem espaços)
                  </label>
                  <Input
                    value={appKey}
                    onChange={(e) => setAppKey(e.target.value)}
                    placeholder="ex: postman"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] text-muted-foreground">
                    Nome amigável
                  </label>
                  <Input
                    value={appName}
                    onChange={(e) => setAppName(e.target.value)}
                    placeholder="ex: Postman API Client"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <label className="text-[11px] text-muted-foreground">
                    Caminho do Executável
                  </label>
                  <Input
                    value={appPath}
                    onChange={(e) => setAppPath(e.target.value)}
                    placeholder="ex: %LOCALAPPDATA%\Postman\Postman.exe"
                    className="h-8 text-xs font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] text-muted-foreground">
                    Argumentos opcionais
                  </label>
                  <Input
                    value={appArgs}
                    onChange={(e) => setAppArgs(e.target.value)}
                    placeholder="ex: --disable-gpu"
                    className="h-8 text-xs font-mono"
                  />
                </div>
                <div className="flex items-center justify-between pt-4 px-1">
                  <label className="text-xs text-muted-foreground">
                    Exigir confirmação ao abrir
                  </label>
                  <Switch
                    checked={appConfirm}
                    onCheckedChange={setAppConfirm}
                  />
                </div>
              </div>
              <Button
                type="submit"
                size="sm"
                className="h-8 text-xs gap-1.5 cursor-pointer"
              >
                <Plus className="h-3.5 w-3.5" />
                Solicitar Cadastro / Atualização
              </Button>
            </form>

            <div className="space-y-2">
              {apps.map((app) => (
                <div
                  key={app.key}
                  className="flex items-center justify-between gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground">
                        {app.name}
                      </span>
                      <Badge
                        variant="outline"
                        className="font-mono text-[10px] px-1.5 py-0 h-4 text-primary"
                      >
                        {app.key}
                      </Badge>
                      {app.requires_confirmation && (
                        <Badge
                          variant="outline"
                          className="text-[10px] px-1.5 py-0 h-4 border-warning/40 text-warning"
                        >
                          Sensível
                        </Badge>
                      )}
                    </div>
                    <div className="text-[11px] font-mono text-muted-foreground truncate mt-0.5">
                      {app.executable_path} {app.args}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setAppKey(app.key);
                        setAppName(app.name);
                        setAppPath(app.executable_path);
                        setAppArgs(app.args);
                        setAppConfirm(app.requires_confirmation);
                      }}
                      className="h-7 px-2 text-xs cursor-pointer"
                    >
                      <Edit3 className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void handleDeleteApp(app.key)}
                      className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive cursor-pointer"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </TabsContent>

          {/* ABA 2: WORKSPACES COMPOSTOS */}
          <TabsContent value="workspaces" className="space-y-4 pt-3">
            <form
              onSubmit={(e) => void handleSubmitWorkspace(e)}
              className="rounded-xl border border-border bg-background/50 p-3.5 space-y-3"
            >
              <div className="text-xs font-semibold text-foreground">
                Adicionar / Atualizar Workspace Composto
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <div className="space-y-1">
                  <label className="text-[11px] text-muted-foreground">
                    Chave do Workspace
                  </label>
                  <Input
                    value={wsKey}
                    onChange={(e) => setWsKey(e.target.value)}
                    placeholder="ex: dev_fullstack"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] text-muted-foreground">
                    Nome do Workspace
                  </label>
                  <Input
                    value={wsName}
                    onChange={(e) => setWsName(e.target.value)}
                    placeholder="ex: Ambiente Fullstack"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <label className="text-[11px] text-muted-foreground">
                    Descrição
                  </label>
                  <Input
                    value={wsDesc}
                    onChange={(e) => setWsDesc(e.target.value)}
                    placeholder="Abre editor, terminal e documentação..."
                    className="h-8 text-xs"
                  />
                </div>
              </div>

              {/* Passos do Workspace */}
              <div className="space-y-2 pt-1">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-muted-foreground">
                    Passos Sequenciais ({wsSteps.length})
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleAddStep}
                    className="h-6 px-2 text-[11px] gap-1 cursor-pointer"
                  >
                    <Plus className="h-3 w-3" />
                    Passo
                  </Button>
                </div>

                {wsSteps.map((step, idx) => (
                  <div
                    key={idx}
                    className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-center rounded-lg border border-border/70 bg-card p-2"
                  >
                    <div className="sm:col-span-4">
                      <Select
                        value={step.type}
                        onValueChange={(val) =>
                          handleUpdateStep(idx, "type", val as StepType)
                        }
                      >
                        <SelectTrigger className="h-7 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="app">Aplicativo (key)</SelectItem>
                          <SelectItem value="url">URL (http/https)</SelectItem>
                          <SelectItem value="vscode_project">
                            Pasta no VS Code
                          </SelectItem>
                          <SelectItem value="terminal_cmd">
                            Comando Terminal
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="sm:col-span-7">
                      <Input
                        value={step.target}
                        onChange={(e) =>
                          handleUpdateStep(idx, "target", e.target.value)
                        }
                        placeholder="Alvo (ex: vscode, http://localhost:5173, git status)"
                        className="h-7 text-xs font-mono"
                      />
                    </div>
                    <div className="sm:col-span-1 flex justify-end">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={wsSteps.length <= 1}
                        onClick={() => handleRemoveStep(idx)}
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive cursor-pointer"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between pt-1">
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Switch
                    checked={wsConfirm}
                    onCheckedChange={setWsConfirm}
                  />
                  <span>Exigir confirmação antes de executar</span>
                </label>

                <Button
                  type="submit"
                  size="sm"
                  className="h-8 text-xs gap-1.5 cursor-pointer"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Solicitar Salvamento
                </Button>
              </div>
            </form>

            <div className="space-y-2">
              {workspaces.map((ws) => (
                <div
                  key={ws.key}
                  className="flex items-center justify-between gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground">
                        {ws.name}
                      </span>
                      <Badge
                        variant="outline"
                        className="font-mono text-[10px] px-1.5 py-0 h-4 text-primary"
                      >
                        {ws.key}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground">
                        ({ws.steps.length} passos)
                      </span>
                    </div>
                    <div className="text-[11px] text-muted-foreground truncate mt-0.5">
                      {ws.description}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setWsKey(ws.key);
                        setWsName(ws.name);
                        setWsDesc(ws.description);
                        setWsConfirm(ws.requires_confirmation);
                        setWsSteps(ws.steps);
                      }}
                      className="h-7 px-2 text-xs cursor-pointer"
                    >
                      <Edit3 className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void handleDeleteWorkspace(ws.key)}
                      className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive cursor-pointer"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </TabsContent>

          {/* ABA 3: REPOSITÓRIOS GIT MONITORADOS */}
          <TabsContent value="repos" className="space-y-4 pt-3">
            <form
              onSubmit={(e) => void handleSubmitRepo(e)}
              className="rounded-xl border border-border bg-background/50 p-3.5 space-y-3"
            >
              <div className="text-xs font-semibold text-foreground">
                Adicionar / Atualizar Repositório Git
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <div className="space-y-1">
                  <label className="text-[11px] text-muted-foreground">
                    Chave do Repositório
                  </label>
                  <Input
                    value={repoKey}
                    onChange={(e) => setRepoKey(e.target.value)}
                    placeholder="ex: meu-saas"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] text-muted-foreground">
                    Nome do Repositório
                  </label>
                  <Input
                    value={repoName}
                    onChange={(e) => setRepoName(e.target.value)}
                    placeholder="ex: Repositório Meu SaaS"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <label className="text-[11px] text-muted-foreground">
                    Caminho Absoluto no Disco
                  </label>
                  <Input
                    value={repoPath}
                    onChange={(e) => setRepoPath(e.target.value)}
                    placeholder="ex: C:\Users\xouel\Projetos\meu-saas"
                    className="h-8 text-xs font-mono"
                  />
                </div>
              </div>
              <Button
                type="submit"
                size="sm"
                className="h-8 text-xs gap-1.5 cursor-pointer"
              >
                <Plus className="h-3.5 w-3.5" />
                Solicitar Monitoramento
              </Button>
            </form>

            <div className="space-y-2">
              {repos.map((repo) => (
                <div
                  key={repo.key}
                  className="flex items-center justify-between gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground">
                        {repo.name}
                      </span>
                      <Badge
                        variant="outline"
                        className="font-mono text-[10px] px-1.5 py-0 h-4 text-primary"
                      >
                        {repo.key}
                      </Badge>
                    </div>
                    <div className="text-[11px] font-mono text-muted-foreground truncate mt-0.5">
                      {repo.repo_path}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setRepoKey(repo.key);
                        setRepoName(repo.name);
                        setRepoPath(repo.repo_path);
                      }}
                      className="h-7 px-2 text-xs cursor-pointer"
                    >
                      <Edit3 className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void handleDeleteRepo(repo.key)}
                      className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive cursor-pointer"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

