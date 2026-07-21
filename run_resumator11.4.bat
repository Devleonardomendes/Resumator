@echo off
title Resumator 11.4
cd /d "%~dp0"
set "LOCAL_PY=C:\Users\Leonardo\AppData\Local\Programs\Python\Python314\python.exe"
if exist "%LOCAL_PY%" (
  "%LOCAL_PY%" app.py
  goto :done
)
py -3 app.py
if errorlevel 1 python app.py
:done
pause
