"""
Evaluation framework for CodeLens agent.

Compares two configurations using Pass@1 with an LLM-as-judge scorer.

Config A: Full agent — all tools including RAG (fetch_pr_diff, list_pr_files,
          query_codebase, index_directory, post_github_review)
Config B: Minimal agent — fetch_pr_diff and list_pr_files only (no RAG)

Usage:
    python -m eval.evaluate
    python -m eval.evaluate --cases eval/test_cases.json --k 3
"""
import argparse
import json
import os
import math
from dataclasses import dataclass, field
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

JUDGE_PROMPT = """\
You are evaluating an AI code-review agent's response.

Test input: {input}
Agent response: {response}
Pass criteria: {criteria}

Does the agent's response satisfy the criteria?
Return a JSON object only, no markdown:
{{"score": 0 or 1, "reason": "one sentence explanation"}}"""


@dataclass
class TestCase:
    id: str
    description: str
    input: str
    criteria: str


@dataclass
class EvalResult:
    case_id: str
    config: str
    run: int
    response: str
    score: int
    reason: str


def load_cases(path: str) -> list[TestCase]:
    with open(path) as f:
        raw = json.load(f)
    return [TestCase(**c) for c in raw]


def _judge_client() -> OpenAI:
    return OpenAI(
        base_url="https://tritonai-api.ucsd.edu/v1",
        api_key=os.environ["TRITON_API_KEY"],
    )


def score_response(input_text: str, response: str, criteria: str) -> tuple[int, str]:
    client = _judge_client()
    prompt = JUDGE_PROMPT.format(input=input_text, response=response, criteria=criteria)
    try:
        resp = client.chat.completions.create(
            model="api-gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        parsed = json.loads(raw)
        return int(parsed["score"]), parsed.get("reason", "")
    except Exception as e:
        return 0, f"Judge error: {e}"


def pass_at_k(scores: list[int], k: int) -> float:
    """Pass@k = 1 - C(n-c, k) / C(n, k) where n=total runs, c=passing runs."""
    n = len(scores)
    c = sum(scores)
    if c == 0:
        return 0.0
    if n - c < k:
        return 1.0
    # Use log to avoid overflow: C(n-c,k)/C(n,k)
    log_num = sum(math.log(n - c - i) for i in range(k))
    log_den = sum(math.log(n - i) for i in range(k))
    return 1.0 - math.exp(log_num - log_den)


def run_config(cases: list[TestCase], config_name: str, k: int, use_rag: bool) -> list[EvalResult]:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage
    from agent.tools import fetch_pr_diff, list_pr_files, query_codebase, index_directory
    from agent.guardrails import CONFIRMATION_TOOLS, is_prohibited
    from agent.agent import SYSTEM_PROMPT, _run_turn

    eval_tools = [fetch_pr_diff, list_pr_files]
    if use_rag:
        eval_tools += [query_codebase, index_directory] + CONFIRMATION_TOOLS

    import agent.agent as _agent_mod
    original_tools = _agent_mod.ALL_TOOLS
    original_map = _agent_mod.TOOLS_MAP
    _agent_mod.ALL_TOOLS = eval_tools
    _agent_mod.TOOLS_MAP = {t.name: t for t in eval_tools}

    llm = ChatOpenAI(
        base_url="https://tritonai-api.ucsd.edu/v1",
        api_key=os.environ["TRITON_API_KEY"],
        model="api-gpt-oss-120b",
        temperature=0.2,
    )

    results = []
    for case in cases:
        run_scores = []
        for run_idx in range(k):
            print(f"  [{config_name}] case={case.id} run={run_idx+1}/{k} ...", end=" ", flush=True)

            if is_prohibited(case.input):
                response = "I'm not allowed to do that — it's outside my permitted operations."
            else:
                try:
                    msgs = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=case.input)]
                    response = _run_turn(llm, msgs)
                except Exception as e:
                    response = f"Agent error: {e}"

            score, reason = score_response(case.input, response, case.criteria)
            print(f"score={score}")
            run_scores.append(score)
            results.append(EvalResult(
                case_id=case.id,
                config=config_name,
                run=run_idx,
                response=response,
                score=score,
                reason=reason,
            ))

    _agent_mod.ALL_TOOLS = original_tools
    _agent_mod.TOOLS_MAP = original_map
    return results


def print_report(cases: list[TestCase], all_results: list[EvalResult], k: int) -> None:
    configs = sorted({r.config for r in all_results})

    print("\n" + "=" * 60)
    print(f"EVALUATION REPORT  (Pass@{k})")
    print("=" * 60)

    for config in configs:
        config_results = [r for r in all_results if r.config == config]
        print(f"\nConfig: {config}")
        print(f"{'Case':<10} {'Pass@'+str(k):<10} {'Reason (last run)'}")
        print("-" * 60)

        overall_scores = []
        for case in cases:
            case_runs = [r for r in config_results if r.case_id == case.id]
            scores = [r.score for r in case_runs]
            pk = pass_at_k(scores, k)
            overall_scores.append(pk)
            last_reason = case_runs[-1].reason if case_runs else ""
            print(f"{case.id:<10} {pk:<10.2f} {last_reason[:50]}")

        avg = sum(overall_scores) / len(overall_scores) if overall_scores else 0
        print(f"\n  Average Pass@{k}: {avg:.2f}")

    print("\n" + "=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CodeLens agent configs")
    parser.add_argument("--cases", default="eval/test_cases.json")
    parser.add_argument("--k", type=int, default=1, help="k for Pass@k (default 1)")
    parser.add_argument("--output", default="eval/results.json", help="Where to save raw results")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    print(f"Loaded {len(cases)} test cases. Running k={args.k} per case per config.\n")

    print("Running Config A: Full agent (all tools + RAG)...")
    results_a = run_config(cases, "A_full", k=args.k, use_rag=True)

    print("\nRunning Config B: Minimal agent (fetch + list only, no RAG)...")
    results_b = run_config(cases, "B_minimal", k=args.k, use_rag=False)

    all_results = results_a + results_b
    with open(args.output, "w") as f:
        json.dump([vars(r) for r in all_results], f, indent=2)
    print(f"\nRaw results saved to {args.output}")

    print_report(cases, all_results, args.k)


if __name__ == "__main__":
    main()
