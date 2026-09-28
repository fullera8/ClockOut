# ClockOut — first build prompt

You are the orchestrator for ClockOut. First read `.github/copilot-instructions.md`
and your own agent instructions, then confirm the `planner`, `coder`, and
`tester` agents are visible and runnable before delegating anything.

Build the app end to end on the current branch (`agents/firstBuild`), one work
unit at a time, delegating labor to the subagents:
1. planner produces the ordered unit list (pure logic first, UI last).
2. For each unit: coder implements it, then tester verifies it against the
   contract before moving on.

Obey every guardrail in `.github/copilot-instructions.md` — especially the
secret rules (no real `.env`, no real sends) and the git boundaries (commit
only, no push, no merge, never touch `main`).

When finished, write `release/agent-progress.md` containing: completed units;
the exact commands you ran and their results; any failing or skipped tests;
unimplemented files; uncertain assumptions; and the next smallest task. End it
with a **"Manual verification checklist for the human"**: force the 4:50 prompt,
click Yes and confirm a message would post, confirm the 30/60-min re-prompt
timing, and confirm `.env` is git-ignored and absent. Do not report the app as
working end to end — that check is the human's.