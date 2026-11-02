# X-Assistant

> **Windows Local AI Desktop Assistant & Developer Productivity Copilot**  
> 100% Offline-first, Seguro e Otimizado para Hardware com Memória Flex Mode (Intel Core i3 12ª Ger / 20 GB RAM).

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![Tailwind CSS v4](https://img.shields.io/badge/Tailwind-v4-38B2AC.svg?style=flat&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-black.svg?style=flat&logo=ollama&logoColor=white)](https://ollama.ai/)
[![Tests](https://img.shields.io/badge/Tests-59%20Passed-success.svg?style=flat&logo=pytest&logoColor=white)](backend/tests/)

---

## Visão Geral

O **X-Assistant** é um assistente de produtividade desktop para Windows que roda **completamente local**, sem envio de dados ou telemetria para a nuvem. Ele combina modelos de linguagem (LLMs via Ollama), reconhecimento de voz com IA (Faster-Whisper), síntese de voz nativa (Windows SAPI5) e visão computacional multimodal em uma interface **Bento Box** moderna e responsiva.

Projetado especificamente para rodar com eficiência em hardware com restrições de barramento de memória (como o **Intel Core i3-1215U com 20 GB em Flex Mode**), o sistema implementa políticas ativas de contenção de RAM e ejeção de modelos, garantindo máxima fluidez do sistema operacional.

---

## Principais Funcionalidades

- **Roteamento Inteligente de Modelos (Triagem):**
  - `x-fast` (*Llama 3.2 3B*): Roteamento de comandos de sistema, conversas rápidas e triagem de intenções em milissegundos.
  - `x-coder` (*Qwen 2.5 Coder 7B*): Geração de código avançado, refatoração e resolução de bugs.
  - `x-vision` (*Moondream2 / Llama 3.2 Vision*): Análise multimodal direta da tela do usuário.
- **Voz Offline de Alta Velocidade:**
  - **STT (Speech-to-Text):** Faster-Whisper local com ativação por Push-to-Talk (`Ctrl + Espaço` ou clique contínuo).
  - **TTS (Text-to-Speech):** Síntese nativa offline via Windows SAPI5 (`pyttsx3`), com zero overhead de latência ou consumo de VRAM.
- **Ferramentas de Produtividade para Desenvolvedores:**
  - **Gerador de Git Commits:** Inspeciona `git diff --staged` ou `git diff` do repositório ativo e sugere mensagens no padrão Conventional Commits com 1 clique.
  - **Smart Clipboard:** Análise instantânea do conteúdo da área de transferência com ações contextuais (explicar código, formatar JSON, converter dados).
  - **Visão de Tela (Screen Vision):** Captura instantânea e análise contextual do que você está vendo.
  - **Gerenciador de Workspaces:** Alternância rápida entre diretórios de trabalho e projetos.
- **Segurança em Camadas (Defense-in-Depth):**
  - Execução restrita por **Allowlist** (`os_executor.py`), proibindo comandos arbitrários e prevenindo shell injection (`shell=False` estrito).
  - **Confirmação em 2 Etapas:** Ações de risco (ex: formatar disco, mutações na allowlist ou comandos de terminal) exigem autorização explícita do usuário via interface.
  - **Autenticação Local por Token:** Comunicação REST e WebSockets protegida por token criptográfico (`secrets.token_hex`) único armazenado localmente.
  - **Trilha de Auditoria Imutável:** Todas as ações, confirmações e comandos são registrados com hash e timestamp em banco SQLite local (`assistant.db`).
- **Telemetria de Hardware em Tempo Real:**
  - Medição de CPU e uso de memória de 20 GB com destaque visual para a **Zona Segura Dual-Channel** (até 8.5 GB a 128-bit vs Single-Channel acima disso).
  - Monitoramento do RSS do Ollama e botão de **Ejeção Imediata de RAM** para liberar a memória instantaneamente.
- **Interface Flutuante & Atalho Global:**
  - Inicialização em modo aplicativo leve (Edge Chromium App Mode) sem bordas de navegador.
  - Atalho global Win32: **`Ctrl + Alt + X`** (ou **`Ctrl + Shift + X`**) para invocar/ocultar a janela instantaneamente de qualquer lugar no Windows.

---

## Arquitetura do Sistema

```text
x-assistant/
├── backend/                  # Servidor FastAPI e Lógica de Negócio
│   ├── app/
│   │   ├── main.py           # Endpoints REST, WebSockets e Servidor de Assets
│   │   ├── orchestrator.py   # Roteador de intenções e triagem de LLMs
│   │   ├── database.py       # SQLite (WAL mode, auditoria e allowlist)
│   │   ├── security.py       # Tokens locais, validação de origem e CORS
│   │   ├── schemas.py        # Modelos Pydantic v2
│   │   └── services/
│   │       ├── dev_tools.py      # Git diff, Smart Clipboard, Captura de tela
│   │       ├── ollama_service.py # Cliente HTTP assíncrono Ollama + Ejetor
│   │       ├── os_executor.py    # Execução controlada via Allowlist
│   │       ├── telemetry.py      # Monitoramento psutil + Flex Mode 128-bit
│   │       └── voice_service.py  # Faster-Whisper + Windows SAPI5
│   └── tests/                # 59 Testes automatizados (pytest)
├── frontend/                 # Interface do Usuário (Bento Box)
│   ├── src/
│   │   ├── components/       # TelemetryCard, QuickActions, ChatPanel, etc.
│   │   ├── hooks/            # useAssistant.ts (WebSocket + REST client)
│   │   └── index.css         # Tailwind v4 com Obsidian Dark Theme
│   └── dist/                 # Build estático pré-compilado (Zero Node em prod)
├── docs/                     # Documentação Completa e Benchmarks
│   └── DOCUMENTACAO_COMPLETA.md
├── scripts/                  # Automações de Inicialização e Atalhos
│   ├── launcher.pyw          # Launcher Win32 (RegisterHotKey + Edge App Mode)
│   ├── install_startup.py    # Instalador do atalho no Windows Startup
│   └── setup_models.bat      # Criação automatizada de Modelfiles no Ollama
└── start_x_assistant.bat     # Script de inicialização com 1 clique
```

---

## Instalação e Uso Rápido

### 1. Pré-requisitos
- **Windows 10 ou 11 (64-bit)**
- **Python 3.11+**
- **Node.js 18+** (apenas para desenvolvimento ou compilação do frontend)
- **Ollama**: [Baixar e instalar Ollama](https://ollama.ai/)
- **Microfone e Caixas de Som / Fones** configurados no Windows

### 2. Configuração do Backend
Clone o repositório e configure o ambiente virtual:
```powershell
# Crie e ative o ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Instale as dependências
pip install -r backend\requirements.txt
```

### 3. Configuração dos Modelos de IA
Inicie o Ollama e prepare os modelos otimizados:
```powershell
# Baixe os modelos base recomendados
ollama pull llama3.2:3b
ollama pull qwen2.5-coder:7b
ollama pull moondream

# Crie os modelos especializados do assistente
.\scripts\setup_models.bat
```

### 4. Build do Front-end (Opcional se já estiver compilado)
```powershell
cd frontend
npm install
npm run build
cd ..
```

### 5. Iniciar o Assistente
Basta dar duplo clique em `start_x_assistant.bat` ou executar no terminal:
```powershell
.\start_x_assistant.bat
```

- **Abrir/Focar o Assistente:** Pressione **`Ctrl + Alt + X`** (ou `Ctrl + Shift + X`).
- **Comando de Voz:** Mantenha pressionado **`Ctrl + Espaço`** para falar e solte para transcrever.

### 6. Execução e Empacotamento Desktop com Tauri
O projeto inclui suporte nativo ao **Tauri v2** configurado em `frontend/src-tauri`:
```powershell
cd frontend
npm run tauri dev    # Executa a janela nativa desktop em modo de desenvolvimento
npm run tauri build  # Gera o executável/instalador .exe de produção (requer Rust toolchain)
```

---

## Testes Automatizados

O projeto possui **100% de aprovação** em sua suíte de 59 testes automatizados cobrindo segurança, banco de dados, allowlist, execução de SO, integração de voz, visão multimodal e telemetria:

```powershell
cd backend
..\.venv\Scripts\python -m pytest -v
```

---

## Documentação Detalhada

Para uma visão aprofundada de todas as decisões arquiteturais, métricas de benchmark, especificações de endpoints, fluxos de segurança e lições aprendidas:
- Consulte [docs/DOCUMENTACAO_COMPLETA.md](docs/DOCUMENTACAO_COMPLETA.md).

---

## Licença

Distribuído sob a licença MIT. Consulte `LICENSE` para mais informações.
