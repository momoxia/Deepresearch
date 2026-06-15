from claude_agent_sdk import create_sdk_mcp_server

from agents.tools.artifact_tools import generate_artifact
from agents.tools.memory_tools import load_memory, save_memory
from agents.tools.pdf_tools import pdf_grep, pdf_parse, pdf_read, pdf_vision
from agents.tools.web_tools import (
    web_fetch,
    web_search,
    web_search_and_fetch,
    web_search_scholar,
)

research_mcp_server = create_sdk_mcp_server(
    name="research-tools",
    version="0.1.0",
    tools=[
        load_memory,
        save_memory,
        web_search,
        web_search_scholar,
        web_fetch,
        web_search_and_fetch,
        pdf_parse,
        pdf_read,
        pdf_grep,
        pdf_vision,
        generate_artifact,
    ],
)

TOOLS_ORCHESTRATOR = [
    "mcp__research-tools__load_memory",
    "mcp__research-tools__save_memory",
    "mcp__research-tools__web_search",
    "mcp__research-tools__web_search_scholar",
    "mcp__research-tools__web_fetch",
    "mcp__research-tools__web_search_and_fetch",
    "mcp__research-tools__pdf_parse",
    "mcp__research-tools__pdf_read",
    "mcp__research-tools__pdf_grep",
    "mcp__research-tools__pdf_vision",
    "mcp__research-tools__generate_artifact",
]
