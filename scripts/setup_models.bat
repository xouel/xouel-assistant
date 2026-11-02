@echo off
chcp 65001 >nul
echo =========================================================
echo   X-Assistant: Setup de Modelos e Perfis de Hardware
echo   CPU: Intel Core i3-1215U (num_thread = 4)
echo =========================================================
echo.

REM Garante a trava de 1 modelo na RAM por vez
setx OLLAMA_MAX_LOADED_MODELS 1 >nul
set OLLAMA_MAX_LOADED_MODELS=1
echo [1/6] OLLAMA_MAX_LOADED_MODELS=1 garantido no ambiente.

echo.
echo [2/6] Verificando download do modelo padrao (qwen2.5:3b-instruct)...
ollama pull qwen2.5:3b-instruct

echo.
echo [3/6] Criando perfil 'x-fast' a partir do Modelfile.fast...
ollama create x-fast -f "%~dp0..\backend\Modelfiles\Modelfile.fast"

echo.
echo [4/6] Verificando download do modelo dev (qwen2.5-coder:7b-instruct)...
echo (Aguarde o download se for a primeira vez...)
ollama pull qwen2.5-coder:7b-instruct

echo.
echo [5/6] Criando perfil 'x-coder' a partir do Modelfile.coder...
ollama create x-coder -f "%~dp0..\backend\Modelfiles\Modelfile.coder"

echo.
echo [6/6] Verificando download do modelo visao (gemma3:4b)...
echo (Aguarde o download se for a primeira vez...)
ollama pull gemma3:4b
ollama create x-vision -f "%~dp0..\backend\Modelfiles\Modelfile.vision"

echo.
echo =========================================================
echo   Setup Concluido! Perfis disponiveis no Ollama:
echo =========================================================
ollama list
echo.
pause

