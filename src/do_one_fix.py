from tools import Project, split_patch
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from operator import itemgetter
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain import hub
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages
from langchain.globals import set_debug
from langchain_core.callbacks import FileCallbackHandler
from logger import logger
from dotenv import load_dotenv
import os, sys, re, time
from tools import Project
from prompt import SYSTEM_PROMPT, USER_PROMPT_HUNK, USER_PROMPT_PATCH
import yaml


load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
patch_target = os.getenv("PATCH_TARGET")
project_dir = os.getenv("PROJECT_DIR")
patch_dataset_dir = os.getenv("PATCH_DATASET_DIR")

with open(patch_dataset_dir + 'config.yml', 'r') as file:
    config = yaml.safe_load(file)
project = config['project']
project_url = config['project_url']
new_patch = config['new_patch']
new_patch_parent = config['new_patch_parent']
target_release = config['target_release']
sanitizer = config['sanitizer']
error_message = config['error_massage']

if base_url is None:
    base_url = 'https://api.openai.com/v1'

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
import check_api_usage
before_usage = check_api_usage.get_usage(api_key)

llm = ChatOpenAI(temperature=0.5, model="gpt-4-turbo", api_key=api_key, 
                    openai_api_base=base_url,verbose=True)

prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", SYSTEM_PROMPT),
                    ("user", USER_PROMPT_HUNK),
                    MessagesPlaceholder(variable_name="agent_scratchpad"),
                ]
            )

project = Project(project_url, project_dir, patch_dataset_dir)
viewcode, locate_symbol, validate = project.get_tools()
tools = [viewcode,  locate_symbol, validate]
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=30)


logfile = "output.log"
log_handler = FileCallbackHandler(logfile)

'''
split patch into hunks and try to backport each hunk, if failed, use LLM to generate a fix
'''

tmp_patch = '''--- a/tools/tiffcp.c
+++ b/tools/tiffcp.c
@@ -1490,6 +1490,13 @@
 		return 0;
 	}
+
+	if ((imagew - tilew * spp) > INT_MAX) {
+		TIFFError(TIFFFileName(in),
+		          "Error, image raster scan line size is too large");
+		return 0;
+	}
+
 	iskew = imagew - tilew*spp;
 	tilebuf = limitMalloc(tilesize);
 	if (tilebuf == 0)
'''
patch = project._get_patch(new_patch)
# patch = project._get_patch(patch_target)
pps = split_patch(patch)
# pps = [tmp_patch]
for idx, pp in enumerate(pps):
    project.round_succeeded = False
    ret = project._apply_hunks(target_release, pp)
    if project.round_succeeded:
        logger.info(f"Hunk {idx} can be applied without any conflicts")
        continue
    else:
        similar_block = re.findall(r'section.\n(.*?)\nPlease', ret, re.DOTALL)[0]
        logger.info(f'Hunk {idx} can not be applied, using LLM to generate a fix')
        logger.info(f"Patch in the new version as below\n----------------------------------\n{pp}\n----------------------------------\n")
        agent_executor.invoke(
            {
                "project_url": project_url,
                "new_patch_parent":new_patch_parent,
                "new_patch":pp,
                "target_release":target_release,
                "similar_block":similar_block
            },
            {"callbacks": [log_handler]}
        )
        if not project.round_succeeded:
            logger.error(f"Failed to backport the hunk {idx} \n----------------------------------\n{pp}\n----------------------------------\n")
            logger.error(f"Abort")
            exit(1)

'''
now all hunks can be applied successfully, merge them and try to compile, if failed, use LLM to generate a fix
'''
project.all_hunks_applied_succeeded = True
logger.info("Successfully apply all hunks, try to join all hunks into one patch and test")
complete_patch = '\n'.join(project.succeeded_patches)
print(complete_patch)


# create symbolic link for each patch dataset file
for file in os.listdir(patch_dataset_dir):
    if os.path.exists(f"{project_dir}{file}"):
        os.remove(f"{project_dir}{file}")
    os.symlink(f"{patch_dataset_dir}{file}", f"{project_dir}{file}")
    logger.info(f"Create symbolic link {project_dir}{file}")

project.compile_succeeded = True
project.testcase_succeeded = True
# project.poc_succeeded = True
validate_ret = project.not_wraped_validate(target_release, complete_patch)
print(validate_ret)
if project.poc_succeeded:
    logger.info(f"Successfully backport patch to target release {target_release}")

for patch in project.succeeded_patches:
    print(patch)

time.sleep(10)
after_usage = check_api_usage.get_usage(api_key)
print(f"\nCurrent time: {after_usage['current_time']}")
print(f"This patch total cost: ${(after_usage['total_cost'] - before_usage['total_cost']):.2f}")
print(f"This patch total consume tokens: {(after_usage['total_consume_tokens'] - before_usage['total_consume_tokens'])/1000}(k)\n")

exit(1)

prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("user", USER_PROMPT_PATCH),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=5)
agent_executor.invoke(
    {
        "project_url": project_url,
        "new_patch_parent":new_patch_parent,
        "new_patch":complete_patch,
        "target_release":target_release,
        "error_message":validate_ret
    },
    {"callbacks": [log_handler]}
)
if not project.compile_succeeded:
    logger.error(f"Failed to complie the patch\n")
    logger.error(f"Abort")
else:
    logger.info(f"Successfully backport the patch to target release {target_release}")


time.sleep(10)
after_usage = check_api_usage.get_usage(api_key)
print(f"\nCurrent time: {after_usage['current_time']}")
print(f"This patch total cost: ${(after_usage['total_cost'] - before_usage['total_cost']):.2f}")
print(f"This patch total consume tokens: {(after_usage['total_consume_tokens'] - before_usage['total_consume_tokens'])/1000}(k)\n")

# agent_executor.invoke(
#     {
#         "project_url":"https://github.com/openssl/openssl",
# 		"new_patch_parent":'8e257b86e5812c6e1cfa9e8e5f5660ac7bed899d',
# 		"new_patch":'63bcf189be73a9cc1264059bed6f57974be74a83',
# 		"target_release":'43d8f88511991533f53680a751e9326999a6a31f'
# 	},
#     {"callbacks": [log_handler]}
# )


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

