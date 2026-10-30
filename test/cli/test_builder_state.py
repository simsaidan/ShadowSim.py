"""Tests for collapsing an initial-state card."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

_SITE = Path(__file__).resolve().parents[2] / "shadowsim" / "cli" / "site"
CHECKS = _SITE / "checks.js"
BUILDER = _SITE / "builder.js"

_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");

function NodeType() {}
function Element(tag) {
  this.tag = tag;
  this.attrs = {};
  this.children = [];
  this.className = "";
  this.listeners = {};
  this._text = "";
}
Element.prototype = Object.create(NodeType.prototype);
Element.prototype.setAttribute = function (name, value) {
  this.attrs[name] = String(value);
};
Element.prototype.append = function (...kids) {
  for (const kid of kids) {
    this.children.push(kid);
    if (kid && typeof kid === "object") kid.parentNode = this;
  }
};
Element.prototype.matches = function (selector) {
  return selector === ".chip" && this.className.split(/\s+/).includes("chip");
};
Element.prototype.closest = function (selector) {
  let node = this;
  while (node) {
    if (node.matches && node.matches(selector)) return node;
    node = node.parentNode;
  }
  return null;
};
Element.prototype.replaceWith = function (...nodes) {
  const parent = this.parentNode;
  if (!parent) return;
  const index = parent.children.indexOf(this);
  parent.children.splice(index, 1, ...nodes.filter(Boolean));
  for (const node of nodes) {
    if (node) node.parentNode = parent;
  }
  this.parentNode = null;
};
Element.prototype.addEventListener = function (type, fn) {
  if (!this.listeners[type]) this.listeners[type] = [];
  this.listeners[type].push(fn);
};
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
  process,
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

const probe = `
function textOf(node) {
  if (!node.tag) return node.text || "";
  return node.children.map(textOf).join("");
}
function walk(node, found) {
  found.push(node);
  for (const child of node.children || []) {
    if (child.tag) walk(child, found);
  }
  return found;
}
function click(node) {
  const listeners = node.listeners && node.listeners.click;
  if (!listeners || !listeners.length) throw new Error("missing click listener");
  listeners[0]({ currentTarget: node, stopPropagation() {} });
}
function describe(card) {
  const nodes = walk(card, []);
  const done = nodes.find((node) => node.tag === "button" && node.className === "done");
  const field = nodes.find((node) => node.tag === "input");
  const detail = nodes.find((node) => node.className === "basis-detail");
  const head = nodes.find((node) => node.className === "basis-head");
  return {
    editing: card.className.includes("is-editing"),
    done: done ? textOf(done) : null,
    field: Boolean(field),
    detail: detail ? textOf(detail) : null,
    head: head ? head.children[0] : null,
    doneNode: done || null,
  };
}

function plain(card) {
  return { editing: card.editing, done: card.done, field: card.field, detail: card.detail };
}

basisBits = "10";
stateOpen = true;
const holder = document.createElement("div");
holder.append(basisChip());
const open = describe(holder.children[0]);
let redraws = 0;
draw = () => { redraws += 1; };
click(open.doneNode);
const closed = describe(holder.children[0]);
click(closed.head);
const afterReopen = redraws;
const again = describe(holder.children[0]);
const reopened = stateOpen === true && again.editing === true && again.field === true;
stateOpen = false;
place("state", "basis");
const placed = selection.state === "basis" && stateOpen === true;
clearLane("state");
const cleared = selection.state === null && stateOpen === false;
stateOpen = true;
const siblings = ["gray", "angle", "amplitude"].map((id) => {
  selection.state = id;
  let card = grayChip();
  if (id === "angle") {
    card = numberChip("angle", "Angle", "Radians", "Angles", "Enter angles", () => angleText, (value) => {
      angleText = value;
    });
  }
  if (id === "amplitude") {
    card = numberChip(
      "amplitude",
      "Amplitude",
      "Amplitudes",
      "Amplitudes",
      "Enter amplitudes",
      () => amplitudeText,
      (value) => {
        amplitudeText = value;
      },
    );
  }
  return describe(card).done;
});

process.stdout.write(JSON.stringify({
  open: plain(open),
  closed: Object.assign(plain(closed), {
    header: closed.head ? closed.head.tag : null,
    headerType: closed.head ? closed.head.attrs.type : null,
  }),
  redraws: afterReopen,
  reopened,
  placed,
  cleared,
  siblings,
}));
`;

vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
vm.runInContext(`${fs.readFileSync(process.argv[2], "utf8")}\n${probe}`, sandbox);
"""


def _card() -> dict[str, Any]:
    """Return the open, closed, and reopened basis-state card."""
    try:
        completed = subprocess.run(
            ["node", "-e", _HARNESS, str(CHECKS), str(BUILDER)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        pytest.fail(f"node is required to test the basis-state card: {exc}")
    if completed.returncode != 0:
        pytest.fail(completed.stderr or completed.stdout)
    page: dict[str, Any] = json.loads(completed.stdout)
    return page


def test_basis_state_card_closes_from_done() -> None:
    page = _card()
    assert page["open"] == {
        "editing": True,
        "done": "Done",
        "field": True,
        "detail": "Start in |10>",
    }
    assert page["closed"]["editing"] is False
    assert page["closed"]["done"] is None
    assert page["closed"]["field"] is False
    assert page["closed"]["detail"] == "Start in |10>"
    assert page["closed"]["header"] == "button"
    assert page["closed"]["headerType"] == "button"
    assert page["redraws"] == 0
    assert page["reopened"] is True
    assert page["placed"] is True
    assert page["cleared"] is True
    assert page["siblings"] == ["Done", "Done", "Done"]
