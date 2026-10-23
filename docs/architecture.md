# Inkself 技术结构

Inkself 是少样本个人字迹网页应用，当前在本机以单用户服务运行。公开源代码不等于已经提供公开在线服务。

## 网页主流程

`web/static/` 提供采样、上传、试写、作品和评价页面。FastAPI 服务 `web/app.py` 管理本地档案、队列、下载与反馈。`launch.py` 在检查服务状态后启动 loopback 服务，Windows 入口为 `Start Inkself.cmd`。

流程：指定短文 → 自然书写图片 → EXIF 方向修正、背景归一化及适度倾斜校正 → 文字行切分 → 人工选择 → 档案与模型风格编码 → 新词图生成 → A4 排版及 PDF → 内容与相似度人工评价。

`web/samples.py` 不把切行成功当作 OCR、转录匹配或相似度验收通过。严重透视、多栏、竖排及弯曲纸页不属于已验证条件。

## 少样本生成

`web/runtime/vatr_worker.py` 在独立进程运行固定版本 VATr++ 生成器。参考文字行被缩放并切为图块，编码器计算风格表示，生成器按指定新内容输出整词图像。编码可缓存复用，不对每个用户进行模型训练。

仅初始化并严格加载预训练生成器，不初始化训练判别器、OCR、评价网络和优化器。推理离线；字符原型及权重来自安装脚本固定的模型版本，资产不放入 Git。

按词排版为 A4 图片与 PDF，保留显式换行，以普通词距呈现多个空格；支持字号、行距、墨色和种子。它不是段落级连续笔画模型。报告记录输入与来源，但尚无独立 OCR 自动核对，结果默认待人工评价。

## 存储与服务边界

档案、原图、文字行、风格缓存、任务、PDF、日志和反馈位于 `.local/web-data/`，可通过 `INKSELF_DATA` 调整。不需要把样本发往云端。

服务仅监听 `127.0.0.1`，包含 Host、同源令牌、上传限制、下载白名单和排队上限。它没有远程多用户认证和租户隔离，不能直接开放监听地址当作正式在线产品。云端仍需认证、私有存储、持久队列及独立推理部署。

## 辅助字形引擎

`engines/glyphs/` 保留逐字定位采样、切分、联系表审核和真实字形复用，只能渲染已经采样的字符。其确定性 PDF/SVG 可检查字符映射、哈希、页界和可见墨迹。

该引擎与网页生成模型是独立流程。其上下标、数学符号及确定性映射能力不能直接宣称为网页模型的能力；其测试也不能证明网页真人相似度或生成文字准确性通过。

进度见 [产品路线](roadmap.md)，操作见 [使用指南](web-guide.md)。


## Document and math pipeline

The reference and habit modes preflight content through `runtime/document_input.py`. Opted-in math is parsed by the bounded, non-executing `math_syntax.py` parser. `math_renderer.py` builds baseline-aware boxes from personal rasters and explicitly allowed `math_glyphs.py` supplements; source provenance and the AST are retained. Mathematical structure is not an OCR or symbolic solving service.

`document_layout.py` plans complete lines and semantic keep groups before assigning pages. It then writes one raster page at a time, with positions, baselines, warnings and display-formula scaling in `layout.json`. Experiment fingerprints include parser, glyph, math and document layout code; image/PDF/layout/report files are hashed for replay. Unknown commands and unapproved missing glyphs fail before a job is queued.

## Windows desktop

`desktop.py` dispatches the native window, isolated loopback server and frozen local workers. `desktop_runtime.py` owns the server process tree through a Windows Job Object, verifies a per-launch instance identity, and enforces one controller per data folder. Startup probes use direct loopback HTTP without proxy or TLS configuration. `web/runtime_paths.py` separates read-only bundled resources from portable `data` and optional external neural assets; source development paths remain compatible.

PyInstaller bundles public web sources for renderer fingerprints and optional external Python workers. Core glyph/math workers re-enter `Inkself.exe --worker`, so no system Python is needed. The clean ZIP excludes personal profiles, history and model weights. Explicit profile imports validate relative asset paths and checksums, reject links, skip existing IDs and never copy old absolute job requests. See [desktop guide](desktop-guide.md).
