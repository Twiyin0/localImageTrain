# Translation API

翻译 API 已废弃，项目不再请求外部翻译服务。

当前中文标签输出完全由 `datasets/selected_tags_cn.csv` 控制：

- `name`：原始 tag 名，通常来自模型的 `selected_tags.csv`
- `translatedname`：中文展示名

API 和前端仍保留语言选择：

- `zh`：使用 `datasets/selected_tags_cn.csv`
- `en`：保留原始 tag

如果需要调整词语，例如把 `white_socks` 显示为 `白丝`，直接修改 `datasets/selected_tags_cn.csv` 对应行即可。
