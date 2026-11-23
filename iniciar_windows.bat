@echo off
cd /d "%~dp0"
echo Instalando librerias (solo la primera vez tarda)...
python -m pip install -r requirements.txt
echo Abriendo el simulador en el navegador...
python -m streamlit run app.py
pause
