@echo off
cd /d "%~dp0"
python_embed\python.exe -m streamlit run app.py --server.port 8501
pause
