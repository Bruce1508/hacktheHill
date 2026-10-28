# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. GitHub Issue & Milestone Tracking

**Track real follow-up work. Don't create issues for their own sake.**

Create a GitHub issue when:
- Work is identified but deliberately not done now (deferred, blocked, quota-bound, needs a decision).
- The user asks to track something, or asks "what's left."

Do NOT create an issue for:
- Work finished in the current session (that's a PR/commit, not an issue).
- A single trivial task with no real follow-up.
- Something already covered by an existing open issue — check `gh issue list` first.

Before creating, always check existing state first:
- `gh issue list --state all` — don't duplicate.
- `gh label list` — reuse existing labels (`bug`, `enhancement`, etc.); don't invent new ones without asking.
- `gh api repos/{owner}/{repo}/milestones` — reuse an open milestone if one already fits this initiative.

Issue body standard (every issue, no exceptions):
- **Context** — why this exists, one short paragraph, link related issues/PRs.
- **Task breakdown** — a `- [ ]` checklist of concrete, independently-verifiable steps. Not vague ("improve X") — each item should be checkable by one person in one sitting.
- **Acceptance criteria** — the one-sentence condition that makes this closeable.

Milestones: use one milestone per initiative (e.g. "Day 4 wrap-up"), not one per issue. Create a milestone only when there are 2+ related issues that belong grouped together; a single standalone issue doesn't need one. When an initiative spans multiple issues, also create one lightweight tracker issue (checklist of `#N` references to the sub-issues) so progress is visible from one place — assign the tracker to the same milestone.

The test: every issue should be something a teammate could pick up cold and finish, without asking "what does this actually mean."

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.