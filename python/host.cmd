@echo off
setlocal
REM Ruta ABSOLUTA a tu host.py
set SCRIPT=C:\Users\pqric\Documents\extensions\tooltBot\python\host.py

REM Opción 1: usar el Python Launcher (recomendado si existe)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT%"
  exit /b %errorlevel%
)

REM Opción 2: ruta fija a python.exe (ajústala si es distinta)
"C:\Users\pqric\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe" "%SCRIPT%"
