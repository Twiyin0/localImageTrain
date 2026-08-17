# NAS Deployment

## Target

- Host path: `/opt/python/huggingface/localImageTrain` or your NAS project directory
- Runtime: Debian-like Linux with Docker
- CPU target: Intel N100
- WebUI runtime: Node.js static frontend proxy, inference remains in the Python API container

## Files used

- `Dockerfile.api`
- `Dockerfile.webui`
- `compose.nas.yml`
- `requirements-api.txt`
- `.env.nas`
- `models/wd-convnext-tagger-v3`

## Manual deploy

```bash
cd /opt/python/huggingface/localImageTrain
docker build -t localimagetrain-wd-tagger-api -f Dockerfile.api .
docker build -t localimagetrain-wd-tagger-webui -f Dockerfile.webui .
docker compose -f compose.nas.yml up -d --no-build
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
- `http://<nas-ip>:7861` for the lightweight Node WebUI

## Automated deploy from Windows

Recommended wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy_nas.ps1 `
  -HostName 10.1.0.2 `
  -Username root `
  -Password "<your-password>" `
  -RemoteDir /opt/python/huggingface/localImageTrain
```

Use `-NoUpload` when the server already has the latest code:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy_nas.ps1 `
  -HostName 10.1.0.2 `
  -Username root `
  -Password "<your-password>" `
  -RemoteDir /opt/python/huggingface/localImageTrain `
  -NoUpload
```

Direct Python entry:

```powershell
.\.venv\Scripts\python.exe deploy_nas.py `
  --host 10.1.0.2 `
  --username root `
  --password "<your-password>" `
  --remote-dir /opt/python/huggingface/localImageTrain
```

If the server already has the latest code from `git pull`, skip uploading and only rebuild/restart containers:

```powershell
.\.venv\Scripts\python.exe deploy_nas.py `
  --host 10.1.0.2 `
  --username root `
  --password "<your-password>" `
  --remote-dir /opt/python/huggingface/localImageTrain `
  --no-upload
```

## Automated deploy from macOS/Linux

```bash
HOST_NAME=10.1.0.2 \
USERNAME=root \
PASSWORD='<your-password>' \
REMOTE_DIR=/opt/python/huggingface/localImageTrain \
sh scripts/deploy_nas.sh
```

If the server already has the latest code:

```bash
HOST_NAME=10.1.0.2 \
USERNAME=root \
PASSWORD='<your-password>' \
REMOTE_DIR=/opt/python/huggingface/localImageTrain \
NO_UPLOAD=1 \
sh scripts/deploy_nas.sh
```
