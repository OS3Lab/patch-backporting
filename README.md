# patch-backporting

## Setup

```shell
curl -sSL https://pdm-project.org/install-pdm.py | python3 -
pdm install
source .venv/bin/activate
```

## Usage

```shell
cd src
python do_on_fix.py --config example.yml # Remember fill out the config.
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
patch_dataset_dir: ~/backports/patch_dataset/libtiff/CVE-2023-3576/ # path to your patchset, include biuld.sh, test.sh ....

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

## How to judge results?

After going through the validation chain that exists, the results are analyzed for correctness manually(Compare to Ground Truth(GT)).

First judge whether the generated patch **matches the logical block of code** modified by GT.(It doesn't say hunk match because there are some cases of hunk merging.)

Secondly, check that the **location** of the code change is the same or equivalent to GT.

Finally, check that the **semantics** of the modified code is equivalent to GT.

