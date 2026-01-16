[![zh-CN](https://img.shields.io/badge/Lang-中文-red.svg)](./design.zh-CN.md)

# Design Document

## I. System Architecture

For large-scale projects maintaining multiple versions simultaneously, migrating security patches to older versions often presents challenges. When developers fix a security vulnerability in the **Mainline** version, the **Stable** versions they maintain (e.g., v6.6 in the diagram below) face similar risks. However, patches from Mainline often cannot be directly migrated (backported) to Stable versions. This requires manual intervention, which inevitably leaves the Stable version exposed to security vulnerabilities for a longer period.

![Security Patch Backport Flow](public/image1.jpeg)

During the manual backport process, developers must handle conflicts based on error messages from automated tools (e.g., `cherry-pick` conflicts) to successfully merge the patch. This process typically involves the following operations:

- Identifying hunks within the patch that contain conflicts and handling them individually.
- Locating the context of the hunk within the Stable version.
- Locating files that may have been moved or renamed during version progression.
- Resolving context conflicts in the hunk and merging them.
- After migrating all hunks, performing compilation and PoC (Proof of Concept) testing, and continuously fixing issues until all tests pass.

Therefore, this project attempts to simulate the developer's manual processing workflow by offloading the backport task to a **Large Language Model (LLM)**. Through **Agents**, we provide the LLM with tools to query necessary information and process data locally, granting it capabilities similar to a developer during the backporting process. The system architecture uses two Agents to handle tasks and dialogue with the LLM: the **Hunk Processing Agent** and the **Full Patch Error Handling Agent**.

- **Hunk Processing Agent:** This agent pre-processes the patch, splitting it into multiple hunks to be tested individually. Hunks that cannot be migrated directly are handed over to the LLM. The LLM continuously invokes tools provided by the Agent to guide the hunk toward a successful migration.
- **Full Patch Error Handling Agent:** Once the full patch is successfully migrated, if issues arise during the validation chain (e.g., compilation errors), this agent is invoked to handle the errors.

![Agent-based LLM Automatic Patch Backport Framework](public/image2.jpeg)

## II. Patch Preprocessing and Localization

### 1. Patch Slicing

In the real world, security patches vary significantly in size, ranging from a few lines to thousands. Attempting to migrate a thousand-line patch in one go is unrealistic for both developers and LLMs, as the patch often contains too many details requiring attention.

Therefore, we attempt to slice the patch, focusing each repair on a small section. In standard patch formats, the smallest unit of division is a **hunk**. A patch may consist of multiple hunks that do not conflict with each other. The image below shows the fix for **libtiff CVE-2023-41175**, composed of two non-conflicting hunks. When using the LLM for backporting, we split the patch into individual hunks. We first attempt to apply the hunk directly; only if that fails do we hand it over to the LLM for processing.

![CVE-2023-41175 Fix Patch](public/image3.png)

Patch slicing simulates the manual backporting process and avoids issues caused by the LLM's context window limits. Furthermore, hunks that apply directly do not require LLM intervention, reducing the number of LLM interaction rounds.

### 2. File Move Handling

In the patch workflow, the tool identifies the file pointed to by the patch and locates the code block matching the context for modification. However, as versions evolve, some files may be moved or renamed.

![Comparison of patches across versions](public/image4.png)

The image above shows a partial patch for **Linux CVE-2023-38432** applied to v5.15 (left) and Mainline (right). The context and modifications in the patch are identical, but the `patch` tool fails because the directory structure changed. Similarly, when the patch is handed to the LLM, it cannot infer the file's current location from the existing information alone.

To help the LLM locate files, we note that even if files move, the **symbols** (functions, structs, etc.) within the patch context often remain unchanged. By locating these symbols, we can mark the file containing them as a potential target and attempt to apply the patch:

- For cases where the patch applies successfully, we verify this as the target file location in the old version and inform the LLM.
- If the application fails (potentially due to context changes), the set of potential target files is passed to the LLM for processing.
- If no usable symbols are found in the context for localization, the case is handled in the "Similar Code Block Matching" section.

### 3. Similar Code Block Matching

In a patch, lines starting with a space or `-` are referred to as the **patch context**. The patch tool searches for an exact context match in the target file; any difference causes failure.

To help the LLM quickly locate the code block where the context has changed, we calculate the **edit distance** between the target file content and the patch context. The code block with the minimum edit distance is marked as a "similar code block" for the LLM. Additionally, whenever the LLM provides a patch for validation and it fails, this matching mechanism provides specific failure reasons.

If the file in the patch does not exist and File Move Handling fails to locate it, we perform **similar filename matching**. We calculate the edit distance between the patch filename and all files in the repository. The five files with the smallest edit distances are selected as potential targets. We then perform similar code block matching on these five files, selecting the result with the minimum edit distance to feedback to the LLM alongside the filename.

### 4. Apply Hunk Failure Feedback

![Git apply flow chart](public/image5.jpeg)

`git apply` typically fails in three ways:

1. **Context Mismatch:** The lines starting with space or `-` in the patch file cannot be found in the Stable version's target file.
2. **File Not Found:** The target file to be patched does not exist in the Stable version's repository.
3. **Format Error:** Usually occurs when the patch file contains lines not starting with `+`, `-`, or space.

Handling strategies for cases 1 and 2 are shown in the flow chart above:

- **Context Mismatch:** First, call `find_most_similar_block` to search the Stable version target file for the block most similar to the Mainline patch context. Compare this block line-by-line with the LLM-generated patch context. The inconsistent lines are fed back to the LLM, prompting it to generate a new patch that matches the Stable version's context.
- **File Not Found:** Call the `_apply_file_move_handling` function. The goal is to find where the target code block exists in the Stable version. There are two methods:
  - (1) Attempt to extract symbols from the Mainline patch, then call `locate_symbol` to find the file location in the Stable version. In the examples below, symbols `ksmbd_transport_ops` and `stop_sessions` can be extracted.
  - (2) Find the most similar files in the Stable repository based on the filename. Once a potential target is found, attempt to apply the patch. If a context mismatch occurs, feed the potential path and mismatch information back to the LLM.

    ```c
    @@ -135,7 +135,6 @@ struct ksmbd_transport_ops {
    @@ -416,13 +416,7 @@ static void stop_sessions(void)
    ```

- **Format Error:** Extract the line number causing the format issue from the `git apply` error message. Feed this line number back to the LLM, indicating a formatting problem.

## III. Agent Functional Design

### 1. Agent Toolset

- **viewcode**
  The LLM can use this tool to view specific lines of a specific file in a specific commit.

    ```python
    def _viewcode(self, ref: str, path: str, startline: int, endline: int) -> str:
        """
        View a file from a specific ref of the target repository. Lines between startline and endline are shown.

        Args:
            ref (str): The specific ref of the target repository.
            path (str): The path of the file to view.
            startline (int): The starting line number to display.
            endline (int): The ending line number to display.

        Returns:
            str: The content of the file between the specified startline and endline.
                If the file doesn't exist in the commit, a message indicating that is returned.
        """
    ```

- **locate_symbol**
  The LLM can use this tool to obtain the location of a specific symbol in a specific commit. Implemented via `ctags`.

    ```python
    def _locate_symbol(self, ref: str, symbol: str) -> List[Tuple[str, int]] | None:
        """
        Locate a symbol in a specific ref of the target repository.

        Args:
            ref (str): The reference of the target repository.
            symbol (str): The symbol to locate.

        Returns:
            List[Tuple[str, int]] | None: File path and code lines.
        """
    ```

- **validate**
  The LLM uses this tool to verify the correctness of the patch. For the **Hunk Processing Agent**, this tool checks if the LLM-provided hunk can be applied. If successful, validation passes; otherwise, error information is returned.

    ```python
    def _validate(self, ref: str, patch: str) -> str:
        """
        Validates a patch by using the `_compile_patch`, `_run_testcase`, and `_run_poc` methods.

        Args:
            ref (str): The reference string.
            patch (str): The patch string.

        Returns:
            str: The validation result.
        """
    ```

### 2. Generating Patch Validation Chain

For the **Full Patch Error Handling Agent**, the `validate` tool checks if the complete patch provided by the LLM can compile, pass testcases, and pass PoC testing. This step requires the user to prepare compilation scripts, testcase scripts, and PoC scripts. If a script is missing for any stage, that stage is considered passed.

- **Compilation Test:**
  The tool first merges all previously successful hunks into a complete patch and attempts to apply it. Since every hunk has already passed `git apply` testing individually, errors here are likely limited to context mismatches during the merge. If an error occurs, the mismatched lines are fed back to the LLM (as per previous logic) to regenerate the patch. Once applied, the prepared compilation script runs. If compilation fails, the error log is sent to the LLM to regenerate the patch.

- **Testcase Verification:**
  The tool executes the prepared testcase script. If successful, it proceeds to PoC testing. If it fails, the error information is sent to the LLM to regenerate the patch.

- **PoC Verification:**
  The tool executes the prepared PoC script. If successful, the LLM-generated patch is considered fully verified. If it fails, the error information is sent to the LLM to regenerate the patch.
