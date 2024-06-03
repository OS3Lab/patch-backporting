from langchain_core.tools import tool
import requests
import os
from git import Repo
import io
import subprocess
import json
import re
import logging
import tempfile
import traceback

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
            logging.warning("No match found for the context")
        if len(match_pos) > 1:
            logging.warning("Multiple matches found for the context")
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
        logging.warning("Failed to revise patch")
        logging.warning(e)
        print(''.join(traceback.TracebackException.from_exception(e).format()))
        return patch, False

class Project:
    def __init__(self, project_url:str, dir:str):
        self.project_url = project_url
        self.dir = dir
        self.repo = Repo(dir)
    
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
        file = self.repo.tree(ref) / path
        content = file.data_stream.read().decode('utf-8')
        lines = content.split('\n')
        ret = []
        endline = min(endline,len(lines))
        for i in range(startline-1,endline):
            ret.append(lines[i])
        return '\n'.join(ret)
    
    def _get_patch(self, ref:str) -> str:
        return self.repo.git.show(f'{ref}^..{ref}')
    
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
    
    def _test_patch(self, ref:str, patch:str) -> str:
        print('test_patch',ref,patch)
        self._checkout(ref)
        revised_patch, fixed = revise_patch(patch, self.dir)
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(revised_patch)
        print('revised_patch')
        print(revised_patch)
        # print(f'Applying patch {f.name}')
        logging.info(f'Applying patch {f.name}')
        try:
            self.repo.git.apply([f.name],v=True)
            ret = 'Patch applied successfully'
        except Exception as e:
            ret = f'Patch failed to apply with error: {e.stderr}'

        # TODO: compile & PoC & testcase
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


# @tool
# def get_patch(ref:str) -> str:
#     '''
#     Get a patch of a specific ref of the target repository.
#     '''
#     return project._get_patch(ref)

def create_validate_tool(project:Project):
    @tool
    def validate(ref:str, patch:str) -> str:
        '''
        validate a patch on a specific ref of the target repository.
        '''
        return project._test_patch(ref, patch)
    
    return validate
