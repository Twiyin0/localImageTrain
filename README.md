# WaifuDiffusion Tagger for macOS

这个项目现在按 `macOS` 本地运行整理，且只使用项目目录里的 `.venv`，不会改系统自带的 `python3 3.9.6`。

## 环境要求

- macOS
- Apple Silicon 或 Intel Mac
- 项目虚拟环境里的 Python `3.11`

重要说明：

- 不要直接用系统 `python3`
- 当前项目要求 `Python 3.11+`
- 如果误用 `3.9.6`，程序会直接报错并提示当前解释器路径

## 1. 在项目目录安装本地 Python 3.11

这个步骤会把 `Python 3.11.15` 编译到项目目录：

```bash
bash scripts/bootstrap_python311_macos.sh
```

安装位置：

```text
.local/python-3.11.15
```

这不会替换系统 Python，也不会改全局 PATH。

## 2. 创建项目 `.venv`

```bash
bash scripts/setup_macos.sh
```

默认会：

- 用项目里的 `Python 3.11.15` 创建 `.venv`
- 安装 `requirements.txt`
- 安装训练依赖 `requirements-train.txt`
- 安装适合 macOS 的 `torch / torchvision / torchaudio`

如果你只想装推理环境：

```bash
INSTALL_TRAINING=0 bash scripts/setup_macos.sh
```

## 3. 启动本地 UI

```bash
bash scripts/run_app_macos.sh
```

或直接：

```bash
./.venv/bin/python app.py --host 127.0.0.1 --port 7860
```

浏览器打开：

```text
http://127.0.0.1:7860
```

首次启动会自动下载模型到：

```text
.cache/wd_tagger
```

## 4. 启动 API

```bash
bash scripts/run_api_macos.sh
```

或直接：

```bash
./.venv/bin/python api.py --host 127.0.0.1 --port 8000
```

接口文档：

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Markdown 文档: [docs/API.md](/Volumes/UMIS1TB/Project/python/huggingface/waifu/docs/API.md)

## 5. 命令行推理

```bash
./.venv/bin/python infer.py your_image.png --json-out outputs/result.json
```

使用本地模型目录：

```bash
./.venv/bin/python infer.py your_image.png --model-dir models/wd-convnext-tagger-v3 --json-out outputs/result.json
```

切换模型：

```bash
./.venv/bin/python infer.py your_image.png --repo-id SmilingWolf/wd-vit-tagger-v3
```

## 6. 训练

默认会优先选择：

- `cuda`，如果机器有 NVIDIA CUDA
- `mps`，如果是支持 Metal 的 macOS
- `cpu`，否则回退到 CPU

训练示例：

```bash
./.venv/bin/python train.py --manifest your_manifest.csv --epochs 3 --batch-size 1 --grad-accum 8 --gradient-checkpointing
```

训练输出目录：

```text
outputs/finetune
```

微调后推理：

```bash
./.venv/bin/python infer_finetuned.py your_image.png --checkpoint outputs/finetune/best.pt
```

## 7. ONNX Runtime 说明

macOS 默认使用：

- `onnxruntime`
- `CPUExecutionProvider`

项目不再默认安装 `onnxruntime-gpu`，因为这套配置是面向 Windows / CUDA 的，不适合当前的 macOS 本地环境。

如果你已经手动下载好了模型，也可以离线运行：

```bash
export WD_TAGGER_MODEL_DIR="$PWD/models/wd-convnext-tagger-v3"
./.venv/bin/python app.py --host 127.0.0.1 --port 7860
```

## 8. 主要文件

- `app.py`: 本地 Gradio UI
- `api.py`: FastAPI 服务
- `infer.py`: 命令行 ONNX 推理
- `train.py`: 微调训练入口
- `infer_finetuned.py`: 微调权重推理
- `wd_tagger/`: 核心实现

## 9. 说明

仓库里保留了原来的 Windows PowerShell 脚本和 NAS 部署文件，但本地开发流程现在以 macOS 为主。
