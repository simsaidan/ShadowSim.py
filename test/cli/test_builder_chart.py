"""Tests for the builder page results chart."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

BUILDER = Path(__file__).resolve().parents[2] / "shadowsim" / "cli" / "site" / "builder.js"

_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");

function NodeType() {}
function Element(tag) {
  this.tag = tag;
  this.attrs = {};
  this.children = [];
  this.className = "";
  this._text = "";
}
Element.prototype = Object.create(NodeType.prototype);
Element.prototype.setAttribute = function (name, value) {
  this.attrs[name] = String(value);
};
Element.prototype.append = function (...kids) {
  this.children.push(...kids);
};
Element.prototype.addEventListener = function () {};
Object.defineProperty(Element.prototype, "textContent", {
  set(value) { this._text = String(value); },
  get() { return this._text; },
});
function TextNode(value) {
  this.text = String(value);
}
TextNode.prototype = Object.create(NodeType.prototype);

const sandbox = {
  console,
  Node: NodeType,
  document: {
    querySelector() { return null; },
    createElement: (tag) => new Element(tag),
    createElementNS: (_ns, tag) => new Element(tag),
    createTextNode: (text) => new TextNode(text),
  },
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
if (typeof sandbox.chartComponent !== "function") {
  throw new Error("chartComponent was not loaded");
}

function revive(value) {
  if (value === "__NaN__") return NaN;
  if (value === "__Infinity__") return Infinity;
  if (Array.isArray(value)) return value.map(revive);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, revive(item)]));
  }
  return value;
}

function serialize(node) {
  if (node instanceof TextNode) return { kind: "text", text: node.text };
  return {
    kind: "element",
    tag: node.tag,
    className: node.className,
    attrs: node.attrs,
    text: node._text,
    children: node.children.map(serialize),
  };
}

const payload = revive(JSON.parse(fs.readFileSync(0, "utf8")));
process.stdout.write(JSON.stringify(serialize(sandbox.chartComponent(payload))));
"""


def _chart(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the chart tree produced for ``payload``."""
    try:
        completed = subprocess.run(
            ["node", "-e", _HARNESS, str(BUILDER)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        pytest.fail(f"node is required to test the results chart: {exc}")
    if completed.returncode != 0:
        pytest.fail(completed.stderr or completed.stdout)
    tree: dict[str, Any] = json.loads(completed.stdout)
    return tree


def _svg(chart: dict[str, Any]) -> dict[str, Any]:
    return next(child for child in chart["children"] if child["tag"] == "svg")


def _polylines(chart: dict[str, Any]) -> list[dict[str, Any]]:
    return [child for child in _svg(chart)["children"] if child["tag"] == "polyline"]


def _points(polyline: dict[str, Any]) -> list[tuple[float, float]]:
    raw = str(polyline["attrs"]["points"])
    assert "NaN" not in raw
    points: list[tuple[float, float]] = []
    for pair in raw.split():
        x_text, y_text = pair.split(",")
        points.append((float(x_text), float(y_text)))
    return points


def _axis_labels(chart: dict[str, Any]) -> tuple[list[str], list[str]]:
    texts = [child for child in _svg(chart)["children"] if child["tag"] == "text"]
    y_ticks = [str(child["text"]) for child in texts if child["attrs"].get("dominant-baseline") == "middle"]
    x_ends = [str(child["text"]) for child in texts if "dominant-baseline" not in child["attrs"]]
    return y_ticks, x_ends


def _swatches(chart: dict[str, Any]) -> list[str]:
    legend = next(child for child in chart["children"] if child["className"] == "legend")
    swatches: list[str] = []
    for item in legend["children"]:
        style = str(item["children"][0]["attrs"]["style"])
        assert style.startswith("background:")
        swatches.append(style.removeprefix("background:"))
    return swatches


def test_two_observables_show_both_curves_and_scales() -> None:
    chart = _chart({"times": [0, 1.25], "observables": [[1, -1], [0.25, 0.5]]})
    assert len(_polylines(chart)) == 2
    y_ticks, x_ends = _axis_labels(chart)
    assert y_ticks[0] == "-1"
    assert y_ticks[-1] == "1"
    assert x_ends == ["0", "1.25"]


def test_mismatched_series_drops_missing_points() -> None:
    chart = _chart({"times": [0, 1, 2], "observables": [[1, "__NaN__", 0, 9], [None, 1]]})
    lines = _polylines(chart)
    assert len(lines) == 2
    longer = _points(lines[0])
    shorter = _points(lines[1])
    assert len(longer) == 2
    assert len(shorter) == 1
    assert longer[0][0] < shorter[0][0] < longer[1][0]
    y_ticks, x_ends = _axis_labels(chart)
    assert y_ticks == ["0", "0.5", "1"]
    assert x_ends == ["0", "2"]


def test_six_curves_use_six_legend_colors() -> None:
    chart = _chart({"times": [0, 1], "observables": [[index, index + 1] for index in range(6)]})
    strokes = [str(line["attrs"]["stroke"]) for line in _polylines(chart)]
    assert len(strokes) == 6
    assert len(set(strokes)) == 6
    assert _swatches(chart) == strokes
