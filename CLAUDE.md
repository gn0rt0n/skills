Skills are organized into bucket folders under `skills/`:

- `engineering/` — daily code work
- `productivity/` — daily non-code workflow tools
- `misc/` — kept around but rarely used, not promoted

`engineering/` and `productivity/` are the **promoted** buckets; `misc/` is not. If you ever need to stage a draft or retire a skill, create an `in-progress/` or `deprecated/` bucket lazily when first needed — neither exists yet, and both would be non-promoted like `misc/`.

Every skill in `engineering/` or `productivity/` (the **promoted** buckets) must have a reference in the top-level `README.md` and an entry in `.claude-plugin/plugin.json`'s `skills` array (the Claude Code plugin ships exactly the promoted set). Skills in any non-promoted bucket (`misc/`, plus any `in-progress/`/`deprecated/` you add) must not appear in either.

This is a personal, symlink-installed fork of [mattpocock/skills](https://github.com/mattpocock/skills) (see `scripts/link-skills.sh`), not a published bundle — there is no marketplace, changeset, or automated release tooling. A minimal `.claude-plugin/plugin.json` is kept only to describe the promoted set for local Claude Code use; run `claude plugin validate . --strict` after touching it. The changelog is hand-maintained. The fork stance (snapshot, no upstream tracking) and why the publishing stack was removed live in [.agents/adr/0003-personal-fork-local-distribution.md](./.agents/adr/0003-personal-fork-local-distribution.md).

Each skill entry in the top-level `README.md` must link the skill name to its `SKILL.md`.

Each bucket folder has a `README.md` that lists every skill in the bucket with a one-line description, with the skill name linked to its `SKILL.md`. The promoted buckets' `README.md`s and the top-level `README.md` group entries into **User-invoked** and **Model-invoked**; the non-promoted `misc/` `README.md` uses a flat list.

Skills in `engineering/` and `productivity/` also have a human-facing docs page at `docs/<bucket>/<skill-name>.md` (the docs tree mirrors those two bucket folders under `skills/`). These are **internal reference pages** — there is no published docs site; cross-links between docs pages are relative (`./<name>.md`, or `../<bucket>/<name>.md` across buckets). When you add, rename, or change the behaviour of a skill in `engineering/` or `productivity/`, create or re-sync its docs page following [.agents/writing-docs.md](./.agents/writing-docs.md). Skills in non-promoted buckets (`misc/`, plus any `in-progress/`/`deprecated/`) get **no** docs page.

Every `SKILL.md` is either user-invoked (`disable-model-invocation: true` plus `policy.allow_implicit_invocation: false` in `agents/openai.yaml`, reachable only by the human) or model-invoked (model- or user-reachable). See [.agents/invocation.md](./.agents/invocation.md).

[`which-skill`](./skills/engineering/which-skill/SKILL.md) is the router that maps every user-reachable skill and how they relate. The same trigger that re-syncs a docs page applies to it: whenever you add, rename, remove, or change how a user-reachable skill fits the flows, re-read `which-skill`'s `SKILL.md` and update it so the map stays accurate — a new skill it never mentions, or a stale one it still routes to, is a router that lies.

To (re)link every skill into the local harness skill directories (`~/.claude/skills`, `~/.agents/skills`), run `scripts/link-skills.sh`. Each entry is a symlink into this repo, so a `git pull` keeps installed skills current; re-run the script after adding, removing, or renaming a skill.
