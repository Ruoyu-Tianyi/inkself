# Inkself

Few-shot handwriting imitation from a short reference sample, with a local web studio, Windows and macOS desktop packages, bundled CPU inference runtime and PDF export.

通过一段自然书写的英文与数字样本，生成带有个人书写风格的新内容。**当前为本机单用户网页及 Windows/macOS 桌面预览版，真人验收进行中，尚未达到稳定正式版的质量门槛。**

## 桌面预览版下载

前往 [GitHub Releases](https://github.com/Ruoyu-Tianyi/inkself/releases) 下载 Windows x64 安装包，或 macOS Apple Silicon / Intel DMG。Mac 应用拖入 Applications 后运行；个人数据保存在用户目录，不写入应用包。

Windows 包尚未签名；Mac 包采用临时签名，尚无 Apple Developer ID 签名或公证。操作系统可能提示拦截，请核对官方发布和 SHA-256，并阅读 [Mac 安装说明](docs/macos-guide.md) 或 [Windows 桌面指南](docs/desktop-guide.md)。不要关闭系统全局安全保护。

## 当前能力

- 英文/数字采样及可选数学/希腊字母采样，PNG/JPEG/WebP 上传、文字行切分和类型确认。
- 多字迹档案、个人风格缓存及字号、行距、墨色偏好。
- 固定版本 VATr++ 预训练生成器的真实离线 CPU 推理，可生成样本之外的新词句及数字。
- 原图对照、A4 预览、PDF 下载、历史作品和人工评价。
- 长文按完整行规划分页，尽量保留题号、公式与解释，减少段落孤行，并按页输出。习惯适配/字形保真上限为 20,000 字符。
- 词间距按可见笔画计算，保存样本中的间距分布并生成可复现的自然变化；证据不足时明确使用保守估计。
- 数学输入支持行内/独立公式、上下标、分式、根号、嵌套括号、求和、积分和希腊字母；括号与根号参考样本笔宽、倾斜和轻微变化绘制，缺失数学字形须明确允许使用配套手写字形。
- Markdown 文件导入：本机解析标题、段落、列表、强调和公式，预览后直接生成；保存原文及转换提示。
- 作业答卷输出：数字题号、选择题分栏、表格、文本决策树、常见下标记号、同题分页和表头重复；可填写首面信息，需已核对个人字形档案。
- Windows 当前用户安装器、Mac 双架构应用和独立本地 CPU AI 引擎，首次下载并校验固定模型；无需用户配置 Python 或 API 密钥，个人数据独立保存。
- 可复用的批量对照流程：固定测试文本、输入快照、模型/代码指纹、HTML 对照页与逐文件复现校验。
- 实验性样本习惯适配：从人工核对的词图拟合共享字母尺寸、部分正文异体字、抬笔与连接统计；可将部分规则应用到未见新词。
- 习惯适配中的符号变化：校正过大的百分号和过粗斜线，加入可复现的轻微形状变化，并保护小字号的小数点、冒号与百分号圆圈。
- 实验性原稿字形库：经人工标注和逐字核对后，可选择原稿字形保真，或模型字宽/倾斜校正并对原稿数字做有界形态与间距变化。该字形库目前需开发者准备，尚未自动从上传图片建立。

当前按词生成与排版，不是完整段落级连续笔画。习惯适配仍使用原稿栅格笔画骨架，不是端到端的笔画轨迹生成器；尚不能从任意未标注短样本自动克隆字迹。默认模型不使用通用字体替换，也不要求逐字采集所有字符。另有需人工逐字核对的原稿字形保真对照模式：复用已见词、片段及字母，不能推断未见字符或连笔。

## 快速开始

Windows 普通用户使用完整安装版 **Inkself-Setup.exe**：

1. 安装并启动 Inkself，点击“准备本地 AI”。首次从固定模型版本下载约 580 MB 文件，完成校验后可离线使用。
2. 自然抄写应用提供的英文与数字；需要公式时加抄可选数学区。拍照上传，逐行选择英文/数字、数学/希腊字母或不使用。
3. 输入新内容或导入 Markdown，生成试写，对照原图逐字检查。
4. 下载 PDF，记录内容准确性、字迹相似度与自然程度。

安装版面向 Windows 10/11 的兼容 x64 环境，内置 CPU 推理运行时；完整安装流程仍按内测标准验证。它解决环境配置门槛，尚不代表任意短样本高相似度克隆已通过质量验收。首次下载需要网络，个人样本和文档不会随下载发送。含结构化公式的 Markdown 仍需已核对的个人字形档案，见 [桌面指南](docs/desktop-guide.md)、[Markdown 导入](docs/markdown-import.md) 和 [AI 工作流程](docs/ai-workflow.md)。

开发者也可从源码运行。Windows，Python **3.10–3.12**：

```powershell
git clone https://github.com/Ruoyu-Tianyi/inkself.git
cd inkself
./setup-web.ps1
```

安装后双击 **Start Inkself.cmd**，打开 `http://127.0.0.1:8765`。已安装的电脑无需重复安装。模型和依赖下载需要网络及额外磁盘空间；遵循本机 PowerShell 执行策略，不需要关闭全局保护。

详细安装、停止服务和排错见 [使用指南](docs/web-guide.md)。

基础便携包仍可通过 `python scripts/build_desktop.py` 构建，菜单保留旧档案导入与已有模型环境连接；基础包本身不包含 AI 运行时。

## 验证状态与边界

| 项目 | 状态 |
| --- | --- |
| 本地自动测试 | 最近一次 Windows 检查 244 项：243 通过，1 项实际符号链接测试因 Windows 权限跳过；Mac 原生检查结果见 GitHub Actions |
| 真实模型推理 | 源码环境及独立 InkselfAI.exe 已实际生成，验证缓存复用、完整结果与任务日志；不代表相似度通过 |
| 网页流程 | 已试跑上传、确认、生成、预览和 PDF；检查过桌面/手机宽度布局 |
| 本人相似度与真人泛化 | **验收进行中，尚无通过结论** |
| 全面内容准确性 | **尚未全面验收；习惯适配已补充数字/符号回归检查，默认模型仍可能误写** |
| 独立 OCR 与自动纠错 | 尚未接入，输出默认待人工核对 |
| 远程多用户服务 | 尚未部署，本机服务不应直接暴露到公网 |

当前支持英文大小写、数字和模型字母表内的部分标点。默认神经模型暂不支持中文、等号、美元符号及结构化公式。数学模式需选择习惯适配或字形保真，并以 $...$ / $$...$$ 输入；未采样数学字形可显式启用配套路径，具体写法尚未从个人样本学得。生成成功、内容日志或下载成功不能证明文字写对了，也不能证明字迹像本人。

## 开发与结构

```sh
# 在项目 Python 环境中运行
python -m unittest discover -s tests -v
node --check web/static/app.js
python -m uvicorn web.app:app --host 127.0.0.1 --port 8765
```

- `web/`：网页、本地 API、样本处理和 VATr++ 推理适配器。
- `scripts/setup_model.py`：固定版本模型资产下载与大文件哈希检查。
- `web/model_setup.py`、`web/model-assets.json`：首次使用下载、断点续传和逐文件校验。
- `ai_worker.py`、`packaging/`、`scripts/build_*.py`：独立 AI 运行时、便携程序和当前用户安装器；公共安装包不嵌入模型权重。
- `engines/glyphs/`：逐字采样和确定性字形复用工具，用作辅助及对照，不属于网页的少样本生成模型。
- `tests/`：合成样本及接口测试，不代表真人相似度通过。

习惯拟合的开发者工作流及验证边界见 [习惯适配实验](docs/habit-adapter.md)；批量生成和携带输入快照重跑见 [可复现对照流程](docs/experiment-workflow.md)。仓库提供 [三组测试文本](examples/evaluation-suite.json)，不包含个人字迹。

长文与公式的输入方式、配套字形来源、AI 依赖与边界见 [数学与文档指南](docs/math-and-documents.md)。

参见 [技术结构](docs/architecture.md)、[产品路线](docs/roadmap.md) 和 [辅助字形工作流](engines/glyphs/workflow.md)。

## 模型、数据与隐私

网页使用 [VATr++](https://huggingface.co/blowing-up-groundhogs/vatrpp) 固定版本生成器；来源、许可与适配方式见 [第三方模型说明](docs/model-notice.md)。公共安装包内置推理依赖，不内嵌权重、上游模型代码或字符原型；首次由用户操作从模型来源下载到本机。它们不随源码仓库推送。

样本、转录、风格缓存、文档及包含完整输入的报告默认只保存在本机，已排除 Git 跟踪。仅使用本人或经授权的样本，不提供签名或身份认证功能。

早期实验受 [TypeScribe](https://github.com/rudyoactiv/typescribe-handwriting) 启发；当前网页的静态图片风格生成使用 VATr++，不是 TypeScribe 的笔迹轨迹 priming 接口。

## 许可与商业授权

本项目自有代码采用 [PolyForm Noncommercial 1.0.0](LICENSE)，属于限制用途的源码可用项目。非商业用途及许可明确列出的机构用途可按条款使用；超出许可范围的商业使用须取得单独书面授权，作者保留商业化授权权利。参见 [商业授权说明](COMMERCIAL-LICENSE.md) 和 [贡献政策](CONTRIBUTING.md)。第三方组件、字体与模型保留各自许可。
