"""Cite the PauliPropagation paper on its backend API page.

``mkdocs-bibtex`` only sees page markdown, not mkdocstrings docstrings, so this
hook injects ``[@rudolph2025pauli]`` before bibtex runs.
"""

from __future__ import annotations

from collections.abc import Mapping

from mkdocs.plugins import event_priority

_PAGE_URI = "reference/shadowsim/backends/pauli_propagation.md"
_CITE_LINE = "Based on Pauli propagation [@rudolph2025pauli].\n\n"


@event_priority(100)
def on_page_markdown(
    markdown: str,
    page: object,
    config: Mapping[str, object],
    files: object,
) -> str:
    """Prepend the paper cite and a local bibliography on the backend page."""
    del config, files
    src_uri = getattr(getattr(page, "file", None), "src_uri", None)
    if src_uri != _PAGE_URI:
        return markdown
    if "[@rudolph2025pauli]" not in markdown:
        markdown = _CITE_LINE + markdown
    if "\\bibliography" not in markdown:
        markdown = f"{markdown.rstrip()}\n\n\\bibliography\n"
    return markdown
