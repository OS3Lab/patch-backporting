[![zh-CN](https://img.shields.io/badge/Lang-中文-red.svg)](./setup-and-usage.zh-CN.md)

# Build and Usage Guide

## I. Build Instructions

### Repository Description

This project consists of two code repositories:

* **`patch_dataset`**: Contains 150 real-world backport failure cases (100 C/C++ and 50 Golang CVE patches). Data is prepared individually for each CVE in every project, including failure information, build scripts, partial test suite scripts, and partial PoC (Proof of Concept) scripts.
* **`patch-backporting`**: The project source code, which includes the agents for interacting with Large Language Models (LLMs) and utility tools.

### Source Code Directory Structure

```text
.
├── README.md
├── logs
├── pdm.lock
├── pyproject.toml
├── requirements.txt
├── src
│   ├── agent
│   │   ├── __init__.py
│   │   ├── invoke_llm.py
│   │   └── prompt.py
│   ├── backporting.py
│   ├── check
│   │   ├── __init__.py
│   │   └── usage.py
│   ├── example.yml
│   └── tools
│       ├── __init__.py
│       ├── logger.py
│       ├── project.py
│       └── utils.py
└── test
    ├── test_hunk.py
    └── test_patch.py

```

### Software Prerequisites

* Python >= 3.10
* Ctags 5.9.0 (`sudo apt install universal-ctags`)
* PDM 2.18.2 ([https://github.com/pdm-project/pdm](https://github.com/pdm-project/pdm))

### Dependency Configuration

1. Install PDM

    ```bash
    curl -sSL https://pdm-project.org/install-pdm.py | python3 -
    ```

2. Configure Python and Dependencies

    ```bash
    # Inside the patch-backporting directory
    $ pdm install
    $ source .venv/bin/activate
    ```

## II. Usage Instructions

### Data Configuration

Before starting a test, two components of data must be prepared: `config.yml` (containing project information for the backport) and the build/test scripts relevant to the target patch.

1. Configuration Information

    ```yaml
    # example config yaml
    project: libtiff
    project_url: https://github.com/libsdl-org/libtiff 
    new_patch: 881a070194783561fd209b7c789a4e75566f7f37 # patch commit id in new version, Version A (Fixed)    
    new_patch_parent: 6bb0f1171adfcccde2cd7931e74317cccb7db845 # patch parent commit, Version A 
    target_release: 13f294c3d7837d630b3e9b08089752bc07b730e6 # commit id which needs to be fixed, Version B 
    sanitizer: LeakSanitizer # sanitizer type for poc, could be empty
    error_message: "ERROR: LeakSanitizer" # poc trigger message for poc, could be empty
    tag: CVE-2023-3576
    openai_key: # Your openai key
    project_dir: dataset/libsdl-org/libtiff # path to your project source code
    patch_dataset_dir: ~/backports/patch_dataset/libtiff/CVE-2023-3576/ 
    # path to your patchset, include build.sh, test.sh ....

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

2. Related Scripts

To ensure the verification chain functions correctly, you must provide build, test, and PoC scripts in the directory specified by `patch_dataset_dir`. As shown in the directory structure below, the build script should be named `build.sh`, the test script `test.sh`, and the CVE PoC trigger script `poc.sh`. Place any files required by these scripts into the same directory. The tool will automatically invoke these for verification after the LLM generates a patch.

```text
CVE-2023-3576
├── build.sh
├── config.yml
├── poc
├── poc.sh
└── test.sh
```

*Note: The tool can function even if these scripts are missing, but providing a build script offers the backporting process more context and information.*

### Testing

```bash
python backporting.py --config example.yml --debug
# python backporting.py --config YOUR_CONFIG [--debug]
# python backporting.py -c YOUR_CONFIG [-d]

```

Execute the `backporting` script located in the `src` folder using the commands above to perform patch migration testing. Replace `example.yml` with your configured target YAML file.

The `debug` mode provides detailed information regarding the interaction with the LLM, allowing you to monitor the migration process. The output for a test run in non-debug mode appears as follows:![Test output in non-debug mode](public/image1.png)
