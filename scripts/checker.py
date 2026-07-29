#!/usr/bin/env python3
"""Assert this repo's structural invariants.

The checker discovers skills by finding every ``SKILL.md`` under the repo, so it
is layout-agnostic: it works before, during, and after the restructure that
moves skills out of topic buckets and into lifecycle directories.

A skill is **active** unless one of the directories above it names a non-active
lifecycle (``misc``, ``drafts``, ``retired``, ``in-progress``, ``deprecated``).
Active means documented, with no exception list — so every check below that
takes a set of skills takes the active set.

Invariants asserted:

  name        Each skill's ``name`` frontmatter matches its directory name.
  docs        Each active skill has exactly one docs page; no orphan pages
              survive in a directory that holds skill pages.
  router      The router names every active skill at least once.
  links       Every relative markdown link resolves. Links inside fenced code
              blocks and ``<*-template>`` blocks are exempt — they are example
              paths, not references.
  invocation  ``disable-model-invocation: true`` in frontmatter is paired with
              ``policy.allow_implicit_invocation: false`` in the Codex
              ``agents/openai.yaml``, in both directions.

Reported at a second severity, as warnings:

  staleness   A skill has been committed more recently than its docs page or
              than the router, so what documents it may have fallen behind.

Structural violations exit non-zero; staleness warnings alone exit zero. The
split is deliberate: a gate that blocks a one-word typo fix is a gate that
teaches bypass. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

# Directories whose name marks everything beneath them as non-active. Covers
# both the pre-restructure bucket (`misc`) and the lifecycle directories that
# replace it.
NON_ACTIVE_DIRS = frozenset({"misc", "drafts", "retired", "in-progress", "deprecated"})

# Directories never walked, wherever they appear.
SKIP_DIRS = frozenset({".git", "node_modules"})

ROUTER_NAME = "which-skill"
DOCS_DIR = "docs"


# --------------------------------------------------------------------------
# Minimal YAML — enough for frontmatter and the two-level Codex policy file
# --------------------------------------------------------------------------


def _scalar(value: str):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value in ("true", "false"):
        return value == "true"
    return value


def parse_yaml(text: str) -> dict:
    """Parse the ``key: value`` subset this repo actually uses.

    Nested mappings and single-line scalars only. Sequences and block scalars
    are skipped rather than guessed at — every value this checker reads
    (``name``, ``disable-model-invocation``, ``allow_implicit_invocation``) is
    a one-line scalar, and silently mangling a construct is worse than
    dropping it.
    """
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", "- ", "-\t")) or stripped == "-":
            continue
        indent = len(raw) - len(raw.lstrip())
        key, sep, value = stripped.partition(":")
        if not sep:
            continue
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value.strip():
            parent[key.strip()] = _scalar(value)
        else:
            child: dict = {}
            parent[key.strip()] = child
            stack.append((indent, child))
    return root


def parse_frontmatter(text: str) -> dict:
    """Return the YAML frontmatter block of a markdown file, or ``{}``."""
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return parse_yaml("\n".join(lines[1:i]))
    return {}


# --------------------------------------------------------------------------
# Link extraction
# --------------------------------------------------------------------------

INLINE_LINK = re.compile(r"\[[^\]\n]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
TEMPLATE_OPEN = re.compile(r"^\s*<([a-zA-Z][\w-]*-template)>\s*$")
TEMPLATE_CLOSE = re.compile(r"^\s*</([a-zA-Z][\w-]*-template)>\s*$")

EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")


@dataclass(frozen=True)
class Link:
    source: Path
    line: int
    target: str
    exempt: bool


def extract_links(path: Path, text: str) -> list[Link]:
    """Every markdown link in ``text``, flagged for fenced/template exemption.

    A link is exempt when it sits inside a fenced code block or a
    ``<name-template>`` block. Both are literal examples — the paths in them
    are shapes to fill in, not references to follow.
    """
    links: list[Link] = []
    fence: str | None = None
    template: str | None = None

    for lineno, line in enumerate(text.splitlines(), start=1):
        fence_match = FENCE.match(line)
        if fence is not None:
            if fence_match and line.strip().startswith(fence):
                fence = None
                continue
        elif fence_match:
            fence = fence_match.group(1)
            continue
        elif template is None:
            opened = TEMPLATE_OPEN.match(line)
            if opened:
                template = opened.group(1)
                continue
        else:
            closed = TEMPLATE_CLOSE.match(line)
            if closed and closed.group(1) == template:
                template = None
                continue

        exempt = fence is not None or template is not None
        for match in INLINE_LINK.finditer(line):
            links.append(
                Link(source=path, line=lineno, target=match.group(1), exempt=exempt)
            )

    return links


def resolves(root: Path, link: Link) -> bool | None:
    """``True``/``False`` if the link is repo-relative, ``None`` if external."""
    target = link.target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]  # markdown's angle-wrapped destination
    if not target or target.startswith("#") or EXTERNAL.match(target):
        return None
    target = unquote(target.split("#", 1)[0])
    if not target:
        return None
    base = root if target.startswith("/") else link.source.parent
    return (base / target.lstrip("/")).exists()


# --------------------------------------------------------------------------
# Repo model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Skill:
    name: str
    directory: Path
    frontmatter: dict
    codex: dict | None

    @property
    def skill_md(self) -> Path:
        return self.directory / "SKILL.md"

    @property
    def user_invoked(self) -> bool:
        return self.frontmatter.get("disable-model-invocation") is True

    @property
    def codex_user_invoked(self) -> bool:
        codex = self.codex or {}
        policy = codex.get("policy")
        if not isinstance(policy, dict):
            return False
        return policy.get("allow_implicit_invocation") is False


@dataclass
class Repo:
    root: Path
    history: "History" = field(default_factory=lambda: History(None, {}))
    skills: list[Skill] = field(default_factory=list)
    markdown: list[Path] = field(default_factory=list)

    @classmethod
    def load(cls, root: Path) -> "Repo":
        repo = cls(root=root, history=load_history(root))
        for path in sorted(walk_markdown(root)):
            repo.markdown.append(path)
            if path.name == "SKILL.md":
                repo.skills.append(load_skill(path))
        return repo

    @property
    def active(self) -> list[Skill]:
        return [s for s in self.skills if is_active(self.root, s.directory)]

    @property
    def router(self) -> Skill | None:
        for skill in self.skills:
            if skill.directory.name == ROUTER_NAME:
                return skill
        return None

    @property
    def docs_pages(self) -> list[Path]:
        docs = self.root / DOCS_DIR
        return [p for p in self.markdown if docs in p.parents]


def walk_markdown(root: Path):
    """Every non-symlinked ``.md`` file in the repo."""
    for path in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        yield path


def load_skill(skill_md: Path) -> Skill:
    directory = skill_md.parent
    codex_path = directory / "agents" / "openai.yaml"
    codex = None
    if codex_path.is_file():
        codex = parse_yaml(codex_path.read_text(encoding="utf-8"))
    return Skill(
        name=directory.name,
        directory=directory,
        frontmatter=parse_frontmatter(skill_md.read_text(encoding="utf-8")),
        codex=codex,
    )


def is_active(root: Path, directory: Path) -> bool:
    """A skill is active unless a directory above it names a non-active lifecycle."""
    ancestors = directory.relative_to(root).parts[:-1]
    return not any(part in NON_ACTIVE_DIRS for part in ancestors)


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


FAIL = "FAIL"
WARN = "WARN"


@dataclass(frozen=True)
class Finding:
    check: str
    message: str
    severity: str = FAIL


def check_names(repo: Repo) -> list[Finding]:
    findings = []
    for skill in repo.skills:
        declared = skill.frontmatter.get("name")
        where = rel(repo, skill.skill_md)
        if declared is None:
            findings.append(Finding("name", f"{where}: no `name` in frontmatter"))
        elif declared != skill.name:
            findings.append(
                Finding(
                    "name",
                    f"{where}: frontmatter name '{declared}' does not match "
                    f"directory '{skill.name}'",
                )
            )
    return findings


def skill_docs_dirs(repo: Repo) -> set[Path]:
    """Directories under ``docs/`` that hold at least one skill page.

    Inferring the skill-docs directories rather than hard-coding them is what
    lets orphan detection survive the docs tree being reshaped, while leaving
    sibling concerns (ADRs, per-repo config templates) alone. Matching against
    every skill, not just the active ones, is what makes a demoted skill's
    left-behind page an orphan rather than the reason its directory stops
    being scanned.

    The limit of the inference: a directory in which *no* page matches any
    skill is indistinguishable from a sibling-concern directory, so a docs
    directory consisting entirely of orphans is not reported. The realistic
    shapes are covered — a rename inside a populated directory is caught here,
    and a wholesale move of the docs tree is caught by the duplicate-page
    check, which fires on every page left behind.
    """
    names = {s.name for s in repo.skills}
    return {p.parent for p in repo.docs_pages if p.stem in names}


def check_docs(repo: Repo) -> list[Finding]:
    findings = []
    active = repo.active
    active_names = {s.name for s in active}
    pages = repo.docs_pages

    by_name: dict[str, list[Path]] = {}
    for page in pages:
        by_name.setdefault(page.stem, []).append(page)

    for skill in active:
        found = by_name.get(skill.name, [])
        if not found:
            findings.append(
                Finding("docs", f"{skill.name}: active skill has no docs page")
            )
        elif len(found) > 1:
            listed = ", ".join(rel(repo, p) for p in sorted(found))
            findings.append(
                Finding("docs", f"{skill.name}: {len(found)} docs pages ({listed})")
            )

    page_dirs = skill_docs_dirs(repo)
    for page in pages:
        if page.parent in page_dirs and page.stem not in active_names:
            findings.append(
                Finding(
                    "docs",
                    f"{rel(repo, page)}: orphan docs page — no active skill "
                    f"named '{page.stem}'",
                )
            )
    return findings


def check_router(repo: Repo) -> list[Finding]:
    router = repo.router
    if router is None:
        return [Finding("router", f"no '{ROUTER_NAME}' skill found")]

    text = router.skill_md.read_text(encoding="utf-8")
    findings = []
    for skill in repo.active:
        if skill.name == router.name:
            continue
        # `\b` treats `-` as a boundary, so it would count `code-review` as a
        # mention of a skill named `review`. Require a non-name character.
        if not re.search(rf"(?<![\w-]){re.escape(skill.name)}(?![\w-])", text):
            findings.append(
                Finding(
                    "router",
                    f"{ROUTER_NAME} never mentions active skill '{skill.name}'",
                )
            )
    return findings


def check_invocation(repo: Repo) -> list[Finding]:
    findings = []
    for skill in repo.skills:
        if skill.codex is None:
            if skill.user_invoked:
                findings.append(
                    Finding(
                        "invocation",
                        f"{skill.name}: user-invoked in frontmatter but has no "
                        f"agents/openai.yaml to pair with",
                    )
                )
            continue
        if skill.user_invoked and not skill.codex_user_invoked:
            findings.append(
                Finding(
                    "invocation",
                    f"{skill.name}: `disable-model-invocation: true` without "
                    f"`policy.allow_implicit_invocation: false`",
                )
            )
        elif skill.codex_user_invoked and not skill.user_invoked:
            findings.append(
                Finding(
                    "invocation",
                    f"{skill.name}: `policy.allow_implicit_invocation: false` "
                    f"without `disable-model-invocation: true`",
                )
            )
    return findings


# --------------------------------------------------------------------------
# Staleness — git history
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class History:
    """When each path in the repo last changed, from one ``git log`` pass.

    One pass rather than one call per path. The checker asks about a
    hundred-odd paths and runs on every commit, so one subprocess versus a
    hundred is the difference between a hook that gets used and one that gets
    bypassed.

    Paths are keyed relative to the **git toplevel**, which is not necessarily
    the root being checked — ``--root`` may name a subdirectory, or a checkout
    nested inside another repo. Holding the toplevel in here is what stops
    that detail leaking into callers and silently missing every lookup.

    Blind spot: ``--name-only`` lists no paths for a merge commit, so a file
    edited while resolving a conflict does not read as touched by it.
    """

    toplevel: Path | None
    times: dict[str, int]

    @property
    def available(self) -> bool:
        """False when git had nothing to tell us — no commits, no git, no repo."""
        return bool(self.times)

    def last_touched(self, path: Path) -> int | None:
        """When ``path`` last changed — for a directory, when anything under it did."""
        if self.toplevel is None:
            return None
        try:
            key = str(path.resolve().relative_to(self.toplevel))
        except ValueError:
            return None  # outside the tree this history describes
        if key in self.times:
            return self.times[key]
        prefix = key + "/"
        return max(
            (t for p, t in self.times.items() if p.startswith(prefix)), default=None
        )


def load_history(root: Path) -> History:
    """Read commit times from git, or return an empty history.

    Every failure path lands on the same empty result rather than raising:
    staleness is advisory, and a repo without usable history is not a defect
    the checker should block a commit over.
    """

    def git(*args: str) -> str | None:
        try:
            proc = subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True, check=True
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return proc.stdout

    toplevel = git("rev-parse", "--show-toplevel")
    log = git(
        "-c",
        "core.quotePath=false",
        "log",
        "--format=%x00%ct",
        "--name-only",
    )
    if toplevel is None or log is None:
        return History(None, {})

    times: dict[str, int] = {}
    stamp: int | None = None
    for line in log.splitlines():
        if line.startswith("\x00"):
            # A stamp git wrote in some shape we can't read is worth skipping,
            # not crashing the hook over.
            stamp = int(line[1:]) if line[1:].isdigit() else None
        elif line and stamp is not None:
            # `git log` walks newest-first topologically, which is not the same
            # as monotonically by commit date — clock skew and imported history
            # both break it — so take the max rather than trusting first-seen.
            times[line] = max(times.get(line, stamp), stamp)
    return History(Path(toplevel.strip()).resolve(), times)


def format_time(stamp: int) -> str:
    """Minute precision, because same-day edits are the common case here."""
    return datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M")


def check_staleness(repo: Repo) -> list[Finding]:
    """Warn where a skill has outrun what documents it.

    Deliberately a proxy: touching a page without fixing it clears the flag.
    A proxy that runs beats a rule that does not — which is also why these are
    warnings. Both arms compare against the skill's whole directory, so any
    edit to a skill counts, not only edits to its ``SKILL.md``.
    """
    history = repo.history
    router = repo.router
    router_md = router.skill_md if router else None
    router_time = history.last_touched(router_md) if router_md else None
    pages = {page.stem: page for page in repo.docs_pages}

    findings = []
    for skill in repo.active:
        changed = history.last_touched(skill.directory)
        if changed is None:
            continue  # never committed; nothing to have fallen behind it

        behind: list[tuple[Path, int]] = []
        page = pages.get(skill.name)
        if page is not None:
            page_time = history.last_touched(page)
            if page_time is not None and page_time < changed:
                behind.append((page, page_time))
        # The router documents every skill but its own entry, so comparing it
        # against itself would warn on every commit that touches it.
        if router_md is not None and router_time is not None:
            if skill.name != router.name and router_time < changed:
                behind.append((router_md, router_time))

        for path, stamp in behind:
            findings.append(
                Finding(
                    "staleness",
                    f"{skill.name}: {rel(repo, path)} last changed "
                    f"{format_time(stamp)}, the skill {format_time(changed)}",
                    WARN,
                )
            )
    return findings


def collect_links(repo: Repo) -> list[Link]:
    links = []
    for path in repo.markdown:
        links.extend(extract_links(path, path.read_text(encoding="utf-8")))
    return links


def check_links(repo: Repo, broken: list[Link]) -> list[Finding]:
    return [
        Finding("links", f"{rel(repo, link.source)}:{link.line}: {link.target}")
        for link in broken
        if not link.exempt
    ]


def rel(repo: Repo, path: Path) -> str:
    return str(path.relative_to(repo.root))


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

CHECK_ORDER = ["name", "docs", "router", "links", "invocation", "staleness"]


def count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def run(root: Path, verbose: bool) -> int:
    repo = Repo.load(root)
    links = collect_links(repo)
    broken = [link for link in links if resolves(repo.root, link) is False]

    findings = (
        check_names(repo)
        + check_docs(repo)
        + check_router(repo)
        + check_links(repo, broken)
        + check_invocation(repo)
        + check_staleness(repo)
    )

    exempt = [link for link in links if link.exempt]
    print(
        f"{len(repo.skills)} skills ({len(repo.active)} active), "
        f"{len(repo.docs_pages)} docs pages, {len(repo.markdown)} markdown files"
    )
    broken_exempt = [link for link in broken if link.exempt]
    print(
        f"{len(exempt)} links exempt inside fenced or template blocks "
        f"({len(broken_exempt)} of them would not resolve)"
    )
    if not repo.history.available:
        print("no git history available — staleness not checked")

    if verbose:
        for link in broken_exempt:
            print(f"  exempt  {rel(repo, link.source)}:{link.line}: {link.target}")

    by_check: dict[str, list[Finding]] = {}
    for finding in findings:
        by_check.setdefault(finding.check, []).append(finding)

    # Anything not in CHECK_ORDER still gets printed — a finding counted in the
    # exit code but never shown would be worse than an out-of-order one.
    order = CHECK_ORDER + [c for c in by_check if c not in CHECK_ORDER]
    for check in order:
        hits = by_check.get(check, [])
        if not hits:
            if verbose:
                print(f"\nok {check}")
            continue
        tally = [
            count(len([h for h in hits if h.severity == sev]), noun)
            for sev, noun in ((FAIL, "problem"), (WARN, "warning"))
            if any(h.severity == sev for h in hits)
        ]
        print(f"\n{check}: {', '.join(tally)}")
        for finding in hits:
            print(f"  {finding.severity}  {finding.message}")

    problems = [f for f in findings if f.severity == FAIL]
    warnings = [f for f in findings if f.severity == WARN]

    print()
    if problems:
        summary = count(len(problems), "problem") + " found"
        if warnings:
            summary += f", {count(len(warnings), 'warning')}"
        print(summary)
        return 1
    if warnings:
        # Warnings never fail the run — see the module docstring.
        print(f"structural checks passed, {count(len(warnings), 'warning')}")
        return 0
    print("all checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assert this repo's structural invariants.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repo root to check (default: the repo this script lives in)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="list passing checks and the exempt links that would not resolve",
    )
    args = parser.parse_args(argv)
    return run(args.root.resolve(), args.verbose)


if __name__ == "__main__":
    sys.exit(main())
