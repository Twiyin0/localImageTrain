# NAS Deployment

## Target

- Host path: `/volume2/Project/python/huggingface`
- Runtime: Debian-like Linux with Docker
- CPU target: Intel N100

## Files used

- `Dockerfile.api`
- `compose.nas.yml`
- `requirements-api.txt`
- `.env.nas`
- `models/wd-convnext-tagger-v3`

## Manual deploy

```bash
cd /volume2/Project/python/huggingface
docker compose -f compose.nas.yml up -d --build
```

## API key

The NAS deployment reads the API key from `.env.nas`.

Example:

```env
WD_TAGGER_API_KEY=replace-with-a-long-random-secret
```

## Offline model mode

This deployment is configured to prefer:

```text
/app/models/wd-convnext-tagger-v3
```

The directory must contain:

- `model.onnx`
- `selected_tags.csv`

## Service URLs

- `http://<nas-ip>:8000/health`
- `http://<nas-ip>:8000/docs`
- `http://<nas-ip>:8000/tag`
- `http://<nas-ip>:8000/tag/batch`

## Automated deploy from Windows

```powershell
.\.venv\Scripts\python.exe deploy_nas.py `
  --host 10.1.0.2 `
  --username root `
  --password "<your-password>" `
  --remote-dir /volume2/Project/python/huggingface
```
