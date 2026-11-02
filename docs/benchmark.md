# Benchmark de Threads e Desempenho de Inferência na CPU

**Hardware:** Notebook Intel Core i3-1215U (2 P-Cores / 4 threads + 4 E-Cores / 4 threads = 6C / 8T)  
**Memória:** 20 GB RAM (Flex Mode)  
**Objetivo:** Identificar o número ótimo de threads (`num_thread`) para inferência na CPU, evitando que os núcleos de eficiência (E-Cores) atrasem a sincronização dos núcleos de performance (P-Cores).

---

## 1. Configurações de Ambiente

- `OLLAMA_MAX_LOADED_MODELS`: `1` (Configurado permanentemente no usuário Windows)
- `OLLAMA_KEEP_ALIVE`: `5m` (Padrão)

---

## 2. Testes de Benchmark Reais (Tokens / Segundo)

### Modelo: `qwen2.5:3b-instruct` (Q4_K_M, ~1.9 GB download / ~2.2 GB RAM)
**Prompt fixo de teste:**  
> "Explique em 3 parágrafos objetivos o que é concorrência em sistemas distribuídos e quais os principais desafios."

| Threads (`num_thread`) | Prompt Eval Rate (tokens/s) | Eval Rate / Geração (tokens/s) | Comportamento Observado |
| :---: | :---: | :---: | :--- |
| **2** (Apenas 1 P-Core ou 2 threads) | 19.78 t/s | 6.31 t/s | Subutiliza a capacidade computacional dos 2 P-Cores disponíveis. |
| **4** (2 P-Cores com HT completo) | **26.36 t/s** | **6.50 t/s** | **Ponto ideal de geração contínua:** utiliza 100% dos P-Cores sem gargalo de sincronização. |
| **6** (2 P-Cores + 2 E-Cores) | 37.35 t/s | **5.45 t/s** | **Queda de ~16% na taxa de geração:** embora o processamento inicial do prompt seja mais rápido em lote, a geração token-a-token sofre com os P-Cores esperando a conclusão dos E-Cores mais lentos. |

---

## 3. Conclusão Técnica e Definição para a Task 02 (Modelfiles)

1. **Geração Token a Token (Chat e Respostas):**
   - O gargalo perceptível pelo usuário durante o uso do assistente é a velocidade de digitação/geração (`eval rate`).
   - Fixar `num_thread = 4` garante a maior velocidade sustentada de geração (**6.50 tokens/s vs 5.45 tokens/s**) e evita aquecimento desnecessário nos E-Cores.
2. **Definição para os perfis:**
   - **`x-fast` (`qwen2.5:3b-instruct`):** `num_thread 4`
   - **`x-vision` (`gemma3:4b`):** `num_thread 4`
   - **`x-coder` (`qwen2.5-coder:7b-instruct`):** `num_thread 4` (ou testado sob demanda, priorizando estabilidade térmica e fluidez).
