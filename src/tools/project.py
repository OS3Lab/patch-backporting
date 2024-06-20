import os
import re
import subprocess
import tempfile

from git import Repo
from langchain_core.tools import tool

import tools.utils as utils
from logger import logger


class Project:
    def __init__(self, project_url: str, dir: str, err_msg: str = "no err_msg"):
        self.project_url = project_url
        self.dir = dir
        self.repo = Repo(dir)
        self.err_msg = err_msg
        self.succeeded_patches = []
        self.round_succeeded = False
        self.all_hunks_applied_succeeded = False
        self.compile_succeeded = False
        self.testcase_succeeded = False
        self.poc_succeeded = False

    def _checkout(self, ref: str):
        self.repo.git.checkout(ref)

    def _get_patch(self, ref: str) -> str:
        try:
            return self.repo.git.show(f"{ref}^..{ref}")
        except:
            return "Error commit id, please check if the commit id is correct."

    def _prepare(self):
        ctags = subprocess.run(
            ["ctags", "--excmd=number", "-R", "."],
            stdout=subprocess.PIPE,
            cwd=self.dir,
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        ctags.check_returncode()
        self.symbol_map = {}
        with open(os.path.join(self.dir, "tags"), "r") as f:
            for line in f:
                if line.startswith("!_TAG_"):
                    continue
                try:
                    symbol, file, line = line.strip().split(';"')[0].split("\t")
                    line = int(line)
                    if symbol not in self.symbol_map:
                        self.symbol_map[symbol] = []
                    self.symbol_map[symbol].append((file, line))
                except:
                    print("Error parsing line:", line)

    def _viewcode(self, ref: str, path: str, startline: int, endline: int) -> str:
        """
        View a file from a specific ref of the target repository. Lines between startline and endline are shown.
        """
        try:
            file = self.repo.tree(ref) / path
        except:
            return "This file doesn't exist in this commit."
        content = file.data_stream.read().decode("utf-8")
        lines = content.split("\n")
        ret = []
        endline = min(endline, len(lines))
        for i in range(startline - 1, endline):
            ret.append(lines[i])
        return "\n".join(ret)

    def _locate_symbol(self, ref: str, symbol: str) -> str:
        """
        Locate a symbol in a specific ref of the target repository.
        """
        try:
            self._checkout(ref)
        except:
            ret = f"Oops, it looks like you give a error commit id.\n"
            ret += "Please check commit id and retry to check the patch.\n"
            return ret
        self._prepare()
        if symbol in self.symbol_map:
            return self.symbol_map[symbol]
        else:
            return None

    def _apply_hunk(self, ref: str, patch: str) -> str:
        """
        apply a hunk to a specific ref of the target repository.
        """
        try:
            self.repo.git.reset("--hard")
            self._checkout(ref)
        except:
            ret = f"Oops, it looks like you give a error commit id.\n"
            ret += "Please check commit id and retry to check the patch.\n"
            return ret
        self.repo.git.reset("--hard")
        revised_patch, fixed = utils.revise_patch(patch, self.dir)
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(revised_patch)
        logger.debug("original patch")
        logger.debug(patch)
        logger.debug("revised_patch")
        logger.debug(revised_patch)
        logger.info(f"Applying patch {f.name}")
        try:
            self.repo.git.apply([f.name], v=True)
            ret = "Patch applied successfully"
            # FIXME: patch or revised_patch?
            self.succeeded_patches.append(revised_patch)
            self.round_succeeded = True
        except Exception as e:
            ret = f"Patch failed to apply with error, context mismatch.\n"
            ret += "This patch does not apply, you CAN NOT send it to me again. Repeated patches will harm the lives of others.\n"
            ret += "Next I'll give you the context of the previous error patch in the old version, and you should modify the previous error patch according to this section.\n"
            path = re.findall(r"--- a/(.*)", revised_patch)[0]
            file = self.repo.tree(ref) / path
            content = file.data_stream.read().decode("utf-8")
            lines = content.split("\n")
            context, num_context = utils.process_string(revised_patch)
            lineno = utils.find_most_similar_block(context, lines, num_context)
            startline = max(lineno - 5, 0)
            endline = min(lineno + 5 + num_context, len(lines))
            ret += "Here are lines {} through {} of file {} for commit {}.\n".format(
                startline, endline, path, ref
            )
            ret += "```code snippet\n"
            for i in range(startline, endline):
                ret = ret + lines[i] + "\n"
            ret += "```\n"
            ret += "Please replace the error context in the error patch using the code in the code snippet above.(Including the difference between SPACE and INDENTATION.) At tbe beginning and end of the hunk, ONLY need 3 lines context. For lines that start with '-' and ' ', both need to be matched as context. You MUST never confuse '->' with ''s'.\n"
            ret += "Or use tools `locate_symbol` and `viewcode` to re-check patch-related code snippet.\n"
        self.repo.git.reset("--hard")
        return ret

    def _compile_patch(self, ref: str, complete_patch: str) -> str:
        """
        if all hunks could be applied successfully
        compile the patch, return error message if failed
        """
        self._checkout(ref)
        self.repo.git.reset("--hard")
        ret = ""
        # apply joined patch
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(complete_patch)
        try:
            self.repo.git.apply([f.name], v=True)
            logger.info(f"The joined patch could {f.name} be applied successfully")
        except Exception as e:
            logger.info(f"Failed to apply Complete patch {f.name}")
            # TODO: give feedback to LLM about which line can not be applied
            apply_result = ""
            ret += f"The joined patch could not be applied successfully, please try to revise the patch with provided tools and the following error message during applying the patch: {apply_result}\n"
            self.repo.git.reset("--hard")
            return ret

        # compile the patch
        logger.info(f"Start compile the patched source code")
        if not os.path.exists(os.path.join(self.dir, "build.sh")):
            logger.info("No build.sh file found.")
            exit(1)

        build_process = subprocess.Popen(
            ["/bin/bash", "build.sh"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.dir,
        )
        try:
            stdout, stderr = build_process.communicate(timeout=60 * 60)
            compile_result = stderr.decode("utf-8")
        except subprocess.TimeoutExpired:
            build_process.kill()
            ret += f"The compilation process of the patched source code is timeout. "
            return ret

        if build_process.returncode != 0:
            logger.info(f"Compilation failed\n{compile_result}\n")
            ret += "The source code could not be COMPILED successfully after applying the patch. "
            ret += "Next I'll give you the error message during compiling, and you should modify the error patch. "
            ret += f"Here is the error message:\n{compile_result}\n"
            ret += "Please revise the patch with above error message. "
            ret += "Or use tools `locate_symbol` and `viewcode` to re-check patch-related code snippet. "
            ret += "Please DO NOT send the same patch to me, repeated patches will harm the lives of others.\n"
            self.repo.git.reset("--hard")
        else:
            logger.info(f"Compilation succeeded\n")
            ret += "The patched source code could be COMPILED successfully! I really thank you for your great efforts.\n"
            self.compile_succeeded = True
        return ret

    def _run_testcase(self) -> str:
        """
        if a patch could be compiled successfully
        run the testcase, return error message if failed
        """
        ret = ""
        logger.info(f"Run testcase after compile")

        if not os.path.exists(os.path.join(self.dir, "test.sh")):
            logger.info("No test.sh file found, considered as test passed.")
            self.testcase_succeeded = True
            ret += "The patched source code could pass TESTCASE! I really thank you for your great efforts.\n"
            return ret
        testcase_process = subprocess.Popen(
            ["/bin/bash", "test.sh"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.dir,
        )

        try:
            stdout, stderr = testcase_process.communicate(timeout=60 * 30)
            testcase_result = stderr.decode("utf-8")
        except subprocess.TimeoutExpired:
            testcase_process.kill()
            ret += f"The TESTCASE process of the patched source code is timeout. "
            return ret

        if testcase_process.returncode != 0:
            logger.info(f"Testcase failed\n{testcase_result}\n")
            ret = "The patched program could not pass the testcase. "
            ret += "Next I'll give you the error message during running the testcase, and you should modify the previous error patch according to this section. "
            ret += f"Here is the error message:\n{testcase_result}\n"
            ret += "Please revise the patch with above error message. "
            ret += "Or use tools `locate_symbol` and `viewcode` to re-check patch-related code snippet. "
            ret += "Please DO NOT send the same patch to me, repeated patches will harm the lives of others.\n"
            self.compile_succeeded = False
            self.repo.git.reset("--hard")
        else:
            logger.info(f"Testcase succeeded\n")
            ret += "The patched source code could pass TESTCASE! I really thank you for your great efforts.\n"
            self.testcase_succeeded = True
        return ret

    def _run_poc(self) -> str:
        """
        if a patch could be compiled successfully
        run the testcase, return error message if failed
        """
        ret = ""
        logger.info(f"Run PoC after compile and run testcase")

        if not os.path.exists(os.path.join(self.dir, "poc.sh")):
            logger.info("No poc.sh file found, considered as PoC passed.")
            self.poc_succeeded = True
            ret += "Existing PoC could NOT TRIGGER the bug, which means your patch successfully fix the bug! I really thank you for your great efforts.\n"
            return ret
        poc_process = subprocess.Popen(
            ["/bin/bash", "poc.sh"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.dir,
        )

        try:
            stdout, stderr = poc_process.communicate(timeout=60 * 10)
            # FIXME: why stderr, not stdout
            poc_result = stderr.decode("utf-8")
        except subprocess.TimeoutExpired:
            poc_process.kill()
            ret += f"The TESTCASE process of the patched source code is timeout. "
            return ret

        if self.err_msg in poc_result:
            logger.info(f"PoC test FAIL, returncode = {poc_process.returncode}\n")
            logger.info(f"stderr: {poc_result}\n")
            ret += "Existing PoC could still trigger the bug, which means your patch fail to fix the bug. "
            ret += "Next I'll give you the error message during running the PoC, and you should modify the previous error patch according to this section. "
            ret += f"Here is the error message:\n{poc_result}\n"
            ret += "Please revise the patch with above error message. "
            ret += "Or use tools `locate_symbol` and `viewcode` to re-check patch-related code snippet. "
            ret += "Please DO NOT send the same patch to me, repeated patches will harm the lives of others.\n"
            self.compile_succeeded = False
            self.testcase_succeeded = False
            self.repo.git.reset("--hard")
        else:
            logger.info(f"PoC test PASS, returncode = {poc_process.returncode}\n")
            logger.info(f"stderr: {poc_result}\n")
            logger.info(f"stdout: {stdout}\n")
            ret += "Existing PoC could NOT TRIGGER the bug, which means your patch successfully fix the bug! I really thank you for your great efforts.\n"
            self.poc_succeeded = True
        return ret

    def _validate(self, ref: str, patch: str) -> str:
        """
        use _compile_patch, _run_testcase and _run_poc to validate a patch
        """
        if self.all_hunks_applied_succeeded:
            ret = ""
            if not self.compile_succeeded:
                ret += self._compile_patch(ref, patch)
            if self.compile_succeeded and not self.testcase_succeeded:
                ret += self._run_testcase()
            if (
                self.compile_succeeded
                and self.testcase_succeeded
                and not self.poc_succeeded
            ):
                ret += self._run_poc()
            return ret
        else:
            return self._apply_hunk(ref, patch)

    def get_tools(self):
        return (
            creat_viewcode_tool(self),
            creat_locate_symbol_tool(self),
            create_validate_tool(self),
        )


def creat_locate_symbol_tool(project: Project):
    @tool
    def locate_symbol(ref: str, symbol: str) -> str:
        """
        Locate a symbol in a specific ref of the target repository.
        """
        res = project._locate_symbol(ref, symbol)
        if res is not None:
            return "\n".join([f"{file}:{line}" for file, line in res])
        else:
            return "Symbol not found"

    return locate_symbol


def creat_viewcode_tool(project: Project):
    @tool
    def viewcode(ref: str, path: str, startline: int, endline: int) -> str:
        """
        View a file from a specific ref of the target repository. Lines between startline and endline are shown.
        """
        return project._viewcode(ref, path, startline, endline)

    return viewcode


def create_validate_tool(project: Project):
    @tool
    def validate(ref: str, patch: str) -> str:
        """
        validate a patch on a specific ref of the target repository.
        """
        return project._validate(ref, patch)

    return validate
