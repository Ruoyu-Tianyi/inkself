# 第三方模型说明

网页内测使用 VATr++ 预训练生成器。模型来源为 [blowing-up-groundhogs/vatrpp](https://huggingface.co/blowing-up-groundhogs/vatrpp)，这是原 VATr 官方仓库链接的实现；上游研究项目为 [EDM-Research/VATr-pp](https://github.com/EDM-Research/VATr-pp) 和 [aimagelab/VATr](https://github.com/aimagelab/VATr)。

固定版本：`fb73be2be8e96ce70d9cad9675a30667e19ac376`。HF 模型页标注 MIT，原项目代码使用其仓库许可。上游模型卡同时要求遵循原仓库许可；若商业分发模型或提供公开商业服务，应进一步核实训练数据及模型使用条件。本次仅下载到忽略的 `.local/vendor/vatrpp` 用于本地研究内测，未将权重、字体原型或上游代码重新发布到本仓库。

安装脚本下载固定版本的代码、`model.safetensors`、字符原型及辅助文本，不下载 IAM 训练数据。LFS 文件按官方 API 提供的 SHA-256 校验；本地 download-manifest.json 保存来源和哈希。模型运行离线，生成器之外的训练网络、优化器和评价网络不初始化。ResNet 全部使用该 checkpoint 的训练权重，无需另行下载初始化权重。

上游字符原型文件为 pickle，仅从固定官方模型仓库下载并校验；不支持用户上传模型或 pickle。Safetensors 权重严格检查生成器键名匹配。用户上传只接受图像格式。

生成结果需要逐字人工核对，尤其是数字；未将生成任务成功、内容记录或可见像素等同于识字准确性或本人相似度通过。
