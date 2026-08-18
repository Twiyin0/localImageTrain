# WaifuDiffusion Tagger API

Current API version: `1.0.0`

Key capabilities:

- API key authentication via `X-API-Key` or Bearer token
- Multipart uploads remain compatible and are read in chunks internally
- Raw stream upload for single images
- Raw zip stream upload for batch processing
- Timing headers on all processing responses

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
  "version": "1.0.0",
  "frontend": "static-html",
  "python": "/usr/local/bin/python",
  "repo_id": "SmilingWolf/wd-convnext-tagger-v3",
  "model_dir": "/app/models/wd-convnext-tagger-v3",
  "providers": ["CPUExecutionProvider"],
  "auth_enabled": true
}
```

## 输出语言

所有处理接口都支持可选参数 `lang`：

- `lang=zh`：使用 `datasets/selected_tags_cn.csv` 输出中文标签
- `lang=en`：输出原文
- 不传 `lang` 时，默认输出 `zh`

项目已经彻底放弃翻译 API。中文标签完全离线、确定性输出；需要调整词语时，直接修改 `datasets/selected_tags_cn.csv` 的 `translatedname`。

JSON 响应里会保留：

- `caption_original`：原始标签串
- `caption_display`：当前输出语言对应的展示标签串
- `translation.lang`：请求/默认选择的输出语言
- `translation.source`：中文输出使用的对照表路径

- `risk.flagged_tags_original`：后端按原文判定命中的风险标签
- `risk.flagged_tags`：对应的当前展示标签
- `risk.flagged_tag_pairs`：每个风险标签的 `{original, display}` 对照
- `risk.sensitive_threshold`：当前敏感评分阈值
## Legacy Endpoints

### Single image JSON

```http
POST /tag
```

Form fields:

- `image`
- `general_threshold`
- `character_threshold`
- `sensitive_threshold`
- `general_mcut`
- `character_mcut`
- `lang`

### Batch image JSON

```http
POST /tag/batch
```

Form fields:

- `images`
- `general_threshold`
- `character_threshold`
- `sensitive_threshold`
- `general_mcut`
- `character_mcut`
- `lang`

### Single image JSON from raw stream

```http
POST /tag/stream?filename=demo.jpg
Content-Type: image/jpeg
```

This endpoint accepts the image as the raw request body, including chunked transfer from clients that support streaming uploads.

Optional query parameters:

- `lang`: optional output language, `zh` or `en`
- `general_threshold`
- `character_threshold`
- `sensitive_threshold`
- `general_mcut`
- `character_mcut`

Example:

```bash
curl -X POST "http://10.1.0.2:8000/tag/stream?filename=demo.jpg" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: image/jpeg" \
  --data-binary "@demo.jpg"
```

### Batch image JSON from zip stream

```http
POST /tag/batch/stream?filename=images.zip
Content-Type: application/zip
```

This endpoint accepts a zip archive as the raw request body. Supported image entries inside the zip: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`.

Optional query parameters:

- `lang`: optional output language, `zh` or `en`
- `general_threshold`
- `character_threshold`
- `sensitive_threshold`
- `general_mcut`
- `character_mcut`

Example:

```bash
curl -X POST "http://10.1.0.2:8000/tag/batch/stream?filename=images.zip" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/zip" \
  --data-binary "@images.zip"
```

## Unified Endpoint

```http
POST /process
```

All processing endpoints also return timing headers:

- `X-WD-Backend-Process-Time-Ms`: model-side processing time on the backend
- `X-WD-Backend-Total-Time-Ms`: backend total request time, including image decode/load and processing
- `X-WD-Backend-Prepare-Time-Ms`: request/body/image preparation time before model processing
- `X-WD-Backend-Post-Inference-Time-Ms`: post-inference processing time on the backend
- `X-WD-Risk-Summary`: JSON-encoded risk summary, including original/display tag pairs

Shared form fields:

- `type`
- `general_threshold`
- `character_threshold`
- `sensitive_threshold`
- `general_mcut`
- `character_mcut`
- `lang`
- `output_filename_template`: output filename template. Default is `${origin_filename}_tagged${origin_ext}`

Optional inputs:

- `image`: for single-image modes
- `image_url`: for single-image modes using a network URL
- `images`: for uploaded batch modes
- `image_urls`: for batch modes using network URLs. Split multiple URLs with comma, semicolon, pipe, or newline
- `input_dir`: server-side directory path for batch modes
- `export_format`: only used by `type=json`, values are `inline`, `json`, `csv`, `both`

## Stream Upload Endpoint

```http
POST /process/stream?type=tag&filename=demo.jpg
Content-Type: image/jpeg
```

`/process/stream` keeps the original `/process` behavior while accepting raw streamed request bodies instead of `multipart/form-data`.

Single-image modes expect an image body. Batch modes expect a zip body.

Supported query parameters:

- `type`: `tag`, `arrary`, `array`, `tagimg`, `json`, or `mulitagimg`
- `filename`: optional original image filename or zip filename, used for type inference and output naming
- `export_format`: only used by `type=json`, values are `inline`, `json`, `csv`, `both`
- `lang`: optional output language, `zh` or `en`
- `general_threshold`
- `character_threshold`
- `sensitive_threshold`
- `general_mcut`
- `character_mcut`
- `output_filename_template`

Notes:

- Batch stream mode reads image files from a zip archive.
- Batch modes can still use `/process` with multipart `images`, `image_urls`, or `input_dir`.
- Existing `/process`, `/tag`, and `/tag/batch` clients remain compatible; multipart uploads are now read in chunks internally.

Example:

```bash
curl -X POST "http://10.1.0.2:8000/process/stream?type=tag&filename=demo.jpg" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: image/jpeg" \
  --data-binary "@demo.jpg"
```

Chunked streaming example with Python:

```python
import httpx

def chunks(path, size=1024 * 1024):
    with open(path, "rb") as file:
        while data := file.read(size):
            yield data

response = httpx.post(
    "http://10.1.0.2:8000/process/stream",
    params={"type": "tag", "filename": "demo.jpg"},
    headers={"X-API-Key": "your-api-key", "Content-Type": "image/jpeg"},
    content=chunks("demo.jpg"),
)
response.raise_for_status()
print(response.text)
```

Batch zip stream example:

```bash
curl -X POST "http://10.1.0.2:8000/process/stream?type=json&filename=images.zip&export_format=inline" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/zip" \
  --data-binary "@images.zip"
```

Batch tagged-image zip stream example:

```bash
curl -X POST "http://10.1.0.2:8000/process/stream?type=mulitagimg&filename=images.zip" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/zip" \
  --data-binary "@images.zip" \
  -o tagged_images.zip
```

Filename template variables:

- `${origin_filename}`: original filename without extension
- `${origin_basename}`: original filename with extension
- `${origin_ext}` / `${ext}`: output extension, such as `.jpg`, `.png`, `.zip`, `.json`, `.csv`
- `${type}`: process type, such as `tagimg` or `mulitagimg`
- `${index}`: 1-based index in batch mode
- `${date}` / `${time}` / `${timestamp}`: local server time

Built-in template examples:

- `${origin_filename}_tagged${origin_ext}`
- `${origin_filename}${origin_ext}`
- `${origin_filename}_${type}_${index}${origin_ext}`
- `${origin_filename}_${timestamp}${origin_ext}`

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

URL example:

```bash
curl -X POST "http://10.1.0.2:8000/process" \
  -H "X-API-Key: your-api-key" \
  -F "type=tag" \
  -F "image_url=https://example.com/demo.jpg"
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
- exported image metadata writes original English tags as the primary caption/tags; Chinese labels are kept only as display metadata

### `type=json`

Batch mode.

Input:

- uploaded `images`
- `image_urls`
- or `input_dir`
- or any combination of the above

Output depends on `export_format`:

- `inline`: JSON response body
- `json`: downloadable `results.json`
- `csv`: downloadable `results.csv`
- `both`: downloadable zip containing both files

Batch JSON items include cache metadata:

- `cache.cache_hit`: `miss` / `exact` / `similar`
- `cache.source_md5`
- `cache.similarity_score`
- `risk.flagged_tags_original`: matched original tags used by backend risk detection
- `risk.flagged_tags`: current display labels for those matched tags
- `risk.flagged_tag_pairs`: original/display pairs returned together
- `risk.sensitive_threshold`: threshold used for flagged rating detection

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
  -F "image_urls=https://example.com/a.jpg;https://example.com/b.png" \
  -F "export_format=both"
```

### `type=mulitagimg`

Batch mode.

Input:

- uploaded `images`
- `image_urls`
- or `input_dir`
- or any combination of the above

Output:

- zip file
- contains tagged images with metadata
- also contains `results.json`

Custom output filename example:

```bash
curl -X POST "http://10.1.0.2:8000/process" \
  -H "X-API-Key: your-api-key" \
  -F "type=tagimg" \
  -F "image=@demo.jpg" \
  -F 'output_filename_template=${origin_filename}_${timestamp}${origin_ext}'
```

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
  "detail": "single-image types require image or image_url"
}
```

### Missing required batch input

```json
{
  "detail": "batch types require images, image_urls, or input_dir"
}
```
