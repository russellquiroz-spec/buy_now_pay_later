@echo off
REM Respalda lo unico que NO se rehace corriendo el pipeline:
REM   archivos_bnpl.*             los 4 CSV del Drive (uno es del 2026-01-08: puede que ya no este)
REM   bnpl.bnpl_clientes_concurso el Excel de negocio
REM   bnpl_ops.*                  el historico de frescura, calidad y corridas — irrecuperable
REM Todo lo demas (mongo_bnpl, redshift_bnpl, las 11 matviews, las 19 vistas) lo rehace main.py.
setlocal
set PGBIN=C:\Program Files\PostgreSQL\17\bin
set DESTINO=D:\Respaldos\bnpl
set PGHOST=localhost
set PGPORT=9553
set PGDATABASE=rabbit-bi-local
set PGUSER=RELLENAR_USUARIO
REM Sin PGPASSWORD: la contrasena va en %APPDATA%\postgresql\pgpass.conf
REM   localhost:9553:rabbit-bi-local:RELLENAR_USUARIO:<contrasena>

for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set HOY=%%d
if not exist "%DESTINO%" mkdir "%DESTINO%"

REM Dos invocaciones: pg_dump ignora -n cuando se pasa -t, y un dump con los dos juntos
REM saldria con la tabla del concurso y los DOS schemas VACIOS, imprimiendo "Respaldo OK".
"%PGBIN%\pg_dump.exe" -Fc -n archivos_bnpl -n bnpl_ops -f "%DESTINO%\bnpl_ops_archivos_%HOY%.dump"
if errorlevel 1 (echo RESPALDO FALLIDO ^(schemas^) & exit /b 1)

"%PGBIN%\pg_dump.exe" -Fc -t bnpl.bnpl_clientes_concurso -f "%DESTINO%\bnpl_concurso_%HOY%.dump"
if errorlevel 1 (echo RESPALDO FALLIDO ^(concurso^) & exit /b 1)

REM Retencion: 30 dias.
forfiles /p "%DESTINO%" /m bnpl_*_*.dump /d -30 /c "cmd /c del @path" 2>nul
echo Respaldo OK: %DESTINO%
endlocal
