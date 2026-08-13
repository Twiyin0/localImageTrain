# WaifuDiffusion Tagger API

## Base URL

- `http://<host>:8000`
- Swagger UI: `/docs`
- ReDoc: `/redoc`

## Authentication

All processing endpoints require an API key.

You can provide it as either:

```http
X-API-Key: your-api-key
```

or:

```http
Authorization: Bearer your-api-key
```

## Health Check

```http
GET /health
```

Example response:

```json
{
  "status": "ok",
  "python": "/usr/local/bin/python",
  "repo_id": "SmilingWolf/wd-convnext-tagger-v3",
  "model_dir": "/app/models/wd-convnext-tagger-v3",
  "providers": ["CPUExecutionProvider"],
  "auth_enabled": true
}
```

## Legacy Endpoints

### Single image JSON

```http
POST /tag
```

Form fields:

- `image`
- `general_threshold`
- `character_threshold`
- `general_mcut`
- `character_mcut`

### Batch image JSON

```http
POST /tag/batch
```

Form fields:

- `images`
- `general_threshold`
- `character_threshold`
- `general_mcut`
- `character_mcut`

## Unified Endpoint

```http
POST /process
```

All processing endpoints also return timing headers:

- `X-WD-Backend-Process-Time-Ms`: model-side processing time on the backend
- `X-WD-Backend-Total-Time-Ms`: backend total request time, including image decode/load and processing

Shared form fields:

- `type`
- `general_threshold`
- `character_threshold`
- `general_mcut`
- `character_mcut`

Optional inputs:

- `image`: for single-image modes
- `images`: for uploaded batch modes
- `input_dir`: server-side directory path for batch modes
- `export_format`: only used by `type=json`, values are `inline`, `json`, `csv`, `both`

## Supported `type` Values

### `type=tag`

Single image only.

Output:

- plain text
- only the final caption/tag string

Example:

```bash
curl -X POST "http://10.1.0.2:8000/process" \
  -H "X-API-Key: your-api-key" \
  -F "type=tag" \
  -F "image=@demo.jpg"
```

### `type=arrary`

Single image only.

Output:

- JSON string array
- only the selected general tags

Example response:

```json
["1girl", "solo", "pink hair"]
```

Example timing headers:

```http
X-WD-Backend-Process-Time-Ms: 1420.37
X-WD-Backend-Total-Time-Ms: 1548.92
```

### `type=tagimg`

Single image only.

Output:

- image file download
- tags are written into image metadata

Notes:

- PNG output stores text metadata
- JPEG/WebP tries to write EXIF comment fields

### `type=json`

Batch mode.

Input:

- uploaded `images`
- or `input_dir`
- or both

Output depends on `export_format`:

- `inline`: JSON response body
- `json`: downloadable `results.json`
- `csv`: downloadable `results.csv`
- `both`: downloadable zip containing both files

Batch JSON items include cache metadata:

- `cache.cache_hit`: `miss` / `exact` / `similar`
- `cache.source_md5`
- `cache.similarity_score`

Batch summary also includes:

- `cache_stats.miss`
- `cache_stats.exact`
- `cache_stats.similar`

Notes:

- `similar` cache reuse is only enabled for batch processing
- single-image modes only use exact cache hits

Example:

```bash
curl -X POST "http://10.1.0.2:8000/process" \
  -H "X-API-Key: your-api-key" \
  -F "type=json" \
  -F "input_dir=/volume2/Project/images" \
  -F "export_format=both"
```

### `type=mulitagimg`

Batch mode.

Input:

- uploaded `images`
- or `input_dir`
- or both

Output:

- zip file
- contains tagged images with metadata
- also contains `results.json`

## Error Cases

### Invalid or missing API key

```json
{
  "detail": "Invalid or missing API key"
}
```

### Unsupported `type`

```json
{
  "detail": "Unsupported type"
}
```

### Missing required single image input

```json
{
  "detail": "single-image types require the image field"
}
```

### Missing required batch input

```json
{
  "detail": "batch types require images or input_dir"
}
```
