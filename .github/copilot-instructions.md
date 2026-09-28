# ClockOut — repo-wide agent instructions

This file is auto-loaded for every Copilot agent in this repo. Every agent
(orchestrator, planner, coder, tester) must obey it.

## What we're building
A small Windows Python system-tray app. It sits silently in the tray. At
4:50 PM LOCAL time on weekdays it raises a small ALWAYS-ON-TOP window in a
screen corner: "Are you going to be home on time?" with three buttons.
- "Yes" -> POST "I'll be home on time tonight." -> mark day DONE, silent until tomorrow.
- "I'll be another 30 min" -> POST "I'm going to be about 30 minutes late." -> re-prompt 30 min after THIS click.
- "I'll be another hour" -> POST "I'm going to be about an hour late." -> re-prompt 1 hour after THIS click.
Delivery is a Google Chat incoming-webhook POST. No OAuth, no login.

## Contract (non-negotiable)
- Every button sends a message. There is NO silent snooze.
- Re-prompt interval is measured from the click, not from 4:50.
- SEND FAILURE (non-2xx or network error) blocks the state transition: do not
  advance state, do not mark done, show "Message not sent — retry?". NO auto
  retries. NO durable outbox.
- "Today" = machine LOCAL calendar date, stored as plain YYYY-MM-DD, no timezone.
- The prompt is a real OS window (always-on-top, corner). NOT a browser, NOT a
  Windows toast-with-buttons.
- Build pure logic (data layer, messaging client, state machine) and test it
  BEFORE building the UI.

## v1 non-goals (reject work that adds these)
Multi-user, two-way messaging, free-text composition, OAuth, background
execution while closed, OS scheduling, cross-timezone correctness, editing
message strings without touching code.

## SECRET RULES — highest priority
- The webhook lives in a git-ignored `.env` as GCHAT_WEBHOOK_URL.
- During this build there is NO real `.env` and there SHOULD NOT be one. Use
  `.env.example` (empty value) as your reference.
- If GCHAT_WEBHOOK_URL is unset, that is EXPECTED. Do not ask for it, do not
  invent one, do not create a `.env`.
- NEVER print, log, or place the webhook URL in any exception message.
- NEVER send a real message. All messaging tests use mocks/stubs. If something
  genuinely cannot be verified without a live URL, mark it
  "requires manual verification by human" — do NOT fabricate a success.

## Git boundaries
- Work ONLY on the current branch. Commit passing increments only.
- Do NOT push. Do NOT merge. Do NOT touch `main`. Do NOT open or approve PRs.
  The human pushes the branch and opens the PR after review.

## Honesty rules
- Do not report a test as passing unless you ran it and observed the pass.
- Do not claim the app "works end to end." The tray UI and real message
  delivery require manual human verification you cannot perform. Say so.
- If you can't finish, leave a BUILDABLE repo and an honest progress report.

## When to stop and ask the human
Only for: a genuine missing prerequisite (e.g., Python not installed), an
unsafe external action (sending a real message, committing a secret), or a
real contradiction in this contract. Do not stop for routine edits or local tests.