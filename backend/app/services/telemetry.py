import psutil
import httpx
from typing import Dict, Any, List, Tuple

# Aquecimento inicial do psutil: a primeira chamada sempre retorna 0.0
# Realizar o aquecimento no carregamento do módulo inicializa o delta de tempo do SO
psutil.cpu_percent(interval=None)


def warmup_telemetry() -> None:
    """Realiza uma leitura inicial para calibrar os contadores de CPU."""
    psutil.cpu_percent(interval=None)


def get_ollama_processes_memory() -> Tuple[int, int]:
    """
    Varre os processos ativos do Windows somando o RSS de todos os processos
    filhos e serviços associados ao Ollama (ollama.exe, ollama app.exe, llama runners).
    Retorna (total_rss_bytes, quantidade_processos).
    """
    total_rss = 0
    count = 0
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if "ollama" in name or "llama" in name:
                mem = proc.info.get("memory_info")
                if mem:
                    total_rss += mem.rss
                    count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return total_rss, count


async def get_loaded_ollama_models() -> List[str]:
    """
    Consulta o daemon do Ollama em http://127.0.0.1:11434/api/ps de forma assíncrona
    para identificar quais modelos estão carregados na memória neste exato momento.
    Caso o Ollama esteja desligado, retorna lista vazia de forma resiliente.
    """
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get("http://127.0.0.1:11434/api/ps")
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                return [m.get("model") or m.get("name") for m in models if m.get("model") or m.get("name")]
    except Exception:
        pass
    return []


async def get_system_telemetry() -> Dict[str, Any]:
    """
    Coleta o snapshot completo de hardware e memória em tempo real:
    - Uso percentual de CPU (Intel Core i3-1215U)
    - RAM do Sistema (Total, Usada, Livre, %)
    - Consumo real de processos do Ollama no Windows (MB / GB)
    - Modelos ativos na RAM reportados pelo Ollama
    - Status de zona de desempenho Flex Mode (Dual-Channel nos primeiros 8 GB)
    """
    cpu = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    ollama_rss_bytes, ollama_proc_count = get_ollama_processes_memory()
    active_models = await get_loaded_ollama_models()

    ram_total_gb = round(vm.total / (1024 ** 3), 2)
    ram_used_gb = round(vm.used / (1024 ** 3), 2)
    ram_free_gb = round(vm.available / (1024 ** 3), 2)
    ram_percent = round(vm.percent, 1)

    ollama_mb = round(ollama_rss_bytes / (1024 ** 2), 1)
    ollama_gb = round(ollama_rss_bytes / (1024 ** 3), 2)

    # Diagnóstico da arquitetura de memória Flex Mode do hardware (20 GB total)
    # Primeiros ~8 GB operam em Dual-Channel simétrico (largura de banda máxima)
    is_dual_channel = ram_used_gb <= 8.5
    memory_mode_label = "Pico Dual-Channel (128-bit)" if is_dual_channel else "Flex Mode Estendido (64-bit)"

    return {
        "cpu_percent": round(cpu, 1),
        "ram_total_gb": ram_total_gb,
        "ram_used_gb": ram_used_gb,
        "ram_free_gb": ram_free_gb,
        "ram_percent": ram_percent,
        "ollama_ram_mb": ollama_mb,
        "ollama_ram_gb": ollama_gb,
        "ollama_processes_count": ollama_proc_count,
        "active_models": active_models,
        "active_model_label": active_models[0] if active_models else "Nenhum na RAM (0 MB)",
        "is_dual_channel": is_dual_channel,
        "memory_mode_label": memory_mode_label,
    }

