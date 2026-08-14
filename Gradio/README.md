# Local Gradio

This folder preserves the current local Gradio frontend.

Start it from the project root or from this directory:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_in_windows_by_localMode.ps1
```

macOS / Linux:

```bash
sh scripts/run_in_macos_linux_by_localMode.sh
```

Compatibility wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File Gradio\run.ps1
```

Or run directly from the project root:

```powershell
.\.venv\Scripts\python.exe Gradio\app.py --host 127.0.0.1 --port 7861
```

Notes:

- This is the preserved local-processing frontend.
- Windows defaults to `CUDAExecutionProvider, CPUExecutionProvider` for local ONNX inference.
- The UI includes model warmup status, highlighted unsuitable tags, resource metrics, cache status, and export files.
- Image inputs support local uploads and network URLs. Batch URL lists can be split by comma, semicolon, pipe, or newline.
- The native Gradio `settings` link controls the default export filename template. Default: `${origin_filename}_tagged${origin_ext}`.
- The main project root `app.py` is now the remote NAS API client frontend.
