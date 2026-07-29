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

Exits non-zero if any invariant is violated. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
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
    skills: list[Skill] = field(default_factory=list)
    markdown: list[Path] = field(default_factory=list)

    @classmethod
    def load(cls, root: Path) -> "Repo":
        repo = cls(root=root)
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


@dataclass(frozen=True)
class Finding:
    check: str
    message: str


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

CHECK_ORDER = ["name", "docs", "router", "links", "invocation"]


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
        print(f"\n{check}: {len(hits)} problem{'s' if len(hits) != 1 else ''}")
        for finding in hits:
            print(f"  FAIL  {finding.message}")

    print()
    if findings:
        print(f"{len(findings)} problem{'s' if len(findings) != 1 else ''} found")
        return 1
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
