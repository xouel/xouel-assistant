import { useState } from "react";
import {
  Activity,
  Cpu,
  HardDrive,
  Info,
  Layers,
  Trash2,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import type { SystemTelemetry } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface TelemetryCardProps {
  telemetry: SystemTelemetry | null;
  lastTelemetryAt: string | null;
  onFreeMemory: () => Promise<unknown>;
}

export function TelemetryCard({
  telemetry,
  lastTelemetryAt,
  onFreeMemory,
}: TelemetryCardProps) {
  const [isUnloading, setIsUnloading] = useState(false);

  const handleEjectRam = async () => {
    if (isUnloading) return;
    setIsUnloading(true);
    try {
      await toast.promise(onFreeMemory(), {
        loading: "Ejetando modelos do Ollama e Whisper da RAM...",
        success: "Memória RAM liberada com sucesso (0 MB em modelos).",
        error: (err) =>
          `Falha ao liberar memória: ${
            err instanceof Error ? err.message : String(err)
          }`,
      });
    } finally {
      setIsUnloading(false);
    }
  };

  const hasActiveModel =
    telemetry && telemetry.active_models && telemetry.active_models.length > 0;

  return (
    <Card className="border-border bg-card/90 shadow-sm">
      <CardHeader className="pb-3 pt-4 px-4 flex flex-row items-center justify-between space-y-0">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/15 text-primary">
            <Activity className="h-4 w-4" />
          </div>
          <div>
            <CardTitle className="text-sm font-semibold tracking-tight">
              Telemetria de Hardware
            </CardTitle>
            <p className="text-[11px] text-muted-foreground">
              {lastTelemetryAt
                ? `Pulso em tempo real • ${lastTelemetryAt}`
                : "Aguardando pulso /ws..."}
            </p>
          </div>
        </div>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              disabled={isUnloading}
              onClick={() => void handleEjectRam()}
              className="h-7 gap-1.5 text-xs border-border bg-secondary/70 hover:bg-destructive/15 hover:text-destructive hover:border-destructive/40 cursor-pointer"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>{isUnloading ? "Ejetando..." : "Ejetar RAM"}</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="max-w-xs text-xs">
            Envia <code>keep_alive=0</code> ao Ollama e descarrega o modelo
            Whisper da CPU para devolver toda a memória ao Windows.
          </TooltipContent>
        </Tooltip>
      </CardHeader>

      <CardContent className="px-4 pb-4 space-y-3.5">
        {!telemetry ? (
          <div className="space-y-3 py-2 animate-pulse">
            <div className="h-12 rounded-lg bg-secondary/60" />
            <div className="h-12 rounded-lg bg-secondary/60" />
            <div className="h-12 rounded-lg bg-secondary/60" />
          </div>
        ) : (
          <>
            {/* 1. CPU i3-1215U */}
            <div className="rounded-lg border border-border/70 bg-background/60 p-3 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 font-medium text-foreground">
                  <Cpu className="h-3.5 w-3.5 text-primary" />
                  Intel Core i3-1215U
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        aria-label="Informações sobre a topologia da CPU"
                        className="text-muted-foreground hover:text-foreground cursor-help"
                      >
                        <Info className="h-3 w-3" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs text-xs">
                      Arquitetura híbrida (2 P-Cores / 4T + 4 E-Cores). Os
                      Modelfiles usam <code>num_thread 4</code> fixo nos P-Cores
                      para máxima taxa de tokens/s sem gargalo de sincronização.
                    </TooltipContent>
                  </Tooltip>
                </span>
                <span className="font-mono font-semibold text-foreground">
                  {telemetry.cpu_percent.toFixed(1)}%
                </span>
              </div>
              <Progress value={Math.min(telemetry.cpu_percent, 100)} className="h-1.5" />
            </div>

            {/* 2. RAM 20 GB Flex Mode */}
            <div className="rounded-lg border border-border/70 bg-background/60 p-3 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 font-medium text-foreground">
                  <HardDrive className="h-3.5 w-3.5 text-primary" />
                  RAM ({telemetry.ram_used_gb.toFixed(1)} /{" "}
                  {telemetry.ram_total_gb.toFixed(1)} GB)
                </span>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge
                      variant="outline"
                      className={`text-[10px] px-1.5 py-0 h-5 cursor-help ${
                        telemetry.is_dual_channel
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : "border-warning/40 bg-warning/10 text-warning"
                      }`}
                    >
                      {telemetry.is_dual_channel ? "Dual-Channel" : "Flex Mode"}
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs text-xs">
                    <strong>{telemetry.memory_mode_label}</strong>: Os primeiros
                    ~8.5 GB operam em Dual-Channel simétrico (128-bit). Manter
                    apenas 1 modelo ativo na RAM preserva a largura de banda de
                    memória.
                  </TooltipContent>
                </Tooltip>
              </div>

              <Progress value={Math.min(telemetry.ram_percent, 100)} className="h-1.5" />

              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <span>Uso: {telemetry.ram_percent.toFixed(1)}%</span>
                <span>Livre: {telemetry.ram_free_gb.toFixed(1)} GB</span>
              </div>
            </div>

            {/* 3. Motor Ollama & Modelo Ativo */}
            <div className="rounded-lg border border-border/70 bg-background/60 p-3 flex items-center justify-between gap-2">
              <div className="space-y-0.5 min-w-0">
                <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                  <Layers className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span>Modelo na RAM (Max 1)</span>
                </div>
                <div className="flex items-center gap-1.5 truncate">
                  <span
                    className={`h-2 w-2 rounded-full shrink-0 ${
                      hasActiveModel ? "bg-primary animate-pulse" : "bg-muted-foreground/50"
                    }`}
                  />
                  <span className="text-xs font-mono truncate text-muted-foreground">
                    {telemetry.active_model_label}
                  </span>
                </div>
              </div>

              <div className="text-right shrink-0">
                <div className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-0.5 text-xs font-mono font-semibold text-foreground">
                  <Zap className="h-3 w-3 text-primary" />
                  {telemetry.ollama_ram_mb.toFixed(0)} MB
                </div>
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  {telemetry.ollama_processes_count} proc. Ollama
                </div>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

