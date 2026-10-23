# 第三方模型说明

少样本模式使用 VATr++ 预训练生成器。固定推理实现和权重来自 [blowing-up-groundhogs/vatrpp](https://huggingface.co/blowing-up-groundhogs/vatrpp)，模型卡引用的上游研究项目包括 [EDM-Research/VATr-pp](https://github.com/EDM-Research/VATr-pp) 和 [aimagelab/VATr](https://github.com/aimagelab/VATr)。这与使用已核对个人字形库的原稿保真、习惯适配流程不同。

固定版本：`fb73be2be8e96ce70d9cad9675a30667e19ac376`。HF 模型页标注 MIT，同时要求遵循原仓库许可；该标签不能代替对权重、上游代码、字符原型各自来源与分发条件的核实。特别是字符原型使用 Unifont 衍生数据，须确认其具体版本及相应许可。训练数据的使用条件也需单独核实，不能从模型页标签推定。

默认完整安装器内置独立 CPU 推理引擎及其依赖，不内嵌上述模型资产。用户首次点击“准备本地 AI”后，程序按仓库内的 [固定清单](../web/model-assets.json) 下载模型代码、`model.safetensors`、字符原型及辅助文本，共 49 个文件、583,100,045 字节；不下载 IAM 训练数据。每个文件核对大小和 SHA-256，支持中断后继续，全部通过后才标记就绪。本机保存校验记录；这些文件不随 Git 提交。可选全离线包仅用于内部测试，尚不作为模型资产公开再分发许可已核实的声明。

下载只获取公开资产，不上传个人笔迹或生成内容。模型准备后推理可离线运行；生成器之外的训练网络、优化器和评价网络不初始化。ResNet 使用该 checkpoint 的训练权重，无需另行下载初始化权重。

上游模型包含 Python 推理代码及 pickle 字符原型，程序仅接受上述固定来源并校验，不支持用户上传模型或 pickle；Safetensors 权重严格检查生成器键名匹配。笔迹采样上传只接受图像，正文可另行导入 Markdown；Markdown 不作为程序或模型代码执行。

安装器和独立运行时附带各自第三方依赖许可及文件校验清单。更多分发边界见 [安装说明](desktop-guide.md)，当前产品能力及 AI 参与步骤见 [首次使用流程](ai-workflow.md)。

生成结果需要逐字人工核对，尤其是数字；未将生成任务成功、内容记录或可见像素等同于识字准确性或本人相似度通过。
