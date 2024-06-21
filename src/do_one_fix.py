import argparse
import os
from types import SimpleNamespace

import yaml

from agent.backports import do_backport, initial_agent
from check.usage import get_usage
from tools.logger import logger
from tools.project import Project


def load_yml(file_path: str):
    with open(file_path, "r") as file:
        config = yaml.safe_load(file)

    data = SimpleNamespace()
    data.project = config.get("project")
    data.project_url = config.get("project_url")
    data.project_dir = config.get("project_dir")
    data.patch_dataset_dir = config.get("patch_dataset_dir")
    data.openai_key = config.get("openai_key")
    data.tag = config.get("tag")

    data.new_patch = config.get("new_patch", "")
    if not data.new_patch or not data.new_patch:
        logger.error(
            "Please check your configuration to make sure new_patch is correct!\n"
        )
        exit(1)

    data.new_patch_parent = config.get("new_patch_parent", "")
    if not data.new_patch_parent or not data.new_patch_parent:
        logger.error(
            "Please check your configuration to make sure new_patch_parent is correct!\n"
        )
        exit(1)

    data.target_release = config.get("target_release", "")
    if not data.target_release or not data.target_release:
        logger.error(
            "Please check your configuration to make sure target_release is correct!\n"
        )
        exit(1)

    data.sanitizer = config.get("sanitizer", "")
    data.error_message = config.get("error_massage", "")
    if not data.sanitizer or not data.error_message:
        logger.warning(
            "Dataset without error info which means that this vulnerability may not have PoC\n"
        )

    return data


def main():
    parser = argparse.ArgumentParser(
        description="Backports patch with the help of LLM",
        usage="%(prog)s --config CONFIG.yml\ne.g.: python %(prog)s --config CVE-examaple.yml",
    )
    parser.add_argument(
        "-c", "--config", type=str, required=True, help="CVE config yml"
    )
    args = parser.parse_args()

    config_file = args.config
    data = load_yml(config_file)

    data.project_dir = os.path.expanduser(
        data.project_dir if data.project_dir.endswith("/") else data.project_dir + "/"
    )
    data.patch_dataset_dir = os.path.expanduser(
        data.patch_dataset_dir
        if data.patch_dataset_dir.endswith("/")
        else data.patch_dataset_dir + "/"
    )

    if not os.path.isdir(data.project_dir):
        logger.error(f"Project directory does not exist: {data.project_dir}")
        exit(1)
    if not os.path.isdir(data.patch_dataset_dir):
        logger.error(
            f"Patch dataset directory does not exist: {data.patch_dataset_dir}"
        )
        exit(1)

    project = Project(data.project_url, data.project_dir, data.patch_dataset_dir)
    agent_executor = initial_agent(project, data.openai_key)

    before_usage = get_usage(data.openai_key)
    do_backport(agent_executor, project, data)
    after_usage = get_usage(data.openai_key)
    logger.info(
        f"This patch total cost: ${(after_usage['total_cost'] - before_usage['total_cost']):.2f}"
    )
    logger.info(
        f"This patch total consume tokens: {(after_usage['total_consume_tokens'] - before_usage['total_consume_tokens'])/1000}(k)"
    )


if __name__ == "__main__":
    main()

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
