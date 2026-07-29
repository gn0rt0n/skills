# gn0rt0n Skills

Installed locally as symlinks; model-agnostic.

A personal fork of [mattpocock/skills](https://github.com/mattpocock/skills) (Matt Pocock, MIT-licensed). The original is excellent — start there. This copy has diverged, drops the upstream publishing apparatus for local-only use, and does **not** track upstream; see [`.agents/adr/0003-personal-fork-local-distribution.md`](./.agents/adr/0003-personal-fork-local-distribution.md) for the fork stance.

## Setup

These are consumed locally as symlinks — there's no marketplace or installer.

1. Clone this repo, then link the skills into your harness skill directories (`~/.claude/skills`, `~/.agents/skills`):

   ```bash
   scripts/link-skills.sh
   ```

   Each entry is a symlink back into the repo, so a `git pull` keeps installed skills current. Re-run after adding, removing, or renaming a skill.

2. Run `/setup-gn0rt0n-skills` once per repo you use them in. It will:
   - Ask which issue tracker you want to use (GitHub, Linear, or local files)
   - Ask what labels you apply to tickets when you triage them (`/triage` uses labels)
   - Ask where to save any docs we create

## Why These Skills Exist

### #1: The Agent Didn't Do What I Want

**The Problem**: The most common failure mode is misalignment. You think the agent knows what you want; then you see what it built and realize it didn't understand you at all.

**The Fix**: A **grilling session** — the agent asks you detailed questions about the change before it starts.

- [`/grill-me`](./skills/productivity/grill-me/SKILL.md) — for non-code uses
- [`/grill-with-docs`](./skills/engineering/grill-with-docs/SKILL.md) — same, but also builds your project's domain model (see below)

### #2: The Agent Is Way Too Verbose

**The Problem**: Agents get dropped into a project and figure out the jargon as they go, so they use 20 words where 1 would do.

**The Fix**: A shared language — a document that decodes the project's jargon.

<details>
<summary>
Example
</summary>

Here's an example of the payoff from a real `CONTEXT.md`. Which one is easier to read?

- **BEFORE**: "There's a problem when a lesson inside a section of a course is made 'real' (i.e. given a spot in the file system)"
- **AFTER**: "There's a problem with the materialization cascade"

This concision pays off session after session.

</details>

This is built into [`/grill-with-docs`](./skills/engineering/grill-with-docs/SKILL.md): a grilling session that also builds a shared language with the agent and records hard-to-explain decisions as ADRs.

> [!TIP]
> A shared language has many other benefits than reducing verbosity:
>
> - **Variables, functions and files are named consistently**, using the shared language
> - As a result, the **codebase is easier to navigate** for the agent
> - The agent also **spends fewer tokens on thinking**, because it has access to a more concise language

### #3: The Code Doesn't Work

**The Problem**: You're aligned on what to build, and the agent still produces crap. Without feedback on how its code actually runs, it's flying blind.

**The Fix**: The usual feedback loops — static types, browser access, automated tests. For tests, a red-green-refactor loop matters most: the agent writes a failing test first, then makes it pass.

- [`/tdd`](./skills/engineering/tdd/SKILL.md) — red-green-refactor, with guidance on what makes good and bad tests
- [`/diagnosing-bugs`](./skills/engineering/diagnosing-bugs/SKILL.md) — a disciplined debugging loop

### #4: We Built A Ball Of Mud

**The Problem**: Agents speed up coding, which also accelerates entropy — codebases get complex fast and hard to change.

**The Fix**: Care about the design of the code, at every layer.

- [`/to-spec`](./skills/engineering/to-spec/SKILL.md) — quizzes you about which modules you're touching before writing a spec
- [`/improve-codebase-architecture`](./skills/engineering/improve-codebase-architecture/SKILL.md) — rescues a codebase that's become a ball of mud; worth running every few days

## Reference

These split on one axis — who can invoke them. **User-invoked** skills are reachable only when you type them (e.g. `/grill-me`); their job is to orchestrate. **Model-invoked** skills can be invoked by you _or_ reached for automatically by the agent when the task fits; they hold the reusable discipline. A user-invoked skill may invoke model-invoked skills, but never another user-invoked one.

### Engineering

**User-invoked**

- **[which-skill](./skills/engineering/which-skill/SKILL.md)** — Ask which skill or flow fits your situation. A router over every skill this repo documents — model-invoked as well as user-invoked.
- **[grill-with-docs](./skills/engineering/grill-with-docs/SKILL.md)** — Grilling session that also builds your project's domain model, sharpening terminology and updating `CONTEXT.md` and ADRs inline.
- **[triage](./skills/engineering/triage/SKILL.md)** — Move issues through a state machine of triage roles.
- **[improve-codebase-architecture](./skills/engineering/improve-codebase-architecture/SKILL.md)** — Scan a codebase for deepening opportunities, present them as a visual HTML report, then grill through whichever one you pick.
- **[setup-gn0rt0n-skills](./skills/engineering/setup-gn0rt0n-skills/SKILL.md)** — Configure this repo for the engineering skills (issue tracker, triage labels, domain doc layout). Run once per repo before using the other engineering skills.
- **[to-spec](./skills/engineering/to-spec/SKILL.md)** — Turn the current conversation into a spec and publish it to the issue tracker. No interview — just synthesizes what you've already discussed.
- **[to-tickets](./skills/engineering/to-tickets/SKILL.md)** — Break any plan, spec, or conversation into a set of tracer-bullet tickets, each declaring its blocking edges — written as text in a local file, or as native blocking links on a real tracker.
- **[implement](./skills/engineering/implement/SKILL.md)** — Build the work described by a spec or set of tickets, driving `/tdd` at pre-agreed seams and closing out with `/code-review` before committing.
- **[wayfinder](./skills/engineering/wayfinder/SKILL.md)** — Plan a huge chunk of work, more than one agent session can hold, as a shared map of investigation tickets on the issue tracker — resolve them one at a time until the way to the destination is clear.

**Model-invoked**

- **[prototype](./skills/engineering/prototype/SKILL.md)** — Build a throwaway prototype to answer a design question — a runnable terminal app for state/logic questions, or several radically different UI variations toggleable from one route.
- **[diagnosing-bugs](./skills/engineering/diagnosing-bugs/SKILL.md)** — Disciplined diagnosis loop for hard bugs and performance regressions: reproduce → minimise → hypothesise → instrument → fix → regression-test.
- **[research](./skills/engineering/research/SKILL.md)** — Investigate a question against high-trust primary sources and capture the findings as a cited Markdown file in the repo, run as a background agent.
- **[tdd](./skills/engineering/tdd/SKILL.md)** — Test-driven development with a red-green-refactor loop. Builds features or fixes bugs one vertical slice at a time.
- **[domain-modeling](./skills/engineering/domain-modeling/SKILL.md)** — Actively build and sharpen a project's domain model — challenge terms against the glossary, stress-test with edge-case scenarios, and update `CONTEXT.md` and ADRs inline.
- **[codebase-design](./skills/engineering/codebase-design/SKILL.md)** — Shared discipline and vocabulary for designing deep modules: a lot of behaviour behind a small interface, placed at a clean seam, testable through that interface.
- **[code-review](./skills/engineering/code-review/SKILL.md)** — Two-axis review of the diff since a fixed point: **Standards** (does it follow the repo's coding standards, plus a Fowler smell baseline?) and **Spec** (does it faithfully implement the originating issue/PRD?), run as parallel sub-agents so neither pollutes the other.
- **[resolving-merge-conflicts](./skills/engineering/resolving-merge-conflicts/SKILL.md)** — Work through an in-progress git merge or rebase conflict hunk by hunk, resolving by intent traced to each side's primary source, then finish the operation — never `--abort`.

### Productivity

General workflow tools, not code-specific.

**User-invoked**

- **[grill-me](./skills/productivity/grill-me/SKILL.md)** — Get relentlessly interviewed about a plan or design until every branch of the decision tree is resolved.
- **[handoff](./skills/productivity/handoff/SKILL.md)** — Compact the current conversation into a handoff document so another agent can continue the work.
- **[teach](./skills/productivity/teach/SKILL.md)** — Teach the user a new skill or concept over multiple sessions, using the current directory as a stateful teaching workspace.
- **[writing-great-skills](./skills/productivity/writing-great-skills/SKILL.md)** — Reference for writing and editing skills well: the vocabulary and principles that make a skill predictable.

**Model-invoked**

- **[grilling](./skills/productivity/grilling/SKILL.md)** — Interview the user relentlessly about a plan, decision, or idea until every branch of the decision tree is resolved. The reusable loop behind `grill-me` and `grill-with-docs`.
