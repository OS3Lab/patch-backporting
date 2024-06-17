from langchain_core.tools import tool
import requests
import os
from git import Repo
import io
import subprocess
import json
import re
from logger import logger
import tempfile
import traceback
import Levenshtein
from typing import List, Tuple

def find_most_similar_block(code_snippet: str, lines: List[str], snippet_num: int) -> int:
    min_distance = float('inf')
    best_start_index = -1

    for i in range(len(lines) - snippet_num + 1): 
        combined = '\n'.join(lines[i: i + snippet_num])
        # for j in range(snippet_num):
        #     combined += ''.join(lines[i + j].strip())
        
        distance = Levenshtein.distance(combined, code_snippet)
        if distance < min_distance:
            min_distance = distance
            best_start_index = i + 1

    return best_start_index

def process_string(input_string: str) -> tuple[str, int]:
    
    lines = input_string.split('\n')
    processed_lines = []
    
    for line in lines[3:-1]:
        if line.startswith(' '):
            processed_lines.append(line[1:])
        elif line.startswith('-'):
            processed_lines.append(line[1:])
        elif line.startswith('+'):
            continue
        else:
            processed_lines.append(line)
    
    processed_lines_count = len(processed_lines)
    processed_string = '\n'.join(processed_lines)
    
    return processed_string, processed_lines_count

def find_sub_list(lst,neddle):
    match_pos = []
    # KMP algorithm
    def get_next(p):
        next = [0] * len(p)
        for i in range(1,len(p)):
            j = next[i-1]
            while j > 0 and p[i] != p[j]:
                j = next[j-1]
            if p[i] == p[j]:
                j += 1
            next[i] = j
        return next
    next = get_next(neddle)
    i = 0
    j = 0
    while i < len(lst):
        if lst[i] == neddle[j]:
            i += 1
            j += 1
            if j == len(neddle):
                match_pos.append(i - j)
                j = next[j-1]
        else:
            if j == 0:
                i += 1
            else:
                j = next[j-1]
    return match_pos


def revise_patch(patch: str, project_path: str) -> tuple[str, bool]:
    def revise_hunk(lines: list[str], file_content: list[str]) -> tuple[str, bool]:
        if len(lines[-1]) == 0:
            lines = lines[:-1]
        orignal_line_number = sum(1 for line in lines[1:] if not line.startswith("+"))
        patched_line_number = sum(1 for line in lines[1:] if not line.startswith("-"))
        # @@ -3357,10 +3357,16 @@
        # extract the line number and the number of lines
        chunks = re.findall(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)", lines[0])[0]
        if chunks[0] != chunks[2]:
            fixed = True
        orignal_content = []
        patched_content = []

        for line in lines[1:]:
            if line.startswith("-"):
                orignal_content.append(line[1:])
            elif line.startswith("+"):
                patched_content.append(line[1:])
            elif line.startswith(" "):
                orignal_content.append(line[1:])
                patched_content.append(line[1:])
        
        # find the context lines
        match_pos = find_sub_list(file_content,orignal_content)
        if len(match_pos) == 0:
            logger.warning("No match found for the context")
        if len(match_pos) > 1:
            logger.warning("Multiple matches found for the context")
        if len(match_pos) == 1:
            start = match_pos[0]
            if lines[-1][0] != ' ':
                end = start + len(orignal_content)
                if end < len(file_content):
                    lines.append(' '+file_content[end])
                    orignal_line_number += 1
                    patched_line_number += 1

        hunk = "\n".join(lines[1:])

        header = f"@@ -{chunks[0]},{orignal_line_number} +{chunks[2]},{patched_line_number} @@{chunks[4]}\n"

        fixed = True
        return header + hunk, fixed

    def revise_block(lines: list[str]) -> tuple[list[str], bool]:
        file_path_a = re.findall(r"--- a/(.*)", lines[0])[0]
        file_path_b = re.findall(r"\+\+\+ b/(.*)", lines[1])[0]
        fixed_file_path_a = os.path.normpath(file_path_a)
        fixed_file_path_b = os.path.normpath(file_path_b)
        block_fixed = file_path_a != fixed_file_path_a or file_path_b != fixed_file_path_b

        assert file_path_a == file_path_b and fixed_file_path_a == fixed_file_path_b
        fixed_lines = [
            f"--- a/{fixed_file_path_a}",
            f"+++ b/{fixed_file_path_b}",
        ]

        with open(os.path.join(project_path, file_path_a), "r") as f:
            file_content = f.readlines()
            file_content = [line.rstrip() for line in file_content]

        last_line = -1
        for line_no in range(2, len(lines)):
            if lines[line_no].startswith("@@"):
                if last_line != -1:
                    hunk_lines, hunk_fixed = revise_hunk(lines[last_line:line_no], file_content)
                    fixed_lines.append(hunk_lines)
                    block_fixed = block_fixed or hunk_fixed
                last_line = line_no
        if last_line != -1:
            hunk_lines, hunk_fixed = revise_hunk(lines[last_line:], file_content)
            fixed_lines.append(hunk_lines)
            block_fixed = block_fixed or hunk_fixed

        return fixed_lines, block_fixed

    try:
        lines = patch.splitlines()
        fixed_lines = []

        last_line = -1
        fixed = False
        for line_no in range(len(lines)):
            if lines[line_no].startswith("--- a/"):
                if last_line != -1:
                    block_lines, block_fixed = revise_block(lines[last_line:line_no])
                    fixed_lines += block_lines
                    fixed = fixed or block_fixed
                last_line = line_no
        if last_line != -1:
            block_lines, block_fixed = revise_block(lines[last_line:])
            fixed_lines += block_lines
            fixed = fixed or block_fixed

        return "\n".join(fixed_lines)+'\n', fixed
    except Exception as e:
        logger.warning("Failed to revise patch")
        logger.warning(e)
        print(''.join(traceback.TracebackException.from_exception(e).format()))
        return patch, False

class Project:
    def __init__(self, project_url:str, dir:str, sh_path:str=''):
        self.project_url = project_url
        self.dir = dir
        self.build_sh_path = sh_path
        self.repo = Repo(dir)
        self.succeeded_patches = []
        self.round_succeeded = False
        self.all_hunks_applied_succeeded = False
        self.compile_succeeded = False

    def _checkout(self, ref:str):
        self.repo.git.checkout(ref)

    def _prepare(self):
        ctags = subprocess.run(['ctags','--excmd=number','-R','.'],stdout=subprocess.PIPE,cwd=self.dir,stdin=subprocess.PIPE,stderr=subprocess.DEVNULL)
        ctags.check_returncode()
        self.symbol_map = {}
        with open(os.path.join(self.dir,'tags'),'r') as f:
            for line in f:
                if line.startswith('!_TAG_'):
                    continue
                try:
                    symbol,file,line = line.strip().split(';"')[0].split('\t')
                    line = int(line)
                    if symbol not in self.symbol_map:
                        self.symbol_map[symbol] = []
                    self.symbol_map[symbol].append((file,line))
                except:
                    print('Error parsing line:',line)

    def _viewcode(self, ref:str, path:str, startline:int, endline:int) -> str:
        try: 
            file = self.repo.tree(ref) / path
        except:
            return "This file doesn't exist in this commit."
        content = file.data_stream.read().decode('utf-8')
        lines = content.split('\n')
        ret = []
        endline = min(endline,len(lines))
        for i in range(startline-1,endline):
            ret.append(lines[i])
        return '\n'.join(ret)
    
    def _get_patch(self, ref:str) -> str:
        try:
            return self.repo.git.show(f'{ref}^..{ref}')
        except:
            return "Error commit id, please check if the commit id is correct."
    
    def _locate_symbol(self, ref:str, symbol:str) -> str:
        self._checkout(ref)
        self._prepare()
        if symbol in self.symbol_map:
            return self.symbol_map[symbol]
        else:
            return None
        #locate the symbol in the repo
        # compile the code to get the symbol
        # subprocess.run(['bear','make'],cwd=self.dir).check_returncode()
        # locate the symbol
        # clangd = subprocess.run(['clangd'],stdout=subprocess.PIPE,cwd=self.dir,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        #         {
        #     "jsonrpc": "2.0",
        #     "id": 2,
        #     "method": "textDocument/definition",
        #     "params": {
        #         "textDocument": {
        #             "uri": f"file://{path}",
        #         },
        #         "position": {
        #             "line": line,
        #             "character": chr,
        #         },
        #     },
        # }
    
    def _apply_hunks(self, ref:str, patch:str) -> str:
        # print('test_patch',ref,patch)
        self._checkout(ref)
        self.repo.git.reset('--hard')
        revised_patch, fixed = revise_patch(patch, self.dir)
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(revised_patch)
        # print('revised_patch')
        # print(revised_patch)
        logger.debug('original patch')
        logger.debug(patch)
        logger.debug('revised_patch')
        logger.debug(revised_patch)
        # print(f'Applying patch {f.name}')
        logger.info(f'Applying patch {f.name}')
        try:
            self.repo.git.apply([f.name],v=True)
            ret = 'Patch applied successfully'
            self.succeeded_patches.append(patch)
            self.round_succeeded = True
        except Exception as e:
            ret = f'Patch failed to apply with error, context mismatch.\n'
            ret += 'This patch does not apply, you CAN NOT send it to me again. Repeated patches will harm the lives of others.\n'
            ret += 'Next I\'ll give you the context of the previous error patch in the old version, and you should modify the previous error patch according to this section.\n'
            path = re.findall(r"--- a/(.*)", revised_patch)[0]
            file = self.repo.tree(ref) / path
            content = file.data_stream.read().decode('utf-8')
            lines = content.split('\n')
            context, num_context = process_string(revised_patch)
            lineno = find_most_similar_block(context, lines, num_context)
            startline = max(lineno - 5, 0)
            endline = min(lineno + 5 + num_context, len(lines))
            ret += 'Here are lines {} through {} of file {} for commit {}.\n'.format(startline, endline, path, ref)
            ret += '```code snippet\n'
            for i in range(startline, endline):
                ret = ret + lines[i] + '\n'
            ret += '```\n'
            ret += 'Please replace the error context in the error patch using the code in the code snippet above.(Including the difference between SPACE and INDENTATION.)\n'
            ret += 'Or use tools `locate_symbol` and `viewcode` to re-check patch-related code snippet.\n'
        self.repo.git.reset('--hard')
        return ret
    
    def _compile_patch(self, ref: str, complete_patch: str) -> str:
        """
        if all hunks could be applied successfully
        compile the patch, return error message if failed
        """
        self._checkout(ref)
        self.repo.git.reset('--hard')
        ret = ''
        # apply joined patch
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(complete_patch)
        try:
            self.repo.git.apply([f.name],v=True)
            logger.info(f'The joined patch could {f.name} be applied successfully')
        except Exception as e:
            logger.info(f'Failed to apply Complete patch {f.name}')
            # TODO: 反馈具体哪一行不能apply, 让大模型直接修改整个patch
            error_msg = ''
            ret += 'The joined patch could not be applied successfully, please try to revise the patch with provided tools and the following error message during applying the patch:\n'
            ret += error_msg
            self.repo.git.reset('--hard')
            return ret
        
        # compile the patch
        logger.info(f'Start compile the patched source code')
        build_process = subprocess.Popen(
            ['/bin/bash', self.build_sh_path],
            stdin=subprocess.DEVNULL,
            # stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.dir,
            # env=env,
            # shell=True,
            # executable="/bin/bash",
        )
        try:
            stdout, stderr = build_process.communicate(timeout=60 * 60)
        except subprocess.TimeoutExpired:
            build_process.kill()
            ret += f'The compilation process of the patched source code is timeout.'
            exit(1)

        if build_process.returncode != 0:
            logger.info(f'\nCompilation failed\n{stderr}\n')
            compile_result = stderr.decode('utf-8')   
            ret += 'The source code could not be compiled successfully after applying the patch. '
            ret += 'Next I\'ll give you the error message during compiling, and you should modify the error patch.'
            ret += f'Here is the error message:\n{compile_result}\n'
            ret += 'Please revise the patch with above error message.'
            ret += 'Or use tools `locate_symbol` and `viewcode` to re-check patch-related code snippet. '
            ret += 'Please DO NOT send the same patch to me, repeated patches will harm the lives of others.\n'
        else:
            ret += 'The patched source code could be compiled successfully! I really thank you for your great efforts.\n'
            self.compile_succeeded = True
        self.repo.git.reset('--hard')
        return ret
    
    def get_tools(self):
        return creat_viewcode_tool(self), creat_locate_symbol_tool(self), create_validate_tool(self)


def creat_locate_symbol_tool(project:Project):
    @tool
    def locate_symbol(ref:str, symbol:str) -> str:
        '''
        Locate a symbol in a specific ref of the target repository.
        '''
        res = project._locate_symbol(ref, symbol)
        if res is not None:
            return '\n'.join([f'{file}:{line}' for file,line in res])
        else:
            return 'Symbol not found'
    
    return locate_symbol

def creat_viewcode_tool(project:Project):
    @tool
    def viewcode(ref:str, path:str, startline:int, endline:int) -> str:
        '''
        View a file from a specific ref of the target repository. Lines between startline and endline are shown.
        '''
        return project._viewcode(ref, path, startline, endline)
    
    return viewcode

def create_validate_tool(project:Project):
    @tool
    def validate(ref:str, patch:str) -> str:
        '''
        validate a patch on a specific ref of the target repository.
        '''
        if project.all_hunks_applied_succeeded:
            return project._compile_patch(ref, patch)
        else:
            return project._apply_hunks(ref, patch)
    
    return validate

def split_patch(patch):
    def split_block(lines:list[str]):
        file_path_line_a = lines[0]
        file_path_line_b = lines[1]
        last_line = -1
        for line_no in range(2, len(lines)):
            if lines[line_no].startswith("@@"):
                if last_line != -1:
                    content=  file_path_line_a+ '\n' + file_path_line_b + '\n' + '\n'.join(lines[last_line:line_no])
                    yield content
                last_line = line_no
        if last_line != -1:
            content=  file_path_line_a+ '\n' + file_path_line_b + '\n'  + '\n'.join(lines[last_line:])
            yield content

    try:
        lines = patch.splitlines()
        message = ''
        last_line = -1
        fixed = False
        for line_no in range(len(lines)):
            if lines[line_no].startswith("--- a/"):
                if last_line >= 0:
                    print("_______________________________________ll_______")
                    print(lines[line_no], last_line)
                    for x in split_block(lines[last_line:line_no - 2]):
                        yield message + x
                if last_line == -1:
                    message = '\n'.join(lines[:line_no - 2])
                if lines[line_no].endswith(".rst") or lines[line_no].endswith(".yaml") or lines[line_no].endswith(".yml") or lines[line_no].endswith(".md"):
                    last_line = -2
                else: 
                    last_line = line_no
        if last_line >= 0:
            for x in split_block(lines[last_line:]):
                yield message + x

    except Exception as e:
        logger.warning("Failed to split patch")
        logger.warning(e)
        print(''.join(traceback.TracebackException.from_exception(e).format()))
        return None