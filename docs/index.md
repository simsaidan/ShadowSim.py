---
hide:
  - navigation
  - toc
---

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } __Docs__

    ---

    Start with the [API reference](reference/utils.md) for standalone utilities.

-   :material-github:{ .lg .middle } __Source__

    ---

    [:octicons-arrow-right-24: Repository](https://github.com/simsaidan/ShadowSim.py)

</div>

---

!!! note "Work in progress"
    Public APIs are still **draft** until a stable release. Expect changes.

## Local preview

```bash
uv sync --group docs
uv run mkdocs serve
```

Open the URL printed in the terminal (usually `http://127.0.0.1:8000`).

## Customizing this site

Edit **`mkdocs.yml`** (theme, colors, fonts, nav) and add Markdown files under **`docs/`**. Push to `main` to redeploy.
