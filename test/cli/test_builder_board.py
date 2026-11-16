"""Tests for restoring the builder board, copying its script, and updating it in place."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from shadowsim.cli.catalog import listed_actions, listed_measurements, listed_states
from shadowsim.cli.run import _page_limits

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
Element.prototype.click = function () {
  if (this.tag === "a") {
    downloads.push({ name: this.attrs.download || "", href: this.attrs.href || "" });
  }
  const listeners = this.listeners && this.listeners.click;
  if (!listeners) return;
  for (const fn of listeners) fn({ currentTarget: this, target: this, stopPropagation() {} });
};
Element.prototype.remove = function () {
  const parent = this.parentNode;
  if (!parent || !parent.children) return;
  const index = parent.children.indexOf(this);
  if (index >= 0) parent.children.splice(index, 1);
  this.parentNode = null;
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
const downloads = [];
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
sandbox.Promise = Promise;
sandbox.downloads = downloads;
sandbox.Blob = function Blob(parts, options) {
  this.parts = parts;
  this.type = options && options.type;
};
sandbox.URL = {
  createObjectURL(blob) {
    downloads.push({ text: String(blob.parts[0]), type: blob.type });
    return "blob:board";
  },
  revokeObjectURL() {},
};
sandbox.document.body = new Element("body");
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
  for (const key of Object.keys(stateText)) delete stateText[key];
  qubitsSource = null;
  preexistingId = null;
  factoryText = {};
  modelTerms.splice(0, modelTerms.length);
  placedSims.splice(0, placedSims.length);
  placedThens.splice(0, placedThens.length);
  for (const key of Object.keys(actionText)) delete actionText[key];
  for (const key of Object.keys(pathOpen)) delete pathOpen[key];
  for (const block of BLOCKS.then) {
    if (block.field && block.field.kind === "path") actionText[block.id] = block.field.default;
  }
  measureSites = null;
  for (const key of Object.keys(expressionText)) delete expressionText[key];
  stateOpen = false;
  measureOpen = false;
  preexistingOpen = false;
  boardReady = false;
}
function fillIsing() {
  resetPage();
  BLOCKS.simulator = [{
    id: "qutip",
    title: "QuTiP",
    observables: true,
    detail: "Reference",
    setup: [
      "{name} = QutipSimulator({hamiltonians}, {lindblads}, state,",
      "                    e_ops, num_qubits={qubits},",
      "                    total_time={total}, time_steps={time_steps})",
    ].join(String.fromCharCode(10)),
    fields: [{
      name: "time_steps",
      label: "Time steps",
      kind: "integer",
      default: "11",
      minimum: 1,
      maximum: limits.timeSteps,
    }],
  }];
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
  stateText.basis = "01";
  settings.qubits = "2";
  settings.total = "1";
  qubitsSource = "state";
  actionText.save = "results/kept";
  measureSites = [0];
  placedSims.push({ id: "qutip", key: 3, open: true, params: { time_steps: "11" } });
  placedThens.push("plot");
}
function fillCircuit() {
  fillIsing();
  BLOCKS.simulator = [{
    id: "trotterization",
    title: "Trotterization",
    observables: false,
    detail: "",
    setup: [
      "{name} = TrotterizationSimulator(",
      "    {hamiltonians},",
      "    {lindblads},",
      "    state,",
      "    num_qubits={qubits},",
      "    total_time={total},",
      "    time_steps={time_steps},",
      "    num_steps={num_steps},",
      "    trotter_depth={trotter_depth},",
      "    order={order},",
      "    seed={seed}{basis},",
      "    circuit_backend={backend},",
      ")",
    ].join(String.fromCharCode(10)),
    fields: [
      {
        name: "time_steps",
        label: "Time steps",
        kind: "integer",
        default: "11",
        minimum: 1,
        maximum: limits.timeSteps,
      },
      {
        name: "num_steps",
        label: "Product steps",
        kind: "integer",
        default: "4",
        minimum: 1,
        maximum: limits.numSteps,
      },
      {
        name: "trotter_depth",
        label: "Trotter depth",
        kind: "integer",
        default: "1",
        minimum: 1,
        maximum: limits.trotterDepth,
      },
      { name: "order", label: "Order", kind: "choice", default: "1", choices: ["1", "2"] },
      { name: "seed", label: "Seed", kind: "integer", default: "0" },
    ],
  }];
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
    params: { time_steps: "11", num_steps: "4", trotter_depth: "1", seed: "0", order: "1" },
    backend: "aer",
    shots: "256",
  });
}

const request = JSON.parse(process.argv[4]);
if (!applyLimits(request.limits)) throw new Error("missing limits");
BLOCKS.state = request.states;
BLOCKS.measure = request.measures;
BLOCKS.then = request.actions;
const surface = { replaceChildren() {} };
let result;
if (request.action === "roundtrip") {
  fillIsing();
  draw(surface);
  const storedEarly = localStorage.getItem("shadowsim.builder.board");
  boardReady = true;
  draw(surface);
  const storedBeforeAccept = localStorage.getItem("shadowsim.builder.board");
  const accepted = applyCheck();
  const stored = localStorage.getItem("shadowsim.builder.board");
  const body = JSON.stringify(runRequest());
  settings.total = "4";
  refreshSummaryAndPreview();
  const duringEdit = localStorage.getItem("shadowsim.builder.board");
  const checks = [];
  fetch = async (url, options) => {
    checks.push({
      url,
      method: options && options.method,
      contentType: options && options.headers && options.headers["Content-Type"],
      body: options && options.body,
    });
    return { ok: true, json: async () => ({ qubits: 2 }) };
  };
  resetPage();
  boardReady = true;
  result = (async () => {
    await restoreBoard();
    return {
      storedEarly,
      storedBeforeAccept,
      accepted,
      matches: stored === body,
      held: duringEdit === stored,
      document: stored ? JSON.parse(stored) : null,
      stored,
      checks,
      restored: JSON.stringify(runRequest()) === stored,
      state: selection.state,
      bits: stateText.basis || "",
    };
  })();
} else if (request.action === "broken") {
  result = (async () => {
    fillIsing();
    const before = selection.state;
    const checks = [];
    fetch = async (url, options) => {
      checks.push({ url, body: options && options.body });
      return { ok: false, json: async () => ({ error: "unknown version 2" }) };
    };
    localStorage.setItem("shadowsim.builder.board", "{");
    await restoreBoard();
    const malformed = {
      state: selection.state,
      stored: localStorage.getItem("shadowsim.builder.board"),
      checks: checks.length,
    };
    resetPage();
    const rejected = JSON.stringify({ version: 2 });
    localStorage.setItem("shadowsim.builder.board", rejected);
    await restoreBoard();
    return {
      before,
      malformed,
      status: statusHold,
      state: selection.state,
      bits: stateText.basis || "",
      stored: localStorage.getItem("shadowsim.builder.board"),
      check: checks[0],
    };
  })();
} else if (request.action === "unknown") {
  result = (async () => {
    fillCircuit();
    const before = JSON.stringify(runRequest());
    localStorage.setItem(
      "shadowsim.builder.board",
      JSON.stringify({ version: 1, simulators: [{ id: "missing" }] }),
    );
    fetch = async () => ({ ok: false, json: async () => ({ error: "unknown simulator missing" }) });
    await restoreBoard();
    return {
      state: selection.state,
      status: statusHold,
      unchanged: JSON.stringify(runRequest()) === before,
      stored: localStorage.getItem("shadowsim.builder.board"),
    };
  })();
} else if (request.action === "counts") {
  fillCircuit();
  BLOCKS.measure = request.measures.filter((block) => block.id === "counts");
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
  const typedRequest = runRequest().measure.expression;
  const box = labeled(board, "Qubit 1");
  box.listeners.change[0]({ target: { ...box, checked: false, closest: (s) => box.closest(s) } });
  const narrowStatus = statusMessage();
  const narrowHint = hint();
  const narrowPlaceholder = input.placeholder;
  const body = JSON.stringify(runRequest());
  emptyBoard();
  const cleared = expressionText.counts ?? "";
  result = (async () => {
    fetch = async () => ({ ok: true, json: async () => ({ qubits: 2 }) });
    localStorage.setItem("shadowsim.builder.board", body);
    await restoreBoard();
    const rebuilt = JSON.stringify(runRequest());
    selection.measure = "z";
    return {
      blankStatus,
      blankHint,
      blankPlaceholder,
      typedStatus,
      typedRequest,
      narrowStatus,
      narrowHint,
      narrowPlaceholder,
      stored: JSON.parse(body).measure.expression,
      cleared,
      restored: expressionText.counts ?? "",
      matches: rebuilt === body,
      zRequest: Object.hasOwn(runRequest().measure, "expression"),
    };
  })();
} else if (request.action === "launch") {
  result = (async () => {
    fillIsing();
    boardReady = true;
    applyCheck();
    const saved = localStorage.getItem("shadowsim.builder.board");
    resetPage();
    boardReady = true;
    fetch = async () => ({ ok: true, json: async () => ({ qubits: 2 }) });
    await restoreBoard();
    return {
      saved,
      stored: localStorage.getItem("shadowsim.builder.board"),
      state: selection.state,
      bits: stateText.basis || "",
      matches: JSON.stringify(runRequest()) === saved,
    };
  })();
} else if (request.action === "clear") {
  fillIsing();
  boardReady = true;
  applyCheck();
  const saved = localStorage.getItem("shadowsim.builder.board");
  running = true;
  emptyBoard();
  const kept = selection.state === "basis";
  const keptStored = localStorage.getItem("shadowsim.builder.board");
  running = false;
  document.querySelector = (selector) => (selector === ".board" ? surface : null);
  const button = walk(settingsComponent(), []).find((node) => node.className === "clear");
  click(button);
  result = {
    kept,
    saved,
    keptStored,
    state: selection.state,
    qubits: settings.qubits,
    bits: stateText.basis || "",
    sims: placedSims.length,
    terms: modelTerms.length,
    thens: placedThens.length,
    preexistingId,
    stored: localStorage.getItem("shadowsim.builder.board"),
  };
} else if (request.action === "copy") {
  resetPage();
  const empty = walk(panelsComponent(), []).find((node) => node.className === "copy");
  click(empty);
  const emptyWrites = writes.length;
  fillIsing();
  applyCheck();
  const full = walk(panelsComponent(), []).find((node) => node.className === "copy");
  click(full);
  result = {
    emptyDisabled: Object.hasOwn(empty.attrs, "disabled"),
    emptyWrites,
    fullDisabled: Object.hasOwn(full.attrs, "disabled"),
    write: writes[0] ?? null,
    preview: previewText(),
  };
} else if (request.action === "boardcopy") {
  resetPage();
  const board = document.createElement("section");
  board.className = "board";
  document.documentElement.append(board);
  draw(board);
  const panel = () => document.querySelector('.panel[aria-label="Code preview"]');
  const scriptButton = () => walk(panel(), []).find((node) => node.className === "copy");
  const boardButton = () => walk(panel(), []).find((node) => node.className === "copy-board");
  const shown = () => {
    const node = walk(panel(), []).find((item) => item.className === "board-json");
    return node.textContent ?? nodeText(node);
  };
  click(scriptButton());
  const emptyScriptWrites = writes.length;
  click(boardButton());
  const emptyWrite = writes[0] ?? null;
  const emptyShown = shown();
  const emptyDisabled = Object.hasOwn(scriptButton().attrs, "disabled");
  const emptyLabel = boardButton().attrs["aria-label"];
  fillIsing();
  applyCheck(2);
  const before = writes.length;
  click(boardButton());
  const acceptedWrite = writes[before] ?? null;
  result = {
    emptyDisabled,
    emptyScriptWrites,
    emptyWrite,
    emptyShown,
    emptyLabel,
    acceptedScriptDisabled: Object.hasOwn(scriptButton().attrs, "disabled"),
    acceptedWrite,
    acceptedShown: shown(),
    acceptedBody,
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
      {
        name: "topology",
        label: "topology",
        kind: "choice",
        default: "chain",
        choices: ["chain"],
        disables: ["edges"],
      },
      {
        name: "boundary",
        label: "boundary",
        kind: "choice",
        default: "open",
        choices: ["open", "periodic"],
        disables: ["edges"],
      },
      { name: "edges", label: "edges", kind: "edges", default: "", disables: ["topology", "boundary"] },
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
  const body = runRequest();
  factoryText = { J: "9", h: "4" };
  applyDocument(body);
  const hParam = modelFactories[0].params.find((param) => param.name === "h");
  result = {
    defaults,
    topologyLocked,
    boundaryLocked,
    edgesLocked,
    applied: true,
    storedJ: body.model.arguments.J,
    storedEdges: body.model.arguments.edges,
    storedBoundary: body.model.arguments.boundary,
    storedH: body.model.arguments.h,
    restoredJ: factoryText.J,
    restoredH: factoryText.h,
    hDefault: paramText(hParam),
    request: runRequest().model.arguments,
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
  applyCheck();
  const blankPreview = previewText();
  const blankStatus = statusMessage();
  typeInto(gates, "RX, ry, RX");
  applyCheck();
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
  stateText.basis = "00";
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
  stateText.basis = "0";
  syncStateQubits();
  typeInto(matrix, "[[1, 0], [0, -1]]");
  const validHamiltonian = operatorAlert(board.querySelector(".chip.hamiltonian"));
  stateText.basis = "000";
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
} else if (request.action === "files") {
  result = (async () => {
    fillIsing();
    boardReady = true;
    const board = document.createElement("section");
    board.className = "board";
    document.documentElement.append(board);
    draw(board);
    const exportButton = () => walk(board, []).find((node) => node.className === "board-file export-board");
    const earlyDisabled = Object.hasOwn(exportButton().attrs, "disabled");
    applyCheck(2);
    const file = JSON.stringify(runRequest());
    const enabled = Object.hasOwn(exportButton().attrs, "disabled");
    click(exportButton());
    const blob = downloads.find((item) => item.text != null);
    const link = downloads.find((item) => item.name != null);
    resetPage();
    fillIsing();
    settings.total = "9";
    draw(board);
    const kept = localStorage.getItem("shadowsim.builder.board");
    const keptState = selection.state;
    const keptTotal = settings.total;
    async function choose(text) {
      const input = document.querySelector(".board-file-input");
      input.files = [{ text: async () => text }];
      input.listeners.change[0]({ target: input });
      for (let step = 0; step < 8; step += 1) await Promise.resolve();
    }
    fetch = async () => ({ ok: false, json: async () => ({ error: "unknown version 2" }) });
    await choose("{");
    const malformed = {
      status: statusHold,
      state: selection.state,
      total: settings.total,
      stored: localStorage.getItem("shadowsim.builder.board") === kept,
    };
    await choose(JSON.stringify({ version: 2 }));
    const rejected = {
      status: statusHold,
      state: selection.state,
      total: settings.total,
      stored: localStorage.getItem("shadowsim.builder.board") === kept,
      present: localStorage.getItem("shadowsim.builder.board") != null,
    };
    let posted = null;
    fetch = async (_url, options) => {
      posted = options && options.body;
      return { ok: true, json: async () => ({ qubits: 2 }) };
    };
    await choose(file);
    const stored = localStorage.getItem("shadowsim.builder.board");
    return {
      earlyDisabled,
      enabled,
      file,
      text: blob && blob.text,
      type: blob && blob.type,
      name: link && link.name,
      posted: posted === file,
      restored: JSON.stringify(runRequest()) === file,
      state: selection.state,
      bits: stateText.basis || "",
      malformed,
      rejected,
      keptState,
      keptTotal,
      stored,
    };
  })();
} else {
  throw new Error("unknown action");
}
Promise.resolve(result).then((value) => {
  process.stdout.write(JSON.stringify(value));
}).catch((error) => {
  console.error(error);
  process.exit(1);
});
`;

vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), sandbox);
vm.runInContext(`${fs.readFileSync(process.argv[3], "utf8")}\n${probe}`, sandbox);
"""


def _call(action: str) -> dict[str, Any]:
    """Return the builder probe result for one board action.

    The probe is read from stdin. Passing it to ``node -e`` exceeds the
    Windows command-line length.
    """
    try:
        completed = subprocess.run(
            [
                "node",
                "-",
                str(CHECKS),
                str(BUILDER),
                json.dumps(
                    {
                        "action": action,
                        "limits": _page_limits(),
                        "states": listed_states(),
                        "measures": listed_measurements(),
                        "actions": listed_actions(),
                    }
                ),
            ],
            input=_HARNESS,
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
    assert page["storedH"] == "0"
    assert page["restoredJ"] == "2"
    assert page["restoredH"] == "0"
    assert page["hDefault"] == "0"
    assert page["request"] == {
        "J": "2",
        "h": "0",
        "field": "transverse",
        "topology": "chain",
        "boundary": "periodic",
        "edges": "",
        "n_qubits": "",
    }


def test_an_accepted_run_is_what_gets_stored() -> None:
    page = _call("roundtrip")
    assert page["storedEarly"] is None
    assert page["storedBeforeAccept"] is None
    assert page["accepted"] is True
    assert page["matches"] is True
    assert page["held"] is True
    document = page["document"]
    assert set(document) == {"version", "total", "state", "model", "simulators", "measure", "actions"}
    assert document["version"] == 1
    assert document["total"] == "1"
    assert document["state"] == {"id": "basis", "value": "01"}
    assert "server" not in document
    assert page["checks"] == [
        {
            "url": "/runs/check",
            "method": "POST",
            "contentType": "application/json",
            "body": page["stored"],
        }
    ]
    assert page["restored"] is True
    assert page["state"] == "basis"
    assert page["bits"] == "01"


def test_counts_chip_edits_the_expression() -> None:
    page = _call("counts")
    assert page["blankStatus"] == "Enter a counts expression."
    assert page["blankHint"] == "Keys list qubits 0, 1 in that order. shots is the total."
    assert page["blankPlaceholder"] == 'counts["00"] / shots'
    assert page["typedStatus"] == "Checking the selection."
    assert page["typedRequest"] == 'counts["01"] / shots'
    assert page["narrowStatus"] == "Counts keys must be 1 characters of 0 and 1."
    assert page["narrowHint"] == "Keys list qubit 0 in that order. shots is the total."
    assert page["narrowPlaceholder"] == 'counts["0"] / shots'
    assert page["stored"] == page["typedRequest"]
    assert page["cleared"] == ""
    assert page["restored"] == page["typedRequest"]
    assert page["matches"] is True
    assert page["zRequest"] is False


def test_a_new_server_keeps_the_saved_document() -> None:
    page = _call("launch")
    assert page["saved"] is not None
    assert page["stored"] == page["saved"]
    assert json.loads(page["stored"])["version"] == 1
    assert "server" not in json.loads(page["stored"])
    assert page["state"] == "basis"
    assert page["bits"] == "01"
    assert page["matches"] is True


def test_clear_empties_the_board() -> None:
    page = _call("clear")
    assert page["kept"] is True
    assert page["saved"] is not None
    assert page["keptStored"] == page["saved"]
    assert page["state"] is None
    assert page["qubits"] == ""
    assert page["bits"] == ""
    assert page["sims"] == 0
    assert page["terms"] == 0
    assert page["thens"] == 0
    assert page["preexistingId"] is None
    assert page["stored"] is None


def test_a_bad_saved_document_does_not_fill_the_board() -> None:
    page = _call("broken")
    assert page["before"] == "basis"
    assert page["malformed"] == {"state": "basis", "stored": None, "checks": 0}
    assert page["status"] == "unknown version 2"
    assert page["state"] is None
    assert page["bits"] == ""
    assert json.loads(page["stored"]) == {"version": 2}
    assert page["check"] == {"url": "/runs/check", "body": page["stored"]}


def test_a_rejected_check_leaves_the_board() -> None:
    page = _call("unknown")
    assert page["state"] == "basis"
    assert page["unchanged"] is True
    assert page["status"] == "unknown simulator missing"
    assert json.loads(page["stored"])["simulators"] == [{"id": "missing"}]


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


def test_copy_board_writes_the_document_while_the_script_is_empty() -> None:
    page = _call("boardcopy")
    assert page["emptyDisabled"] is True
    assert page["emptyScriptWrites"] == 0
    assert page["emptyLabel"] == "Copy board"
    assert page["emptyWrite"] == page["emptyShown"]
    empty = json.loads(page["emptyWrite"])
    assert empty["version"] == 1
    assert "server" not in empty
    assert page["acceptedScriptDisabled"] is False
    assert page["acceptedWrite"] == page["acceptedShown"]
    assert page["acceptedWrite"] == page["acceptedBody"]
    accepted = json.loads(page["acceptedWrite"])
    assert "server" not in accepted
    assert accepted["state"] == {"id": "basis", "value": "01"}


def test_export_and_import_round_trip_the_board() -> None:
    page = _call("files")
    assert page["earlyDisabled"] is True
    assert page["enabled"] is False
    assert page["text"] == page["file"]
    assert page["type"] == "application/json"
    assert page["name"] == "shadowsim-board.json"
    assert page["posted"] is True
    assert page["restored"] is True
    assert page["state"] == "basis"
    assert page["bits"] == "01"
    assert json.loads(page["file"])["total"] == "1"
    assert page["keptState"] == "basis"
    assert page["keptTotal"] == "9"
    assert page["malformed"] == {
        "status": "The selection was rejected.",
        "state": "basis",
        "total": "9",
        "stored": True,
    }
    assert page["rejected"] == {
        "status": "unknown version 2",
        "state": "basis",
        "total": "9",
        "stored": True,
        "present": True,
    }
    stored = json.loads(page["stored"])
    assert page["stored"] == page["file"]
    assert stored["version"] == 1
    assert "server" not in stored
    assert stored["state"] == {"id": "basis", "value": "01"}
    assert stored["total"] == "1"
