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
import os
from tools import Project
from prompt import SYSTEM_PROMPT, USER_PROMPT


load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
if base_url is None:
    base_url = 'https://api.openai.com/v1'

llm = ChatOpenAI(temperature=0, model="gpt-4-turbo", api_key=api_key, 
                    openai_api_base=base_url,verbose=True)

prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", SYSTEM_PROMPT),
                    ("user", USER_PROMPT),
                    MessagesPlaceholder(variable_name="agent_scratchpad"),
                ]
            )

project_url = 'https://github.com/FFmpeg/FFmpeg'
new_patch = '7971f62120a55c141ec437aa3f0bacc1c1a3526b'
new_patch_parent = '82ad1b76751bcfad5005440db48c46a4de5d6f02'
target_release = '6a69e7a2cbcacd8a9678675ed1e77cd26937b4f1'
project_dir = 'dataset/FFmpeg/FFmpeg'

project = Project(project_url, project_dir)

viewcode, locate_symbol, validate = project.get_tools()

tools = [viewcode,  locate_symbol, validate]
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=30)


logfile = "output.log"
log_handler = FileCallbackHandler(logfile)



patch = project._get_patch(new_patch)

print(patch)

pps = split_patch(patch)
for idx, pp in enumerate(pps):
    project.round_succeeded = False
    project._test_patch(target_release, pp)
    if project.round_succeeded:
        logger.info(f"Hunk {idx} can be applied without any conflicts")
        continue
    else:
        logger.info(f'Hunk {idx} can not be applied, using LLM to generate a fix')
        logger.info(f"Patch in the new version as below\n----------------------------------\n{pp}\n----------------------------------\n")
        agent_executor.invoke(
            {
                "project_url": project_url,
                "new_patch_parent":new_patch_parent,
                "new_patch":pp,
                "target_release":target_release
            },
            {"callbacks": [log_handler]}
        )
        if not project.round_succeeded:
            logger.error(f"Failed to backport the hunk {idx} \n----------------------------------\n{pp}\n----------------------------------\n")
            logger.error(f"Abort")
            break
else:
    logger.info("Successfully backported the patch")
    for patch in project.succeeded_patches:
        print(patch)

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

