"""Tests for restoring the builder board, copying its script, and updating it in place."""

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
  for (const kid of kids) {
    this.children.push(kid);
    if (kid && typeof kid === "object") kid.parentNode = this;
  }
};
Element.prototype.replaceChildren = function (...kids) {
  for (const child of this.children) {
    if (child && typeof child === "object") child.parentNode = null;
  }
  this.children = [];
  this.append(...kids);
};
Element.prototype.replaceWith = function (...nodes) {
  const parent = this.parentNode;
  if (!parent) return;
  const next = nodes.filter(Boolean);
  const index = parent.children.indexOf(this);
  parent.children.splice(index, 1, ...next);
  for (const node of next) node.parentNode = parent;
  this.parentNode = null;
};
Element.prototype.matches = function (selector) {
  return matchSimple(this, selector);
};
Element.prototype.closest = function (selector) {
  let node = this;
  while (node) {
    if (node.matches && node.matches(selector)) return node;
    node = node.parentNode;
  }
  return null;
};
Element.prototype.querySelector = function (selector) {
  return findAll(this, selector)[0] || null;
};
Element.prototype.querySelectorAll = function (selector) {
  return findAll(this, selector);
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
Object.defineProperty(Element.prototype, "dataset", {
  get() {
    const data = {};
    for (const [key, value] of Object.entries(this.attrs)) {
      if (!key.startsWith("data-")) continue;
      const name = key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
      data[name] = value;
    }
    return data;
  },
});
Object.defineProperty(Element.prototype, "hidden", {
  get() { return Object.hasOwn(this.attrs, "hidden"); },
  set(value) {
    if (value) this.attrs.hidden = "";
    else delete this.attrs.hidden;
  },
});
function TextNode(value) {
  this.text = String(value);
}
TextNode.prototype = Object.create(NodeType.prototype);

function splitTop(selector, separator) {
  const parts = [];
  let current = "";
  let quote = "";
  let depth = 0;
  for (const char of selector) {
    if (quote) {
      current += char;
      if (char === quote) quote = "";
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      current += char;
      continue;
    }
    if (char === "[") depth += 1;
    else if (char === "]" && depth > 0) depth -= 1;
    if (char === separator && depth === 0) {
      if (current.trim()) parts.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}
function matchSimple(node, selector) {
  if (!node || !node.tag || !selector) return false;
  let rest = selector;
  const tag = /^[a-zA-Z][a-zA-Z0-9-]*/.exec(rest);
  if (tag && !rest.startsWith(".") && !rest.startsWith("[")) {
    if (node.tag !== tag[0]) return false;
    rest = rest.slice(tag[0].length);
  }
  while (rest.length) {
    if (rest.startsWith(".")) {
      const name = /^[A-Za-z0-9_-]+/.exec(rest.slice(1));
      if (!name) return false;
      const classes = String(node.className || "").split(/\s+/);
      if (!classes.includes(name[0])) return false;
      rest = rest.slice(1 + name[0].length);
    } else if (rest.startsWith("[")) {
      const end = rest.indexOf("]");
      if (end < 0) return false;
      const quoted = rest.slice(1, end).match(/^([^=]+)="([^"]*)"$/);
      if (!quoted || node.attrs[quoted[1]] !== quoted[2]) return false;
      rest = rest.slice(end + 1);
    } else return false;
  }
  return true;
}
function descendants(node) {
  const found = [];
  for (const child of node.children || []) {
    if (!child || !child.tag) continue;
    found.push(child);
    found.push(...descendants(child));
  }
  return found;
}
function findAll(root, selector) {
  const found = [];
  for (const part of splitTop(selector, ",")) {
    if (part.startsWith(":scope >")) {
      const simple = part.slice(":scope >".length).trim();
      for (const child of root.children || []) {
        if (matchSimple(child, simple)) found.push(child);
      }
      continue;
    }
    let level = [root];
    for (const simple of splitTop(part, " ")) {
      const next = [];
      for (const node of level) {
        for (const candidate of descendants(node)) {
          if (matchSimple(candidate, simple)) next.push(candidate);
        }
      }
      level = next;
    }
    found.push(...level);
  }
  return found;
}

const pageRoot = new Element("html");
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
    documentElement: pageRoot,
    querySelector: (selector) => findAll(pageRoot, selector)[0] || null,
    querySelectorAll: (selector) => findAll(pageRoot, selector),
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
function nodeText(node) {
  if (!node) return "";
  if (!node.tag) return node.text || "";
  return (node.children || []).map(nodeText).join("");
}
function operatorAlert(chip) {
  const alert = chip.querySelector(".basis-alert");
  const field = chip.querySelector("textarea");
  const describedby = field && Object.hasOwn(field.attrs, "aria-describedby") ? field.attrs["aria-describedby"] : null;
  return {
    label: alert.attrs["aria-label"] || null,
    title: alert.attrs.title || null,
    hidden: alert.hidden === true,
    linked: describedby != null && describedby === alert.attrs.id,
    describedby,
  };
}
function toggleSite(chip, site, checked) {
  const kind = chip.className.split(" ").includes("lindblad") ? "Lindblad" : "Local";
  const box = chip.querySelector('[aria-label="' + kind + " qubit " + site + '"]');
  box.checked = checked;
  box.listeners.change[0]({ target: box });
}
function typeInto(node, value) {
  node.value = value;
  const listeners = node.listeners && node.listeners.input;
  if (!listeners || !listeners.length) throw new Error("missing input listener");
  listeners[0]({ target: node, currentTarget: node });
}
function labeled(root, label) {
  return walk(root, []).find((node) => node.tag === "input" && node.attrs["aria-label"] === label);
}
function chipByClass(root, kind) {
  return walk(root, []).find((node) => {
    const classes = node.className.split(" ");
    return classes.includes("chip") && classes.includes(kind);
  });
}
function openChip(root, kind) {
  const chip = chipByClass(root, kind);
  click(chip.children[0].children[0]);
  return chipByClass(root, kind);
}
function resultsNode() {
  const panel = document.querySelector('.panel[aria-label="Results"]');
  return panel.querySelector(":scope > .placeholder, :scope > .chart, :scope > .results");
}
function installChart() {
  const chart = document.createElement("div");
  chart.className = "chart";
  setResults(chart);
  shownRun = JSON.stringify(runRequest());
  return chart;
}
function showingPlaceholder() {
  const node = resultsNode();
  return node.className === "placeholder" && nodeText(node) === "Run a simulation to see results here.";
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
  cavityText = "1";
  hoppingText = "0";
  factoryText = {};
  modelTerms.splice(0, modelTerms.length);
  placedSims.splice(0, placedSims.length);
  placedThens.splice(0, placedThens.length);
  savePath = DEFAULT_SAVE_PATH;
  exportPath = DEFAULT_EXPORT_PATH;
  measureSites = null;
  countsExpression = "";
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
} else if (request.action === "counts") {
  fillCircuit();
  BLOCKS.measure = [{ id: "counts", title: "Counts", detail: "Expression on all qubits", phrase: "Counts" }];
  selection.measure = "counts";
  measureSites = null;
  const board = document.createElement("section");
  board.className = "board";
  document.documentElement.append(board);
  draw(board);
  openChip(board, "measure");
  const input = labeled(board, "Counts expression");
  const hint = () => {
    const node = walk(board, []).find((item) => item.className === "counts-hint");
    return node.textContent ?? nodeText(node);
  };
  const blankStatus = statusMessage();
  const blankHint = hint();
  const blankPlaceholder = input.attrs.placeholder;
  typeInto(input, ' counts["01"] / shots ');
  const typedStatus = statusMessage();
  const typedRequest = runRequest().expression;
  const box = labeled(board, "Qubit 1");
  box.listeners.change[0]({ target: { ...box, checked: false, closest: (s) => box.closest(s) } });
  const narrowStatus = statusMessage();
  const narrowHint = hint();
  const narrowPlaceholder = input.placeholder;
  const snap = boardSnapshot();
  emptyBoard();
  const cleared = countsExpression;
  applyBoard(snap);
  selection.measure = "z";
  result = {
    blankStatus,
    blankHint,
    blankPlaceholder,
    typedStatus,
    typedRequest,
    narrowStatus,
    narrowHint,
    narrowPlaceholder,
    stored: snap.countsExpression,
    cleared,
    restored: countsExpression,
    zRequest: Object.hasOwn(runRequest(), "expression"),
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
} else if (request.action === "inplace") {
  fillCircuit();
  const board = document.createElement("section");
  board.className = "board";
  document.documentElement.append(board);
  draw(board);
  const total = labeled(board, "Total time");
  let chart = installChart();
  openChip(board, "basis");
  const openKeepsChart = resultsNode() === chart;
  const openKeepsTotal = labeled(board, "Total time") === total;
  click(walk(chipByClass(board, "basis"), []).find((node) => node.className === "done"));
  const doneKeepsChart = resultsNode() === chart;
  const doneKeepsTotal = labeled(board, "Total time") === total;
  typeInto(total, "4");
  const totalClearsChart = showingPlaceholder();
  const totalKeepsInput = labeled(board, "Total time") === total;
  chart = installChart();
  openChip(board, "backend");
  const shots = labeled(board, "Shots");
  const shotsOpenKeepsChart = resultsNode() === chart;
  typeInto(shots, "128");
  const shotsClearsChart = showingPlaceholder();
  const shotsKeepsInput = labeled(board, "Shots") === shots;
  chart = installChart();
  place("then", "save");
  const placeClearsChart = showingPlaceholder();
  const placeKeepsTotal = labeled(board, "Total time") === total;
  const placedSave = placedThens.includes("save");
  chart = installChart();
  removeThen("save");
  const removeClearsChart = showingPlaceholder();
  const removedSave = !placedThens.includes("save");
  chart = installChart();
  attachBackend("aer");
  result = {
    openKeepsChart,
    openKeepsTotal,
    doneKeepsChart,
    doneKeepsTotal,
    totalClearsChart,
    totalKeepsInput,
    total: settings.total,
    shotsOpenKeepsChart,
    shotsClearsChart,
    shotsKeepsInput,
    shots: placedSims[0].shots,
    placeClearsChart,
    placeKeepsTotal,
    placedSave,
    removeClearsChart,
    removedSave,
    attachKeepsChart: resultsNode() === chart,
  };
} else if (request.action === "grid") {
  resetPage();
  BLOCKS.model = [{ id: "preexisting", title: "Preexisting model", detail: "Choose a built-in model" }];
  const board = document.createElement("section");
  board.className = "board";
  document.documentElement.append(board);
  draw(board);
  place("state", "basis");
  place("model", "preexisting");
  place("measure", "z");
  function cell(selector) {
    const node = board.querySelector(selector);
    return { column: node.style.gridColumn, row: node.style.gridRow };
  }
  result = {
    state: cell('.slot[data-slot="state"]'),
    model: cell('.slot[data-slot="model"]'),
    modelPalette: cell('.lane[data-palette="model"]'),
    measure: cell('.slot[data-slot="measure"]'),
    simulator: cell('.slot[data-slot="simulator"]'),
  };
} else if (request.action === "factory") {
  resetPage();
  BLOCKS.model = [{ id: "preexisting", title: "Preexisting model", detail: "Choose a built-in model" }];
  modelFactories = [{
    id: "ising",
    title: "Ising",
    qubits: true,
    setup: "model = ising(n_qubits={qubits})",
    params: [
      { name: "J", label: "J", kind: "number", default: "1" },
      { name: "h", label: "h", kind: "number", default: "0" },
      { name: "field", label: "field", kind: "choice", default: "transverse", choices: ["classical", "transverse"] },
      { name: "topology", label: "topology", kind: "choice", default: "chain", choices: ["chain"] },
      { name: "boundary", label: "boundary", kind: "choice", default: "open", choices: ["open", "periodic"] },
      { name: "edges", label: "edges", kind: "edges", default: "" },
    ],
  }];
  const board = document.createElement("section");
  board.className = "board";
  document.documentElement.append(board);
  draw(board);
  place("model", "preexisting");
  function control(label) {
    return board.querySelector('[aria-label="' + label + '"]');
  }
  function optionValue(select) {
    const option = (select.children || []).find((child) => child.attrs && Object.hasOwn(child.attrs, "selected"));
    return option ? option.attrs.value : null;
  }
  const defaults = {
    detail: nodeText(board.querySelector(".preexisting-detail")),
    J: control("J").attrs.value,
    h: control("h").attrs.value,
    field: optionValue(control("field")),
    topology: optionValue(control("topology")),
    boundary: optionValue(control("boundary")),
    edges: control("edges").attrs.value,
    alertHidden: Object.hasOwn(board.querySelector(".preexisting-alert").attrs, "hidden"),
  };
  typeInto(control("J"), "2");
  typeInto(control("edges"), "0-1, 1-2");
  const topologyLocked = control("topology").disabled === true;
  const boundaryLocked = control("boundary").disabled === true;
  typeInto(control("edges"), "");
  const boundary = control("boundary");
  boundary.value = "periodic";
  boundary.listeners.change[0]({ target: boundary, currentTarget: boundary });
  const edgesLocked = control("edges").disabled === true;
  const snap = boardSnapshot();
  factoryText = { J: "9", h: "4" };
  const applied = applyBoard(snap);
  const hParam = modelFactories[0].params.find((param) => param.name === "h");
  result = {
    defaults,
    topologyLocked,
    boundaryLocked,
    edgesLocked,
    applied,
    storedJ: snap.factoryText.J,
    storedEdges: snap.factoryText.edges,
    storedBoundary: snap.factoryText.boundary,
    storedH: Object.hasOwn(snap.factoryText, "h"),
    restoredJ: factoryText.J,
    restoredH: Object.hasOwn(factoryText, "h"),
    hDefault: paramText(hParam),
    request: runRequest().factory,
  };
} else if (request.action === "gates") {
  fillCircuit();
  BLOCKS.backend[0].setup = "circuit_backend = AerCircuitBackend(shots={shots}, basis_gates={basis_gates})";
  BLOCKS.backend[0].fields = [{
    name: "basis_gates",
    label: "Gates",
    default: "",
    allow_inf: false,
    kind: "gates",
    choices: ["cx", "h", "rx", "ry", "rz"],
  }];
  const board = document.createElement("section");
  board.className = "board";
  document.documentElement.append(board);
  draw(board);
  const chip = openChip(board, "backend");
  const gates = labeled(board, "Gates");
  const blankPreview = previewText();
  const blankStatus = statusMessage();
  typeInto(gates, "RX, ry, RX");
  const detail = chip.querySelector(".backend-detail");
  result = {
    shots: Boolean(labeled(board, "Shots")),
    blankPreview,
    blankStatus,
    typedPreview: previewText(),
    typedDetail: detail.textContent,
    typedValue: placedSims[0].backendFields.basis_gates,
    unknownStatus: (typeInto(gates, "foo"), statusMessage()),
    unknownPreview: previewText(),
    commaStatus: (typeInto(gates, ",,,"), statusMessage()),
  };
} else if (request.action === "operators") {
  resetPage();
  BLOCKS.model = [
    { id: "hamiltonian", title: "Hamiltonian", adds: true, detail: "" },
    { id: "local_hamiltonian", title: "Local Hamiltonian", adds: true, detail: "" },
    { id: "lindblad", title: "Lindblad", adds: true, detail: "" },
  ];
  selection.state = "basis";
  basisBits = "00";
  settings.qubits = "2";
  qubitsSource = "state";
  const board = document.createElement("section");
  board.className = "board";
  document.documentElement.append(board);
  draw(board);
  place("model", "hamiltonian");
  const matrix = board.querySelector(".chip.hamiltonian textarea");
  typeInto(matrix, "[[1, 1], [0, 1]]");
  const nonhermitian = operatorAlert(board.querySelector(".chip.hamiltonian"));
  typeInto(matrix, "[[1, 0], [0, -1]]");
  const wrongSize = operatorAlert(board.querySelector(".chip.hamiltonian"));
  basisBits = "0";
  syncStateQubits();
  typeInto(matrix, "[[1, 0], [0, -1]]");
  const validHamiltonian = operatorAlert(board.querySelector(".chip.hamiltonian"));
  basisBits = "000";
  syncStateQubits();
  place("model", "local_hamiltonian");
  place("model", "lindblad");
  const local = () => board.querySelector(".chip.local-hamiltonian");
  const lindblad = () => board.querySelector(".chip.lindblad");
  const emptyLocal = operatorAlert(local());
  toggleSite(local(), 0, true);
  toggleSite(local(), 2, true);
  toggleSite(lindblad(), 0, true);
  toggleSite(lindblad(), 2, true);
  const splitLocal = operatorAlert(local());
  const splitLindblad = operatorAlert(lindblad());
  toggleSite(local(), 2, false);
  typeInto(local().querySelector("textarea"), "[[1, 0], [0, -1]]");
  const validLocal = operatorAlert(local());
  result = { nonhermitian, wrongSize, validHamiltonian, emptyLocal, splitLocal, splitLindblad, validLocal };
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


def test_placed_blocks_keep_their_grid_cells() -> None:
    page = _call("grid")
    assert page["state"] == {"column": "1", "row": "1"}
    assert page["model"] == {"column": "3", "row": "1"}
    assert page["modelPalette"] == {"column": "3", "row": "2"}
    assert page["simulator"] == {"column": "5", "row": "1"}
    assert page["measure"] == {"column": "7", "row": "1"}


def test_factory_fields_keep_edits_and_fall_back_to_defaults() -> None:
    page = _call("factory")
    assert page["defaults"] == {
        "detail": "at least 2 qubits",
        "J": "1",
        "h": "0",
        "field": "transverse",
        "topology": "chain",
        "boundary": "open",
        "edges": "",
        "alertHidden": True,
    }
    assert page["topologyLocked"] is True
    assert page["boundaryLocked"] is True
    assert page["edgesLocked"] is True
    assert page["applied"] is True
    assert page["storedJ"] == "2"
    assert page["storedEdges"] == ""
    assert page["storedBoundary"] == "periodic"
    assert page["storedH"] is False
    assert page["restoredJ"] == "2"
    assert page["restoredH"] is False
    assert page["hDefault"] == "0"
    assert page["request"] == {
        "J": "2",
        "h": "0",
        "field": "transverse",
        "topology": "chain",
        "boundary": "periodic",
        "edges": "",
    }


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


def test_counts_chip_edits_the_expression() -> None:
    page = _call("counts")
    assert page["blankStatus"] == "Enter a counts expression."
    assert page["blankHint"] == "Keys list qubits 0, 1 in that order. shots is the total."
    assert page["blankPlaceholder"] == 'counts["00"] / shots'
    assert page["typedStatus"] == "Ready to run."
    assert page["typedRequest"] == 'counts["01"] / shots'
    assert page["narrowStatus"] == "Counts keys must be 1 characters of 0 and 1."
    assert page["narrowHint"] == "Keys list qubit 0 in that order. shots is the total."
    assert page["narrowPlaceholder"] == 'counts["0"] / shots'
    assert page["stored"] == ' counts["01"] / shots '
    assert page["cleared"] == ""
    assert page["restored"] == ' counts["01"] / shots '
    assert page["zRequest"] is False


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


def test_operator_alerts_name_the_current_problem() -> None:
    page = _call("operators")
    shown = {
        "nonhermitian": "Matrix must be Hermitian.",
        "wrongSize": "Must be 4\u00d74 for 2 qubits.",
        "emptyLocal": "Pick at least one qubit.",
        "splitLocal": "Qubits must be contiguous.",
        "splitLindblad": "Qubits must be contiguous.",
    }
    for key, label in shown.items():
        assert page[key]["label"] == label
        assert page[key]["title"] == label
        assert page[key]["hidden"] is False
        assert page[key]["linked"] is True
    for key in ("validHamiltonian", "validLocal"):
        assert page[key]["hidden"] is True
        assert page[key]["linked"] is False
        assert page[key]["describedby"] is None


def test_aer_card_edits_gates_beside_shots() -> None:
    page = _call("gates")
    assert page["shots"] is True
    assert page["blankStatus"] == "Ready to run."
    assert "basis_gates=None" in page["blankPreview"]
    assert page["typedValue"] == "rx, ry, rx"
    assert page["typedDetail"] == "256 shots, rx, ry"
    assert 'basis_gates=["rx", "ry"]' in page["typedPreview"]
    assert page["unknownStatus"] == "Unknown gate foo."
    assert page["unknownPreview"] == ""
    assert page["commaStatus"] == "Enter gate names separated by commas."


def test_edits_keep_the_chart_until_the_run_changes() -> None:
    page = _call("inplace")
    assert page["openKeepsChart"] is True
    assert page["openKeepsTotal"] is True
    assert page["doneKeepsChart"] is True
    assert page["doneKeepsTotal"] is True
    assert page["totalClearsChart"] is True
    assert page["totalKeepsInput"] is True
    assert page["total"] == "4"
    assert page["shotsOpenKeepsChart"] is True
    assert page["shotsClearsChart"] is True
    assert page["shotsKeepsInput"] is True
    assert page["shots"] == "128"
    assert page["placeClearsChart"] is True
    assert page["placeKeepsTotal"] is True
    assert page["placedSave"] is True
    assert page["removeClearsChart"] is True
    assert page["removedSave"] is True
    assert page["attachKeepsChart"] is True


def test_copy_writes_the_script_only_when_one_is_shown() -> None:
    page = _call("copy")
    assert page["emptyDisabled"] is True
    assert page["emptyWrites"] == 0
    assert page["fullDisabled"] is False
    assert page["write"] == page["preview"]
    assert "from shadowsim.encoding import ComputationalBasisEncoding" in page["write"]
    assert "import *" not in page["write"]
