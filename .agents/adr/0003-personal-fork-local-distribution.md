# Personal fork: snapshot from upstream, local-only distribution

**Status: accepted.** Supersedes [0002](./0002-ship-as-a-claude-code-plugin.md).

This repo is a **personal fork of [mattpocock/skills](https://github.com/mattpocock/skills)**, taken as a point-in-time snapshot. We treat it as our own repo, not a living fork: there is **no `upstream` remote and no ongoing sync**. Bringing in a future upstream change is a deliberate manual cherry-pick, never a merge. We chose this over a living fork because every personal edit to an inherited skill would otherwise become a recurring merge conflict — and this repo's strict README/plugin.json/docs sync rules multiply that cost. The price we accept is losing automatic upstream updates.

Because the only consumer is the author, distribution is **local symlinks** via `scripts/link-skills.sh` (into `~/.claude/skills` and `~/.agents/skills`), not a published bundle. We therefore removed the upstream **publishing apparatus** that served a public audience: `.claude-plugin/marketplace.json`, the Changesets tooling (`.changeset/`, the release workflow, `package.json`/`package-lock.json`), and the skills.sh install path. A minimal `.claude-plugin/plugin.json` is kept only to describe the promoted set for local Claude Code use, and the changelog is now **hand-maintained** (`CHANGELOG.md`, Keep-a-Changelog style) rather than generated — automated version PRs and registry tags earn their keep only when publishing on a cadence, which we no longer do.

## Consequences

- The `mattpocock-skills` plugin was renamed to `gn0rt0n-skills`; the `ask-matt` router to `which-skill` and `setup-matt-pocock-skills` to `setup-gn0rt0n-skills`. Attribution to the original author is retained in `LICENSE` (MIT requires it) and the README.
- Docs pages under `docs/` are now **internal reference pages** with repo-relative links, not pages published to `aihero.dev`.
- `claude plugin validate . --strict` still passes on `plugin.json` alone (no `marketplace.json` required).
- The `2` in [0002](./0002-ship-as-a-claude-code-plugin.md)'s invariant — "`plugin.json` version tracks `package.json` version" — no longer applies: there is no `package.json`.
