import urllib.request
import json
import time

PROMPT = "Explique em 3 parágrafos objetivos o que é concorrência em sistemas distribuídos e quais os principais desafios."
MODEL = "qwen2.5:3b-instruct"
THREADS_TO_TEST = [2, 4, 6]

print(f"=== Benchmark de Threads na CPU para {MODEL} ===")
print(f"Prompt: {PROMPT}\n")

results = []

for threads in THREADS_TO_TEST:
    print(f"--> Testando com num_thread = {threads}...")
    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "stream": False,
        "options": {
            "num_thread": threads,
            "temperature": 0.2
        }
    }
    
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    start_time = time.time()
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    total_wall_time = time.time() - start_time
    
    prompt_eval_count = data.get("prompt_eval_count", 0)
    prompt_eval_dur = data.get("prompt_eval_duration", 1) / 1e9
    prompt_rate = prompt_eval_count / prompt_eval_dur if prompt_eval_dur > 0 else 0
    
    eval_count = data.get("eval_count", 0)
    eval_dur = data.get("eval_duration", 1) / 1e9
    eval_rate = eval_count / eval_dur if eval_dur > 0 else 0
    
    total_dur = data.get("total_duration", 0) / 1e9
    
    print(f"    Tokens gerados: {eval_count}")
    print(f"    Prompt eval rate: {prompt_rate:.2f} tokens/s")
    print(f"    Eval rate (geração): {eval_rate:.2f} tokens/s")
    print(f"    Tempo total: {total_dur:.2f} s (Wall time: {total_wall_time:.2f} s)\n")
    
    results.append({
        "threads": threads,
        "prompt_rate": round(prompt_rate, 2),
        "eval_rate": round(eval_rate, 2),
        "total_dur": round(total_dur, 2),
        "eval_count": eval_count
    })

print("=== Resumo dos Resultados ===")
print(f"{'Threads':<10} | {'Prompt Eval (t/s)':<18} | {'Eval Rate (t/s)':<16} | {'Tempo (s)':<10}")
print("-" * 62)
for r in results:
    print(f"{r['threads']:<10} | {r['prompt_rate']:<18} | {r['eval_rate']:<16} | {r['total_dur']:<10}")

