import { useState, useRef, useEffect, useCallback } from "react";
import {
  AlertTriangle,
  Bot,
  Check,
  CheckCircle2,
  Copy,
  Eraser,
  Loader2,
  Mic,
  MicOff,
  Send,
  ShieldAlert,
  Sparkles,
  User,
  Volume2,
  VolumeX,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import type {
  ChatMessage,
  ModelMode,
  PendingConfirmation,
} from "@/types";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface ChatPanelProps {
  mode: ModelMode;
  onSelectMode: (mode: ModelMode) => void;
  speakReply: boolean;
  onToggleSpeakReply: (enabled: boolean) => void;
  messages: ChatMessage[];
  isGenerating: boolean;
  lastError: string | null;
  pendingConfirmations: PendingConfirmation[];
  onSendMessage: (
    prompt: string,
    options?: { mode?: ModelMode; speak?: boolean; stream?: boolean }
  ) => Promise<void>;
  onConfirmAction: (confirmationId: string, approved: boolean) => Promise<unknown>;
  onClearHistory: () => Promise<void>;
  onTranscribeAudio: (blob: Blob) => Promise<string>;
}

/**
 * Renderiza texto com suporte a blocos de código (```lang ... ```) copiáveis em 1 clique.
 */
function FormattedMessageContent({ content }: { content: string }) {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const handleCopyCode = async (code: string, idx: number) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedIndex(idx);
      toast.success("Código copiado para a área de transferência!");
      window.setTimeout(() => setCopiedIndex(null), 1800);
    } catch {
      toast.error("Não foi possível copiar o código.");
    }
  };

  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-2 text-xs leading-relaxed break-words">
      {parts.map((part, idx) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          const inner = part.slice(3, -3).trim();
          const firstNewline = inner.indexOf("\n");
          let lang = "code";
          let codeBody = inner;
          if (firstNewline !== -1) {
            const firstLine = inner.slice(0, firstNewline).trim();
            if (/^[a-zA-Z0-9_-]+$/.test(firstLine)) {
              lang = firstLine;
              codeBody = inner.slice(firstNewline + 1);
            }
          }

          return (
            <div
              key={idx}
              className="rounded-lg border border-border bg-background/90 overflow-hidden my-1.5"
            >
              <div className="flex items-center justify-between px-3 py-1.5 bg-secondary/70 border-b border-border text-[10px] font-mono text-muted-foreground">
                <span className="uppercase">{lang}</span>
                <button
                  type="button"
                  onClick={() => void handleCopyCode(codeBody, idx)}
                  className="inline-flex items-center gap-1 text-foreground hover:text-primary transition-colors cursor-pointer"
                >
                  {copiedIndex === idx ? (
                    <>
                      <Check className="h-3 w-3 text-primary" />
                      <span className="text-primary">Copiado</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" />
                      <span>Copiar</span>
                    </>
                  )}
                </button>
              </div>
              <pre className="p-3 overflow-x-auto font-mono text-[11px] text-foreground">
                <code>{codeBody}</code>
              </pre>
            </div>
          );
        }

        if (!part.trim()) return null;
        return (
          <p key={idx} className="whitespace-pre-wrap">
            {part}
          </p>
        );
      })}
    </div>
  );
}

export function ChatPanel({
  mode,
  onSelectMode,
  speakReply,
  onToggleSpeakReply,
  messages,
  isGenerating,
  lastError,
  pendingConfirmations,
  onSendMessage,
  onConfirmAction,
  onClearHistory,
  onTranscribeAudio,
}: ChatPanelProps) {
  const [promptInput, setPromptInput] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [micPermissionError, setMicPermissionError] = useState<string | null>(
    null
  );

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const isRecordingRef = useRef<boolean>(false);

  // Scroll automático suave para a última mensagem
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingConfirmations]);

  // ==========================================================================
  // PUSH-TO-TALK (MEDIARECORDER: BOTÃO SEGURAR OU CTRL + ESPAÇO)
  // ==========================================================================

  const stopRecordingTracks = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (isRecordingRef.current || isTranscribing) return;
    setMicPermissionError(null);

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMicPermissionError(
        "Seu navegador não suporta captura de áudio (MediaDevices indisponível)."
      );
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      audioChunksRef.current = [];

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        stopRecordingTracks();
        isRecordingRef.current = false;
        setIsRecording(false);

        const chunks = audioChunksRef.current;
        if (chunks.length === 0) return;

        const audioBlob = new Blob(chunks, {
          type: recorder.mimeType || "audio/webm",
        });
        if (audioBlob.size < 400) {
          return;
        }

        setIsTranscribing(true);
        try {
          const text = await onTranscribeAudio(audioBlob);
          if (text.trim()) {
            setPromptInput((prev) =>
              prev.trim() ? `${prev.trim()} ${text.trim()}` : text.trim()
            );
            toast.success("Voz transcrita via Faster-Whisper!");
            inputRef.current?.focus();
          } else {
            toast.info("Nenhuma fala detectada na gravação.");
          }
        } catch (err) {
          toast.error(
            `Falha na transcrição: ${
              err instanceof Error ? err.message : String(err)
            }`
          );
        } finally {
          setIsTranscribing(false);
        }
      };

      mediaRecorderRef.current = recorder;
      isRecordingRef.current = true;
      setIsRecording(true);
      recorder.start();
    } catch (err) {
      stopRecordingTracks();
      isRecordingRef.current = false;
      setIsRecording(false);
      const msg = err instanceof Error ? err.message : String(err);
      setMicPermissionError(
        `Acesso ao microfone negado (${msg}). Clique no ícone de cadeado na barra do navegador/Edge e permita o uso do Microfone.`
      );
      toast.error("Microfone bloqueado pelo navegador.");
    }
  }, [isTranscribing, onTranscribeAudio, stopRecordingTracks]);

  const stopRecording = useCallback(() => {
    if (!isRecordingRef.current) return;
    try {
      if (
        mediaRecorderRef.current &&
        mediaRecorderRef.current.state !== "inactive"
      ) {
        mediaRecorderRef.current.stop();
      } else {
        stopRecordingTracks();
        isRecordingRef.current = false;
        setIsRecording(false);
      }
    } catch {
      stopRecordingTracks();
      isRecordingRef.current = false;
      setIsRecording(false);
    }
  }, [stopRecordingTracks]);

  // Atalho de teclado global na janela: Segurar Ctrl + Espaço para Push-to-Talk
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.code === "Space" && !e.repeat) {
        e.preventDefault();
        void startRecording();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space" && isRecordingRef.current) {
        e.preventDefault();
        stopRecording();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [startRecording, stopRecording]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const clean = promptInput.trim();
    if (!clean || isGenerating) return;
    setPromptInput("");
    await onSendMessage(clean, { mode, speak: speakReply, stream: true });
  };

  const handleConfirm = async (id: string, approved: boolean) => {
    await toast.promise(onConfirmAction(id, approved), {
      loading: approved
        ? "Confirmando e executando ação..."
        : "Cancelando solicitação...",
      success: approved ? "Ação autorizada e executada!" : "Ação cancelada.",
      error: (err) =>
        `Erro ao resolver confirmação: ${
          err instanceof Error ? err.message : String(err)
        }`,
    });
  };

  return (
    <Card className="border-border bg-card/90 shadow-sm flex flex-col h-full min-h-[540px]">
      {/* Top Bar: Seletor de Modelos (3B/7B/4B), Switch TTS e Limpar Histórico */}
      <CardHeader className="py-3 px-4 border-b border-border flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <div className="flex items-center gap-2">
          <ToggleGroup
            type="single"
            value={mode}
            onValueChange={(val) => {
              if (val) onSelectMode(val as ModelMode);
            }}
            className="bg-background/80 p-0.5 rounded-lg border border-border"
          >
            <ToggleGroupItem
              value="x-fast"
              aria-label="Modelo rápido 3B"
              className="h-7 px-2.5 text-xs data-[state=on]:bg-primary data-[state=on]:text-primary-foreground cursor-pointer"
            >
              x-fast (3B)
            </ToggleGroupItem>
            <ToggleGroupItem
              value="x-coder"
              aria-label="Modelo especialista em código 7B"
              className="h-7 px-2.5 text-xs data-[state=on]:bg-primary data-[state=on]:text-primary-foreground cursor-pointer"
            >
              x-coder (7B)
            </ToggleGroupItem>
            <ToggleGroupItem
              value="x-vision"
              aria-label="Modelo multimodal de visão 4B"
              className="h-7 px-2.5 text-xs data-[state=on]:bg-primary data-[state=on]:text-primary-foreground cursor-pointer"
            >
              x-vision (4B)
            </ToggleGroupItem>
          </ToggleGroup>
        </div>

        <div className="flex items-center gap-3">
          {/* Switch de Voz Offline SAPI5 */}
          <Tooltip>
            <TooltipTrigger asChild>
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
                {speakReply ? (
                  <Volume2 className="h-3.5 w-3.5 text-primary" />
                ) : (
                  <VolumeX className="h-3.5 w-3.5" />
                )}
                <span>Voz SAPI5</span>
                <Switch
                  checked={speakReply}
                  onCheckedChange={onToggleSpeakReply}
                  aria-label="Ativar resposta falada offline via SAPI5"
                />
              </label>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-xs">
              Fala respostas curtas usando o sintetizador nativo Microsoft Maria
              (SAPI5) com custo zero de RAM.
            </TooltipContent>
          </Tooltip>

          {/* Limpar Histórico */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  void onClearHistory().then(() =>
                    toast.success("Histórico de chat limpo.")
                  );
                }}
                className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <Eraser className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent className="text-xs">
              Limpar histórico de conversas
            </TooltipContent>
          </Tooltip>
        </div>
      </CardHeader>

      {/* Banners de Erro (Ollama Offline / Modelo Ausente / Microfone Negado) */}
      {(lastError || micPermissionError) && (
        <div className="px-4 pt-3 space-y-2">
          {lastError && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-2.5 text-xs text-destructive">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <div className="font-semibold">Aviso do Motor Local</div>
                <div>{lastError}</div>
              </div>
            </div>
          )}
          {micPermissionError && (
            <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-2.5 text-xs text-warning">
              <MicOff className="h-4 w-4 shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <div className="font-semibold">Permissão de Microfone</div>
                <div>{micPermissionError}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Cards de Confirmação de Segurança Pendentes (ID Único Servidor) */}
      {pendingConfirmations.length > 0 && (
        <div className="px-4 pt-3 space-y-2">
          {pendingConfirmations.map((conf) => (
            <div
              key={conf.confirmation_id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/50 bg-warning/10 p-3"
            >
              <div className="flex items-start gap-2.5 min-w-0">
                <ShieldAlert className="h-4 w-4 text-warning shrink-0 mt-0.5" />
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <span>Confirmação Exigida</span>
                    <Badge
                      variant="outline"
                      className="text-[10px] px-1.5 py-0 h-4 font-mono border-warning/40 text-warning"
                    >
                      {conf.intent}:{conf.target}
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
                  onClick={() => void handleConfirm(conf.confirmation_id, true)}
                  className="h-7 px-2.5 text-xs gap-1 bg-primary text-primary-foreground hover:opacity-90 cursor-pointer"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Aprovar
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    void handleConfirm(conf.confirmation_id, false)
                  }
                  className="h-7 px-2.5 text-xs gap-1 border-border hover:bg-destructive/15 hover:text-destructive cursor-pointer"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  Recusar
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Área de Mensagens do Chat */}
      <CardContent className="flex-1 overflow-y-auto p-4 space-y-3 max-h-[420px]">
        {messages.length === 0 ? (
          <div className="h-full min-h-[260px] flex flex-col items-center justify-center text-center space-y-3 px-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Sparkles className="h-5 w-5" />
            </div>
            <div className="space-y-1 max-w-md">
              <h3 className="text-sm font-semibold text-foreground">
                Pronto para Comandos Locais e Copiloto Dev
              </h3>
              <p className="text-xs text-muted-foreground">
                Digite um comando, use os atalhos rápidos abaixo ou segure{" "}
                <kbd className="rounded border border-border bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
                  Ctrl + Espaço
                </kbd>{" "}
                para falar via Push-to-Talk.
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-1.5 pt-1">
              {[
                "abrir calc",
                "abrir taskmgr",
                "iniciar dev_web",
                "liberar ram",
                "Explique em 3 linhas como funciona o WAL no SQLite",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() =>
                    void onSendMessage(suggestion, {
                      mode,
                      speak: speakReply,
                      stream: true,
                    })
                  }
                  className="rounded-full border border-border bg-secondary/70 hover:bg-accent hover:border-primary/40 px-3 py-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => {
            const isUser = msg.role === "user";
            return (
              <div
                key={msg.id}
                className={`flex gap-2.5 ${
                  isUser ? "justify-end" : "justify-start"
                }`}
              >
                {!isUser && (
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary mt-0.5">
                    <Bot className="h-4 w-4" />
                  </div>
                )}

                <div
                  className={`max-w-[85%] rounded-xl px-3.5 py-2.5 border ${
                    isUser
                      ? "bg-primary/15 border-primary/30 text-foreground"
                      : "bg-background/80 border-border text-foreground"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3 mb-1 text-[10px] text-muted-foreground">
                    <span className="font-semibold uppercase tracking-wider">
                      {isUser ? "Você" : `X-Assistant • ${msg.model_used}`}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {msg.intent && msg.intent !== "chat_response" && (
                        <Badge
                          variant="outline"
                          className="text-[9px] px-1 py-0 h-3.5 font-mono"
                        >
                          {msg.intent}
                        </Badge>
                      )}
                      {msg.isStreaming && (
                        <span className="inline-flex items-center gap-1 text-primary font-medium">
                          <Loader2 className="h-2.5 w-2.5 animate-spin" />
                          gerando...
                        </span>
                      )}
                    </div>
                  </div>

                  <FormattedMessageContent content={msg.content} />
                </div>

                {isUser && (
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-secondary text-foreground mt-0.5">
                    <User className="h-4 w-4" />
                  </div>
                )}
              </div>
            );
          })
        )}
        <div ref={messagesEndRef} />
      </CardContent>

      {/* Barra de Input + Push-to-Talk (Segurar Botão ou Ctrl + Espaço) */}
      <div className="p-3 border-t border-border bg-background/40">
        <form onSubmit={(e) => void handleSubmit(e)} className="flex items-center gap-2">
          {/* Botão Push-to-Talk */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant={isRecording ? "default" : "outline"}
                size="sm"
                disabled={isTranscribing}
                onMouseDown={() => void startRecording()}
                onMouseUp={stopRecording}
                onMouseLeave={() => {
                  if (isRecording) stopRecording();
                }}
                onTouchStart={(e) => {
                  e.preventDefault();
                  void startRecording();
                }}
                onTouchEnd={(e) => {
                  e.preventDefault();
                  stopRecording();
                }}
                className={`h-9 px-3 gap-1.5 text-xs shrink-0 select-none cursor-pointer ${
                  isRecording
                    ? "bg-destructive text-destructive-foreground animate-pulse"
                    : "border-border bg-secondary/70 hover:bg-accent"
                }`}
              >
                {isTranscribing ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                    <span className="hidden sm:inline">Transcrevendo...</span>
                  </>
                ) : isRecording ? (
                  <>
                    <Mic className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">Ouvindo (Solte)...</span>
                  </>
                ) : (
                  <>
                    <Mic className="h-3.5 w-3.5 text-primary" />
                    <span className="hidden sm:inline">PTT</span>
                  </>
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-xs">
              <strong>Push-to-Talk Offline (Faster-Whisper)</strong>: Mantenha
              este botão pressionado (ou segure <code>Ctrl + Espaço</code>)
              enquanto fala e solte para transcrever.
            </TooltipContent>
          </Tooltip>

          <input
            ref={inputRef}
            type="text"
            value={promptInput}
            onChange={(e) => setPromptInput(e.target.value)}
            placeholder={
              isRecording
                ? "Gravando áudio... Solte para transcrever no campo"
                : `Comando ou pergunta para ${mode}... (Segure Ctrl+Espaço para falar)`
            }
            className="flex-1 h-9 rounded-lg border border-input bg-background px-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />

          <Button
            type="submit"
            size="sm"
            disabled={isGenerating || !promptInput.trim()}
            className="h-9 px-4 gap-1.5 text-xs font-semibold cursor-pointer"
          >
            {isGenerating ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
            <span>Enviar</span>
          </Button>
        </form>
      </div>
    </Card>
  );
}

