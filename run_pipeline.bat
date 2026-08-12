@echo off
REM Punto de entrada para el Task Scheduler. main.py escribe su propio log en logs\;
REM esto captura ademas lo que falle antes de que el logging arranque.

cd /d "%~dp0"
if not exist logs mkdir logs

echo [%date% %time%] iniciando run_pipeline.bat >> logs\scheduler.log

".venv\Scripts\python.exe" main.py %* >> logs\scheduler.log 2>&1
set CODIGO=%ERRORLEVEL%

if %CODIGO% NEQ 0 (
    echo [%date% %time%] FALLO con codigo %CODIGO% >> logs\scheduler.log
) else (
    echo [%date% %time%] terminado correctamente >> logs\scheduler.log
)

exit /b %CODIGO%
