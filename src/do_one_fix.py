from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.callbacks import FileCallbackHandler
from logger import logger
from types import SimpleNamespace
from tools import Project, split_patch
from prompt import SYSTEM_PROMPT, USER_PROMPT_HUNK, USER_PROMPT_PATCH
from check.usage import get_usage
import os, re, argparse, yaml

def load_yml(file_path: str):
    with open(file_path, 'r') as file:
        config = yaml.safe_load(file)
        
    data = SimpleNamespace()
    data.project = config.get('project')
    data.project_url = config.get('project_url')
    data.project_dir = config.get('project_dir')
    data.patch_dataset_dir = config.get('patch_dataset_dir')
    data.openai_key = config.get('openai_key')
    data.tag = config.get('tag')
    
    data.new_patch = config.get('new_patch', "")
    if not data.new_patch or not data.new_patch:
        logger.error("Please check your configuration to make sure new_patch is correct!\n")
        exit(1)
    
    data.new_patch_parent = config.get('new_patch_parent', "")
    if not data.new_patch_parent or not data.new_patch_parent:
        logger.error("Please check your configuration to make sure new_patch_parent is correct!\n")
        exit(1)
        
    data.target_release = config.get('target_release', "")
    if not data.target_release or not data.target_release:
        logger.error("Please check your configuration to make sure target_release is correct!\n")
        exit(1)
    
    data.sanitizer = config.get('sanitizer', "")
    data.error_message = config.get('error_massage', "")
    if not data.sanitizer or not data.error_message:
        logger.warning("Dataset without error info which means that this vulnerability may not have PoC\n")
    
    return data

def initial_agent(project: Project, api_key: str):
    base_url = 'https://api.openai.com/v1'

    llm = ChatOpenAI(temperature=0, model="gpt-4-turbo", api_key=api_key, 
                        openai_api_base=base_url,verbose=True)

    prompt = ChatPromptTemplate.from_messages(
                    [
                        ("system", SYSTEM_PROMPT),
                        ("user", USER_PROMPT_HUNK),
                        MessagesPlaceholder(variable_name="agent_scratchpad"),
                    ]
                )
    viewcode, locate_symbol, validate = project.get_tools()
    tools = [viewcode,  locate_symbol, validate]
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=30)
    return agent_executor

def do_backport(agent_executor, project, data):
    
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    logfile = os.path.join(log_dir, "{}-llm.log".format(data.tag))
    log_handler = FileCallbackHandler(logfile)
    
    patch = project._get_patch(data.new_patch)
    pps = split_patch(patch)
    for idx, pp in enumerate(pps):
        project.round_succeeded = False
        ret = project._apply_hunks(data.target_release, pp)
        if project.round_succeeded:
            logger.info(f"Hunk {idx} can be applied without any conflicts")
            continue
        else:
            similar_block = re.findall(r'section.\n(.*?)\nPlease', ret, re.DOTALL)[0]
            logger.info(f'Hunk {idx} can not be applied, using LLM to generate a fix')
            logger.info(f"Patch in the new version as below\n----------------------------------\n{pp}\n----------------------------------\n")
            agent_executor.invoke(
                {
                    "project_url": data.project_url,
                    "new_patch_parent":data.new_patch_parent,
                    "new_patch":pp,
                    "target_release":data.target_release,
                    "similar_block":similar_block
                },
                {"callbacks": [log_handler]}
            )
            if not project.round_succeeded:
                logger.error(f"Failed to backport the hunk {idx} \n----------------------------------\n{pp}\n----------------------------------\n")
                logger.error(f"Abort")
                exit(1)

    project.all_hunks_applied_succeeded = True
    logger.info("Successfully apply all hunks, try to join all hunks into one patch and test")
    complete_patch = '\n'.join(project.succeeded_patches)
    # create symbolic link for each patch dataset file
    for file in os.listdir(data.patch_dataset_dir):
        if os.path.exists(f"{data.project_dir}{file}"):
            os.remove(f"{data.project_dir}{file}")
        os.symlink(f"{data.patch_dataset_dir}{file}", f"{data.project_dir}{file}")

    # project.compile_succeeded = True
    # project.testcase_succeeded = True
    # project.poc_succeeded = True
    validate_ret = project.not_wraped_validate(data.target_release, complete_patch)
    if project.poc_succeeded:
        logger.info(f"Successfully backport patch to target release {data.target_release}")
        for patch in project.succeeded_patches:
            print(patch)
    return
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
        exit(1)
    else:
        logger.info(f"Successfully backport the patch to target release {target_release}")

def main():
    parser = argparse.ArgumentParser(description='Backports patch with the help of LLM', 
                                    usage='%(prog)s --config CONFIG.yml\ne.g.: python %(prog)s --config CVE-examaple.yml')
    parser.add_argument('-c', '--config', type=str, required=True, help='CVE config yml')
    args = parser.parse_args()
    
    config_file = args.config
    data = load_yml(config_file)
    
    data.project_dir = os.path.expanduser(data.project_dir if data.project_dir.endswith('/') else data.project_dir + '/')
    data.patch_dataset_dir = os.path.expanduser(data.patch_dataset_dir if data.patch_dataset_dir.endswith('/') else data.patch_dataset_dir + '/')
    
    if not os.path.isdir(data.project_dir):
        logger.error(f"Project directory does not exist: {data.project_dir}")
        exit(1)
    if not os.path.isdir(data.patch_dataset_dir):
        logger.error(f"Patch dataset directory does not exist: {data.patch_dataset_dir}")
        exit(1)

    project = Project(data.project_url, data.project_dir, data.patch_dataset_dir)
    agent_executor = initial_agent(project, data.openai_key)
    
    before_usage = get_usage(data.openai_key)
    do_backport(agent_executor, project, data)
    after_usage = get_usage(data.openai_key)
    logger.info(f"This patch total cost: ${(after_usage['total_cost'] - before_usage['total_cost']):.2f}")
    logger.info(f"This patch total consume tokens: {(after_usage['total_consume_tokens'] - before_usage['total_consume_tokens'])/1000}(k)\n")

if __name__ == '__main__':
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

