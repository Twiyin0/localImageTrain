# WaifuDiffusion Tagger for macOS

这个仓库默认面向 macOS，使用项目内的 Python `3.11` 和本地虚拟环境，不会改动系统 Python。

项目里保留了两种使用方式：

- 根目录 `app.py`：远程 API 客户端前端，适合连接 NAS 上运行的服务
- `Gradio/app.py`：本地 Gradio 前端，直接在当前 Mac 上做 ONNX 推理

## 1. 环境准备

要求：

- macOS
- Python `3.11`
- 使用项目里的 `.venv`

先准备项目本地 Python：

```bash
./scripts/bootstrap_python311_macos.sh
./scripts/setup_macos.sh
```

如果只想装推理依赖，不装训练依赖：

```bash
INSTALL_TRAINING=0 ./scripts/setup_macos.sh
```

## 2. 本地 Gradio 前端

启动：

```bash
./scripts/run_app_macos.sh
```

或：

```bash
.venv/bin/python Gradio/app.py --host 127.0.0.1 --port 7861
```

浏览器打开：

```text
http://127.0.0.1:7861
```

首次启动会自动下载模型到：

```text
.cache/wd_tagger
```

如果已经手动下载好了 `model.onnx` 和 `selected_tags.csv`，可以指定本地模型目录：

```bash
export WD_TAGGER_MODEL_DIR="$PWD/models/wd-convnext-tagger-v3"
.venv/bin/python Gradio/app.py --host 127.0.0.1 --port 7861
```

macOS 默认使用 `CPUExecutionProvider`，避免误用 Windows/CUDA provider。

## 3. 远程 NAS 客户端前端

启动：

```bash
.venv/bin/python app.py --host 127.0.0.1 --port 7860
```

浏览器打开：

```text
http://127.0.0.1:7860
```

默认远程 API 地址是：

```text
http://127.0.0.1:8000
```

如果你要连 NAS，可在界面里填写真实地址和 API Key，或先设置环境变量：

```bash
export WD_TAGGER_REMOTE_API_URL="http://your-nas:8000"
export WD_TAGGER_REMOTE_API_KEY="your-api-key"
```

仓库里不再内置默认 API Key。

## 4. 本地 API 服务

启动：

```bash
./scripts/run_api_macos.sh
```

或：

```bash
.venv/bin/python api.py --host 127.0.0.1 --port 8000
```

## 5. 命令行推理

```bash
.venv/bin/python infer.py your_image.png --json-out outputs/result.json
```

使用本地模型目录：

```bash
.venv/bin/python infer.py your_image.png --model-dir "$PWD/models/wd-convnext-tagger-v3" --json-out outputs/result.json
```

启用自动阈值：

```bash
.venv/bin/python infer.py your_image.png --general-mcut --character-mcut
```

## 6. 缓存策略

当前推理链路已经内置两层缓存：

- 精确缓存：全局启用。同一模型、同一图片文件内容 `MD5` 相同，直接跳过模型推理
- 近似缓存：只在批量模式启用。对高相似的近重复图片复用结果，减少目录扫描时的重复算力消耗

缓存存储结构：

- 内存热点缓存：保存高频精确命中结果
- SQLite 持久缓存：`./.cache/wd_tagger/prediction_cache.sqlite3`

返回结果里会附带：

- `cache.cache_hit`: `miss` / `exact` / `similar`
- `cache.source_md5`: 当前文件 MD5
- `cache.similarity_score`: 近似命中时的相似度分数

批量 `json/csv` 结果里还会包含：

- `cache_stats.miss`
- `cache_stats.exact`
- `cache_stats.similar`

可调环境变量：

- `WD_TAGGER_EXACT_CACHE_ENABLED=1`
- `WD_TAGGER_SIMILAR_CACHE_ENABLED=1`
- `WD_TAGGER_SIMILARITY_THRESHOLD=0.985`
- `WD_TAGGER_SIMILAR_CANDIDATE_LIMIT=128`
- `WD_TAGGER_CACHE_MAX_ENTRIES=5000`
- `WD_TAGGER_MEMORY_CACHE_SIZE=512`

说明：

- `exact` 命中是可靠复用
- `similar` 命中只在批量 `json/mulitagimg` 模式下启用
- `similar` 更适合近重复图、轻微压缩版、缩放版、导出版，不建议把它理解成“同角色不同姿势一定能安全复用”
- 如果你更重视绝对准确性，可以把 `WD_TAGGER_SIMILAR_CACHE_ENABLED=0`

## 7. 训练

### 数据格式

准备一个 CSV，至少两列：

- `image`: 图片路径
- `tags`: 逗号分隔标签

示例：

```csv
image,tags
train/a.png,"1girl,solo,smile"
train/b.png,"outdoors,sky,tree"
```

### 推荐训练命令

```bash
.venv/bin/python train.py --manifest your_manifest.csv --epochs 3 --batch-size 1 --grad-accum 8 --gradient-checkpointing
```

输出文件在：

```text
outputs/finetune
```

主要包含：

- `best.pt`
- `train_summary.json`

训练完可以直接用微调权重推理：

```bash
.venv/bin/python infer_finetuned.py your_image.png --checkpoint outputs/finetune/best.pt
```

说明：

- 训练依赖会额外安装 `torch / torchvision / torchaudio`
- 当前这套 macOS 本地 Python 如果缺少 `_lzma`，训练链路可能受影响，需要先把本地 Python 3.11 构建完整

## 8. 仓库结构

- `app.py`: 远程 NAS API 客户端 Gradio 界面
- `Gradio/app.py`: 保留的本地 Gradio 界面
- `infer.py`: 命令行推理
- `train.py`: 微调脚本
- `infer_finetuned.py`: 微调权重推理
- `wd_tagger/`: 核心实现
- `wd-vit-large-tagger-v3` 和 `wd-eva02-large-tagger-v3` 体积明显更大，不适合 4GB 显存优先场景。

参考：

- 官方 Space: https://huggingface.co/spaces/SmilingWolf/wd-tagger
- `wd-vit-tagger-v3`: https://huggingface.co/SmilingWolf/wd-vit-tagger-v3
- `wd-convnext-tagger-v3`: https://huggingface.co/SmilingWolf/wd-convnext-tagger-v3
- PyTorch 安装页: https://docs.pytorch.org/get-started/locally/
- PyTorch 历史版本页: https://pytorch.org/get-started/previous-versions/

## 11. HTTP API

启动 API：

```powershell
.\.venv\Scripts\python.exe api.py --host 127.0.0.1 --port 8000
```

接口文档：

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Markdown 文档: [docs/API.md](/e:/project/huggingface/docs/API.md)

统一处理接口：

```text
POST /process
```

支持的 `type`：

- `tag`: 只返回 tag 文本
- `arrary`: 返回 tag 字符串数组
- `tagimg`: 返回带 tag 元数据的图片
- `json`: 批量扫描目录或图片并输出 JSON/CSV
- `mulitagimg`: 批量输出带元数据图片并打包 zip

所有处理接口还会在响应头里返回：

- `X-WD-Backend-Process-Time-Ms`：后端模型处理时间
- `X-WD-Backend-Total-Time-Ms`：后端总处理时间

上传图片打标示例：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/process" -H "X-API-Key: your-api-key" -F "type=tag" -F "image=@outputs/test_input.png"
```

## 12. NAS Docker 部署

面向 `Debian / Intel N100 / 8GB RAM` 的 CPU 容器：

```bash
docker compose -f compose.nas.yml up -d --build
```

默认端口：

- `8000` -> API

默认使用：

- `onnxruntime` CPU
- `SmilingWolf/wd-convnext-tagger-v3`
- API key auth via `.env.nas`
- offline model directory via `models/wd-convnext-tagger-v3`

自动部署脚本：

- [deploy_nas.py](/e:/project/huggingface/deploy_nas.py)
- [docs/NAS-DEPLOY.md](/e:/project/huggingface/docs/NAS-DEPLOY.md)

离线模型准备脚本：

- [scripts/prepare_offline_model.ps1](/e:/project/huggingface/scripts/prepare_offline_model.ps1)
