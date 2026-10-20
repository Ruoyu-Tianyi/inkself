# Personal Handwriting Skill

供 AI 调用的个人字迹工作流：收集英文、数字和数学符号样本，保存个人字迹档案与偏好，再由确定性的排版器生成可校验的文档。

**当前交付是方案与可运行的样本档案管理雏形，不是已经完成的字迹克隆模型。** 当前可创建档案、归档样本及其转录、保存偏好、列出与检查档案。字形切分、字形提取、个人字迹渲染和视觉相似度评测尚未实现。

## 可行性结论

| 目标 | 判断 | 条件与边界 |
| --- | --- | --- |
| 保存自己的样本、字迹偏好与版本 | 高可行 | 本地档案、可验证样本来源与明确的数据结构 |
| 已采样英文字母、数字和符号的忠实渲染 | 高可行，待实现验证 | 使用定位采样页、字形切分和多个真实字形变体；优先保证公式内容 |
| 散文中的自然连笔和上下文形变 | 中等可行，需要实验 | 增加常用词/连字样本，或接入适合离线图像的生成模型 |
| 仅上传任意一小段照片，即准确复现所有字符与长文 | 不应承诺 | 未出现字符没有真实样本；图片不含落笔顺序；模型可能遗漏或改写字符 |

## 推荐实现

Skill 负责理解请求、采样引导、档案选择、偏好覆盖、调用本地程序和验收；字形提取、存储和 PDF 渲染由脚本或引擎承担。Skill 本身不是训练后的字迹模型。

优先开发 **glyph-first 字形库路线**：用户完成英文大小写、数字与符号定位采样页；每个字符采集多个真实变体；从图片提取用户实际笔画；保留字符映射；按同一人的尺度、笔压、基线和间距统计排版。对有样本的字符不换成通用字体，也不将单纯的随机旋转描述成个人字迹学习。

自由手写照片可保存为参考样本，但在完成转录和可靠对齐前不能标记为“可生成风格”。数学公式采用结构化输入，先锁定字符，再渲染字形与上下标；不让生成模型自由改写数字。

## 与 TypeScribe 的关系

灵感来自 [rudyoactiv/typescribe-handwriting](https://github.com/rudyoactiv/typescribe-handwriting)，已检查的上游版本为 `ccae8180a614edfcca5526d80bd8ae6904c7f77b`。

TypeScribe 的 `Hand._sample()` 使用配对的字符和 `(dx, dy, pen-up)` 轨迹进行 priming。它不是照片上传后的个人字迹编码器。上游字符集还缺少常见数学符号及部分大写字母，不能直接用于忠实的数学答卷。

本仓库独立新建，不复制上游代码、模型权重或其依赖环境。未来可增加可选轨迹引擎适配器；若分发上游代码或模型，须分别核实代码许可、模型许可和训练数据使用条件。上游代码的 BSD-3-Clause 不能自动替代模型及数据的权利审查。

## 当前可以运行

Python 3.10+，档案管理仅使用标准库。运行位置为仓库根目录：

```sh
python skills/personal-handwriting/scripts/profile.py --store .local/profiles create my-hand --name "My handwriting"
python skills/personal-handwriting/scripts/profile.py --store .local/profiles add-sample my-hand --file /absolute/path/sample.png --kind freeform --transcript /absolute/path/transcript.txt
python skills/personal-handwriting/scripts/profile.py --store .local/profiles update my-hand --preferences /absolute/path/preferences.json
python skills/personal-handwriting/scripts/profile.py --store .local/profiles show my-hand
python skills/personal-handwriting/scripts/profile.py --store .local/profiles list
python -m unittest discover -s tests -v
```

`create` 使用内部默认偏好；`update` 只接收偏好字段，不覆盖样本。`add-sample` 会复制样本并计算 SHA-256，记录转录；不做 OCR、不提取字形，不把归档成功混同于风格可生成。相同样本重复添加不会增加记录。样本、转录、字形库和输出默认只留本地，仓库的 `.local/` 已忽略。

安装 skill 时，复制 `skills/personal-handwriting/` 整个目录到 AI 工具支持的技能目录。用户档案应放在技能包之外；不要把用户图片打包进 skill。

## 后续开发顺序

1. **采样与存档**：当前提供文件归档和偏好校验；补齐定位采样 PDF、清晰度与倾斜检查、英文转录校对。
2. **字形提取与可信渲染**：实现字符对齐、多变体提取、缺字报告、统一文字/数字/符号渲染和整页验收。这是第一个真正有用的个人字迹 MVP。
3. **自然连笔增强**：常见连字和词库、风格统计、可选图像生成引擎；以字符准确率和用户盲评决定是否启用。

详见 [技术方案](docs/architecture.md)、[实施与验收](docs/roadmap.md) 和 [Skill 入口](skills/personal-handwriting/SKILL.md)。
