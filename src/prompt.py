SYSTEM_PROMPT = '''
Your task is to backport a patch fixing a vuln from a newer(release) version of the software to an older(target) version.
Your objective is to analyze how the patch modifies the newer version and apply the necessary changes to the older version.

You have 3 tools: `viewcode` `locate_symbol` and `test_patch`

- `viewcode` allows you to view a file in the codebase of a ref
0. ref: the commit hash of the ref you want to view the file from.
1. path: the file path of the file you want to view. The patch is the relative path of the file to the project root directory. For example, if you want to view the file `foo.c` in the project root directory, the file path is `foo.c`. If you want to view the file `foo.c` in the directory `bar`, the file path is `bar/foo.c`.
2. startline: the start line of the code snippet you want to view.
3. endline: the end line of the code snippet you want to view.

- `locate_symbol` allows you to locate a symbol (function name for example) in a specific ref, so you can better navigate the codebase. the return value is in format `file_path:line_number`
0. ref: the commit hash of the ref you want to view the file from.
1. symbol: the symbol you want to locate in the codebase.

- `validate` allows you to test whether a patch can fix the vuln on a specific ref without any conflicts.
0. ref: the commit hash of the ref you want to test the patch on.
1. patch: the patch you want to test.
'''

USER_PROMPT = '''
I will give ten dollar tip for your assistance to backport the patch.
our assistance is VERY IMPORTANT to the security research and can save thousands of lives.

the project is {project_url}
For the ref {new_patch_parent},
the patch below is merged to fix a security issue.

```
{new_patch}
```

i want to backport it to ref {target_release}
the patch can not be cherry-picked directly because of conflicts. 
This may be due to context changes or namespace changes, sometimes code structure changes.

Your workflow should be:
1. Review the patch of the newer version
2. review the file in the old codebase and understand why it can not be cherry-picked directly.
3. craft a patch for the older version that can fix the vuln.
4. test the patch on the older version to make sure it can be applied without any conflicts.

You must use the tools provided to analyze the patch and the codebase to craft a patch for the target release.
The patch you craft should be in the unified diff format and does not contain any shortcuts like `...`.
At the beginning and end of the hunk of the crafted patch, there are MUST MUST at least 3 lines of context.
In most cases, the fixing logic is the same as the newer version. You MUST not introduce any new bugs or vulnerabilities.
And finally, you MUST use `validate` to test your patch on the target release to make sure it can fix the vuln without any conflicts. 
Or you need to revise your patch and test it again.
'''