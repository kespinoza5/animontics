"""MkDocs hooks for the animontics docs site.

The site is assembled by embedding the repo's own README/markdown files into
docs pages via the include-markdown plugin (with rewrite-relative-urls=true).
That keeps each embedded file's cross-links pointing at the *original repo file*
— which is correct on GitHub, and also correct in the site for targets that
live under docs/ (e.g. docs/architecture.md). But links to embedded files that
live *outside* docs/ — CONTRIBUTING.md, tools/<x>/README.md, TODO.md — point at
repo paths the site never serves as pages, so they 404.

This hook closes that gap with zero hand-maintained mapping:

  1. on_files          — read every page's `include-markdown "<path>"` directive
                         and build  repo-relative-file -> docs-page  from it.
  2. on_page_markdown  — after include-markdown has inlined the content, rewrite
                         any link that points at one of those embedded repo
                         files so it targets the matching docs page instead.
                         MkDocs then resolves the .md link to the real page URL
                         during render.

Anything not embedded by some page is left untouched (and still surfaces as a
normal MkDocs "link not found" warning), so genuinely missing pages stay visible
rather than being silently papered over.
"""
from __future__ import annotations

import posixpath
import re
from pathlib import Path

# Pull the include path out of an include-markdown jinja block:
#   {% include-markdown "../CONTRIBUTING.md" ... %}
_INCLUDE_RE = re.compile(r'include-markdown\s+["\']([^"\']+)["\']')

# Markdown inline link target:  ](target)
_LINK_RE = re.compile(r"\]\(\s*([^)\s]+)\s*\)")

# repo-relative posix path (e.g. "CONTRIBUTING.md") -> page src_uri (e.g. "contributing.md")
_EMBED_MAP: dict[str, str] = {}


def _repo_rel(abs_path: Path, repo_root: Path) -> str | None:
    """Path of abs_path relative to the repo root, as a posix string, or None
    if it escapes the repo."""
    try:
        return abs_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None


def on_files(files, config):
    """Build the embedded-file -> page map from every page's include directive."""
    _EMBED_MAP.clear()
    repo_root = Path(config["docs_dir"]).parent
    for f in files:
        if not f.is_documentation_page() or not f.abs_src_path.endswith(".md"):
            continue
        try:
            text = Path(f.abs_src_path).read_text(encoding="utf-8")
        except OSError:
            continue
        m = _INCLUDE_RE.search(text)
        if not m:
            continue
        # Resolve the included path relative to the page's own directory.
        included_abs = Path(f.abs_src_path).parent / m.group(1)
        rel = _repo_rel(included_abs, repo_root)
        if rel:
            _EMBED_MAP[rel] = f.src_uri
    return files


def on_page_markdown(markdown, page, config, files):
    """Repoint links that target an embedded repo file at its docs page."""
    if not _EMBED_MAP:
        return markdown

    repo_root = Path(config["docs_dir"]).parent
    page_dir_abs = Path(page.file.abs_src_path).parent
    page_dir_uri = posixpath.dirname(page.file.src_uri)

    def repl(match: re.Match) -> str:
        target = match.group(1)
        # Skip externals, absolutes, pure anchors, images already handled.
        if (
            "://" in target
            or target.startswith(("#", "/", "mailto:", "tel:"))
        ):
            return match.group(0)

        url, sep, frag = target.partition("#")
        if not url.endswith(".md"):
            return match.group(0)

        abs_target = page_dir_abs / url
        rel = _repo_rel(abs_target, repo_root)
        if rel is None or rel not in _EMBED_MAP:
            return match.group(0)

        # Link to the mapped page, expressed relative to the current page so
        # MkDocs' own relative-link resolver turns it into the page URL.
        new_rel = posixpath.relpath(_EMBED_MAP[rel], page_dir_uri or ".")
        return f"]({new_rel}{sep}{frag})"

    return _LINK_RE.sub(repl, markdown)
