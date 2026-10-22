# Inkself

Few-shot handwriting imitation from a short reference sample, with a local web studio for capture, generation, review and PDF export.

通过一段自然书写的英文与数字样本，生成带有个人书写风格的新内容。**当前为本机单用户网页内测版，真人验收进行中，尚未达到正式发布的质量门槛。**

## 当前能力

- 指定采样内容、PNG/JPEG/WebP 上传、文字行切分和人工确认。
- 多字迹档案、个人风格缓存及字号、行距、墨色偏好。
- 固定版本 VATr++ 预训练生成器的真实离线 CPU 推理，可生成样本之外的新词句及数字。
- 原图对照、A4 预览、PDF 下载、历史作品和人工评价。

当前按词生成与排版，不是完整段落级连续笔画。它不使用通用字体替换，也不要求逐字采集所有字符。

## 快速开始

Windows，Python **3.10–3.12**：

```powershell
git clone https://github.com/Ruoyu-Tianyi/inkself.git
cd inkself
./setup-web.ps1
```

安装后双击 **Start Inkself.cmd**，打开 `http://127.0.0.1:8765`。已安装的电脑无需重复安装。模型和依赖下载需要网络及额外磁盘空间；遵循本机 PowerShell 执行策略，不需要关闭全局保护。

1. 自然抄写网页提供的英文与数字，拍照上传。
2. 检查文字行，排除印刷文字、杂物和切分错误。
3. 输入新内容，生成试写，对照原图逐字检查。
4. 下载 PDF，评价内容准确性、字迹相似度与自然程度。

详细安装、停止服务和排错见 [使用指南](docs/web-guide.md)。

## 验证状态与边界

| 项目 | 状态 |
| --- | --- |
| 本地自动测试 | 29 项通过，覆盖网页与辅助字形引擎 |
| 真实模型推理 | 已用合成参考样本运行，并验证风格缓存复用 |
| 网页流程 | 已试跑上传、确认、生成、预览和 PDF；检查过桌面/手机宽度布局 |
| 本人相似度与真人泛化 | **验收进行中，尚无通过结论** |
| 全面内容准确性 | **未通过验收；百分号、加号在合成测试中存在不清晰情况** |
| 独立 OCR 与自动纠错 | 尚未接入，输出默认待人工核对 |
| 远程多用户服务 | 尚未部署，本机服务不应直接暴露到公网 |

当前支持英文大小写、数字和模型字母表内的部分标点。暂不支持中文、等号、美元符号、复杂公式和上下标。生成成功、内容日志或下载成功不能证明文字写对了，也不能证明字迹像本人。

## 开发与结构

```sh
# 在项目 Python 环境中运行
python -m unittest discover -s tests -v
node --check web/static/app.js
python -m uvicorn web.app:app --host 127.0.0.1 --port 8765
```

- `web/`：网页、本地 API、样本处理和 VATr++ 推理适配器。
- `scripts/setup_model.py`：固定版本模型资产下载与大文件哈希检查。
- `engines/glyphs/`：逐字采样和确定性字形复用工具，用作辅助及对照，不属于网页的少样本生成模型。
- `tests/`：合成样本及接口测试，不代表真人相似度通过。

参见 [技术结构](docs/architecture.md)、[产品路线](docs/roadmap.md) 和 [辅助字形工作流](engines/glyphs/workflow.md)。

## 模型、数据与隐私

网页使用 [VATr++](https://huggingface.co/blowing-up-groundhogs/vatrpp) 固定版本生成器；来源、许可与适配方式见 [第三方模型说明](docs/model-notice.md)。权重及下载的上游代码保存在忽略的 `.local/`，未随本仓库重新分发。

样本、转录、风格缓存、文档及包含完整输入的报告默认只保存在本机，已排除 Git 跟踪。仅使用本人或经授权的样本，不提供签名或身份认证功能。

早期实验受 [TypeScribe](https://github.com/rudyoactiv/typescribe-handwriting) 启发；当前网页的静态图片风格生成使用 VATr++，不是 TypeScribe 的笔迹轨迹 priming 接口。
