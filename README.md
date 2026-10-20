# Personal Handwriting Skill 1.0

供 AI 调用的本地个人字迹工具：采样、保存个人字形与偏好、检查缺字、生成 PDF/SVG，并校验输出内容和可见笔迹。Python 3.10+，Windows/Linux/macOS；当前已在 Windows 本地验证。

第一版采用真实字形复用：从定位采样页中提取用户写出的字母、数字和符号，统一用于文档。它不是从任意一段照片训练通用字迹模型；自然连笔与未采样字符的生成仍需后续模型研究。**本仓库测试使用合成样本，个人相似度必须用真实用户样本另行验收。**

## 安装

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

将 `skills/personal-handwriting` 完整目录复制到 AI 工具支持的技能目录（Codex 为 `~/.codex/skills/personal-handwriting`），在同一个 Python 环境安装该目录内的 `requirements.txt`。也可解压本地 `dist/personal-handwriting.zip`。档案应保存在技能目录外，升级技能不会改变档案。

## 使用

在仓库根目录运行；AI 安装后读取 [SKILL.md](skills/personal-handwriting/SKILL.md) 即可按需调用。

```sh
python skills/personal-handwriting/scripts/profile.py --store .local/profiles create my-hand --name "My handwriting"
python skills/personal-handwriting/scripts/handwriting.py template --output outputs/sampling.pdf
```

按采样 PDF 标签，在每个框内写对应字符，每字三个自然变体。使用深色笔、保留四角定位标记和整页边缘，扫描或拍照所有页。保存配套的 `sampling.json`，不要混用其他批次的采样页。

```sh
python skills/personal-handwriting/scripts/handwriting.py --store .local/profiles extract my-hand --manifest outputs/sampling.json --pages scan1.png scan2.png scan3.png
python skills/personal-handwriting/scripts/handwriting.py --store .local/profiles review my-hand
```

打开返回的**全部** contact 图片，核对字符标签、笔画和切分。确认实际检查无误后执行：

```sh
python skills/personal-handwriting/scripts/handwriting.py --store .local/profiles review my-hand --accept
python skills/personal-handwriting/scripts/handwriting.py --store .local/profiles coverage my-hand --input examples/document.json
python skills/personal-handwriting/scripts/handwriting.py --store .local/profiles render my-hand --input examples/document.json --output outputs/result.pdf --seed 42
python skills/personal-handwriting/scripts/handwriting.py validate --report outputs/result.report.json --render-dir outputs/inspection
```

`coverage` 返回缺失字符时先补采。渲染输出 PDF、逐页 SVG 和含字形来源的报告；打开 inspection 中全部页图进行版式及数字核对。文件已存在时换新输出名。CLI 成功退出码 0，缺字 3，其他错误 2；JSON 输出便于 AI 解析。

## 已实现

- 本地多档案、样本 SHA-256 去重、转录归档、偏好持久化及临时覆盖。
- 三页默认英文/数字/符号采样 PDF，可指定字符集与每字 1–5 个变体。
- PNG/JPEG/PDF 导入、旋转和适度透视/光照校正、页码识别、字形提取、空白/边界拒绝、逐页联系表检查。
- 草稿审核后启用，缺字阻断，文字与数字共用个人字形，固定种子可复现。
- 自动换行分页、标题、上下标，PDF/SVG、内容映射与哈希校验、逐字可见墨迹检查。
- 测试覆盖错误采样页、空白、缺字、旋转/透视/阴影、多页、上下标、文件被改动和复现性。

自动校验不能证明用户是否把字写进正确的框，也不能证明与本人字迹相似。无隐藏文字层作为正确性凭据。单字拼排会保留字形，但还原不了自然连笔；不支持签名或身份认证。自由手写照片可归档，暂不自动转成完整字形库。

## 偏好与隐私

偏好见 [字段说明](skills/personal-handwriting/references/profile-contract.md)，可使用 `profile.py update` 保存或 `render --preferences` 临时覆盖。[示例文档](examples/document.json) 展示结构化上下标输入。

样本、字形、转录、文档及报告默认只留本地，`.local/`、`outputs/` 等已被 Git 忽略。**报告包含完整输入内容**，分享时一并考虑隐私。仓库不包含个人样本或作业信息。

## 重现与工程说明

```sh
python examples/synthetic_demo.py --output .local/demo
python scripts/package_skill.py --output dist/personal-handwriting.zip
```

演示用计算机字体填采样页，再提取和渲染，只验证技术流程，不代表个人手写效果。技术结构、已验收与实验边界见 [架构](docs/architecture.md)、[验收记录](docs/roadmap.md)。

灵感来自 [TypeScribe](https://github.com/rudyoactiv/typescribe-handwriting)（检查版本 `ccae8180a614edfcca5526d80bd8ae6904c7f77b`）。其 priming 需要配对的字符和笔迹轨迹，不能直接将任意静态照片转换成个人风格。本项目独立实现，未复制上游代码、模型权重或训练数据。
