"""Tests for enabling Run on the builder page."""

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
  this.disabled = false;
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

function find(node, pred) {
  if (pred(node)) return node;
  for (const child of node.children || []) {
    const found = find(child, pred);
    if (found) return found;
  }
  return null;
}

function resetPage() {
  selection.state = null;
  selection.model = null;
  selection.simulator = null;
  selection.backend = null;
  selection.measure = null;
  selection.then = null;
  settings.qubits = "";
  settings.total = "";
  basisBits = "";
  preexistingId = null;
  modelFactories = [];
  modelTerms.splice(0, modelTerms.length);
  placedSims.splice(0, placedSims.length);
  placedThens.splice(0, placedThens.length);
  running = false;
}

function fillIsing(qubits, total) {
  resetPage();
  BLOCKS.simulator = [{ id: "qutip", observables: true }];
  BLOCKS.backend = [{ id: "statevector", setup: "" }];
  modelFactories = [{
    id: "ising",
    title: "Ising",
    qubits: true,
    setup: "model = ising(n_qubits={qubits})",
  }];
  preexistingId = "ising";
  selection.state = "basis";
  selection.model = "preexisting";
  selection.simulator = "qutip";
  selection.backend = "statevector";
  selection.measure = "z";
  selection.then = "plot";
  basisBits = "00";
  settings.qubits = qubits;
  settings.total = total;
  placedSims.push({ id: "qutip", key: 1, params: { timeSteps: "11" } });
  placedThens.push("plot");
}

const request = JSON.parse(process.argv[3]);
if (request.complete) fillIsing(request.qubits, request.total);
else resetPage();

const button = find(settingsComponent(), (node) => node.className === "run");
document.querySelector = (selector) => (selector === ".run" ? button : null);
syncRunButton();
process.stdout.write(JSON.stringify({
  status: statusMessage(),
  ready: settingsReady(),
  label: textOf(button),
  renderedDisabled: Object.hasOwn(button.attrs, "disabled"),
  syncedDisabled: button.disabled === true,
}));
`;

vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
vm.runInContext(`${fs.readFileSync(process.argv[2], "utf8")}\n${probe}`, sandbox);
"""


def _page(*, complete: bool, qubits: str = "", total: str = "") -> dict[str, Any]:
    """Return the status and Run button state for one builder selection."""
    scenario = {"complete": complete, "qubits": qubits, "total": total}
    try:
        completed = subprocess.run(
            ["node", "-e", _HARNESS, str(CHECKS), str(BUILDER), json.dumps(scenario)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        pytest.fail(f"node is required to test run readiness: {exc}")
    if completed.returncode != 0:
        pytest.fail(completed.stderr or completed.stdout)
    page: dict[str, Any] = json.loads(completed.stdout)
    return page


def _assert_disabled(page: dict[str, Any], status: str) -> None:
    assert page["label"] == "Run simulation"
    assert page["status"] == status
    assert page["ready"] is False
    assert page["renderedDisabled"] is True
    assert page["syncedDisabled"] is True


@pytest.mark.parametrize(
    ("qubits", "total", "status"),
    [
        pytest.param("0", "1", "Qubits must be an integer of at least 2.", id="zero-qubits"),
        pytest.param("-1", "1", "Qubits must be an integer of at least 2.", id="negative-qubits"),
        pytest.param("1.5", "1", "Qubits must be an integer of at least 2.", id="fractional-qubits"),
        pytest.param("1", "1", "Qubits must be an integer of at least 2.", id="ising-one-qubit"),
        pytest.param("2", "0", "Total time must be a positive number.", id="zero-time"),
        pytest.param("2", "-1", "Total time must be a positive number.", id="negative-time"),
    ],
)
def test_invalid_numbers_disable_run(qubits: str, total: str, status: str) -> None:
    _assert_disabled(_page(complete=True, qubits=qubits, total=total), status)


def test_complete_selection_enables_run() -> None:
    page = _page(complete=True, qubits="2", total="1")
    assert page["label"] == "Run simulation"
    assert page["status"] == "Ready to run."
    assert page["ready"] is True
    assert page["renderedDisabled"] is False
    assert page["syncedDisabled"] is False


def test_incomplete_form_disables_run() -> None:
    page = _page(complete=False)
    assert page["label"] == "Run simulation"
    assert page["status"] == "Place a block in each slot."
    assert page["ready"] is False
    assert page["renderedDisabled"] is True
    assert page["syncedDisabled"] is True
