"""Render ``\\full_bibliography`` as a numbered list with arXiv links.

``mkdocs-bibtex`` turns that command into footnotes whose back-links point at
citations on other pages. Those anchors are missing on the References page.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from pybtex.database import Entry, Person, parse_file


def _plain(text: str) -> str:
    """Drop BibTeX brace protection so the text renders as prose."""
    return text.replace("{", "").replace("}", "")


def _person_name(person: Person) -> str:
    """Format one BibTeX person as ``Given Last``."""
    first = _plain(" ".join(person.first_names))
    middle = _plain(" ".join(person.middle_names))
    prelast = _plain(" ".join(person.prelast_names))
    last = _plain(" ".join(person.last_names))
    given = " ".join(part for part in (first, middle, prelast) if part)
    if given and last:
        return f"{given} {last}"
    return last or given


def _format_entry(entry: Entry) -> str:
    """Format one bibliography entry, appending its URL when present."""
    parts: list[str] = []
    if "author" in entry.persons:
        parts.append(", ".join(_person_name(person) for person in entry.persons["author"]))
    title = _plain(entry.fields.get("title", ""))
    if title:
        parts.append(f"*{title}*")
    year = entry.fields.get("year", "")
    if year:
        parts.append(f"({year}).")
    text = " ".join(parts)
    url = entry.fields.get("url", "")
    eprint = entry.fields.get("eprint", "")
    if url and eprint:
        text += f" [arXiv:{eprint}]({url})"
    elif url:
        text += f" [link]({url})"
    return text


def on_page_markdown(
    markdown: str,
    page: object,
    config: Mapping[str, object],
    files: object,
) -> str:
    """Replace ``\\full_bibliography`` before the bibtex plugin sees it."""
    del page, files
    if "\\full_bibliography" not in markdown:
        return markdown

    docs_dir = Path(str(config["docs_dir"]))
    lines: list[str] = []
    number = 1
    for bib_file in sorted(docs_dir.glob("*.bib")):
        for entry in parse_file(str(bib_file)).entries.values():
            lines.append(f"{number}. {_format_entry(entry)}")
            number += 1
    return markdown.replace("\\full_bibliography", "\n".join(lines))
