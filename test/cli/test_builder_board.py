"""Tests for restoring the builder board and copying its script."""

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
  this.style = {};
  this.disabled = false;
}
Element.prototype = Object.create(NodeType.prototype);
Element.prototype.setAttribute = function (name, value) {
  this.attrs[name] = String(value);
};
Element.prototype.removeAttribute = function (name) {
  delete this.attrs[name];
};
Element.prototype.append = function (...kids) {
  this.children.push(...kids);
};
Element.prototype.addEventListener = function (type, fn) {
  if (!this.listeners[type]) this.listeners[type] = [];
  this.listeners[type].push(fn);
};
Element.prototype.classList = { add() {}, remove() {}, toggle() {} };
Object.defineProperty(Element.prototype, "textContent", {
  set(value) { this._text = String(value); },
  get() { return this._text; },
});
function TextNode(value) {
  this.text = String(value);
}
TextNode.prototype = Object.create(NodeType.prototype);

const store = new Map();
const writes = [];
const sandbox = {
  writes,
  console,
  process,
  Node: NodeType,
  setTimeout(fn) { fn(); return 1; },
  clearTimeout() {},
  localStorage: {
    getItem(key) { return store.has(key) ? store.get(key) : null; },
    setItem(key, value) { store.set(key, String(value)); },
    removeItem(key) { store.delete(key); },
  },
  navigator: {
    clipboard: {
      writeText(text) {
        writes.push(text);
        return Promise.resolve();
      },
    },
  },
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
function walk(node, found) {
  if (!node || !node.tag) return found;
  found.push(node);
  for (const child of node.children || []) walk(child, found);
  return found;
}
function click(node) {
  const listeners = node.listeners && node.listeners.click;
  if (!listeners || !listeners.length) throw new Error("missing click listener");
  listeners[0]({ currentTarget: node, stopPropagation() {} });
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
  grayBits = "";
  angleText = "";
  amplitudeText = "";
  qubitsSource = null;
  preexistingId = null;
  emitterText = "1";
  modelTerms.splice(0, modelTerms.length);
  placedSims.splice(0, placedSims.length);
  placedThens.splice(0, placedThens.length);
  savePath = DEFAULT_SAVE_PATH;
  exportPath = DEFAULT_EXPORT_PATH;
  measureSites = null;
  stateOpen = false;
  measureOpen = false;
  saveOpen = false;
  exportOpen = false;
  preexistingOpen = false;
  boardReady = false;
}
function fillIsing() {
  resetPage();
  BLOCKS.simulator = [{ id: "qutip", title: "QuTiP", observables: true, detail: "Reference" }];
  BLOCKS.model = [{ id: "preexisting", title: "Preexisting model", detail: "Choose a built-in model" }];
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
  selection.measure = "z";
  selection.then = "plot";
  basisBits = "01";
  settings.qubits = "2";
  settings.total = "1";
  qubitsSource = "state";
  savePath = "results/kept";
  measureSites = [0];
  placedSims.push({ id: "qutip", key: 3, open: true, params: { timeSteps: "11" } });
  placedThens.push("plot");
}
function fillCircuit() {
  fillIsing();
  BLOCKS.simulator = [{ id: "trotterization", title: "Trotterization", observables: false, detail: "" }];
  BLOCKS.backend = [{
    id: "aer",
    phrase: "Aer",
    shots: true,
    setup: "circuit_backend = AerCircuitBackend(shots={shots})",
  }];
  BLOCKS.model = [
    { id: "preexisting", title: "Preexisting model", detail: "" },
    { id: "hamiltonian", title: "Hamiltonian", adds: true, detail: "" },
  ];
  selection.simulator = "trotterization";
  placedSims.splice(0, placedSims.length, {
    id: "trotterization",
    key: 1,
    params: { timeSteps: "11", numSteps: "4", trotterDepth: "1", seed: "0", order: "1" },
    backend: "aer",
    shots: "256",
  });
}

const request = JSON.parse(process.argv[3]);
const surface = { replaceChildren() {} };
serverSession = "server-1";
let result;
if (request.action === "roundtrip") {
  fillIsing();
  draw(surface);
  const storedEarly = localStorage.getItem("shadowsim.builder.board");
  const before = boardSnapshot();
  boardReady = true;
  draw(surface);
  const stored = localStorage.getItem("shadowsim.builder.board");
  resetPage();
  boardReady = true;
  modelFactories = [{
    id: "ising",
    title: "Ising",
    qubits: true,
    setup: "model = ising(n_qubits={qubits})",
  }];
  BLOCKS.simulator = [{ id: "qutip", title: "QuTiP", observables: true, detail: "Reference" }];
  restoreBoard();
  const after = boardSnapshot();
  settings.total = "4";
  refreshSummaryAndPreview();
  const refreshed = JSON.parse(localStorage.getItem("shadowsim.builder.board"));
  result = {
    storedEarly,
    stored,
    before,
    after,
    openStored: Object.hasOwn(before.placedSims[0], "open"),
    keyStored: Object.hasOwn(before.placedSims[0], "key"),
    openAfter: placedSims[0].open,
    keyAfter: placedSims[0].key,
    refreshedTotal: refreshed.settings.total,
  };
} else if (request.action === "broken") {
  fillIsing();
  const before = JSON.stringify(boardSnapshot());
  const rejected = [null, { version: 2 }, {}].every((snapshot) => applyBoard(snapshot) === false);
  localStorage.setItem("shadowsim.builder.board", "{");
  restoreBoard();
  result = { rejected, unchanged: JSON.stringify(boardSnapshot()) === before };
} else if (request.action === "unknown") {
  fillCircuit();
  const snap = boardSnapshot();
  snap.preexistingId = "gone";
  snap.modelTerms = [
    { id: "hamiltonian", matrix: "[[1, 0], [0, -1]]", sites: [0, 1.5] },
    { id: "nope", matrix: "", sites: [] },
  ];
  const row = snap.placedSims[0];
  snap.placedSims = [
    { ...row, backend: "missing" },
    { ...row, backend: "aer", shots: "128" },
    { id: "missing", params: { timeSteps: "4" }, backend: "aer", shots: "8", backendFields: null },
  ];
  const applied = applyBoard(snap);
  result = {
    applied,
    model: selection.model,
    preexistingId,
    terms: modelTerms.map((term) => ({ id: term.id, matrix: term.matrix, sites: term.sites })),
    sims: placedSims.map((entry) => ({ id: entry.id, backend: entry.backend, shots: entry.shots })),
  };
} else if (request.action === "launch") {
  fillIsing();
  boardReady = true;
  rememberBoard();
  resetPage();
  serverSession = "server-2";
  boardReady = true;
  restoreBoard();
  result = { state: selection.state, stored: localStorage.getItem("shadowsim.builder.board") };
} else if (request.action === "clear") {
  fillIsing();
  boardReady = true;
  running = true;
  emptyBoard();
  const kept = selection.state === "basis";
  running = false;
  document.querySelector = (selector) => (selector === ".board" ? surface : null);
  const button = walk(settingsComponent(), []).find((node) => node.className === "clear");
  click(button);
  const stored = JSON.parse(localStorage.getItem("shadowsim.builder.board"));
  result = {
    kept,
    state: selection.state,
    qubits: settings.qubits,
    bits: basisBits,
    sims: placedSims.length,
    terms: modelTerms.length,
    thens: placedThens.length,
    preexistingId,
    storedState: stored.selection.state,
    storedServer: stored.server,
  };
} else if (request.action === "copy") {
  resetPage();
  const empty = walk(panelsComponent(), []).find((node) => node.className === "copy");
  click(empty);
  const emptyWrites = writes.length;
  fillIsing();
  const full = walk(panelsComponent(), []).find((node) => node.className === "copy");
  click(full);
  result = {
    emptyDisabled: Object.hasOwn(empty.attrs, "disabled"),
    emptyWrites,
    fullDisabled: Object.hasOwn(full.attrs, "disabled"),
    write: writes[0] ?? null,
    preview: previewText(),
  };
} else {
  throw new Error("unknown action");
}
process.stdout.write(JSON.stringify(result));
`;

vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
vm.runInContext(`${fs.readFileSync(process.argv[2], "utf8")}\n${probe}`, sandbox);
"""


def _call(action: str) -> dict[str, Any]:
    """Return the builder probe result for one board action."""
    try:
        completed = subprocess.run(
            ["node", "-e", _HARNESS, str(CHECKS), str(BUILDER), json.dumps({"action": action})],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        pytest.fail(f"node is required to test the builder board: {exc}")
    if completed.returncode != 0:
        pytest.fail(completed.stderr or completed.stdout)
    result: dict[str, Any] = json.loads(completed.stdout)
    return result


def test_board_snapshot_round_trip() -> None:
    page = _call("roundtrip")
    assert page["storedEarly"] is None
    assert page["openStored"] is False
    assert page["keyStored"] is False
    assert json.loads(page["stored"]) == page["before"]
    assert page["after"] == page["before"]
    assert page["openAfter"] is False
    assert page["keyAfter"] != 3
    assert page["before"]["basisBits"] == "01"
    assert page["before"]["savePath"] == "results/kept"
    assert page["before"]["measureSites"] == [0]
    assert page["refreshedTotal"] == "4"


def test_a_new_server_drops_the_saved_board() -> None:
    page = _call("launch")
    assert page == {"state": None, "stored": None}


def test_clear_empties_the_board() -> None:
    page = _call("clear")
    assert page["kept"] is True
    assert page["state"] is None
    assert page["qubits"] == ""
    assert page["bits"] == ""
    assert page["sims"] == 0
    assert page["terms"] == 0
    assert page["thens"] == 0
    assert page["preexistingId"] is None
    assert page["storedState"] is None
    assert page["storedServer"] == "server-1"


def test_broken_snapshot_is_ignored() -> None:
    page = _call("broken")
    assert page == {"rejected": True, "unchanged": True}


def test_unknown_blocks_are_dropped() -> None:
    page = _call("unknown")
    assert page["applied"] is True
    assert page["model"] is None
    assert page["preexistingId"] is None
    assert page["terms"] == [{"id": "hamiltonian", "matrix": "[[1, 0], [0, -1]]", "sites": [0]}]
    assert page["sims"] == [
        {"id": "trotterization", "backend": None, "shots": "256"},
        {"id": "trotterization", "backend": "aer", "shots": "128"},
    ]


def test_copy_writes_the_script_only_when_one_is_shown() -> None:
    page = _call("copy")
    assert page["emptyDisabled"] is True
    assert page["emptyWrites"] == 0
    assert page["fullDisabled"] is False
    assert page["write"] == page["preview"]
    assert "from shadowsim.encoding import ComputationalBasisEncoding" in page["write"]
    assert "import *" not in page["write"]
