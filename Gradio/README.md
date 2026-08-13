# Local Gradio

This folder preserves the current local Gradio frontend.

Start it from this directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Or run directly:

```powershell
..\.venv\Scripts\python.exe .\app.py --host 127.0.0.1 --port 7860
```

Notes:

- This is the preserved local-processing frontend.
- The main project root `app.py` is now the remote NAS API client frontend.
