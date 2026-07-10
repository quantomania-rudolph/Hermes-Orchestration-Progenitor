@echo off
setlocal EnableDelayedExpansion
rem Warm up Qwen3-14B on Intel Arc GPU via chat completion probe.
cd /d "%~dp0\..\.."

if "%HERMES_CHAT_MODEL%"=="" set HERMES_CHAT_MODEL=qwen3-14b-int4
set MODEL=%HERMES_CHAT_MODEL%

echo === Warmup Qwen14B on Intel GPU: %MODEL% ===

call "%~dp0check_nollama_health.bat"
if errorlevel 1 (
    echo [error] NoLlama not running. Run scripts\run_intel_gpu\01_start_nollama.bat first.
    pause
    exit /b 1
)

python ensure_hermes_model.py --check
if errorlevel 1 (
    echo [warn] Chat model not listed. Check HERMES_CHAT_MODEL and install_models scripts.
)

echo.
echo Warming %MODEL% (first load may take 30-90s on Arc GPU)...
python -u -c "from hermes_nollama import resolve_chat_model; from openai import OpenAI; import os; m=resolve_chat_model(prefer_device='GPU') or os.environ.get('HERMES_CHAT_MODEL','qwen3-14b-int4'); c=OpenAI(base_url=os.environ.get('NOLLAMA_OPENAI_BASE_URL','http://localhost:8000/v1'),api_key=os.environ.get('NOLLAMA_API_KEY','nollama'),timeout=180); r=c.chat.completions.with_raw_response.create(model=m,messages=[{'role':'user','content':'/no_think Reply with exactly: OK'}],max_tokens=32,temperature=0); print('[ok] model:', m, 'device:', r.headers.get('X-Device',''), 'reply:', (r.parse().choices[0].message.content or '').strip()[:80])"
if errorlevel 1 (
    echo [FAIL] Chat warmup failed.
    pause
    exit /b 1
)

echo.
echo [OK] Qwen14B chat path is warm on Intel GPU.
exit /b 0
