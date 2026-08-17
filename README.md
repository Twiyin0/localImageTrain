# 4GB 显存可用的 WaifuDiffusion Tagger 本地部署

这个项目把 [SmilingWolf/wd-tagger](https://huggingface.co/spaces/SmilingWolf/wd-tagger) 做成了一个更适合 `4GB` 显存机器的本地版：

- 推理默认使用 `SmilingWolf/wd-convnext-tagger-v3` 的 `ONNX` 版本，显存和内存压力都更低。
- 训练默认使用 `SmilingWolf/wd-vit-tagger-v3` 做 `PyTorch + timm` 微调，并且默认只训练分类头，适合 `RTX 3050 4GB` 这类卡。

## 1. 环境

推荐：

- Python `3.11`
- Windows 10/11、macOS 或 Linux
- Windows 本地推理可使用 NVIDIA GPU；macOS/Linux 默认使用 CPU ONNX 运行时

重要：

- 不要直接用系统全局 `python app.py`
- 请优先使用项目虚拟环境里的 Python：`.\.venv\Scripts\python.exe`
- 这是为了避免误用全局环境中的 `onnxruntime-gpu`，尤其是 `1.27+` 默认会切到 `CUDA 13`

Windows 一键安装：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\app_setup.ps1
```

macOS / Linux 一键安装：

```bash
sh scripts/app_setup.sh
```

如果你要训练，再额外加训练依赖：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\app_setup.ps1 -WithTraining -TorchIndexUrl https://download.pytorch.org/whl/cu121
```

```bash
WITH_TRAINING=1 sh scripts/app_setup.sh
```

Windows 上面的 `torch + cu121` 组合适用于常见 CUDA 12.x 驱动；macOS/Linux 如果要训练，默认从 PyPI 安装对应平台的 PyTorch。

统一脚本都放在 `scripts/`：

- `scripts/app_setup.ps1` / `scripts/app_setup.sh`：一键安装运行环境
- `scripts/run_in_windows_by_localMode.ps1`：Windows 本机模型推理前端
- `scripts/run_in_windows_by_clientMode.ps1`：Windows 远程 API 客户端前端
- `scripts/run_in_windows_by_serverMode.ps1`：Windows API 服务端
- `scripts/run_in_macos_linux_by_localMode.sh`：macOS/Linux 本机模型推理前端
- `scripts/run_in_macos_linux_by_clientMode.sh`：macOS/Linux 远程 API 客户端前端
- `scripts/run_in_macos_linux_by_serverMode.sh`：macOS/Linux API 服务端

这些 Linux 脚本已在 Debian NAS 上通过 `sh -n` 和 Docker API stream 验证。

## 2. 前端结构

现在这个项目有两个前端：

- 根目录 `app.py`：远程 NAS API 客户端前端，本机只负责上传和展示结果
- `/Gradio/app.py`：保留的本地 Gradio 前端，继续使用本机模型推理
- `wd-tagger-webui`：NAS / Docker 侧的 Node.js 静态前端，只负责调用 Python API
- 前端已同步新版 UI：会显示耗时、远端资源占用、缓存命中、风险标签高亮，并在处理完成后自动展开结果区。
- 图像输入支持本地上传和网络 URL；批量 URL 可用逗号、分号、竖线或换行分割。
- 右下角 Gradio 原生 `settings` 可修改导出文件名模板，默认 `${origin_filename}_tagged${origin_ext}`，批量压缩包会使用 `.zip`。
- 标签语言支持原文和中文。中文输出不再调用翻译 API，而是使用 `datasets/selected_tags_cn.csv` 的离线对照表；要改日常用词，直接改这个 CSV 的 `translatedname`。

## 3. 启动远程 NAS 客户端前端

```powershell
.\.venv\Scripts\python.exe app.py --host 127.0.0.1 --port 7860
```

或直接：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_in_windows_by_clientMode.ps1
```

macOS / Linux：

```bash
sh scripts/run_in_macos_linux_by_clientMode.sh
```

浏览器打开：

```text
http://127.0.0.1:7860
```

默认远程 API 指向：

```text
http://10.1.0.2:8000
```

在界面里可直接修改远程 API 地址和 API Key。

远程前端默认指向 `http://10.1.0.2:8000`，也可以通过环境变量覆盖：

```powershell
$env:WD_TAGGER_REMOTE_API_URL = "http://your-nas:8000"
$env:WD_TAGGER_REMOTE_API_KEY = "your-api-key"
```

三个统一启动入口都支持 `-ListenHost` / `-Port` 参数，也支持 `HOST` / `PORT` 环境变量：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_in_windows_by_clientMode.ps1 -ListenHost 127.0.0.1 -Port 7860
powershell -ExecutionPolicy Bypass -File scripts\run_in_windows_by_localMode.ps1 -ListenHost 127.0.0.1 -Port 7861
powershell -ExecutionPolicy Bypass -File scripts\run_in_windows_by_serverMode.ps1 -ListenHost 127.0.0.1 -Port 8000
```

```bash
HOST=127.0.0.1 PORT=7860 sh scripts/run_in_macos_linux_by_clientMode.sh
HOST=0.0.0.0 PORT=7861 sh scripts/run_in_macos_linux_by_localMode.sh
HOST=127.0.0.1 PORT=8000 sh scripts/run_in_macos_linux_by_serverMode.sh
```

Linux 服务器或 Docker 外部访问 WebUI 时，本地模式必须监听 `0.0.0.0`；脚本默认已经使用该地址。若只在当前机器浏览器访问，可显式设置 `HOST=127.0.0.1`。此外还需要在服务器防火墙或云安全组放行 TCP `7861`。

## 4. 启动保留的本地 Gradio 前端

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_in_windows_by_localMode.ps1
```

macOS / Linux：

```bash
sh scripts/run_in_macos_linux_by_localMode.sh
```

也可以直接运行：

```powershell
.\.venv\Scripts\python.exe Gradio\app.py --host 127.0.0.1 --port 7861
```

如果你要继续用本机 GPU / 本地模型推理，再看下面这一节。

## 5. 本地模型推理说明

如果你之前已经装过 `onnxruntime-gpu 1.27+ / 1.28+`，建议在当前项目虚拟环境里重装成 CUDA 12 兼容版本：

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y onnxruntime-gpu
.\.venv\Scripts\python.exe -m pip install "onnxruntime-gpu==1.26.0" --force-reinstall
```

之所以这样改，是因为根据 ONNX Runtime 官方 CUDA Execution Provider 文档，`1.27.x-1.29.x` 的 PyPI GPU 包默认基于 `CUDA 13.0 + cuDNN 9.x`；而 `1.21.x-1.26.x` 仍是 `CUDA 12.x + cuDNN 9.x` 路线，更适合和 `PyTorch cu121` 一起用。

首次启动会自动下载模型到：

```text
.cache/wd_tagger
```

如果你当前网络访问 `huggingface.co` 不稳定，可以在启动前指定镜像：

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
python Gradio\app.py --host 127.0.0.1 --port 7861
```

如果你已经手动下载好了 `model.onnx` 和 `selected_tags.csv`，也可以完全离线运行：

```powershell
$env:WD_TAGGER_MODEL_DIR = "E:\models\wd-convnext-tagger-v3"
python Gradio\app.py --host 127.0.0.1 --port 7861
```

也可以直接放到项目的 `models` 目录，启动时会优先扫描本地模型；发现完整模型后不会再访问 Hugging Face：

```text
models/
  wd-vit-tagger-v3/
    model.onnx
    selected_tags.csv
  wd-swinv2-tagger-v3/
    model.onnx
    selected_tags.csv
```

如果存在多个模型，会优先选择与 `WD_TAGGER_REPO_ID` 同名的目录，例如 `SmilingWolf/wd-vit-tagger-v3` 会优先使用 `models/wd-vit-tagger-v3`。

## 6. 命令行推理

```powershell
.\.venv\Scripts\python.exe infer.py your_image.png --json-out outputs/result.json
```

使用本地模型目录：

```powershell
.\.venv\Scripts\python.exe infer.py your_image.png --model-dir E:\models\wd-convnext-tagger-v3 --json-out outputs/result.json
```

切换模型：

```powershell
python infer.py your_image.png --repo-id SmilingWolf/wd-vit-tagger-v3
```

启用自动阈值：

```powershell
python infer.py your_image.png --general-mcut --character-mcut
```

## 7. 缓存策略

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

## 8. 4GB 显存训练方案

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

默认方案只训练分类头，适合 4GB 显存：

```powershell
.\.venv\Scripts\python.exe train.py --manifest your_manifest.csv --epochs 3 --batch-size 1 --grad-accum 8 --gradient-checkpointing
```

这相当于：

- 单卡小 batch
- 梯度累积
- 混合精度
- 可选梯度检查点
- 默认冻结 backbone，只训练 head

输出文件在：

```text
outputs/finetune
```

主要包含：

- `best.pt`
- `train_summary.json`

训练完可以直接用微调权重推理：

```powershell
.\.venv\Scripts\python.exe infer_finetuned.py your_image.png --checkpoint outputs/finetune/best.pt
```

### 如果显存还是爆

按顺序调整：

1. 保持 `--batch-size 1`
2. 提高 `--grad-accum` 到 `16`
3. 不要加 `--unfreeze-backbone`
4. 保持 `--gradient-checkpointing`
5. 先用 `wd-vit-tagger-v3`，不要上 `vit-large` 或 `eva02-large`

## 9. 这个仓库里的文件

- `app.py`: 远程 NAS API 客户端 Gradio 界面
- `Gradio/app.py`: 保留的本地 Gradio 界面
- `infer.py`: 命令行推理
- `train.py`: 4GB 友好的微调脚本
- `infer_finetuned.py`: 微调权重推理
- `wd_tagger/`: 核心实现

## 10. 说明

- 官方 Space 使用的是 `Gradio + ONNX Runtime + Hugging Face Hub`。
- `wd-vit-tagger-v3` 模型卡给出了 `timm.create_model("hf_hub:SmilingWolf/wd-vit-tagger-v3", pretrained=True)` 的标准加载方式。
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
powershell -ExecutionPolicy Bypass -File scripts\run_in_windows_by_serverMode.ps1
```

macOS / Linux：

```bash
sh scripts/run_in_macos_linux_by_serverMode.sh
```

接口文档：

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Markdown 文档: [docs/API.md](/e:/project/huggingface/docs/API.md)

统一处理接口：

```text
POST /process
```

流式单图接口：

```text
POST /process/stream?type=tag&filename=demo.png
POST /tag/stream?filename=demo.png
```

支持的 `type`：

- `tag`: 只返回 tag 文本
- `arrary`: 返回 tag 字符串数组
- `tagimg`: 返回带 tag 元数据的图片
- `json`: 批量扫描目录或图片并输出 JSON/CSV
- `mulitagimg`: 批量输出带元数据图片并打包 zip

输入来源：

- 单张模式：`image` 或 `image_url`
- 批量模式：`images`、`image_urls`、`input_dir` 可组合使用
- `image_urls` 支持用 `,`、`;`、`|` 或换行分割

导出文件名模板：

- 表单字段：`output_filename_template`
- 默认：`${origin_filename}_tagged${origin_ext}`
- 可用变量：`${origin_filename}`、`${origin_basename}`、`${origin_ext}`、`${type}`、`${index}`、`${date}`、`${time}`、`${timestamp}`

所有处理接口还会在响应头里返回：

- `X-WD-Backend-Process-Time-Ms`：后端模型处理时间
- `X-WD-Backend-Total-Time-Ms`：后端总处理时间

上传图片打标示例：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/process" -H "X-API-Key: your-api-key" -F "type=tag" -F "image=@outputs/test_input.png"
```

流式上传示例：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/process/stream?type=tag&filename=test_input.png" -H "X-API-Key: your-api-key" -H "Content-Type: image/png" --data-binary "@outputs/test_input.png"
```

批量 ZIP 流式上传示例：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/process/stream?type=json&filename=images.zip&export_format=inline" -H "X-API-Key: your-api-key" -H "Content-Type: application/zip" --data-binary "@outputs/images.zip"
```

URL 批量示例：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/process" -H "X-API-Key: your-api-key" -F "type=json" -F "image_urls=https://example.com/a.jpg;https://example.com/b.png" -F "export_format=inline"
```

## 12. NAS Docker 部署

面向 `Debian / Intel N100 / 8GB RAM` 的 CPU 容器：

```bash
docker build -t localimagetrain-wd-tagger-api -f Dockerfile.api .
docker build -t localimagetrain-wd-tagger-webui -f Dockerfile.webui .
docker compose -f compose.nas.yml up -d --no-build
```

默认端口：

- `8000` -> API
- `7861` -> NAS WebUI

默认使用：

- `onnxruntime` CPU
- `SmilingWolf/wd-convnext-tagger-v3`
- API key auth via `.env.nas`
- 模型默认在首次推理时自动下载到持久化缓存；离线部署可在 `.env.nas` 中设置 `WD_TAGGER_MODEL_DIR=/app/models/wd-convnext-tagger-v3`

自动部署脚本：

- [deploy_nas.py](/e:/project/huggingface/deploy_nas.py)
- [docs/NAS-DEPLOY.md](/e:/project/huggingface/docs/NAS-DEPLOY.md)

离线模型准备脚本：

- [scripts/prepare_offline_model.ps1](/e:/project/huggingface/scripts/prepare_offline_model.ps1)
