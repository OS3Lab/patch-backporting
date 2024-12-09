#!/usr/bin/env python3

base_dataset_dir = "/home/sjy/LLM_Backport/patch_dataset"
base_src_dir = "/home/sjy/LLM_Backport/source-project"

import os
import subprocess
import yaml


def update_config(config_dir: str):
    with open(os.path.join(config_dir, "config.yml"), "r") as config_file:
        config_data = yaml.safe_load(config_file) or {}

        proj_name = config_data.get("project", None)
        config_data["project_dir"] = base_src_dir + "/" + proj_name
        config_data["patch_dataset_dir"] = os.path.join(config_dir)

        with open("example.yml", "w") as config_file:
            yaml.dump(config_data, config_file, default_flow_style=False)


def main(start_cve: str = None):
    with open("data.csv", "r") as f:
        white_list = f.read().splitlines()

    i = 0
    start = not start_cve
    for root, dirs, files in os.walk(base_dataset_dir):
        for dir in dirs:
            if dir in white_list:
                i += 1
                print(i, os.path.join(root, dir))
                if dir == start_cve:
                    start = True
                if start:
                    update_config(os.path.join(root, dir))
                    try:
                        process = subprocess.Popen(
                            ["python", "backporting.py", "-c", "example.yml", "-d"]
                        )
                        output, _ = process.communicate(timeout=10 * 60)
                    except subprocess.TimeoutExpired:
                        process.kill()
                else:
                    continue


def download_repo():
    for root, dirs, files in os.walk(base_dataset_dir):
        if (
            "tsbport" in root
            or "fixmorph" in root
            or "focal" in root
            or "jammy" in root
        ):
            continue

        if "pull.sh" in files:
            if os.path.exists(os.path.join(base_src_dir, root.split("/")[-1])):
                continue
            print(f"\n\n=====\npulling {root}...\n=====\n\n")
            subprocess.Popen(
                ["bash", os.path.join(root, "pull.sh")],
                cwd=base_src_dir,
            ).wait()


if __name__ == "__main__":
    main()
