@echo off
cd /d "%~dp0"
echo Iniciando servidor local en el puerto 8130...
start "" http://localhost:8130/rebuy_dashboard.html
python -m http.server 8130
