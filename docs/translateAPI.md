# Translation API

当前服务部署地址：

- Base URL: `http://10.10.1.9:8001`
- Container: `translator-n100`
- Models: `gaudi/opus-mt-zh-en-ctranslate2` + `gaudi/opus-mt-en-zh-ctranslate2`

## 能力说明

当前模型支持 `中文 <-> 英文` 双向翻译。

## 1. 健康检查

### 请求

```http
GET /health
```

### 示例

```bash
curl http://10.10.1.9:8001/health
```

### 返回

```json
{
  "status": "ok"
}
```

## 2. 翻译接口

### 请求

```http
POST /translate
Content-Type: application/json
```

### 请求体

```json
{
  "text": "你好，世界",
  "source_lang": "zh",
  "target_lang": "en",
  "beam_size": 1,
  "max_decoding_length": 128
}
```

### 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `text` | `string` 或 `string[]` | 是 | - | 单条文本或批量文本 |
| `source_lang` | `string` | 否 | 自动识别 | `zh` 或 `en` |
| `target_lang` | `string` | 否 | 自动推断 | `zh` 或 `en` |
| `beam_size` | `integer` | 否 | `1` | 解码 beam size，范围 `1-8` |
| `max_decoding_length` | `integer` | 否 | `128` | 最大生成长度，范围 `1-512` |

### 单条示例

```bash
curl -X POST http://10.10.1.9:8001/translate \
  -H 'Content-Type: application/json' \
  -d '{"text":"你好，世界","source_lang":"zh","target_lang":"en"}'
```

### 单条返回

```json
{
  "model": "zh-en",
  "translations": [
    "Hello, world."
  ]
}
```

### 批量示例

```bash
curl -X POST http://10.10.1.9:8001/translate \
  -H 'Content-Type: application/json' \
  -d '{"text":["你好，世界","今天天气很好。"],"source_lang":"zh","target_lang":"en","beam_size":1,"max_decoding_length":128}'
```

### 批量返回

```json
{
  "model": "zh-en",
  "translations": [
    "Hello, world.",
    "The weather is nice today."
  ]
}
```

## 3. 错误返回

服务内部异常时会返回：

```json
{
  "detail": "error message"
}
```

常见原因：

- 模型加载失败
- 输入格式不合法
- 推理过程中发生异常

## 4. 备注

如果不传 `source_lang` / `target_lang`，服务会自动按文本内容判断方向：

- 中文默认翻英文
- 英文默认翻中文
