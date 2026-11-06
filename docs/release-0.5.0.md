# Inkself 0.5.0-rc.1

本次桌面预览版集中改进间距调节、编辑保护和生成稳定性。下载与各平台构建验证记录见 [GitHub Release](https://github.com/Ruoyu-Tianyi/inkself/releases/tag/v0.5.0-rc.1)。本版本仍需真人验收。

## 下载与升级

- Windows x64 使用 `Inkself-Windows-x64-Setup.exe`。
- Mac Apple Silicon 使用 `Inkself-macOS-arm64.dmg`。
- Mac Intel 使用 `Inkself-macOS-x86_64.dmg`。

升级前确认草稿已保存，关闭应用并备份整个数据目录。Windows 安装版数据在 `%LOCALAPPDATA%/Inkself/data`，Mac 数据在 `~/Library/Application Support/Inkself/data`。当前草稿在目录中的 `compose-draft.json`，包含正文和排版设置。升级应用保留原有个人数据，模型仍在首次设置时另行下载。

Windows 包尚未签名，Mac 包采用临时签名，尚未取得 Developer ID 签名或公证。安装与首次启动说明见 [Windows 指南](desktop-guide.md) 和 [Mac 指南](macos-guide.md)。

## 使用体验

- 新增“自然”“工整”“紧凑”“宽松”四个间距按钮，并提供八项微调。字母、数字、符号内部间距需要习惯适配或字形保真模式。
- 正文与设置自动保存在本机，跨应用重启和端口变化恢复。保存状态与失败重试入口直接显示在试写页。
- 生成完成时保留等待期间的新修改，预览与草稿的区别有明确提示。
- 打开历史作品替换未提交草稿前确认。Markdown 读取期间发生新编辑时保留当前草稿。
- 连接临时中断时重试任务状态，可手动恢复查看，无需重复提交。
- 字符上限随生成模式显示，超限时明确提示，不截断正文。

## 修复与验证

- 修复任务提交、进度或完成状态保存失败后长期停留在排队或运行状态的问题。失败后释放队列位置，支持重新尝试。
- 作业模式独立公式保留单独居中的行，不再混入相邻正文。
- 修复 `12×34` 等紧贴数字的未采集配套符号通过预检后仍生成失败的问题。
- 修复作业金额中的 `\$` 被误当作公式开头的问题。转义只保护内容解析，档案仍须包含 `$` 字形；缺失时可写为 `USD 12.50`。
- 278 项 Python 检查中 277 项通过，1 项因 Windows 符号链接权限跳过，覆盖任务恢复、草稿持久化和公式排版；17 项界面状态测试覆盖间距、编辑保护、导入竞争和重连。安装包的原生验证结果以发布页记录为准。

这次更新改进排版和工作流程，尚未实现任意未标注短样本的自动高相似度克隆。复杂数学内容仍需已准备的个人字形档案；配套字形不代表已学习个人写法。输出继续要求人工核对。

## English

This desktop preview improves spacing controls, editing safety, and generation recovery. Downloads and platform-specific build validation are listed on the [GitHub release](https://github.com/Ruoyu-Tianyi/inkself/releases/tag/v0.5.0-rc.1).

Use `Inkself-Windows-x64-Setup.exe` on Windows, `Inkself-macOS-arm64.dmg` on Apple Silicon, or `Inkself-macOS-x86_64.dmg` on Intel Mac. The Windows package is unsigned. Mac packages are ad-hoc signed, without Developer ID signing or notarization.

Wait for the saved-draft indicator, close the app, and back up its data directory before upgrading. Windows installer data lives in `%LOCALAPPDATA%/Inkself/data`; Mac data lives in `~/Library/Application Support/Inkself/data`. `compose-draft.json` contains the current text and layout settings. Updating the app preserves this data. Model files are still downloaded separately during initial setup.

- Natural, Neat, Compact, and Relaxed buttons apply spacing presets. Eight controls allow individual adjustments. Fine spacing within words, digits, and symbols requires habit or reference mode.
- Local drafts persist across restarts and changing desktop ports. Save failures offer a retry.
- Generation completion preserves newer edits. Opening history confirms before replacing an unsent draft, and Markdown import preserves edits made while reading a file.
- Temporary connection failures retry job status updates, with a manual retry available. Mode-specific character limits are shown without truncating text.
- Failed submission or status writes no longer leave tasks indefinitely queued or running. Failed tasks release their queue slot for another attempt.
- Assignment display formulas keep separate centered lines. Supplemental symbols attached to numbers, such as `12×34`, render correctly after passing preflight.
- Escaped currency dollar signs (`\$`) remain literal in assignments. The profile still needs a `$` glyph; use `USD 12.50` when it is missing.

278 Python checks completed: 277 passed and one Windows symlink-permission check was skipped. They cover recovery, draft persistence, and formula layout. Seventeen UI state tests cover spacing, edit protection, import races, and reconnection. Package validation results are recorded on the release page.

This remains a preview requiring human validation. It does not establish automatic high-fidelity cloning from arbitrary unannotated short samples. Complex mathematics still needs a prepared glyph profile, and supplemental glyphs are not learned personal shapes. Review generated content before use.
