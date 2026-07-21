# Changelog

All notable changes to this repo are recorded here. Maintained by hand — add entries under `## [Unreleased]` as you go.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- `to-tickets` now nests generated slices under their parent as **native sub-issues** (not just a `## Parent` body line) when the source has a parent issue or PRD, so the breakdown surfaces in the parent's sub-issue list and progress indicator. The GitHub tracker reference gains a "create a sub-issue" convention (`gh issue create --parent`, with the sub-issues REST API as a fallback for `gh` < 2.95.0). Adapted from [jenarvaezg/mattpocockskills#1](https://github.com/jenarvaezg/mattpocockskills/pull/1) (upstream mattpocock/skills#47).

### Changed

- Forked from [mattpocock/skills](https://github.com/mattpocock/skills) and rebranded as a personal fork (`gn0rt0n-skills`). No upstream tracking — see [`.agents/adr/0003-personal-fork-local-distribution.md`](./.agents/adr/0003-personal-fork-local-distribution.md).
- Switched to local-only distribution (symlinks via `scripts/link-skills.sh`); removed the marketplace/changeset/skills.sh publishing apparatus.
