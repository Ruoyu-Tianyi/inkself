# Inkself 技术结构

Inkself 是少样本个人字迹应用，网页工作室、Windows 桌面和安装版共用本机单用户服务。公开源代码不等于已经提供公开在线服务。

## 网页主流程

`web/static/` 提供采样、上传、试写、作品和评价页面。FastAPI 服务 `web/app.py` 管理本地档案、队列、下载与反馈。`launch.py` 在检查服务状态后启动 loopback 服务，Windows 入口为 `Start Inkself.cmd`。

流程：指定短文 → 自然书写图片 → EXIF 方向修正、背景归一化及适度倾斜校正 → 文字行切分 → 人工选择 → 档案与模型风格编码 → 新词图生成 → A4 排版及 PDF → 内容与相似度人工评价。

`web/samples.py` 不把切行成功当作 OCR、转录匹配或相似度验收通过。严重透视、多栏、竖排及弯曲纸页不属于已验证条件。

`web/capture_prompt.py` 维护版本化的英文/数字采样及可选数学区，提供两页 PDF。采样包括常用符号、希腊字母和上下标示例。检查时用户分别标记英文/数字行和数学行；`selected_lines` 只用于英文风格编码，`math_lines` 单独保留并标记为待对齐/核对，二者不能重叠。旧版仅提交 `lines` 的接口仍兼容，缺省数学行为空。切分顺序不被用来自动认定符号内容。

## 少样本生成

`web/runtime/vatr_worker.py` 在独立进程运行固定版本 VATr++ 生成器。参考文字行被缩放并切为图块，编码器计算风格表示，生成器按指定新内容输出整词图像。编码可缓存复用，不对每个用户进行模型训练。

仅初始化并严格加载预训练生成器，不初始化训练判别器、OCR、评价网络和优化器。推理离线；字符原型、模型源码及权重来自固定版本的资产清单，不放入 Git。完整安装版的 `InkselfAI.exe --worker request.json` 自带 CPU Torch 等依赖；源代码开发环境仍可使用独立 Python 进程。

`web/model_setup.py` 提供首次使用准备：从固定 Hugging Face revision 获取 `web/model-assets.json` 中列出的文件，支持断点续传，核对大小与 SHA-256 后才标记就绪。检查缓存随文件大小、修改时间及清单变化失效。下载只读取公开模型资产，不上传样本。下载的上游代码通过运行时包路径加载；不把用户上传的图像或 Markdown 当作代码。

按词排版为 A4 图片与 PDF，保留显式换行，以普通词距呈现多个空格；支持字号、行距、墨色和种子。它不是段落级连续笔画模型。报告记录输入与来源，但尚无独立 OCR 自动核对，结果默认待人工评价。

## 存储与服务边界

源码模式的档案、原图、文字行、风格缓存、任务、PDF、日志和反馈位于 `.local/web-data/`；便携模式使用 EXE 旁的 `data`；安装模式使用 `%LOCALAPPDATA%/Inkself/data`，模型在其 `models/vatrpp` 下。`INKSELF_DATA` 可覆盖数据位置。不需要把样本发往云端，升级及卸载默认保留安装模式的数据目录。

服务仅监听 `127.0.0.1`，包含 Host、同源令牌、上传限制、下载白名单和排队上限。它没有远程多用户认证和租户隔离，不能直接开放监听地址当作正式在线产品。云端仍需认证、私有存储、持久队列及独立推理部署。

## 辅助字形引擎

`engines/glyphs/` 保留逐字定位采样、切分、联系表审核和真实字形复用，只能渲染已经采样的字符。其确定性 PDF/SVG 可检查字符映射、哈希、页界和可见墨迹。

该引擎与网页生成模型是独立流程。其上下标、数学符号及确定性映射能力不能直接宣称为网页模型的能力；其测试也不能证明网页真人相似度或生成文字准确性通过。

进度见 [产品路线](roadmap.md)，操作见 [使用指南](web-guide.md)。


## Document and math pipeline

`web/markdown_document.py` converts a bounded Markdown subset into editable text and mathematical notation. It preserves document order and stores source text, parser statistics and conversion warnings locally; jobs record the source hash and whether the imported text was edited. It does not render HTML, follow links, run code or reinterpret document text as instructions. Markdown emphasis retains visible words rather than changing pen weight.

The reference and habit modes preflight content through `runtime/document_input.py`. Opted-in math is parsed by the bounded, non-executing `math_syntax.py` parser. `math_renderer.py` builds baseline-aware boxes from personal rasters and explicitly allowed `math_glyphs.py` supplements; source provenance and the AST are retained. Mathematical structure is not an OCR or symbolic solving service.

`math_strokes.py` redraws scalable delimiters using a reviewed glyph's centreline when available, keeping pen thickness independent of delimiter height. Approved fallback delimiters use supplemental paths. Radical hooks and overbars form a continuous procedural stroke, with separate clearance for root indices and contents. Sample-derived pen width/slant and seeded occurrence variation improve consistency; they do not establish that the writer's personal radical gesture has been learned. Structural stroke methods and variation identifiers are recorded with the formula.

`document_layout.py` plans complete lines and semantic keep groups before assigning pages. It then writes one raster page at a time, with positions, baselines, warnings and display-formula scaling in `layout.json`. Experiment fingerprints include parser, glyph, math and document layout code; image/PDF/layout/report files are hashed for replay. Unknown commands and unapproved missing glyphs fail before a job is queued.

## Windows desktop

`desktop.py` dispatches the native window, isolated loopback server and frozen local workers. `desktop_runtime.py` owns the server process tree through a Windows Job Object, verifies a per-launch instance identity, and enforces one controller per data folder. Startup probes use direct loopback HTTP without proxy or TLS configuration. `web/runtime_paths.py` separates read-only bundled resources, portable/installed user data and neural assets; source development paths remain compatible.

PyInstaller bundles public web sources for renderer fingerprints. Core glyph/math workers re-enter `Inkself.exe --worker`; neural workers use `ai-runtime/InkselfAI.exe --worker`, overridable through `INKSELF_MODEL_WORKER`, with optional external Python compatibility. The AI runtime owns its task log and exits without a GUI. Model code, weights and prototypes are downloaded separately, rather than frozen into this runtime.

`scripts/build_installer.py` validates explicit file allowlists and checksums before invoking Inno Setup. Installation uses the current user's program directory, adds shortcuts and writes an installed-mode marker. It preserves user data when upgrading or uninstalling. The default complete installer combines the core application and AI runtime, without model assets or personal data; an explicit offline-model build is labelled internal-test-only. Explicit profile imports validate relative asset paths and checksums, reject links, skip existing IDs and never copy old absolute job requests. See [desktop guide](desktop-guide.md).
