# WaifuDiffusion Tagger API

## 基础信息

- Base URL: `http://<host>:8000`
- 在线文档: `/docs`
- ReDoc: `/redoc`

## 1. 健康检查

### 请求

```http
GET /health
```

### 响应示例

```json
{
  "status": "ok",
  "python": "/app/.venv/bin/python",
  "repo_id": "SmilingWolf/wd-convnext-tagger-v3",
  "model_dir": null,
  "providers": ["CPUExecutionProvider"]
}
```

## 2. 图片打标

### 请求

```http
POST /tag
Content-Type: multipart/form-data
```

### 表单字段

- `image`: 必填，图片文件
- `general_threshold`: 可选，默认 `0.35`
- `character_threshold`: 可选，默认 `0.85`
- `general_mcut`: 可选，默认 `false`
- `character_mcut`: 可选，默认 `false`

### `curl` 示例

```bash
curl -X POST "http://127.0.0.1:8000/tag" \
  -F "image=@demo.png" \
  -F "general_threshold=0.35" \
  -F "character_threshold=0.85"
```

### 响应示例

```json
{
  "repo_id": "SmilingWolf/wd-convnext-tagger-v3",
  "model_dir": null,
  "providers": ["CPUExecutionProvider"],
  "metrics": {
    "total_elapsed_ms": 142.67,
    "inference_elapsed_ms": 118.41,
    "cpu_elapsed_ms": 96.52,
    "process_current_rss_mb": 186.54,
    "process_peak_rss_mb": 214.38,
    "cpu_user_time_s": 2.4187,
    "cpu_system_time_s": 0.3511
  },
  "thresholds": {
    "general": 0.35,
    "character": 0.85
  },
  "rating": {
    "general": 0.998
  },
  "characters": {},
  "general": {
    "1girl": 0.997,
    "solo": 0.992
  },
  "caption": "1girl, solo",
  "filename": "demo.png",
  "content_type": "image/png"
}
```

## 3. 返回字段说明

- `providers`: 当前实际使用的 ONNX provider
- `metrics`: 推理耗时和当前进程资源占用信息
- `metrics.total_elapsed_ms`: 整个请求处理耗时，单位毫秒
- `metrics.inference_elapsed_ms`: ONNX 模型前向推理耗时，单位毫秒
- `metrics.cpu_elapsed_ms`: 本次请求占用的进程 CPU 时间，单位毫秒
- `metrics.process_current_rss_mb`: 当前进程内存占用，单位 MB
- `metrics.process_peak_rss_mb`: 当前进程历史峰值内存占用，单位 MB
- `rating`: 评级标签
- `characters`: 角色标签
- `general`: 普通标签
- `caption`: 逗号拼接后的标签文本
