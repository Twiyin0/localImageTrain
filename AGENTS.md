# AGENTS.md

## Project Rules

- Use the project-local `.venv` with Python `3.11`; do not touch the system Python or global environment.
- The current deployment root is `/opt/python/huggingface/localImageTrain`.
- Do not commit or sync large/generated data: `.venv`, `.cache`, `outputs`, `logs`, `models`, `.env*`, `.git`, or AppleDouble `._*` files.
- `wd_tagger/app.py` is the remote API client UI, `wd_tagger/api.py` is the HTTP API and static WebUI, and `Gradio/app.py` is legacy Gradio-only UI kept for reference.
- `wd_tagger/api.py` also serves the static WebUI at `/`; do not add a separate Node frontend service unless explicitly requested.
- Keep UI and API behavior aligned when adding features, but keep changes small and focused.
- Tag translation must stay deterministic and offline. Do not use a translation API; Chinese tag output comes from `datasets/selected_tags_cn.csv`.

## Constraints

- 不可过度设计
- 不可过度测试

## Deployment Notes

- `docker-compose.yml` is the primary compose file for the current `/opt/python/huggingface/localImageTrain` deployment.
- The Docker container mounts `/opt/python/huggingface/localImageTrain` to `/app`; after normal source/UI rsync, restart the container without rebuilding. Rebuild only when Docker dependencies change.
- The model directory is mounted at `/app/models` inside containers and should be scanned locally before attempting any Hub download.
- Runtime caches live under `.cache` and should stay out of source control and rsync payloads.
- Sync deployments with `rsync -az`; keep the exclude list minimal but always exclude `.git/`, `.venv/`, `.cache/`, `models/`, `outputs/`, `logs/`, `.env*`, `__pycache__/`, `*.pyc`, `.DS_Store`, and `._*`.
