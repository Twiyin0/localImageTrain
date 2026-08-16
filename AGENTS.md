# AGENTS.md

## Project Rules

- Use the project-local `.venv` with Python `3.11`; do not touch the system Python or global environment.
- The current deployment root is `/opt/python/huggingface/localImageTrain`.
- Do not commit or sync large/generated data: `.venv`, `.cache`, `outputs`, `logs`, `models`, `.env*`, `.git`, or AppleDouble `._*` files.
- `wd_tagger/app.py` is the remote API client UI, `Gradio/app.py` is the local Gradio UI, and `wd_tagger/api.py` is the HTTP API.
- Keep UI and API behavior aligned when adding features, but keep changes small and focused.
- Translation is optional. If the translation API is not configured or not reachable, fall back to the original tags/text without failing the main inference flow.

## Constraints

- 不可过度设计
- 不可过度测试

## Deployment Notes

- `docker-compose.yml` is the primary compose file for the current `/opt/python/huggingface/localImageTrain` deployment.
- The model directory is mounted at `/app/models` inside containers and should be scanned locally before attempting any Hub download.
- Runtime caches live under `.cache` and should stay out of source control and rsync payloads.
