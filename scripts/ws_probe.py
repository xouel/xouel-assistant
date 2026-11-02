import sys
import json
import asyncio
from pathlib import Path

# Adiciona o diretório backend ao sys.path para importar config
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

try:
    import websockets
except ImportError:
    print("[ERRO] Biblioteca 'websockets' não encontrada. Execute 'pip install websockets' no ambiente virtual.")
    sys.exit(1)

from app.config import TOKEN_PATH, PORT, HOST


async def main():
    print("=" * 60)
    print("  X-ASSISTANT: PROBE DE WEBSOCKET & TELEMETRIA (/ws)")
    print("=" * 60)

    # 1. Carrega o token local
    if not TOKEN_PATH.exists():
        print(f"[ERRO] Arquivo de token não encontrado em: {TOKEN_PATH}")
        print("Inicie o backend pelo menos uma vez para gerar o token local.")
        return

    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    print(f"[*] Token local carregado: {token[:8]}...{token[-4:]} ({len(token)} chars)")

    ws_url = f"ws://{HOST}:{PORT}/ws"
    print(f"[*] Conectando ao WebSocket em: {ws_url} ...")

    try:
        async with websockets.connect(ws_url) as ws:
            print("[+] Conexão TCP/WS estabelecida com sucesso!")

            # 2. Handshake de Autenticação
            print("[*] Enviando handshake de autenticação...")
            auth_msg = {"type": "auth", "token": token}
            await ws.send(json.dumps(auth_msg))

            raw_auth_resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            auth_resp = json.loads(raw_auth_resp)
            print(f"[+] Resposta do servidor: {auth_resp.get('type')} -> '{auth_resp.get('text')}'")

            if auth_resp.get("type") != "auth_ok":
                print(f"[ERRO] Falha no handshake: {auth_resp}")
                return

            # 3. Aguarda o primeiro pacote de telemetria
            print("[*] Aguardando pacote inicial de telemetria...")
            raw_telemetry = await asyncio.wait_for(ws.recv(), timeout=10.0)
            telem_data = json.loads(raw_telemetry)
            if telem_data.get("type") == "telemetry":
                d = telem_data.get("data", {})
                cpu = d.get("cpu_percent", 0.0)
                ram_pct = d.get("ram_percent", 0.0)
                ram_free_gb = d.get("ram_free_gb", 0.0)
                ollama_models = d.get("active_models", [])
                mode_label = d.get("memory_mode_label", "")

                print(f"    - CPU: {cpu:.1f}%")
                print(f"    - RAM Usada: {ram_pct:.1f}% (Livre: {ram_free_gb:.1f} GB | Modo: {mode_label})")
                print(f"    - Modelos Ollama na RAM: {ollama_models if ollama_models else 'Nenhum (0 MB)'}")
            else:
                print(f"    - Mensagem recebida: {telem_data}")

            # 4. Envia mensagem de teste de comando rápido (fast-path calc)
            print("\n[*] Enviando mensagem de teste: comando 'calc' (abrir calculadora)...")
            test_msg = {
                "type": "user_message",
                "text": "calc",
                "mode": "x-fast",
                "stream": False,
            }
            await ws.send(json.dumps(test_msg))

            # Aguarda a resposta do comando (descartando telemetrias intermediárias)
            cmd_resp = None
            for _ in range(10):
                raw_resp = await asyncio.wait_for(ws.recv(), timeout=10.0)
                parsed = json.loads(raw_resp)
                if parsed.get("type") in ("action_result", "confirmation_required", "done", "token", "chat_response"):
                    cmd_resp = parsed
                    break

            if cmd_resp:
                print(f"[+] Resposta do assistente:")
                print(f"    - Tipo: {cmd_resp.get('type')}")
                print(f"    - Texto: {cmd_resp.get('text')}")
                if cmd_resp.get("data"):
                    print(f"    - Status: {cmd_resp['data'].get('status')}")
            else:
                print("[-] Nenhuma resposta de comando recebida dentro da janela esperada.")

            print("\n[+] Todos os testes do WebSocket Probe passaram com sucesso!")

    except ConnectionRefusedError:
        print(f"\n[ERRO] Não foi possível conectar a {ws_url}.")
        print("Certifique-se de que o backend está em execução:")
        print("  cd backend")
        print("  ..\\.venv\\Scripts\\python -m app.main")
    except Exception as exc:
        print(f"\n[ERRO] Falha durante o probe do WebSocket: {type(exc).__name__}: {str(exc)}")


if __name__ == "__main__":
    asyncio.run(main())
