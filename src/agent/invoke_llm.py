import os
import re

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.callbacks import FileCallbackHandler
from langchain_openai import ChatOpenAI

from agent.prompt import SYSTEM_PROMPT, USER_PROMPT_HUNK, USER_PROMPT_PATCH
from tools.logger import logger
from tools.project import Project
from tools.utils import split_patch


def initial_agent(project: Project, api_key: str, debug_mode: bool):
    base_url = "https://api.openai.com/v1"

    llm = ChatOpenAI(
        temperature=0.5,
        model="gpt-4-turbo",
        api_key=api_key,
        openai_api_base=base_url,
        verbose=True,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("user", USER_PROMPT_HUNK),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    viewcode, locate_symbol, validate = project.get_tools()
    tools = [viewcode, locate_symbol, validate]
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent, tools=tools, verbose=debug_mode, max_iterations=30
    )
    return agent_executor, llm


def do_backport(
    agent_executor: AgentExecutor, project: Project, data, llm: ChatOpenAI, logfile: str
):
    log_handler = FileCallbackHandler(logfile)

    patch = project._get_patch(data.new_patch)
    pps = split_patch(patch, True)
    for idx, pp in enumerate(pps):
        project.round_succeeded = False
        project.context_mismatch_times = 0
        ret = project._apply_hunk(data.target_release, pp, False)
        if project.round_succeeded:
            logger.debug(f"Hunk {idx} can be applied without any conflicts")
            continue
        else:
            try:
                similar_block = re.findall(
                    r"version.\n(.*?)\nBesides,", ret, re.DOTALL
                )[0]
            except:
                similar_block = "Something error in finding similar block\n"
                logger.warning("Something error in finding similar block")
            logger.debug(f"Hunk {idx} can not be applied, using LLM to generate a fix")
            agent_executor.invoke(
                {
                    "project_url": data.project_url,
                    "new_patch_parent": data.new_patch_parent,
                    "new_patch": pp,
                    "target_release": data.target_release,
                    "similar_block": similar_block,
                },
                {"callbacks": [log_handler]},
            )
            if not project.round_succeeded:
                logger.debug(
                    f"Failed to backport the hunk {idx} \n----------------------------------\n{pp}\n----------------------------------\n"
                )
                logger.error(f"Reach max_iterations for hunk {idx}")
                exit(1)

    project.all_hunks_applied_succeeded = True
    logger.info(f"Aplly all hunks in the patch      PASS")
    complete_patch = "\n".join(project.succeeded_patches)
    project.repo.git.clean("-fdx")
    for file in os.listdir(data.patch_dataset_dir):
        if os.path.exists(f"{data.project_dir}{file}"):
            os.remove(f"{data.project_dir}{file}")
        os.symlink(f"{data.patch_dataset_dir}{file}", f"{data.project_dir}{file}")

    validate_ret = project._validate(data.target_release, complete_patch)
    if project.poc_succeeded:
        logger.info(
            f"Successfully backport the patch to the target release {data.target_release}"
        )
        for patch in project.succeeded_patches:
            logger.info(patch)
        return

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("user", USER_PROMPT_PATCH),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    viewcode, locate_symbol, validate = project.get_tools()
    tools = [viewcode, locate_symbol, validate]
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent, tools=tools, verbose=True, max_iterations=20
    )
    agent_executor.invoke(
        {
            "project_url": data.project_url,
            "new_patch_parent": data.new_patch_parent,
            "target_release": data.target_release,
            "new_patch": patch,
            "complete_patch": complete_patch,
            "compile_ret": validate_ret,
        },
        {"callbacks": [log_handler]},
    )
    if project.poc_succeeded:
        logger.info(
            f"Successfully backport the patch to the target release {data.target_release}"
        )
        for patch in project.succeeded_patches:
            logger.info(patch)
    else:
        logger.error(
            f"Failed backport the patch to the target release {data.target_release}"
        )
