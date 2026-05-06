import os
import traceback
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from agent.tools import AUTONOMOUS_TOOLS
from agent.guardrails import CONFIRMATION_TOOLS, is_prohibited

load_dotenv()

ALL_TOOLS = AUTONOMOUS_TOOLS + CONFIRMATION_TOOLS
TOOLS_MAP = {t.name: t for t in ALL_TOOLS}

SYSTEM_PROMPT = """\
You are CodeLens, an expert AI code review agent. You help developers understand GitHub PRs, \
identify bugs, style problems, and improvement opportunities.

GUARDRAIL POLICY — follow this strictly:
- AUTONOMOUS (call without asking): fetch_pr_diff, list_pr_files, query_codebase, index_directory
- CONFIRMATION REQUIRED (tool handles this): post_github_review
- PROHIBITED (refuse and explain): merging PRs, deleting branches, pushing code, \
  closing PRs, any destructive git operation. Say: \
  "I'm not allowed to do that — it's outside my permitted operations.\""""


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url="https://tritonai-api.ucsd.edu/v1",
        api_key=os.environ["TRITON_API_KEY"],
        model="api-gpt-oss-120b",
        temperature=0.2,
    )


def _run_turn(llm, messages: list, max_steps: int = 8) -> str:
    """
    Core agentic loop using LangChain bind_tools + LCEL.
    Calls the LLM, executes any tool calls it requests, feeds results
    back, and repeats until the model returns a plain text final answer.
    """
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    for _ in range(max_steps):
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        # No tool calls → model gave a final answer
        if not getattr(response, "tool_calls", None):
            return response.content or "(no response)"

        # Execute every tool the model requested
        for tc in response.tool_calls:
            tool = TOOLS_MAP.get(tc["name"])
            if tool is None:
                result = f"Unknown tool: {tc['name']}"
            else:
                try:
                    result = tool.invoke(tc["args"])
                except Exception as e:
                    result = f"Tool error: {e}"

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    return "Reached the maximum number of steps without a final answer."


def run_chat(verbose: bool = False) -> None:
    print("CodeLens Agent — type 'exit' to quit\n")
    llm = _build_llm()
    messages: list = [SystemMessage(content=SYSTEM_PROMPT)]

    while True:
        try:
            user_input = input("You     : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("Goodbye!")
            break

        if is_prohibited(user_input):
            reply = "I'm not allowed to do that — it's outside my permitted operations."
            print(f"\nCodeLens: {reply}\n")
            messages += [HumanMessage(content=user_input), AIMessage(content=reply)]
            continue

        messages.append(HumanMessage(content=user_input))

        try:
            reply = _run_turn(llm, messages, max_steps=8)
        except Exception:
            traceback.print_exc()
            reply = "Something went wrong — see traceback above."

        # _run_turn already appended the final AIMessage; just print it
        print(f"\nCodeLens: {reply}\n")


def run_once(user_input: str, verbose: bool = False) -> str:
    """Single-turn invocation used by the evaluation framework."""
    if is_prohibited(user_input):
        return "I'm not allowed to do that — it's outside my permitted operations."
    llm = _build_llm()
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_input)]
    try:
        return _run_turn(llm, messages)
    except Exception:
        traceback.print_exc()
        return "Agent error — see traceback above."
