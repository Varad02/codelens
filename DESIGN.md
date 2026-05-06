# DESIGN.md — CodeLens Agent

Three key design decisions made while building this system.

---

## 1. Three-Tier Guardrail Architecture

**Decision:** Guardrails are enforced across three distinct tiers — a pre-LLM keyword filter, a structural toolset split, and a mid-execution confirmation gate — rather than relying on the system prompt alone.

**How it works:**

- **Tier 1 — Prohibited (input filter)** (`is_prohibited` in `agent/guardrails.py`): Before the message ever reaches the LLM, it is checked against a set of prohibited phrases (`merge`, `delete branch`, `force push`, etc.). If matched, the agent short-circuits with a refusal and never invokes the LLM or any tool. This stops prompt-injection attempts where a user embeds a destructive command inside an otherwise-benign question.

- **Tier 2 — Autonomous (no confirmation needed)** (`AUTONOMOUS_TOOLS`): Read-only and purely local tools (`fetch_pr_diff`, `list_pr_files`, `query_codebase`, `index_directory`) are called freely. They have no external write side-effects, so no human approval is needed.

- **Tier 3 — Confirmation gate** (`post_github_review` in `agent/guardrails.py`): For actions that are permitted but irreversible — posting a public GitHub review comment — the tool itself halts and asks the user for explicit `[y/N]` confirmation before proceeding. This runs inside the tool, not in the LLM, so it cannot be bypassed by rephrasing the request or by the model deciding to skip the check.

**Why not just use the system prompt?** System prompts are advisory — a sufficiently clever user message or a hallucinating model can override them. A keyword filter at the input boundary and a hard code gate inside the tool are immune to this because they never involve the model's judgment for the safety-critical decision.

**Observed side-effect in evaluation:** In the Pass@1 eval, Config A (which includes `post_github_review`) scored 0 on tc_03 ("find bugs in this PR") because the model chose to invoke `post_github_review` to deliver its findings rather than returning them as plain text. This reveals a real tension in the three-tier design: giving the model access to a write tool causes it to prefer that tool even when a read-only response was expected. A mitigation would be to add explicit system prompt guidance to only invoke `post_github_review` when the user explicitly asks to post a comment.

---

## 2. Toolset Split Encoded in Code, Not Prompt

**Decision:** The autonomous/confirmation boundary is enforced structurally in code (`AUTONOMOUS_TOOLS` vs. `CONFIRMATION_TOOLS` lists) rather than only described in the system prompt, and the confirmation logic lives inside the tool itself rather than in the agent loop.

**Why this matters:** The system prompt tells the model which tools need confirmation, but the tool enforces it unconditionally. Even if the model ignores the prompt guidance, calls `post_github_review` without warning the user, or is manipulated into skipping the confirmation step, the `[y/N]` gate still fires because it is part of the tool's execution — not a model decision.

**Trade-off considered:** A simpler design would put everything in one list and let the model decide when to ask. This was rejected because it makes the safety boundary fuzzy — the model might forget to ask, or a user might convince it that confirmation is unnecessary. Making the boundary structural ensures it is consistent regardless of model behavior.

**Implication for eval:** The two-list design is also what enables Config A vs. Config B comparison in the evaluation — swapping toolsets at runtime by patching `agent.ALL_TOOLS` and `agent.TOOLS_MAP` without touching any other code.

---

## 3. RAG Augmentation for PR Review Context

**Decision:** Rather than sending only the PR diff to the LLM, the agent first retrieves semantically similar code snippets from an indexed local codebase via `query_codebase` and appends them as context. This is the core architectural difference between Config A (full agent) and Config B (minimal agent) in the evaluation.

**How it works:** When reviewing a PR, the agent calls `fetch_pr_diff` to get the changed file patches, then calls `query_codebase` with terms derived from the diff (e.g., function names, changed module paths) to pull the top-k most similar snippets from ChromaDB. The LLM then sees both the diff and the surrounding codebase context before generating its review.

**Why this matters:** A diff alone is decontextualized — the model cannot know whether a changed function is called elsewhere, whether a pattern it introduced already exists in the codebase, or whether a deleted helper is duplicated somewhere. RAG closes this gap, enabling the model to flag things like "this logic already exists in `utils/http.py`" or "this function is called in three other places that will now break."

**Trade-off:** RAG adds latency (one extra embedding query + retrieval) and requires the user to index their codebase first. For repos that haven't been indexed, `query_codebase` returns a clear message instructing the user to run `index_directory`. The evaluation (Config A vs. B) quantifies how much the RAG context actually improves review quality on the test set.

---

## Addendum — GitHub Actions as a Delivery Surface

Beyond the CLI and chat agent, CodeLens also runs as a GitHub Actions workflow (`.github/workflows/codelens-review.yml` in `vkottawar/codelens-eval`). This strips the agent loop entirely — no tool calls, no confirmation gates, no multi-turn — and delivers the review directly as a PR comment the moment a PR is opened.

**Why this matters architecturally:** The core review logic (`fetch_pr_diff` → LLM → structured output) is the same pipeline used by `cli.py review`, but the delivery mechanism changes from stdout to the GitHub Issues API. This demonstrates that the review engine is decoupled from the interaction model — the same LLM call works in a terminal, a chat loop, or a fully automated CI pipeline.

**Guardrail note:** In the Actions context, the three-tier guardrail is irrelevant — there is no user to confirm with and no prohibited commands to intercept. The workflow has `pull-requests: write` permission scoped only to posting comments, and `GITHUB_TOKEN` is provided by GitHub with the minimum required scope. The safety boundary is enforced by the Actions permission model rather than by the agent's own guardrail code.
