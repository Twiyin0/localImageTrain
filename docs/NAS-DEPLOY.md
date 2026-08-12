# NAS Deployment

## Target

- Host path: `/volume2/Project/python/huggingface`
- Runtime: Debian-like Linux with Docker
- CPU target: Intel N100

## Files used

- `Dockerfile.api`
- `compose.nas.yml`
- `requirements-api.txt`

## Manual deploy

```bash
cd /volume2/Project/python/huggingface
docker compose -f compose.nas.yml up -d --build
```

## Service URLs

- `http://<nas-ip>:8000/health`
- `http://<nas-ip>:8000/docs`
- `http://<nas-ip>:8000/tag`

## Automated deploy from Windows

```powershell
.\.venv\Scripts\python.exe deploy_nas.py `
  --host 10.1.0.2 `
  --username root `
  --password "<your-password>" `
  --remote-dir /volume2/Project/python/huggingface
```
