# patch-backporting

The PDF version of our paper is located in the [docs/PortGPT.pdf](docs/PortGPT.pdf).

## Setup

```shell
curl -sSL https://pdm-project.org/install-pdm.py | python3 -
pdm install
source .venv/bin/activate
```

## Usage

```shell
cd src
python backporting.py --config example.yml --debug # Remember fill out the config.
```

## Config structure

```yml
project: libtiff
project_url: https://github.com/libsdl-org/libtiff 
new_patch: 881a070194783561fd209b7c789a4e75566f7f37 # patch commit id in new version, Version A(Fixed)    
new_patch_parent: 6bb0f1171adfcccde2cd7931e74317cccb7db845 # patch parent commit, Version A 
target_release: 13f294c3d7837d630b3e9b08089752bc07b730e6 # commid id which need to be fixed, Version B 
sanitizer: LeakSanitizer # sanitizer type for poc, could be empty
error_message: "ERROR: LeakSanitizer" # poc trigger message for poc, could be empty
tag: CVE-2023-3576
openai_key: # Your openai key
project_dir: dataset/libsdl-org/libtiff # path to your project
patch_dataset_dir: ~/backports/patch_dataset/libtiff/CVE-2023-3576/ # path to your patchset, include build.sh, test.sh ....

# Optional: Azure OpenAI Configuration
# use_azure: true
# azure_endpoint: "https://your-resource.openai.azure.com/"
# azure_deployment: "gpt-4"
# azure_api_version: "2024-12-01-preview"

#                    Version A           Version A(Fixed)     
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

## LLM Provider Options

PortGPT supports both OpenAI and Azure OpenAI:

### Using OpenAI (Default)
```yml
openai_key: sk-your-openai-key
use_azure: false  # or omit this line
```

### Using Azure OpenAI
```yml
openai_key: your-azure-api-key
use_azure: true
azure_endpoint: "https://your-resource.openai.azure.com/"
azure_deployment: "gpt-4"  # or "gpt-5" if available
azure_api_version: "2024-12-01-preview"
```


## How to judge results?

After going through the validation chain that exists, the results are analyzed for correctness manually(Compare to Ground Truth(GT)).

First judge whether the generated patch **matches the logical block of code** modified by GT.(It doesn't say hunk match because there are some cases of hunk merging.)

Secondly, check that the **location** of the code change is the same or equivalent to GT.

Finally, check that the **semantics** of the modified code is equivalent to GT.

## Citation

```
@inproceedings{portgpt,
  title={PORTGPT: Towards Automated Backporting Using Large Language Models},
  author={Zhaoyang Li and Zheng Yu and Jingyi Song and Meng Xu and Yuxuan Luo and Dongliang Mu},
  booktitle={Proceedings of the 47rd IEEE Symposium on Security and Privacy},
  year={2026}
}
```
