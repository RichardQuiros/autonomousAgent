@echo off
setlocal
REM !imoprtante antes de usar, cambiar ruta a la de este archivo: Start-Process cmd.exe -ArgumentList "/c C:\Users\Usuario\Dev\n8n\autonomousAgent\python\host.cmd" -WindowStyle Hidden
REM Ruta ABSOLUTA a tu host.py
REM Ahora se calcula automaticamente a partir de la ruta de este .cmd
set "SCRIPT=%~dp0host.py"

REM Opción 1: usar el Python Launcher (recomendado si existe)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT%"
  exit /b %errorlevel%
)

REM Opcion 2: python.exe en el PATH
where python >nul 2>nul
if %errorlevel%==0 (
  python "%SCRIPT%"
  exit /b %errorlevel%
)

REM Opcion 3: python3.exe en el PATH
where python3 >nul 2>nul
if %errorlevel%==0 (
  python3 "%SCRIPT%"
  exit /b %errorlevel%
)

echo [ERROR] No se encontro Python (py/python/python3) en el PATH.
echo Instala Python y activa la opcion "Add python.exe to PATH".
pause
exit /b 1
