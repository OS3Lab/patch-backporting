[![English](https://img.shields.io/badge/Lang-English-blue.svg)](README.md)

# patch-backporting

我们论文的 PDF 版本位于 [docs/PortGPT.pdf](docs/PortGPT.pdf)。

本仓库包含一个打标签的快照，对应于我们提交论文时使用的代码版本。

标签 **`sp26-submission`** 标记了向 **IEEE S&P 2026** 提交论文 *“PortGPT: Towards Automated Backporting Using Large Language Models”* 时使用的确切代码状态。  
论文中报告的所有实验结果均基于此标签版本。

为了复现结果，请参考此标签，而不是最新的 `main` 分支。

## 安装设置

```shell
curl -sSL [https://pdm-project.org/install-pdm.py](https://pdm-project.org/install-pdm.py) | python3 -
pdm install
source .venv/bin/activate
```

## 使用方法

```shell
cd src
python backporting.py --config example.yml --debug # 记得填写配置文件
```

## Docker 使用方法

构建 Docker 镜像：

```shell
docker build -t patch-backporting .
```

运行容器：

```shell
# 请确保挂载了必要的目录（项目代码、配置文件、数据集）
# 示例：假设当前目录下有 config.yml，数据集位于 /path/to/dataset
docker run --rm -v $(pwd):/app/src -v /path/to/dataset:/path/to/dataset patch-backporting python backporting.py --config config.yml
```

## 配置结构

```yml
project: libtiff
project_url: [https://github.com/libsdl-org/libtiff](https://github.com/libsdl-org/libtiff) 
new_patch: 881a070194783561fd209b7c789a4e75566f7f37 # 新版本中的补丁提交 ID，版本 A（已修复）    
new_patch_parent: 6bb0f1171adfcccde2cd7931e74317cccb7db845 # 补丁父提交，版本 A 
target_release: 13f294c3d7837d630b3e9b08089752bc07b730e6 # 需要修复的提交 ID，版本 B 
sanitizer: LeakSanitizer # poc 的 sanitizer 类型，可为空
error_message: "ERROR: LeakSanitizer" # poc 的触发信息，可为空
tag: CVE-2023-3576
openai_key: # 你的 openai key
project_dir: dataset/libsdl-org/libtiff # 项目路径
patch_dataset_dir: ~/backports/patch_dataset/libtiff/CVE-2023-3576/ # 补丁集路径，包含 build.sh, test.sh 等...

# 可选：Azure OpenAI 配置
# use_azure: true
# azure_endpoint: "[https://your-resource.openai.azure.com/](https://your-resource.openai.azure.com/)"
# azure_deployment: "gpt-4"
# azure_api_version: "2024-12-01-preview"

#                    Version A           Version A(Fixed/已修复)     
#   ┌───┐            ┌───┐             ┌───┐                  
#   │   ├───────────►│   ├────────────►│   │                  
#   └─┬─┘            └───┘             └───┘                  
#     │                                                       
#     │                                                       
#     │                                                       
#     │              Version B                                
#     │              ┌───┐                                    
#     └─────────────►│   ├────────────► ??                    
#                    └───┘                       
```

## LLM 提供商选项

PortGPT 支持 OpenAI 和 Azure OpenAI：

### 使用 OpenAI（默认）

```yml
openai_key: sk-your-openai-key
use_azure: false  # 或者省略此行
```

### 使用 Azure OpenAI

```yml
openai_key: your-azure-api-key
use_azure: true
azure_endpoint: "[https://your-resource.openai.azure.com/](https://your-resource.openai.azure.com/)"
azure_deployment: "gpt-4"  # 如果可用，也可以是 "gpt-5"
azure_api_version: "2024-12-01-preview"
```

## 如何评判结果？

在经过现有的验证链之后，需要人工分析结果的正确性（与 Ground Truth (GT) 进行比较）。

首先，判断生成的补丁是否**匹配 GT 修改的逻辑代码块**。（这里不说 hunk 匹配，是因为存在一些 hunk 合并的情况。）

其次，检查代码更改的**位置**是否与 GT 相同或等效。

最后，检查修改后代码的**语义**是否与 GT 等效。

## 引用

```bibtex
@inproceedings{portgpt,
  title={{PORTGPT}: Towards Automated Backporting Using Large Language Models},
  author={Zhaoyang Li and Zheng Yu and Jingyi Song and Meng Xu and Yuxuan Luo and Dongliang Mu},
  booktitle={Proceedings of the 47th IEEE Symposium on Security and Privacy},
  year={2026}
}
```
