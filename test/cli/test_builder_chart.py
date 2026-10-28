"""Tests for the builder page results chart."""

import json
import subprocess
from collections.abc import Iterator
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
Element.prototype.replaceChildren = function (...kids) {
  this.children = [];
  this.append(...kids);
};
Element.prototype.getAttribute = function (name) {
  return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
};
Element.prototype.addEventListener = function (type, fn) {
  if (!this.listeners) this.listeners = {};
  if (!this.listeners[type]) this.listeners[type] = [];
  this.listeners[type].push(fn);
};
function elementText(node) {
  let text = "";
  for (const child of node.children || []) {
    if (child instanceof TextNode) text += child.text;
    else if (child instanceof Element) text += elementText(child);
  }
  return text;
}
function findButton(node, label) {
  if (!(node instanceof Element)) return null;
  if (node.tag === "button" && elementText(node) === label) return node;
  for (const child of node.children) {
    const found = findButton(child, label);
    if (found) return found;
  }
  return null;
}
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
const call = payload.__call;
const index = payload.__index;
const args = payload.__args;
const clicks = Array.isArray(payload.__clicks) ? payload.__clicks : payload.__click ? [payload.__click] : [];
delete payload.__call;
delete payload.__index;
delete payload.__args;
delete payload.__click;
delete payload.__clicks;
let result;
if (call) {
  if (typeof sandbox[call] !== "function") throw new Error(call + " was not loaded");
  result = args ? sandbox[call](...args) : sandbox[call](payload, index);
} else {
  result = sandbox.chartComponent(payload);
}
for (const click of clicks) {
  const button = findButton(result, click);
  if (!button) throw new Error("missing button: " + click);
  const listeners = button.listeners && button.listeners.click;
  if (!listeners || !listeners.length) throw new Error("missing click listener");
  listeners[0]({ preventDefault() {}, stopPropagation() {} });
}
process.stdout.write(JSON.stringify(result instanceof Element ? serialize(result) : result));
"""


def _run(payload: dict[str, Any]) -> Any:
    """Return the JSON result of drawing ``payload`` in the page script."""
    try:
        completed = subprocess.run(
            ["node", "-e", _HARNESS, str(BUILDER)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        pytest.fail(f"node is required to test the results chart: {exc}")
    if completed.returncode != 0:
        pytest.fail(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


def _chart(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the chart tree produced for ``payload``."""
    tree = _run(payload)
    assert isinstance(tree, dict)
    return tree


def _invoke(
    name: str,
    payload: dict[str, Any],
    index: float | None = None,
    args: list[Any] | None = None,
) -> Any:
    """Return the result of calling ``name`` in the page script."""
    body = dict(payload)
    body["__call"] = name
    if index is not None:
        body["__index"] = index
    if args is not None:
        body["__args"] = args
    return _run(body)


def _results(
    payload: dict[str, Any],
    *,
    click: str | None = None,
    clicks: list[str] | None = None,
) -> dict[str, Any]:
    """Return the results panel, after pressing ``click`` or each label in ``clicks``."""
    body = dict(payload)
    body["__call"] = "resultsComponent"
    if clicks is not None:
        body["__clicks"] = clicks
    elif click is not None:
        body["__click"] = click
    tree = _run(body)
    assert isinstance(tree, dict)
    return tree


def _buttons(root: dict[str, Any]) -> list[dict[str, Any]]:
    return [node for node in _walk(root) if node.get("tag") == "button"]


def _pressed(root: dict[str, Any]) -> list[str]:
    return [_node_text(node) for node in _buttons(root) if node.get("attrs", {}).get("aria-pressed") == "true"]


def _walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("children", []):
        if isinstance(child, dict) and child.get("kind") == "element":
            yield from _walk(child)


def _svg(chart: dict[str, Any]) -> dict[str, Any]:
    return next(node for node in _walk(chart) if node.get("tag") == "svg")


def _by_class(chart: dict[str, Any], class_name: str) -> dict[str, Any]:
    return next(node for node in _walk(chart) if node.get("className") == class_name)


def _node_text(node: dict[str, Any]) -> str:
    parts = [str(node.get("text") or "")]
    for child in node.get("children", []):
        if child.get("kind") == "text":
            parts.append(str(child["text"]))
        elif child.get("kind") == "element":
            parts.append(_node_text(child))
    return "".join(parts)


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
    legend = _by_class(chart, "legend")
    swatches: list[str] = []
    for item in legend["children"]:
        style = str(item["children"][0]["attrs"]["style"])
        assert style.startswith("background:")
        swatches.append(style.removeprefix("background:"))
    return swatches


def _legend(chart: dict[str, Any]) -> list[str]:
    return [_node_text(item) for item in _by_class(chart, "legend")["children"]]


def _line_titles(chart: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for line in _polylines(chart):
        title = next(child for child in line["children"] if child["tag"] == "title")
        titles.append(str(title["text"]))
    return titles


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


def test_labels_name_the_curves_and_both_axes() -> None:
    chart = _chart(
        {
            "times": [0, 1.25],
            "observables": [[1, -1], [0.25, 0.5]],
            "labels": ["⟨Z⟩ on 0", "⟨Z⟩ on 1"],
        }
    )
    assert _legend(chart) == ["⟨Z⟩ on 0", "⟨Z⟩ on 1"]
    assert _line_titles(chart) == ["⟨Z⟩ on 0", "⟨Z⟩ on 1"]
    assert _node_text(_by_class(chart, "y-title")) == "⟨Z⟩"
    assert _node_text(_by_class(chart, "x-title")) == "Time"
    assert _svg(chart)["attrs"]["aria-label"] == "⟨Z⟩ versus time"
    assert _node_text(_by_class(chart, "readout")) == ""


def test_benchmark_series_keep_their_curve_names() -> None:
    chart = _chart(
        {
            "times": [0, 1],
            "labels": ["⟨X⟩ on 1"],
            "series": [
                {"name": "qutip#1", "labels": ["qutip#1 · ⟨X⟩ on 1"], "observables": [[1, 0]]},
                {"name": "qutip#2", "observables": [[0, 1]]},
            ],
        }
    )
    assert _legend(chart) == ["qutip#1 · ⟨X⟩ on 1", "qutip#2 · ⟨X⟩ on 1"]
    assert _node_text(_by_class(chart, "y-title")) == "⟨X⟩"


def test_hover_readout_names_the_nearest_values() -> None:
    payload = {
        "times": [0, 1, 2],
        "observables": [[1, "__NaN__", 0], [None, 0.5, 1]],
        "labels": ["⟨Z⟩ on 0", "⟨Z⟩ on 1"],
    }
    assert _invoke("plotFraction", {}, args=[56, 56, 612]) == 0
    assert _invoke("plotFraction", {}, args=[612, 56, 612]) == 1
    assert _invoke("plotFraction", {}, args=[55, 56, 612]) is None
    assert _invoke("nearestTimeIndex", payload, 0) == 0
    assert _invoke("nearestTimeIndex", payload, 0.6) == 1
    assert _invoke("nearestTimeIndex", payload, 1) == 2
    assert _invoke("hoverReadout", payload, 1) == "t = 1 · ⟨Z⟩ on 1 = 0.5"
    assert _invoke("hoverReadout", payload, 0) == "t = 0 · ⟨Z⟩ on 0 = 1"
    assert _invoke("hoverReadout", payload, 3) == ""


def _benchmark() -> dict[str, Any]:
    return {
        "times": [0, 1],
        "labels": ["⟨Z⟩ on 0", "⟨Z⟩ on 1"],
        "saved": ["results/run1"],
        "series": [
            {
                "name": "qutip#1",
                "labels": ["qutip#1 · ⟨Z⟩ on 0", "qutip#1 · ⟨Z⟩ on 1"],
                "observables": [[2, 0], [1, 1]],
            },
            {
                "name": "qutip#2",
                "labels": ["qutip#2 · ⟨Z⟩ on 0", "qutip#2 · ⟨Z⟩ on 1"],
                "observables": [[0, 0], [1, 0]],
            },
        ],
        "errors": [
            {
                "challenger_id": "qutip_simulator#2",
                "observables": [
                    {"index": 0, "linf": 2, "rmse": 1.5},
                    {"index": 1, "linf": 1, "rmse": 0.5},
                ],
            }
        ],
        "resources": [
            {
                "simulator_id": "qutip_simulator#1",
                "wall_time_s": 0.41,
                "shots_per_job": None,
                "num_jobs": None,
                "total_shots": None,
            },
            {
                "simulator_id": "aer_simulator",
                "wall_time_s": 1.2,
                "shots_per_job": 256,
                "num_jobs": 11,
                "total_shots": 2816,
            },
        ],
    }


def test_one_simulator_has_no_switch() -> None:
    bare = _results({"times": [0, 1], "observables": [[1, 0]], "labels": ["⟨Z⟩ on 0"]})
    assert bare["className"] == "chart"
    assert _buttons(bare) == []
    timed = _results(
        {
            "times": [0, 1],
            "observables": [[1, 0]],
            "labels": ["⟨Z⟩ on 0"],
            "resources": [
                {
                    "simulator_id": "qutip_simulator",
                    "wall_time_s": 0.42,
                    "shots_per_job": None,
                    "num_jobs": None,
                    "total_shots": None,
                }
            ],
        }
    )
    assert _buttons(timed) == []
    assert _node_text(_by_class(timed, "resources")) == "0.42 s"
    sampled = _results(
        {
            "times": [0, 1],
            "observables": [[1, 0]],
            "labels": ["⟨Z⟩ on 0"],
            "resources": [
                {
                    "simulator_id": "trotterization_simulator",
                    "wall_time_s": 1.2,
                    "shots_per_job": 256,
                    "num_jobs": 101,
                    "total_shots": 25856,
                }
            ],
        }
    )
    assert _node_text(_by_class(sampled, "resources")) == "1.2 s, 256 shots × 101"


def test_error_switch_replaces_the_curves_and_keeps_the_resource_line() -> None:
    payload = _benchmark()
    curves = _results(payload)
    assert [_node_text(button) for button in _buttons(curves)] == [
        "All",
        "⟨Z⟩ on 0",
        "⟨Z⟩ on 1",
        "Curves",
        "Error",
    ]
    assert _pressed(curves) == ["All", "Curves"]
    assert _legend(curves) == ["qutip#1 · ⟨Z⟩ on 0", "qutip#1 · ⟨Z⟩ on 1", "qutip#2 · ⟨Z⟩ on 0", "qutip#2 · ⟨Z⟩ on 1"]
    assert _node_text(_by_class(curves, "hint")) == "Saved to results/run1"
    resources = "qutip#1 0.41 s · aer 1.2 s, 256 shots × 11"
    assert _node_text(_by_class(curves, "resources")) == resources

    error = _results(payload, click="Error")
    assert _pressed(error) == ["All", "Error"]
    assert _node_text(_by_class(error, "y-title")) == "Error vs qutip#1"
    assert _svg(error)["attrs"]["aria-label"] == "Error vs qutip#1 versus time"
    assert len(_polylines(error)) == 2
    assert _line_titles(error) == ["qutip#2 · ⟨Z⟩ on 0", "qutip#2 · ⟨Z⟩ on 1"]
    assert _legend(error) == [
        "qutip#2 · ⟨Z⟩ on 0: max 2, RMSE 1.5",
        "qutip#2 · ⟨Z⟩ on 1: max 1, RMSE 0.5",
    ]
    y_ticks, _x_ends = _axis_labels(error)
    assert y_ticks == ["0", "1", "2"]
    difference = _points(_polylines(error)[0])
    assert difference[0][1] < difference[1][1]
    assert _node_text(_by_class(error, "resources")) == resources
    assert _node_text(_by_class(error, "hint")) == "Saved to results/run1"
    readout = _invoke("hoverReadout", payload, 0, args=[payload, 0, "error"])
    assert readout == "t = 0 · qutip#2 · ⟨Z⟩ on 0 = 2 · qutip#2 · ⟨Z⟩ on 1 = 0"


def test_observable_switch_shows_one_chart_at_a_time() -> None:
    payload = _benchmark()
    one = _results(payload, click="⟨Z⟩ on 1")
    assert _pressed(one) == ["⟨Z⟩ on 1", "Curves"]
    assert _legend(one) == ["qutip#1 · ⟨Z⟩ on 1", "qutip#2 · ⟨Z⟩ on 1"]
    assert len(_polylines(one)) == 2

    error = _results(payload, clicks=["⟨Z⟩ on 1", "Error"])
    assert _pressed(error) == ["⟨Z⟩ on 1", "Error"]
    assert _legend(error) == ["qutip#2 · ⟨Z⟩ on 1: max 1, RMSE 0.5"]
    assert _line_titles(error) == ["qutip#2 · ⟨Z⟩ on 1"]
    assert _node_text(_by_class(error, "resources")) == "qutip#1 0.41 s · aer 1.2 s, 256 shots × 11"

    restored = _results(payload, clicks=["⟨Z⟩ on 1", "All"])
    assert _pressed(restored) == ["All", "Curves"]
    assert len(_polylines(restored)) == 4
    readout = _invoke("hoverReadout", payload, 0, args=[payload, 0, "error", 1])
    assert readout == "t = 0 · qutip#2 · ⟨Z⟩ on 1 = 0"
