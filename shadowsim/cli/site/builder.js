/* Builder page. Model, method, and backend cards come from the package. */

const LANES = [
  {
    id: "state",
    title: "Initial state",
    hint: "How the system starts",
    pick: "Pick an initial state",
    tone: "gold",
  },
  {
    id: "model",
    title: "Model",
    hint: "A preexisting model, or operators you add",
    pick: "Pick a model",
    tone: "teal",
  },
  {
    id: "simulator",
    title: "Method",
    hint: "The first row is the reference",
    pick: "Build a method",
    tone: "blue",
  },
  {
    id: "measure",
    title: "Measure",
    hint: "What to record",
    pick: "Pick a measurement",
    tone: "green",
  },
  {
    id: "then",
    title: "Then",
    hint: "What to do with the results",
    pick: "Add an action",
    tone: "rose",
  },
];

const BLOCKS = {
  state: [
    { id: "basis", title: "Basis state", detail: "Bit string of 0 and 1", phrase: "Basis state" },
    { id: "gray", title: "Gray code", detail: "Gray-coded bit string", phrase: "Gray code" },
    { id: "angle", title: "Angle", detail: "Rotation angles per qubit", phrase: "Angle" },
    { id: "amplitude", title: "Amplitude", detail: "Custom amplitudes, auto-padded", phrase: "Amplitude" },
  ],
  model: [],
  simulator: [],
  backend: [],
  measure: [
    { id: "z", title: "Z expectation", detail: "On each qubit", phrase: "Z expectation on each qubit" },
    { id: "x", title: "X expectation", detail: "On each qubit", phrase: "X expectation on each qubit" },
    { id: "counts", title: "Counts", detail: "Expression on all qubits", phrase: "Counts on all qubits" },
  ],
  then: [
    { id: "plot", title: "Plot results", detail: "Curves for each observable", phrase: "plot results" },
    {
      id: "save",
      title: "Save results",
      detail: "Write arrays and metadata to disk",
      phrase: "save results",
    },
    {
      id: "export",
      title: "Export metrics",
      detail: "Runtime and shot budget as JSON",
      phrase: "export metrics",
    },
  ],
};

const STATE_LIMITS = { basis: 15, gray: 15, angle: 15, amplitude: 16 };

const selection = {
  state: null,
  model: null,
  simulator: null,
  backend: null,
  measure: null,
  then: null,
};

const modelTerms = [];
let modelTermKey = 0;
let modelFactories = [];
let preexistingId = null;
let preexistingOpen = false;
let emitterText = "1";
let cavityText = "1";
let hoppingText = "0";
let factoryText = {};
const MAX_EMITTERS = 13;
const MAX_OPERATOR_QUBITS = 8;

const settings = { qubits: "", total: "" };
let basisBits = "";
let grayBits = "";
let angleText = "";
let amplitudeText = "";
let qubitsSource = null;
const placedSims = [];
let simKey = 0;
const placedThens = [];
const DEFAULT_SAVE_PATH = "results/run1";
let savePath = DEFAULT_SAVE_PATH;
let saveOpen = false;
const DEFAULT_EXPORT_PATH = "results";
let exportPath = DEFAULT_EXPORT_PATH;
let exportOpen = false;
let stateOpen = false;
let measureOpen = false;
let measureSites = null;
let countsExpression = "";
const DEFAULT_SHOTS = "256";

let dragging = null;
let running = false;
const BOARD_KEY = "shadowsim.builder.board";
const BOARD_VERSION = 1;
let boardReady = false;
let serverSession = null;
let copyTimer = 0;
let statusHold = null;
let runStartedAt = 0;
let runTimer = null;
let shownRun = null;
const laneNotes = { model: "", simulator: "", backend: "" };

const CURVE_COLORS = ["#4c4cb8", "#1f7a6c", "#a67c1a", "#b66880", "#6a4ca8"];

function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value == null || value === false) continue;
    if (key === "className") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function currentPage() {
  return {
    lanes: LANES,
    blocks: BLOCKS,
    selection,
    settings,
    modelTerms,
    modelFactories,
    preexistingId,
    emitterText,
    cavityText,
    hoppingText,
    factoryText,
    basisBits,
    grayBits,
    angleText,
    amplitudeText,
    placedSims,
    placedThens,
    savePath,
    exportPath,
    measureSites,
    countsExpression,
    qubitsSource,
    stateLimits: STATE_LIMITS,
    maxEmitters: MAX_EMITTERS,
    maxOperatorQubits: MAX_OPERATOR_QUBITS,
  };
}

function check(fn, ...args) {
  return fn(currentPage(), ...args);
}

function blockById(laneId, blockId) {
  return check(checks.blockById, laneId, blockId);
}

function chosenFactory() {
  return check(checks.chosenFactory);
}

function operatorStatus(preview) {
  return check(checks.operatorStatus, preview);
}

function isReference(entry) {
  return check(checks.isReference, entry);
}

function backendFits(entry, backendId) {
  return check(checks.backendFits, entry, backendId);
}

function socketStatus(preview) {
  return check(checks.socketStatus, preview);
}

function isComplete() {
  return check(checks.isComplete);
}

function formatSetting(key) {
  return check(checks.formatSetting, key);
}

function qubitPhrase() {
  return check(checks.qubitPhrase);
}

function stateOwnsQubits() {
  return check(checks.stateOwnsQubits);
}

function numberList(raw, maxCount) {
  return check(checks.numberList, raw, maxCount);
}

function amplitudeQubits(count) {
  return check(checks.amplitudeQubits, count);
}

function emitterCount() {
  return check(checks.emitterCount);
}

function cavityCount() {
  return check(checks.cavityCount);
}

function hoppingValue() {
  return check(checks.hoppingValue);
}

function factoryAlert() {
  return check(checks.factoryAlert);
}

function hubbardSelected() {
  return check(checks.hubbardSelected);
}

function jaynesHubbardSelected() {
  return check(checks.jaynesHubbardSelected);
}

function usesEmitterCount() {
  return check(checks.usesEmitterCount);
}

function cavityModelSelected() {
  return check(checks.cavityModelSelected);
}

function fixedFactoryQubits() {
  return check(checks.fixedFactoryQubits);
}

function emitterProblem() {
  return check(checks.emitterProblem);
}

function stateImpliedQubits() {
  return check(checks.stateImpliedQubits);
}

function stateSizeProblem() {
  return check(checks.stateSizeProblem);
}

function stateSizeStatus(preview) {
  return check(checks.stateSizeStatus, preview);
}

function stateInputProblem() {
  return check(checks.stateInputProblem);
}

function positiveIntText(value) {
  return check(checks.positiveIntText, value);
}

function freshParams(id) {
  if (id === "qutip") return { timeSteps: "101" };
  const params = { timeSteps: "11", numSteps: "4", trotterDepth: "1", seed: "0", order: "1" };
  return params;
}

function simParamsReady() {
  return check(checks.simParamsReady);
}

function sameTimeGrid() {
  return check(checks.sameTimeGrid);
}

function missingPaths() {
  return check(checks.missingPaths);
}

function savePathReady() {
  return check(checks.savePathReady);
}

function qubitCount() {
  return check(checks.qubitCount);
}

function selectedSites(count) {
  return check(checks.selectedSites, count);
}

function shotsReady() {
  return check(checks.shotsReady);
}

function measureSitesReady() {
  return check(checks.measureSitesReady);
}

function countsStatus(preview) {
  return check(checks.countsStatus, preview);
}

function numberProblem(preview) {
  return check(checks.numberProblem, preview);
}

function settingsReady() {
  return check(checks.settingsReady);
}

function runAllowed() {
  return check(checks.runAllowed);
}

function postedTerms() {
  return check(checks.postedTerms);
}

function entryBody(entry) {
  return check(checks.entryBody, entry);
}

function previewText() {
  return check(checks.previewText);
}

function modelChoiceBlocked(block) {
  if (!block) return false;
  if (block.id === "preexisting") return modelTerms.length > 0;
  if (block.adds) return selection.model === "preexisting";
  return false;
}

function blockCard(lane, block, { inSlot, onPlace, onRemove, blocked }) {
  if (inSlot) {
    return el(
      "div",
      { className: `chip tone-${lane.tone}` },
      el("div", {}, el("strong", {}, block.title), el("span", {}, block.detail)),
      el(
        "button",
        {
          className: "remove",
          type: "button",
          "aria-label": `Remove ${block.title}`,
          onclick: (event) => {
            event.stopPropagation();
            onRemove();
          },
        },
        "×",
      ),
    );
  }

  const card = el(
    "button",
    {
      className: `block tone-${lane.tone}`,
      type: "button",
      draggable: blocked ? "false" : "true",
      disabled: Boolean(blocked),
      "data-lane": lane.id,
      "data-block": block.id,
      ondragstart: (event) => {
        if (blocked) {
          event.preventDefault();
          return;
        }
        dragging = { lane: lane.id, id: block.id };
        event.dataTransfer.setData("text/plain", `${lane.id}:${block.id}`);
        event.dataTransfer.effectAllowed = "copy";
      },
      ondragend: () => {
        dragging = null;
      },
      onclick: () => {
        if (!blocked) onPlace();
      },
    },
    el("div", {}, el("strong", {}, block.title), el("span", {}, block.detail)),
  );
  return card;
}

function preexistingDetail() {
  if (preexistingId === "jaynes_cummings") return "3 qubits";
  if (jaynesHubbardSelected()) {
    const qubits = fixedFactoryQubits();
    if (qubits == null) return "Set cavities and hopping";
    const cavities = cavityCount();
    const cavityLabel = cavities === 1 ? "1 cavity" : `${cavities} cavities`;
    return `${cavityLabel}, ${qubits} qubits`;
  }
  if (preexistingId === "tavis_cummings") {
    const count = emitterCount();
    if (count == null) return "Set the emitter count";
    const qubits = 2 + count;
    return count === 1 ? `1 emitter, ${qubits} qubits` : `${count} emitters, ${qubits} qubits`;
  }
  if (hubbardSelected()) {
    const qubits = fixedFactoryQubits();
    if (qubits == null) return "Set cavities, emitters, and hopping";
    const cavities = cavityCount();
    const emitters = emitterCount();
    const cavityLabel = cavities === 1 ? "1 cavity" : `${cavities} cavities`;
    const emitterLabel = emitters === 1 ? "1 emitter" : `${emitters} emitters`;
    return `${cavityLabel}, ${emitterLabel}, ${qubits} qubits`;
  }
  if (preexistingId === "ising") return "at least 2 qubits";
  return chosenFactory()?.title ?? "";
}

function factoryParams() {
  const params = chosenFactory()?.params;
  return Array.isArray(params) ? params : [];
}

function paramText(param) {
  const stored = factoryText[param.name];
  return typeof stored === "string" ? stored : String(param.default ?? "");
}

function movedFromDefault(name) {
  const param = factoryParams().find((item) => item.name === name);
  return Boolean(param) && paramText(param) !== String(param.default ?? "");
}

function edgesFilled() {
  const param = factoryParams().find((item) => item.name === "edges");
  return Boolean(param) && paramText(param).trim() !== "";
}

function fieldLocked(param) {
  if (param.name === "edges") return movedFromDefault("topology") || movedFromDefault("boundary");
  if (param.name === "topology" || param.name === "boundary") return edgesFilled();
  return false;
}

function refreshFactoryLocks(chip) {
  if (!chip) return;
  const filled = edgesFilled();
  const moved = movedFromDefault("topology") || movedFromDefault("boundary");
  const edges = chip.querySelector('[aria-label="edges"]');
  const topology = chip.querySelector('[aria-label="topology"]');
  const boundary = chip.querySelector('[aria-label="boundary"]');
  if (edges) edges.disabled = moved;
  if (topology) topology.disabled = filled;
  if (boundary) boundary.disabled = filled;
}

function rememberFactoryText(name, value) {
  factoryText[name] = value;
}

function factoryField(param) {
  const value = paramText(param);
  const locked = fieldLocked(param);
  if (param.kind === "choice") {
    return el(
      "label",
      { className: "preexisting-field" },
      param.label,
      el(
        "select",
        {
          "aria-label": param.label,
          disabled: locked || null,
          onchange: (event) => {
            rememberFactoryText(param.name, event.target.value);
            refreshFactoryLocks(event.target.closest(".chip"));
            refreshCavityModel();
          },
        },
        ...(Array.isArray(param.choices) ? param.choices : []).map((choice) =>
          el("option", { value: choice, selected: choice === value }, choice),
        ),
      ),
    );
  }
  const numeric = param.kind === "number" || param.kind === "number_or_list";
  return el(
    "label",
    { className: "preexisting-field" },
    param.label,
    el("input", {
      type: "text",
      inputmode: numeric ? "decimal" : "text",
      "aria-label": param.label,
      value,
      disabled: locked || null,
      spellcheck: "false",
      autocomplete: "off",
      oninput: (event) => {
        rememberFactoryText(param.name, event.target.value.trim());
        refreshFactoryLocks(event.target.closest(".chip"));
        refreshCavityModel();
      },
    }),
  );
}

function postedFactory() {
  if (selection.model !== "preexisting") return null;
  const params = factoryParams();
  if (!params.length) return null;
  const body = {};
  for (const param of params) body[param.name] = paramText(param);
  return body;
}

function refreshCavityModel() {
  syncModelQubits();
  const detail = document.querySelector(".preexisting-detail");
  if (detail) detail.textContent = preexistingDetail();
  const alert = document.querySelector(".preexisting-alert");
  if (alert) {
    alert.hidden = !emitterProblem();
    const text = factoryAlert();
    if (text) {
      alert.setAttribute("aria-label", text);
      alert.title = text;
    }
  }
  if (selection.state) refreshStateChip(selection.state);
  else refreshSummaryAndPreview();
}

function replaceChip(node, next) {
  node.closest(".chip").replaceWith(next);
}

function preexistingChip() {
  const factory = chosenFactory();
  const select = el(
    "select",
    {
      "aria-label": "Model",
      onchange: (event) => {
        preexistingId = event.target.value;
        syncModelQubits();
        releaseStatusHold();
        commitLane("model", true);
      },
    },
    ...modelFactories.map((item) =>
      el("option", { value: item.id, selected: item.id === factory?.id }, item.title),
    ),
  );
  const emitters = el("input", {
    type: "text",
    inputmode: "numeric",
    "aria-label": "Emitters",
    value: emitterText,
    spellcheck: "false",
    autocomplete: "off",
    oninput: (event) => {
      const next = event.target.value.replace(/\D/g, "");
      if (event.target.value !== next) event.target.value = next;
      emitterText = next;
      refreshCavityModel();
    },
  });
  const cavities = el("input", {
    type: "text",
    inputmode: "numeric",
    "aria-label": "Cavities",
    value: cavityText,
    spellcheck: "false",
    autocomplete: "off",
    oninput: (event) => {
      const next = event.target.value.replace(/\D/g, "");
      if (event.target.value !== next) event.target.value = next;
      cavityText = next;
      refreshCavityModel();
    },
  });
  const hopping = el("input", {
    type: "text",
    inputmode: "decimal",
    "aria-label": "Hopping",
    value: hoppingText,
    spellcheck: "false",
    autocomplete: "off",
    oninput: (event) => {
      hoppingText = event.target.value.trim();
      refreshCavityModel();
    },
  });
  const alertText = factoryAlert() ?? "Check the model arguments";
  return el(
    "div",
    { className: `chip tone-teal preexisting${preexistingOpen ? " is-editing" : ""}` },
    el(
      "div",
      { className: "preexisting-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (preexistingOpen) return;
            preexistingOpen = true;
            replaceChip(event.currentTarget, preexistingChip());
          },
        },
        el("strong", {}, "Preexisting model"),
        el("span", { className: "preexisting-detail" }, preexistingDetail()),
      ),
      el(
        "div",
        { className: "preexisting-actions" },
        el(
          "span",
          {
            className: "basis-alert preexisting-alert",
            role: "img",
            "aria-label": alertText,
            title: alertText,
            hidden: !emitterProblem(),
          },
          "!",
        ),
        preexistingOpen
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  preexistingOpen = false;
                  replaceChip(event.currentTarget, preexistingChip());
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": "Remove Preexisting model",
            onclick: (event) => {
              event.stopPropagation();
              clearLane("model");
            },
          },
          "×",
        ),
      ),
    ),
    preexistingOpen ? el("label", { className: "preexisting-field" }, "Model", select) : null,
    preexistingOpen && (hubbardSelected() || jaynesHubbardSelected())
      ? el("label", { className: "preexisting-field" }, "Cavities", cavities)
      : null,
    preexistingOpen && usesEmitterCount()
      ? el("label", { className: "preexisting-field" }, "Emitters", emitters)
      : null,
    preexistingOpen && (hubbardSelected() || jaynesHubbardSelected())
      ? el("label", { className: "preexisting-field" }, "Hopping", hopping)
      : null,
    ...(preexistingOpen ? factoryParams().map(factoryField) : []),
  );
}

function grayPrepared(bits) {
  let index = 0;
  for (const bit of bits) index = (index << 1) | (bit === "1" ? 1 : 0);
  return (index ^ (index >>> 1)).toString(2).padStart(bits.length, "0");
}

function stateDetail(id) {
  if (id === "basis") return basisBits ? `Start in |${basisBits}>` : "0s and 1s, up to 15";
  if (id === "gray") return grayBits ? `Start in |${grayPrepared(grayBits)}>` : "0s and 1s, up to 15";
  if (id === "angle") {
    const values = numberList(angleText, STATE_LIMITS.angle);
    if (!values) return "Radians, one per qubit";
    return values.length === 1 ? "1 angle" : `${values.length} angles`;
  }
  const values = numberList(amplitudeText, STATE_LIMITS.amplitude);
  if (!values || values.every((value) => value === 0)) return "Up to 16 numbers";
  const qubits = amplitudeQubits(values.length);
  return qubits === 1 ? "1 qubit" : `${qubits} qubits`;
}

function stateReady(id) {
  if (id === "basis") return basisBits !== "";
  if (id === "gray") return grayBits !== "";
  if (id === "angle") return numberList(angleText, STATE_LIMITS.angle) != null;
  const values = numberList(amplitudeText, STATE_LIMITS.amplitude);
  return Boolean(values && values.some((value) => value !== 0));
}

function writeQubitField() {
  const qubitsInput = document.querySelector('input[aria-label="Qubits"]');
  if (!qubitsInput) return;
  qubitsInput.readOnly = stateOwnsQubits() || cavityModelSelected();
  if (qubitsInput.value !== settings.qubits) qubitsInput.value = settings.qubits;
}

function syncStateQubits() {
  if (!stateOwnsQubits() || cavityModelSelected()) return;
  const count = stateImpliedQubits();
  settings.qubits = count == null ? "" : String(count);
  qubitsSource = count == null ? null : "state";
  syncMeasureChip();
  writeQubitField();
}

function syncModelQubits() {
  if (!cavityModelSelected()) {
    if (qubitsSource !== "model") return;
    if (stateOwnsQubits()) {
      qubitsSource = null;
      syncStateQubits();
    } else {
      qubitsSource = settings.qubits === "" ? null : "user";
      writeQubitField();
    }
    return;
  }
  const fixed = fixedFactoryQubits();
  settings.qubits = fixed == null ? "" : String(fixed);
  qubitsSource = "model";
  syncMeasureChip();
  writeQubitField();
}

function stateAlertLabel(id) {
  const expected = stateSizeProblem();
  if (expected != null) {
    if (id === "basis" || id === "gray") return `Must be ${expected} bits.`;
    if (id === "angle") return `Must be ${expected} angles.`;
    return `Must prepare ${expected} qubits.`;
  }
  if (id === "angle") return "Enter one angle per qubit";
  if (id === "amplitude") return "Enter a non-zero amplitude list";
  return "Enter a bit string";
}

function refreshStateChip(id) {
  if (selection.state === id) syncStateQubits();
  const detail = document.querySelector(".basis-detail");
  if (detail) detail.textContent = stateDetail(id);
  const alert = document.querySelector(".chip.tone-gold .basis-alert");
  if (alert) {
    const label = stateAlertLabel(id);
    alert.hidden = stateReady(id) && stateSizeProblem() == null;
    alert.title = label;
    alert.setAttribute("aria-label", label);
  }
  refreshHamiltonianChips();
  refreshLocalHamiltonianChips();
  refreshSummaryAndPreview();
}

function stateChip(options) {
  const open = stateOpen;
  const input = el("input", {
    type: "text",
    inputmode: options.bits ? "numeric" : "decimal",
    ...(options.bits ? { maxlength: "15" } : {}),
    "aria-label": options.aria,
    value: options.value,
    spellcheck: "false",
    autocomplete: "off",
    oninput: options.oninput,
  });
  return el(
    "div",
    { className: `chip tone-gold ${options.id}${open ? " is-editing" : ""}` },
    el(
      "div",
      { className: "basis-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (stateOpen) return;
            stateOpen = true;
            replaceChip(event.currentTarget, stateChip(options));
          },
        },
        el("strong", {}, options.title),
        el("span", { className: "basis-detail" }, stateDetail(options.id)),
      ),
      el(
        "div",
        { className: "basis-actions" },
        el(
          "span",
          {
            className: "basis-alert",
            role: "img",
            "aria-label": stateAlertLabel(options.id),
            title: stateAlertLabel(options.id),
            hidden: stateReady(options.id) && stateSizeProblem() == null,
          },
          "!",
        ),
        open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  stateOpen = false;
                  replaceChip(event.currentTarget, stateChip(options));
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${options.title}`,
            onclick: (event) => {
              event.stopPropagation();
              clearLane("state");
            },
          },
          "×",
        ),
      ),
    ),
    open ? el("label", { className: "basis-field" }, options.field, input) : null,
  );
}

function basisChip() {
  return stateChip({
    id: "basis",
    title: "Basis state",
    field: "Bits",
    aria: "Basis bits",
    alertLabel: "Enter a bit string",
    bits: true,
    value: basisBits,
    oninput: (event) => {
      const next = event.target.value.replace(/[^01]/g, "").slice(0, 15);
      if (event.target.value !== next) event.target.value = next;
      basisBits = next;
      refreshStateChip("basis");
    },
  });
}

function grayChip() {
  return stateChip({
    id: "gray",
    title: "Gray code",
    field: "Bits",
    aria: "Gray bits",
    alertLabel: "Enter a bit string",
    bits: true,
    value: grayBits,
    oninput: (event) => {
      const next = event.target.value.replace(/[^01]/g, "").slice(0, 15);
      if (event.target.value !== next) event.target.value = next;
      grayBits = next;
      refreshStateChip("gray");
    },
  });
}

function numberChip(id, title, field, aria, alertLabel, read, write) {
  return stateChip({
    id,
    title,
    field,
    aria,
    alertLabel,
    value: read(),
    oninput: (event) => {
      const next = event.target.value.replace(/[^\d.,\s-]/g, "");
      if (event.target.value !== next) event.target.value = next;
      write(next);
      refreshStateChip(id);
    },
  });
}

function simField(params, key, label, seed) {
  return el(
    "label",
    {},
    label,
    el("input", {
      type: "text",
      inputmode: seed ? "text" : "numeric",
      "aria-label": label,
      value: params[key],
      spellcheck: "false",
      oninput: (event) => {
        const next = seed
          ? event.target.value.replace(/[^\d-]/g, "").replace(/(?!^)-/g, "")
          : event.target.value.replace(/\D/g, "");
        if (event.target.value !== next) event.target.value = next;
        params[key] = next;
        refreshSummaryAndPreview();
      },
    }),
  );
}

function simulatorChip(entry) {
  const block = blockById("simulator", entry.id);
  const params = entry.params;
  if (!block) return null;
  const fields = [
    simField(params, "timeSteps", "Time steps", false),
  ];
  if (!isReference(entry)) {
    fields.push(
      simField(params, "numSteps", "Product steps", false),
      simField(params, "trotterDepth", "Trotter depth", false),
      simField(params, "seed", "Seed", true),
      el(
        "label",
        {},
        "Order",
        el(
          "select",
          {
            "aria-label": "Order",
            onchange: (event) => {
              params.order = event.target.value;
              refreshSummaryAndPreview();
            },
          },
          el("option", { value: "1", selected: params.order === "1" }, "1"),
          el("option", { value: "2", selected: params.order === "2" }, "2"),
        ),
      ),
    );
  }
  return el(
    "div",
    { className: `chip tone-blue simulator${entry.open ? " is-editing" : ""}` },
    el(
      "div",
      { className: "simulator-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (entry.open) return;
            entry.open = true;
            replaceChip(event.currentTarget, simulatorChip(entry));
          },
        },
        el("strong", {}, block.title),
        el("span", {}, block.detail),
      ),
      el(
        "div",
        { className: "simulator-actions" },
        entry.open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  entry.open = false;
                  replaceChip(event.currentTarget, simulatorChip(entry));
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${block.title}`,
            onclick: (event) => {
              event.stopPropagation();
              removeSimulator(entry.key);
            },
          },
          "×",
        ),
      ),
    ),
    entry.open ? el("div", { className: "sim-fields" }, ...fields) : null,
  );
}

function pathChip(block, options) {
  const shown = options.path.trim();
  const refresh = (event) => {
    const next = options.kind === "save" ? saveChip(block) : exportChip(block);
    replaceChip(event.currentTarget, next);
  };
  return el(
    "div",
    { className: `chip tone-rose ${options.kind}${options.open ? " is-editing" : ""}` },
    el(
      "div",
      { className: `${options.kind}-head` },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (options.open) return;
            options.setOpen(true);
            refresh(event);
          },
        },
        el("strong", {}, block.title),
        el("span", {}, shown || block.detail),
      ),
      el(
        "div",
        { className: `${options.kind}-actions` },
        options.open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  options.setOpen(false);
                  refresh(event);
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${block.title}`,
            onclick: (event) => {
              event.stopPropagation();
              options.onRemove();
            },
          },
          "×",
        ),
      ),
    ),
    options.open
      ? el(
          "label",
          { className: `${options.kind}-field` },
          "Path",
          el("input", {
            type: "text",
            "aria-label": options.aria,
            value: options.path,
            spellcheck: "false",
            oninput: (event) => {
              options.setPath(event.target.value);
              const detail = event.target.closest(".chip")?.querySelector("span");
              if (detail) detail.textContent = event.target.value.trim() || block.detail;
              refreshSummaryAndPreview();
            },
          }),
        )
      : null,
  );
}

function saveChip(block) {
  return pathChip(block, {
    kind: "save",
    open: saveOpen,
    path: savePath,
    aria: "Save path",
    setOpen: (open) => {
      saveOpen = open;
    },
    setPath: (value) => {
      savePath = value;
    },
    onRemove: () => removeThen("save"),
  });
}

function exportChip(block) {
  return pathChip(block, {
    kind: "export",
    open: exportOpen,
    path: exportPath,
    aria: "Export path",
    setOpen: (open) => {
      exportOpen = open;
    },
    setPath: (value) => {
      exportPath = value;
    },
    onRemove: () => removeThen("export"),
  });
}

function backendFieldNumber(field, text) {
  return check(checks.backendFieldNumber, field, text);
}

function gateSummary(field, text) {
  if (check(checks.gateFieldProblem, field, text)) return "";
  const names = check(checks.gateNames, text);
  return names.length ? names.join(", ") : "";
}

function backendSummary(block, entry) {
  const parts = [];
  if (block.shots) {
    const shotText = String(entry.shots ?? "").trim();
    if (!positiveIntText(shotText)) return block.detail;
    parts.push(`${shotText} shots`);
  }
  for (const field of block.fields ?? []) {
    const text = String(entry.backendFields?.[field.name] ?? "").trim();
    if (field.kind === "gates") {
      const gates = gateSummary(field, text);
      if (gates) parts.push(gates);
      continue;
    }
    if (backendFieldNumber(field, text) == null) return block.detail;
    parts.push(`${field.label} ${text}`);
  }
  return parts.length ? parts.join(", ") : block.detail;
}

function backendChip(entry) {
  const block = blockById("backend", entry.backend);
  if (!block) return null;
  const fields = block.fields ?? [];
  const samples = Boolean(block.shots);
  const configurable = samples || fields.length > 0;
  const editing = samples ? Boolean(entry.shotsOpen) : Boolean(entry.backendOpen) && fields.length > 0;
  const shown = backendSummary(block, entry);
  return el(
    "div",
    { className: `chip tone-violet backend${editing ? " is-editing" : ""}` },
    el(
      "div",
      { className: "backend-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (!configurable || editing) return;
            if (samples) entry.shotsOpen = true;
            else entry.backendOpen = true;
            replaceChip(event.currentTarget, backendChip(entry));
          },
        },
        el("strong", {}, block.title),
        el("span", { className: "backend-detail" }, shown),
      ),
      el(
        "div",
        { className: "backend-actions" },
        editing
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  entry.shotsOpen = false;
                  entry.backendOpen = false;
                  replaceChip(event.currentTarget, backendChip(entry));
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${block.title}`,
            onclick: (event) => {
              event.stopPropagation();
              removeBackend(entry.key);
            },
          },
          "×",
        ),
      ),
    ),
    editing && samples
      ? el(
          "label",
          { className: "backend-field" },
          "Shots",
          el("input", {
            type: "text",
            inputmode: "numeric",
            "aria-label": "Shots",
            value: String(entry.shots ?? ""),
            spellcheck: "false",
            oninput: (event) => {
              const next = event.target.value.replace(/\D/g, "");
              if (event.target.value !== next) event.target.value = next;
              entry.shots = next;
              const detail = event.target.closest(".chip")?.querySelector(".backend-detail");
              if (detail) detail.textContent = backendSummary(block, entry);
              refreshSummaryAndPreview();
            },
          }),
        )
      : null,
    editing && fields.length
      ? el(
          "div",
          { className: "backend-fields" },
          ...fields.map((field) =>
            el(
              "label",
              {},
              field.label,
              el("input", {
                type: "text",
                inputmode: field.kind === "gates" ? "text" : "decimal",
                "aria-label": field.label,
                value: String(entry.backendFields?.[field.name] ?? ""),
                spellcheck: "false",
                autocomplete: "off",
                oninput: (event) => {
                  const gates = field.kind === "gates";
                  const next = gates
                    ? event.target.value.toLowerCase().replace(/[^a-z0-9_,\s]/g, "")
                    : event.target.value.replace(/[^0-9.eE+\-infity]/gi, "");
                  if (event.target.value !== next) event.target.value = next;
                  entry.backendFields = entry.backendFields ?? {};
                  entry.backendFields[field.name] = next;
                  const detail = event.target.closest(".chip")?.querySelector(".backend-detail");
                  if (detail) detail.textContent = backendSummary(block, entry);
                  refreshSummaryAndPreview();
                },
              }),
            ),
          ),
        )
      : null,
  );
}

function backendSocket(entry) {
  return el(
    "div",
    {
      className: "socket",
      "data-socket": String(entry.key),
      ondragover: (event) => {
        if (!dragging || dragging.lane !== "backend") return;
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.classList.add("is-over");
      },
      ondragleave: (event) => event.currentTarget.classList.remove("is-over"),
      ondrop: (event) => {
        if (!dragging || dragging.lane !== "backend") return;
        event.preventDefault();
        event.stopPropagation();
        attachBackend(dragging.id, entry.key);
      },
    },
    "Add a backend",
  );
}

function methodRow(entry) {
  const simulator = simulatorChip(entry);
  if (!simulator) return null;
  if (isReference(entry)) return el("div", { className: "method-row reference" }, simulator);
  const backend = entry.backend ? backendChip(entry) : backendSocket(entry);
  return el("div", { className: "method-row" }, simulator, backend);
}

function squareMatrix(text) {
  return check(checks.squareMatrix, text);
}

function inspectMatrix(text) {
  return check(checks.inspectMatrix, text);
}

function hamiltonianProblem(term) {
  return check(checks.hamiltonianProblem, term);
}

function validHamiltonianQubits() {
  return check(checks.validHamiltonianQubits);
}

function hamiltonianDetail(term) {
  const problem = hamiltonianProblem(term);
  if (!term.matrix.trim()) return "Square Hermitian matrix";
  if (problem) return problem.replace(/\.$/, "");
  const size = inspectMatrix(term.matrix).matrix.length;
  return `${size}×${size}`;
}

function syncHamiltonianQubits() {
  if (stateOwnsQubits() || qubitsSource === "user") return;
  const counts = [...new Set(validHamiltonianQubits())];
  if (counts.length === 1) {
    settings.qubits = String(counts[0]);
    qubitsSource = "hamiltonian";
  } else if (qubitsSource === "hamiltonian") {
    settings.qubits = "";
    qubitsSource = null;
  }
  syncMeasureChip();
  writeQubitField();
  refreshLocalHamiltonianChips();
}

function refreshHamiltonianChips() {
  document.querySelectorAll?.(".chip.hamiltonian")?.forEach((chip) => {
    const term = modelTerms.find((item) => item.key === Number(chip.dataset.key));
    if (!term) return;
    const detail = chip.querySelector(".hamiltonian-detail");
    if (detail) detail.textContent = hamiltonianDetail(term);
    syncOperatorAlert(chip, term);
  });
}

function hamiltonianChip(term) {
  const input = el("textarea", {
    "aria-label": "Hamiltonian matrix",
    spellcheck: "false",
    rows: "4",
    oninput: (event) => {
      term.matrix = event.target.value;
      syncHamiltonianQubits();
      refreshHamiltonianChips();
      refreshSummaryAndPreview();
    },
  });
  input.value = term.matrix;
  const chip = el(
    "div",
    { className: "chip tone-teal hamiltonian is-editing", "data-key": String(term.key) },
    el(
      "div",
      { className: "basis-head" },
      el(
        "div",
        {},
        el("strong", {}, "Add a Hamiltonian"),
        el("span", { className: "hamiltonian-detail" }, hamiltonianDetail(term)),
      ),
      el(
        "div",
        { className: "basis-actions" },
        el("span", { className: "basis-alert", role: "img" }, "!"),
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": "Remove Add a Hamiltonian",
            onclick: (event) => {
              event.stopPropagation();
              removeTerm(term.key);
            },
          },
          "×",
        ),
      ),
    ),
    el("label", { className: "basis-field" }, "Matrix", input),
  );
  syncOperatorAlert(chip, term);
  return chip;
}

function localSites(term, count) {
  return check(checks.localSites, term, count);
}

function localHamiltonianProblem(term) {
  return check(checks.localHamiltonianProblem, term);
}

function lindbladProblem(term) {
  return check(checks.lindbladProblem, term);
}

function actedQubitDetail(term) {
  if (qubitCount() == null) return "Set qubits first";
  const problem = term.id === "lindblad" ? lindbladProblem(term) : localHamiltonianProblem(term);
  if (problem) return problem.replace(/\.$/, "");
  const sites = localSites(term, qubitCount());
  const parsed = term.id === "lindblad" ? squareMatrix(term.matrix) : inspectMatrix(term.matrix);
  const label = sites.length === 1 ? `qubit ${sites[0]}` : `qubits ${sites.join(", ")}`;
  return `${parsed.matrix.length}×${parsed.matrix.length} on ${label}`;
}

function toggleLocalSite(term, site, checked) {
  const next = localSites(term, qubitCount()).filter((index) => index !== site);
  if (checked) next.push(site);
  next.sort((left, right) => left - right);
  term.sites = next;
}

function localSiteFields(term) {
  const count = qubitCount();
  const chosen = new Set(localSites(term, count));
  const boxes = [];
  for (let site = 0; site < count; site += 1) {
    boxes.push(
      el(
        "label",
        { className: "qubit" },
        el("input", {
          type: "checkbox",
          "aria-label": `${term.id === "lindblad" ? "Lindblad" : "Local"} qubit ${site}`,
          checked: chosen.has(site),
          onchange: (event) => {
            toggleLocalSite(term, site, event.target.checked);
            refreshLocalHamiltonianChips();
            refreshSummaryAndPreview();
          },
        }),
        String(site),
      ),
    );
  }
  return el("div", { className: "measure-fields" }, ...boxes);
}

function localFields(term) {
  const input = el("textarea", {
    "aria-label": term.id === "lindblad" ? "Lindblad matrix" : "Local Hamiltonian matrix",
    spellcheck: "false",
    rows: "4",
    oninput: (event) => {
      term.matrix = event.target.value;
      refreshLocalHamiltonianChips();
      refreshSummaryAndPreview();
    },
  });
  input.value = term.matrix;
  return el("div", { className: "local-fields" }, el("label", { className: "basis-field" }, "Matrix", input), localSiteFields(term));
}

function operatorProblem(term) {
  if (term.id === "lindblad") return lindbladProblem(term);
  if (term.id === "local_hamiltonian") return localHamiltonianProblem(term);
  return hamiltonianProblem(term);
}

function syncOperatorAlert(chip, term) {
  const problem = operatorProblem(term);
  const shown = Boolean(problem) && (term.id === "hamiltonian" || qubitCount() != null);
  const alert = chip.querySelector(".basis-alert");
  const field = chip.querySelector("textarea");
  const alertId = `operator-alert-${term.key}`;
  if (alert) {
    alert.hidden = !shown;
    alert.setAttribute("id", alertId);
    if (problem) {
      alert.setAttribute("aria-label", problem);
      alert.setAttribute("title", problem);
      alert.title = problem;
    }
  }
  if (!field) return;
  if (shown && alert) field.setAttribute("aria-describedby", alertId);
  else field.removeAttribute("aria-describedby");
}

function refreshLocalHamiltonianChips() {
  document.querySelectorAll?.(".chip.local-hamiltonian, .chip.lindblad")?.forEach((chip) => {
    const term = modelTerms.find((item) => item.key === Number(chip.dataset.key));
    if (!term) return;
    const count = qubitCount();
    if (count != null) term.sites = localSites(term, count);
    const open = count != null;
    chip.classList.toggle("is-editing", open);
    const detail = chip.querySelector(".hamiltonian-detail");
    if (detail) detail.textContent = actedQubitDetail(term);
    const fields = chip.querySelector(".local-fields");
    if (!open) fields?.remove();
    else if (!fields) chip.append(localFields(term));
    else fields.querySelector(".measure-fields")?.replaceWith(localSiteFields(term));
    syncOperatorAlert(chip, term);
  });
}

function actedQubitChip(term) {
  const open = qubitCount() != null;
  const lindblad = term.id === "lindblad";
  const title = lindblad ? "Add a Lindblad operator" : "Add a Local Hamiltonian";
  const chip = el(
    "div",
    {
      className: `chip tone-teal ${lindblad ? "lindblad" : "local-hamiltonian"}${open ? " is-editing" : ""}`,
      "data-key": String(term.key),
    },
    el(
      "div",
      { className: "basis-head" },
      el("div", {}, el("strong", {}, title), el("span", { className: "hamiltonian-detail" }, actedQubitDetail(term))),
      el(
        "div",
        { className: "basis-actions" },
        el("span", { className: "basis-alert", role: "img" }, "!"),
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${title}`,
            onclick: (event) => {
              event.stopPropagation();
              removeTerm(term.key);
            },
          },
          "×",
        ),
      ),
    ),
    open ? localFields(term) : null,
  );
  syncOperatorAlert(chip, term);
  return chip;
}

function slotChips(lane) {
  const chips = [];
  const chosen = blockById(lane.id, selection[lane.id]);
  if (chosen && !chosen.adds && lane.id !== "then") {
    if (chosen.id === "preexisting") chips.push(preexistingChip());
    else if (chosen.id === "basis") chips.push(basisChip());
    else if (chosen.id === "gray") chips.push(grayChip());
    else if (chosen.id === "angle") {
      chips.push(
        numberChip("angle", "Angle", "Radians", "Angles", "Enter angles", () => angleText, (value) => {
          angleText = value;
        }),
      );
    } else if (chosen.id === "amplitude") {
      chips.push(
        numberChip(
          "amplitude",
          "Amplitude",
          "Amplitudes",
          "Amplitudes",
          "Enter amplitudes",
          () => amplitudeText,
          (value) => {
            amplitudeText = value;
          },
        ),
      );
    }
    else if (chosen.id === "save") chips.push(saveChip(chosen));
    else if (chosen.id === "export") chips.push(exportChip(chosen));
    else if (lane.id === "measure") chips.push(measureChip(chosen));
    else if (lane.id !== "simulator") {
      chips.push(blockCard(lane, chosen, { inSlot: true, onRemove: () => clearLane(lane.id) }));
    }
  }
  if (lane.id === "then") {
    for (const id of placedThens) {
      const block = blockById("then", id);
      if (!block) continue;
      if (id === "save") chips.push(saveChip(block));
      else if (id === "export") chips.push(exportChip(block));
      else chips.push(blockCard(lane, block, { inSlot: true, onRemove: () => removeThen(id) }));
    }
    return chips;
  }
  if (lane.id === "simulator") {
    for (const entry of placedSims) {
      const row = methodRow(entry);
      if (row) chips.push(row);
    }
    return chips;
  }
  if (lane.id !== "model") return chips;
  for (const term of modelTerms) {
    const block = blockById("model", term.id);
    if (!block) continue;
    if (term.id === "hamiltonian") chips.push(hamiltonianChip(term));
    else if (term.id === "local_hamiltonian" || term.id === "lindblad") chips.push(actedQubitChip(term));
    else chips.push(blockCard(lane, block, { inSlot: true, onRemove: () => removeTerm(term.key) }));
  }
  return chips;
}

function laneColumn(lane) {
  return String(1 + LANES.indexOf(lane) * 2);
}

function placeOnGrid(node, lane, row) {
  node.style.gridColumn = laneColumn(lane);
  node.style.gridRow = row;
  return node;
}

function slotAcceptsDrag(laneId) {
  if (!dragging) return false;
  if (dragging.lane === laneId) return true;
  return laneId === "simulator" && dragging.lane === "backend";
}

function slotComponent(lane) {
  const slot = el(
    "section",
    {
      className: `slot tone-${lane.tone}`,
      "data-slot": lane.id,
      ondragover: (event) => {
        if (!slotAcceptsDrag(lane.id)) return;
        event.preventDefault();
        slot.classList.add("is-over");
      },
      ondragleave: () => slot.classList.remove("is-over"),
      ondrop: (event) => {
        if (!slotAcceptsDrag(lane.id)) return;
        event.preventDefault();
        if (dragging.lane === "backend") attachBackend(dragging.id);
        else place(lane.id, dragging.id);
      },
    },
    el("h2", {}, lane.title),
    el("p", { className: "hint" }, lane.hint),
    ...slotChips(lane),
  );
  return placeOnGrid(slot, lane, "1");
}

function methodPalette(lane, onPlace) {
  const noteText = laneNotes.simulator || laneNotes.backend;
  const note = noteText ? el("p", { className: "hint" }, noteText) : null;
  const groups = [
    ["Classical references", BLOCKS.simulator.filter((block) => block.observables), lane],
    ["Simulators", BLOCKS.simulator.filter((block) => !block.observables), lane],
    ["Backends", BLOCKS.backend, { id: "backend", tone: "violet" }],
  ];
  return placeOnGrid(
    el(
      "section",
      { className: "lane", "data-palette": lane.id },
      el("h2", {}, lane.pick),
      note,
      ...groups
        .filter(([, blocks]) => blocks.length)
        .map(([title, blocks, cardLane]) =>
          el(
            "div",
            { className: "palette-group" },
            el("h3", {}, title),
            el(
              "div",
              { className: "cards" },
              ...blocks.map((block) =>
                blockCard(cardLane, block, {
                  inSlot: false,
                  blocked: false,
                  onPlace: () => (cardLane.id === "backend" ? attachBackend(block.id) : onPlace(block.id)),
                }),
              ),
            ),
          ),
        ),
    ),
    lane,
    "2",
  );
}

function paletteComponent(lane, onPlace) {
  if (lane.id === "simulator") return methodPalette(lane, onPlace);
  const note = laneNotes[lane.id] ? el("p", { className: "hint" }, laneNotes[lane.id]) : null;
  return placeOnGrid(
    el(
      "section",
      { className: "lane", "data-palette": lane.id },
      el("h2", {}, lane.pick),
      note,
      el(
        "div",
        { className: "cards" },
        ...BLOCKS[lane.id].map((block) =>
          blockCard(lane, block, {
            inSlot: false,
            blocked: lane.id === "model" && modelChoiceBlocked(block),
            onPlace: () => onPlace(block.id),
          }),
        ),
      ),
    ),
    lane,
    "2",
  );
}

function summaryComponent() {
  if (!isComplete()) {
    return el("p", { className: "summary" }, "Place a block in each slot, then run.");
  }
  const state = blockById("state", selection.state);
  const model = selection.model === "preexisting" ? chosenFactory() : null;
  const actions = thenSummary();
  const qubits = qubitPhrase();
  const total = formatSetting("total");
  const modelPhrase = model
    ? [el("strong", {}, model.title), " model", ...termSummary()]
    : [el("strong", {}, "added operators")];
  return el(
    "p",
    { className: "summary" },
    "Start from ",
    el("strong", {}, state.title),
    ", evolve the ",
    ...modelPhrase,
    " with ",
    ...simulatorSummary(),
    ", measure ",
    el("strong", {}, measurePhrase()),
    ", then ",
    ...actions,
    qubits ? ", on " : "",
    qubits ? el("strong", {}, qubits) : "",
    total ? " for a total time of " : "",
    total ? el("strong", {}, total) : "",
    ".",
  );
}

function settingsComponent() {
  const field = (key, label, inputMode) =>
    el(
      "label",
      { className: "setting" },
      label,
      el("input", {
        type: "text",
        inputmode: inputMode,
        value: settings[key],
        "aria-label": label,
        readonly: key === "qubits" && (stateOwnsQubits() || cavityModelSelected()),
        oninput: (event) => {
          if (key === "qubits" && (stateOwnsQubits() || cavityModelSelected())) return;
          settings[key] = event.target.value.trim();
          if (key === "qubits") {
            qubitsSource = settings.qubits === "" ? null : "user";
            syncMeasureChip();
            syncHamiltonianQubits();
            refreshHamiltonianChips();
            refreshLocalHamiltonianChips();
          }
          refreshSummaryAndPreview();
        },
      }),
    );
  return el(
    "div",
    { className: "settings" },
    el(
      "div",
      { className: "settings-fields" },
      el("h2", {}, "Settings"),
      field("qubits", "Qubits", "numeric"),
      field("total", "Total time", "decimal"),
    ),
    el(
      "div",
      { className: "settings-actions" },
      el("button", {
        className: "clear",
        type: "button",
        disabled: running,
        onclick: () => emptyBoard(),
      }, "Clear"),
      el("button", {
        className: "run",
        type: "button",
        disabled: !running && !runAllowed(),
        onclick: () => void (running ? cancelRun() : startRun()),
      }, running ? "Cancel" : "Run simulation"),
    ),
  );
}

function releaseStatusHold() {
  statusHold = null;
}

function refreshSummaryAndPreview() {
  const summary = document.querySelector(".summary");
  if (summary) summary.replaceWith(summaryComponent());
  if (!running) {
    releaseStatusHold();
    const status = document.querySelector(".status");
    if (status) status.replaceWith(statusComponent());
  }
  const panel = document.querySelector('.panel[aria-label="Code preview"]');
  const body = panel?.querySelector("pre, .placeholder");
  if (body) body.replaceWith(codeBody());
  syncCopyButton();
  syncRunButton();
  rememberBoard();
  clearStaleResults();
}

function statusMessage() {
  if (statusHold) return statusHold;
  if (!isComplete()) return operatorStatus(false) ?? socketStatus(false) ?? "Place a block in each slot.";
  if (factoryAlert()) return `${factoryAlert()}.`;
  if (stateInputProblem() === "size") return stateSizeStatus(false);
  if (stateInputProblem() === "basis") return "Enter a basis bit string and total time.";
  if (stateInputProblem() === "gray") return "Enter a Gray code bit string and total time.";
  if (stateInputProblem() === "angle") return "Enter one angle per qubit and total time.";
  if (stateInputProblem() === "amplitude") return "Enter a non-zero amplitude list and total time.";
  const numbers = numberProblem(false);
  if (numbers) return numbers;
  if (!simParamsReady()) return "Enter simulator parameters.";
  if (!sameTimeGrid()) return "Use the same number of time steps for every simulator.";
  if (!measureSitesReady()) return "Pick at least one qubit.";
  if (countsStatus(false)) return countsStatus(false);
  if (!shotsReady()) return "Enter a shot count.";
  if (!check(checks.backendFieldsReady)) return check(checks.backendFieldStatus, false);
  if (!savePathReady()) return pathMessage(false);
  return "Ready to run.";
}

function statusComponent() {
  const ready = !statusHold && runAllowed();
  return el(
    "p",
    { className: ready ? "status ready" : "status", role: "status" },
    statusMessage(),
  );
}

function syncCopyButton() {
  const copy = document.querySelector('.panel[aria-label="Code preview"] .copy');
  if (!copy) return;
  const enabled = Boolean(previewText());
  copy.disabled = !enabled;
  if (enabled) {
    if (typeof copy.removeAttribute === "function") copy.removeAttribute("disabled");
    return;
  }
  copy.setAttribute("disabled", "");
  copy.textContent = "Copy";
}

function showCopied(button) {
  button.textContent = "Copied";
  if (copyTimer) clearTimeout(copyTimer);
  copyTimer = setTimeout(() => {
    copyTimer = 0;
    if (button.isConnected === false) return;
    button.textContent = "Copy";
  }, 1500);
}

function copyPreview(event) {
  const code = previewText();
  if (!code) return;
  const pending = navigator.clipboard?.writeText?.(code);
  if (!pending || typeof pending.then !== "function") return;
  const button = event?.currentTarget;
  pending.then(() => {
    if (button) showCopied(button);
  }, () => {});
}

function copyButton() {
  return el(
    "button",
    {
      className: "copy",
      type: "button",
      disabled: !previewText(),
      onclick: (event) => copyPreview(event),
    },
    "Copy",
  );
}

function codeBody() {
  const code = previewText();
  if (code) return el("pre", {}, code);
  let message = operatorStatus(true) ?? socketStatus(true) ?? "Place a block in each slot to preview the script.";
  if (isComplete()) {
    const numbers = numberProblem(true);
    if (factoryAlert()) message = `${factoryAlert()} to preview the script.`;
    else if (stateInputProblem() === "size") message = stateSizeStatus(true);
    else if (stateInputProblem() === "basis") message = "Enter a basis bit string and total time to preview the script.";
    else if (stateInputProblem() === "gray") message = "Enter a Gray code bit string and total time to preview the script.";
    else if (stateInputProblem() === "angle") message = "Enter one angle per qubit and total time to preview the script.";
    else if (stateInputProblem() === "amplitude") {
      message = "Enter a non-zero amplitude list and total time to preview the script.";
    }
    else if (numbers) message = numbers;
    else if (!simParamsReady()) message = "Enter simulator parameters to preview the script.";
    else if (!sameTimeGrid()) message = "Use the same number of time steps to preview the script.";
    else if (!measureSitesReady()) message = "Pick at least one qubit to preview the script.";
    else if (countsStatus(true)) message = countsStatus(true);
    else if (!shotsReady()) message = "Enter a shot count to preview the script.";
    else if (!check(checks.backendFieldsReady)) message = check(checks.backendFieldStatus, true);
    else message = pathMessage(true);
  }
  return el("p", { className: "placeholder" }, message);
}

function setStatus(message, ready) {
  const status = document.querySelector(".status");
  if (!status) return;
  status.replaceWith(el("p", { className: ready ? "status ready" : "status", role: "status" }, message));
}

function setResults(node) {
  const panel = document.querySelector('.panel[aria-label="Results"]');
  const body = panel?.querySelector(":scope > .placeholder, :scope > .chart, :scope > .results");
  if (body) body.replaceWith(node);
}

function resultsPlaceholder() {
  return el("p", { className: "placeholder" }, "Run a simulation to see results here.");
}

function clearResults() {
  shownRun = null;
  setResults(resultsPlaceholder());
}

function clearStaleResults() {
  if (shownRun == null) return;
  if (shownRun === JSON.stringify(runRequest())) return;
  clearResults();
}

function formatAxis(value) {
  if (!Number.isFinite(value)) return "";
  if (Number.isInteger(value)) return String(value);
  return String(Math.round(value * 1000) / 1000);
}

function chartCurves(payload) {
  const shared = Array.isArray(payload.labels) ? payload.labels : [];
  if (Array.isArray(payload.series) && payload.series.length) {
    const curves = [];
    for (const series of payload.series) {
      const observables = Array.isArray(series.observables) ? series.observables : [];
      const own = Array.isArray(series.labels) ? series.labels : [];
      observables.forEach((values, index) => {
        const named = typeof own[index] === "string" && own[index] ? own[index] : "";
        const common = typeof shared[index] === "string" ? shared[index] : "";
        const label = named || (common ? `${series.name} · ${common}` : `${series.name} ${index}`);
        curves.push({ label, values, index, simulator: series.name });
      });
    }
    return curves;
  }
  const observables = Array.isArray(payload.observables) ? payload.observables : [];
  return observables.map((values, index) => ({
    label: typeof shared[index] === "string" && shared[index] ? shared[index] : `Observable ${index}`,
    values,
    index,
  }));
}

function subtractSeries(reference, values) {
  const left = Array.isArray(reference) ? reference : [];
  const right = Array.isArray(values) ? values : [];
  const count = Math.max(left.length, right.length);
  const diff = [];
  for (let index = 0; index < count; index++) {
    const a = left[index];
    const b = right[index];
    if (a == null || b == null) {
      diff.push(null);
      continue;
    }
    const y = Number(a) - Number(b);
    diff.push(Number.isFinite(y) ? y : null);
  }
  return diff;
}

function errorCurves(payload) {
  const series = Array.isArray(payload.series) ? payload.series : [];
  if (series.length < 2) return [];
  const reference = Array.isArray(series[0].observables) ? series[0].observables : [];
  const errors = Array.isArray(payload.errors) ? payload.errors : [];
  const curves = [];
  series.slice(1).forEach((challenger, challengerIndex) => {
    const named = chartCurves({ labels: payload.labels, series: [challenger] });
    const observables = Array.isArray(challenger.observables) ? challenger.observables : [];
    const row = errors[challengerIndex];
    const metrics = row && Array.isArray(row.observables) ? row.observables : [];
    observables.forEach((values, index) => {
      const metric = metrics.find((item) => item && item.index === index) || null;
      curves.push({
        label: named[index] ? named[index].label : `${challenger.name} ${index}`,
        values: subtractSeries(reference[index], values),
        metric,
        index,
      });
    });
  });
  return curves;
}

function errorAxisTitle(payload) {
  const series = Array.isArray(payload.series) ? payload.series : [];
  const name = series[0] && series[0].name ? String(series[0].name) : "reference";
  return `Error vs ${name}`;
}

function yAxisTitle(curves) {
  const letters = new Set();
  for (const curve of curves) {
    const match = String(curve.label).match(/⟨([ZX])⟩/);
    if (match) letters.add(match[1]);
  }
  if (letters.size === 1) return `⟨${[...letters][0]}⟩`;
  return "Expectation";
}

function plotFraction(x, plotLeft, plotRight) {
  if (!Number.isFinite(x) || !Number.isFinite(plotLeft) || !Number.isFinite(plotRight)) return null;
  if (x < plotLeft || x > plotRight || plotRight === plotLeft) return null;
  return (x - plotLeft) / (plotRight - plotLeft);
}

function nearestTimeIndex(payload, fraction) {
  const times = Array.isArray(payload.times) ? payload.times : [];
  if (!times.length || !Number.isFinite(fraction)) return -1;
  const first = Number(times[0]);
  const last = Number(times[times.length - 1]);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return -1;
  const clamped = Math.min(1, Math.max(0, fraction));
  const target = first + clamped * (last - first);
  let best = -1;
  let bestDist = Infinity;
  for (let index = 0; index < times.length; index++) {
    const time = Number(times[index]);
    if (!Number.isFinite(time)) continue;
    const dist = Math.abs(time - target);
    if (dist < bestDist) {
      bestDist = dist;
      best = index;
    }
  }
  return best;
}

function simulatorTitle(name) {
  const text = String(name || "");
  const hash = text.indexOf("#");
  const base = hash === -1 ? text : text.slice(0, hash);
  const suffix = hash === -1 ? "" : text.slice(hash);
  const titles = { qutip: "QuTiP", split_jmatrix: "Split J", trotterization: "Trotter" };
  return `${titles[base] || base}${suffix}`;
}

function shownCurves(payload, view, observable) {
  const curves = view === "error" ? errorCurves(payload) : chartCurves(payload);
  const simulator = view && view !== "curves" && view !== "error" ? view : null;
  const matched = simulator == null ? curves : curves.filter((curve) => curve.simulator === simulator);
  if (!Number.isInteger(observable)) return matched;
  return matched.filter((curve) => curve.index === observable);
}

function hoverReadout(payload, index, view, observable) {
  const times = Array.isArray(payload.times) ? payload.times : [];
  if (!Number.isInteger(index) || index < 0 || index >= times.length) return "";
  const time = Number(times[index]);
  if (!Number.isFinite(time)) return "";
  const parts = [];
  for (const curve of shownCurves(payload, view, observable)) {
    const values = Array.isArray(curve.values) ? curve.values : [];
    const raw = values[index];
    if (raw == null) continue;
    const value = Number(raw);
    if (!Number.isFinite(value)) continue;
    parts.push(`${curve.label} = ${formatAxis(value)}`);
  }
  if (!parts.length) return "";
  return [`t = ${formatAxis(time)}`, ...parts].join(" · ");
}

function formatMetric(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return String(Math.round(number * 10000) / 10000);
}

function legendText(curve) {
  const metric = curve.metric;
  if (!metric) return curve.label;
  const max = formatMetric(metric.linf);
  const rmse = formatMetric(metric.rmse);
  if (!max || !rmse) return curve.label;
  return `${curve.label}: max ${max}, RMSE ${rmse}`;
}

function resourceName(id) {
  const text = String(id || "");
  const hash = text.indexOf("#");
  const base = hash === -1 ? text : text.slice(0, hash);
  const suffix = hash === -1 ? "" : text.slice(hash);
  const short = base.endsWith("_simulator") ? base.slice(0, -"_simulator".length) : base;
  return `${short}${suffix}`;
}

function resourceLine(resources) {
  if (!Array.isArray(resources) || !resources.length) return "";
  const several = resources.length > 1;
  const clauses = [];
  for (const record of resources) {
    if (!record || typeof record !== "object") continue;
    const time = formatSeconds(record.wall_time_s);
    const shots = shotBudget(record);
    const body = [time, shots, circuitMetrics(record)].filter(Boolean).join(", ");
    if (!body) continue;
    if (!several) {
      clauses.push(body);
      continue;
    }
    const name = resourceName(record.simulator_id);
    clauses.push(name ? `${name} ${body}` : body);
  }
  return clauses.join(" · ");
}

function formatSeconds(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return `${formatAxis(number)} s`;
}

function shotBudget(record) {
  const shots = record.shots_per_job;
  const jobs = record.num_jobs;
  if (!Number.isInteger(shots) || !Number.isInteger(jobs)) return "";
  return `${shots} shots × ${jobs}`;
}

function circuitMetrics(record) {
  const fields = [
    ["depth", "depth"],
    ["width", "width"],
    ["gate_count", "gates"],
    ["t_count", "T"],
    ["toffoli_count", "Toffoli"],
  ];
  return fields.map(([key, label]) => `${label} ${formatCircuitMetric(record[key])}`).join(", ");
}

function formatCircuitMetric(value) {
  if (typeof value === "number" && Number.isInteger(value)) return String(value);
  return "N/A";
}

function savedNote(payload) {
  const notes = [];
  const saved = Array.isArray(payload.saved) ? payload.saved.filter((item) => typeof item === "string") : [];
  if (saved.length) notes.push(`Saved to ${saved.join(", ")}`);
  if (typeof payload.exported === "string" && payload.exported) notes.push(`Exported to ${payload.exported}`);
  if (!notes.length) return null;
  return el("p", { className: "hint" }, notes.join(". "));
}

function observableChoices(payload) {
  const series = Array.isArray(payload.series) ? payload.series : [];
  if (series.length < 2) return [];
  let count = 0;
  for (const entry of series) {
    const observables = Array.isArray(entry.observables) ? entry.observables.length : 0;
    count = Math.max(count, observables);
  }
  if (count < 2) return [];
  const labels = Array.isArray(payload.labels) ? payload.labels : [];
  const choices = [{ key: "all", label: "All" }];
  for (let index = 0; index < count; index++) {
    const label = typeof labels[index] === "string" && labels[index] ? labels[index] : `Observable ${index}`;
    choices.push({ key: String(index), label });
  }
  return choices;
}

function chartViews(payload) {
  const series = Array.isArray(payload.series) ? payload.series : [];
  if (series.length < 2) return [];
  const views = [{ key: "curves", label: "Curves" }];
  for (const entry of series) {
    if (!entry || !entry.name) continue;
    views.push({ key: String(entry.name), label: simulatorTitle(entry.name) });
  }
  views.push({ key: "error", label: "Error" });
  return views;
}

function resultsComponent(payload) {
  const note = savedNote(payload);
  const views = chartViews(payload);
  const choices = observableChoices(payload);
  const host = el("div", { className: "chart-host" });
  let view = "curves";
  let observable = null;
  function draw() {
    host.replaceChildren(chartComponent(payload, view, observable));
    for (const button of viewButtons) {
      button.setAttribute("aria-pressed", button.getAttribute("data-view") === view ? "true" : "false");
    }
    for (const button of observableButtons) {
      const key = button.getAttribute("data-observable");
      const pressed = observable == null ? key === "all" : key === String(observable);
      button.setAttribute("aria-pressed", pressed ? "true" : "false");
    }
  }
  const viewButtons = views.map((choice) =>
    el(
      "button",
      {
        type: "button",
        role: "tab",
        "data-view": choice.key,
        "aria-pressed": choice.key === "curves" ? "true" : "false",
        onclick: () => {
          view = choice.key;
          draw();
        },
      },
      choice.label,
    ),
  );
  const observableButtons = choices.map((choice) =>
    el(
      "button",
      {
        type: "button",
        role: "tab",
        "data-observable": choice.key,
        "aria-pressed": choice.key === "all" ? "true" : "false",
        onclick: () => {
          observable = choice.key === "all" ? null : Number(choice.key);
          draw();
        },
      },
      choice.label,
    ),
  );
  draw();
  const line = resourceLine(payload.resources);
  const resources = line ? el("p", { className: "resources" }, line) : null;
  const observableSwitcher = observableButtons.length
    ? el("div", { className: "chart-switch", role: "tablist", "aria-label": "Observable" }, ...observableButtons)
    : null;
  const viewSwitcher = viewButtons.length
    ? el("div", { className: "chart-switch", role: "tablist", "aria-label": "Chart" }, ...viewButtons)
    : null;
  if (!note && !observableSwitcher && !viewSwitcher && !resources) return host.children[0];
  return el("div", { className: "results" }, note, observableSwitcher, viewSwitcher, host, resources);
}

function curveColor(index, count) {
  if (count <= CURVE_COLORS.length) return CURVE_COLORS[index];
  const hue = Math.round((360 * index) / count);
  return `hsl(${hue} 58% 42%)`;
}

function finitePairs(times, values) {
  const pairs = [];
  if (!Array.isArray(values)) return pairs;
  const count = Math.min(times.length, values.length);
  for (let index = 0; index < count; index++) {
    const time = times[index];
    const value = values[index];
    if (time == null || value == null) continue;
    const x = Number(time);
    const y = Number(value);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    pairs.push([x, y]);
  }
  return pairs;
}

function chartComponent(payload, view, observable) {
  const times = Array.isArray(payload.times) ? payload.times : [];
  const error = view === "error";
  const curves = shownCurves(payload, view, observable);
  if (!times.length || !curves.length) {
    return el("p", { className: "placeholder" }, "The run returned no curves.");
  }
  const plotted = curves.map((curve) => finitePairs(times, curve.values));
  const width = 640;
  const height = 220;
  const pad = 28;
  const padLeft = 56;
  const first = Number(times[0]);
  const last = Number(times[times.length - 1]);
  let yMin = Infinity;
  let yMax = -Infinity;
  for (const pairs of plotted) {
    for (const [, value] of pairs) {
      yMin = Math.min(yMin, value);
      yMax = Math.max(yMax, value);
    }
  }
  if (!Number.isFinite(yMin) || !Number.isFinite(yMax)) {
    return el("p", { className: "placeholder" }, "The run returned no curves.");
  }
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }
  const xSpan = last - first || 1;
  const ySpan = yMax - yMin;
  const plotLeft = padLeft;
  const plotRight = width - pad;
  const sx = (time) => plotLeft + ((Number(time) - first) / xSpan) * (plotRight - plotLeft);
  const sy = (value) => height - pad - ((Number(value) - yMin) / ySpan) * (height - pad * 2);
  const yTitle = error ? errorAxisTitle(payload) : yAxisTitle(curves);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "plot");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${yTitle} versus time`);
  const axis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  axis.setAttribute("x1", String(padLeft));
  axis.setAttribute("x2", String(width - pad));
  axis.setAttribute("y1", String(height - pad));
  axis.setAttribute("y2", String(height - pad));
  const yAxis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  yAxis.setAttribute("x1", String(padLeft));
  yAxis.setAttribute("x2", String(padLeft));
  yAxis.setAttribute("y1", String(pad));
  yAxis.setAttribute("y2", String(height - pad));
  svg.append(axis, yAxis);
  plotted.forEach((pairs, index) => {
    if (!pairs.length) return;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", curveColor(index, curves.length));
    line.setAttribute("stroke-width", "2");
    line.setAttribute("points", pairs.map(([time, value]) => `${sx(time)},${sy(value)}`).join(" "));
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = curves[index].label;
    line.append(title);
    svg.append(line);
  });
  for (const tick of [yMin, (yMin + yMax) / 2, yMax]) {
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", String(padLeft - 6));
    label.setAttribute("y", String(sy(tick)));
    label.setAttribute("text-anchor", "end");
    label.setAttribute("dominant-baseline", "middle");
    label.textContent = formatAxis(tick);
    svg.append(label);
  }
  const startLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  startLabel.setAttribute("x", String(padLeft));
  startLabel.setAttribute("y", String(height - 8));
  startLabel.textContent = formatAxis(first);
  const endLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  endLabel.setAttribute("x", String(width - pad));
  endLabel.setAttribute("y", String(height - 8));
  endLabel.setAttribute("text-anchor", "end");
  endLabel.textContent = formatAxis(last);
  svg.append(startLabel, endLabel);
  const readout = el("p", { className: "readout" });
  svg.addEventListener("pointermove", (event) => {
    const rect = svg.getBoundingClientRect();
    if (!rect.width) return;
    const x = ((event.clientX - rect.left) / rect.width) * width;
    const fraction = plotFraction(x, plotLeft, plotRight);
    readout.textContent =
      fraction == null ? "" : hoverReadout(payload, nearestTimeIndex(payload, fraction), view, observable);
  });
  svg.addEventListener("pointerleave", () => {
    readout.textContent = "";
  });
  return el(
    "div",
    { className: "chart" },
    el(
      "div",
      { className: "plot-frame" },
      el("span", { className: "y-title" }, yTitle),
      el("div", { className: "plot-column" }, svg, el("p", { className: "x-title" }, "Time")),
    ),
    readout,
    el(
      "ul",
      { className: "legend" },
      ...curves.map((curve, index) =>
        el(
          "li",
          {},
          el("i", { style: `background:${curveColor(index, curves.length)}` }),
          legendText(curve),
        ),
      ),
    ),
  );
}

function runningLabel(elapsedMs) {
  const total = Math.max(0, Math.floor(elapsedMs / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return `Running · ${minutes}:${seconds}`;
}

function showRunningClock() {
  if (!running) return;
  const status = document.querySelector(".status");
  if (!status) return;
  status.className = "status";
  status.setAttribute("aria-live", "off");
  status.textContent = runningLabel(Date.now() - runStartedAt);
}

function stopRunClock() {
  if (runTimer == null) return;
  clearInterval(runTimer);
  runTimer = null;
}

function syncRunButton() {
  const button = document.querySelector(".run");
  if (!button || running) return;
  button.disabled = !runAllowed();
}

function setRunButton(label) {
  const button = document.querySelector(".run");
  if (!button) return;
  button.textContent = label;
  button.disabled = label !== "Cancel" && !runAllowed();
  const clear = document.querySelector(".clear");
  if (clear) clear.disabled = label === "Cancel";
}

async function cancelRun() {
  if (!running) return;
  try {
    await fetch("/runs/cancel", { method: "POST" });
  } catch {
    // The run request stays open and reports the outcome.
  }
}

function runRequest() {
  const factory = postedFactory();
  return {
    ...postedSelection(),
    model: selection.model === "preexisting" ? preexistingId : selection.model,
    qubits: settings.qubits,
    total: settings.total,
    basis: basisBits,
    gray: grayBits,
    angles: numberList(angleText, STATE_LIMITS.angle),
    amplitudes: numberList(amplitudeText, STATE_LIMITS.amplitude),
    sites: explicitSites(),
    ...(selection.measure === "counts" ? { expression: countsExpression.trim() } : {}),
    ...(placedSims[0] ? entryBody(placedSims[0]) : {}),
    simulators: placedSims.map(entryBody),
    then: placedThens[0] ?? null,
    thens: [...placedThens],
    save_path: savePath.trim(),
    export_path: exportPath.trim(),
    terms: postedTerms(),
    ...(selection.model === "preexisting" && preexistingId === "tavis_cummings"
      ? { emitters: emitterCount() }
      : {}),
    ...(selection.model === "preexisting" && preexistingId === "tavis_cummings_hubbard"
      ? { emitters: emitterCount(), cavities: cavityCount(), nu: hoppingValue() }
      : {}),
    ...(selection.model === "preexisting" && preexistingId === "jaynes_cummings_hubbard"
      ? { cavities: cavityCount(), nu: hoppingValue() }
      : {}),
    ...(factory ? { factory } : {}),
  };
}

function showRunResult(requested, node) {
  if (JSON.stringify(runRequest()) !== requested) {
    clearResults();
    return false;
  }
  shownRun = requested;
  setResults(node);
  return true;
}

async function startRun() {
  if (running || !runAllowed()) return;
  running = true;
  releaseStatusHold();
  runStartedAt = Date.now();
  setRunButton("Cancel");
  showRunningClock();
  runTimer = setInterval(showRunningClock, 1000);
  const requested = JSON.stringify(runRequest());
  shownRun = requested;
  setResults(el("p", { className: "placeholder" }, "Running."));
  try {
    const response = await fetch("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: requested,
    });
    const payload = await response.json();
    if (payload.cancelled) {
      if (showRunResult(requested, el("p", { className: "placeholder" }, "Cancelled."))) {
        statusHold = "Cancelled.";
      }
      return;
    }
    if (!response.ok) {
      const message = payload.error || "The run failed.";
      if (showRunResult(requested, el("p", { className: "placeholder" }, message))) statusHold = message;
      return;
    }
    releaseStatusHold();
    showRunResult(requested, resultsComponent(payload));
  } catch {
    if (showRunResult(requested, el("p", { className: "placeholder" }, "The run failed."))) {
      statusHold = "The run failed.";
    }
  } finally {
    stopRunClock();
    running = false;
    setRunButton("Run simulation");
    if (statusHold) setStatus(statusHold);
    else setStatus(statusMessage(), runAllowed());
  }
}

function panelsComponent() {
  return el(
    "div",
    { className: "panels" },
    el(
      "section",
      { className: "panel", "aria-label": "Code preview" },
      el("div", { className: "panel-head" }, el("h2", {}, "Code preview"), copyButton()),
      codeBody(),
    ),
    el(
      "section",
      { className: "panel", "aria-label": "Results" },
      el("h2", {}, "Results"),
      resultsPlaceholder(),
    ),
  );
}

function layoutComponent() {
  const layout = el("div", { className: "layout" });
  LANES.forEach((lane, index) => {
    const slot = slotComponent(lane);
    const palette = paletteComponent(lane, (blockId) => place(lane.id, blockId));
    layout.append(slot, palette);
    if (index === LANES.length - 1) return;
    const chevron = el("div", { className: "chevron", "aria-hidden": "true" }, ">");
    chevron.style.gridColumn = String(2 + index * 2);
    chevron.style.gridRow = "1";
    layout.append(chevron);
  });
  return layout;
}

function draw(board) {
  shownRun = null;
  board.replaceChildren(
    layoutComponent(),
    settingsComponent(),
    summaryComponent(),
    statusComponent(),
    panelsComponent(),
  );
  rememberBoard();
}

function termSummary() {
  const nodes = [];
  modelTerms.forEach((term, index) => {
    const block = blockById("model", term.id);
    if (!block) return;
    nodes.push(index === 0 ? ", plus " : ", ");
    nodes.push(el("strong", {}, block.title));
  });
  return nodes;
}

function measureDetail(count) {
  const block = blockById("measure", selection.measure);
  if (count == null) return block?.detail ?? "";
  const sites = selectedSites(count);
  if (!sites.length) return "No qubits";
  if (sites.length === count) return block?.detail ?? "";
  return `Qubits ${sites.join(", ")}`;
}

function measurePhrase() {
  const block = blockById("measure", selection.measure);
  if (!block) return "";
  const count = qubitCount();
  const sites = selectedSites(count);
  if (count == null || sites.length === count) return block.phrase;
  if (!sites.length) return `${block.title} on no qubits`;
  return `${block.title} on qubits ${sites.join(", ")}`;
}

function explicitSites() {
  const count = qubitCount();
  if (measureSites == null || count == null) return null;
  const sites = selectedSites(count);
  return sites.length === count ? null : sites;
}

function toggleMeasureSite(site, checked) {
  const count = qubitCount();
  if (count == null) return;
  const next = selectedSites(count).filter((index) => index !== site);
  if (checked) next.push(site);
  next.sort((left, right) => left - right);
  measureSites = next.length === count ? null : next;
}

function measureFields() {
  const count = qubitCount();
  const chosen = new Set(selectedSites(count));
  const boxes = [];
  for (let site = 0; site < count; site += 1) {
    boxes.push(
      el(
        "label",
        { className: "qubit" },
        el("input", {
          type: "checkbox",
          "aria-label": `Qubit ${site}`,
          checked: chosen.has(site),
          onchange: (event) => {
            toggleMeasureSite(site, event.target.checked);
            const chip = event.target.closest(".chip");
            const detail = chip?.querySelector(".measure-detail");
            if (detail) detail.textContent = measureDetail(qubitCount());
            const hint = chip?.querySelector(".counts-hint");
            if (hint) hint.textContent = countsHint();
            const input = chip?.querySelector(".counts-field input");
            if (input) input.placeholder = countsPlaceholder();
            refreshSummaryAndPreview();
          },
        }),
        String(site),
      ),
    );
  }
  return el("div", { className: "measure-fields" }, ...boxes);
}

function countsHint() {
  const sites = selectedSites(qubitCount());
  if (!sites.length) return "Pick at least one qubit.";
  const label = sites.length === 1 ? "qubit" : "qubits";
  return `Keys list ${label} ${sites.join(", ")} in that order. shots is the total.`;
}

function countsPlaceholder() {
  const width = Math.max(selectedSites(qubitCount()).length, 1);
  return `counts["${"0".repeat(width)}"] / shots`;
}

function countsField() {
  return el(
    "label",
    { className: "counts-field" },
    "Expression",
    el("input", {
      type: "text",
      "aria-label": "Counts expression",
      value: countsExpression,
      placeholder: countsPlaceholder(),
      spellcheck: "false",
      oninput: (event) => {
        countsExpression = event.target.value;
        refreshSummaryAndPreview();
      },
    }),
    el("span", { className: "counts-hint" }, countsHint()),
  );
}

function syncMeasureChip() {
  const chip = document.querySelector(".chip.measure");
  if (!chip) return;
  const count = qubitCount();
  const detail = chip.querySelector(".measure-detail");
  if (detail) detail.textContent = measureDetail(count);
  if (count == null) {
    measureOpen = false;
    chip.classList.remove("is-editing");
    chip.querySelector(".done")?.remove();
    chip.querySelector(".measure-fields")?.remove();
    chip.querySelector(".counts-field")?.remove();
    return;
  }
  if (!measureOpen) return;
  const fields = chip.querySelector(".measure-fields");
  const next = measureFields();
  if (fields) fields.replaceWith(next);
  else chip.append(next);
  if (selection.measure !== "counts") return;
  const hint = chip.querySelector(".counts-hint");
  if (hint) hint.textContent = countsHint();
  else chip.append(countsField());
}

function measureChip(block) {
  const count = qubitCount();
  const open = measureOpen && count != null;
  return el(
    "div",
    { className: `chip tone-green measure${open ? " is-editing" : ""}` },
    el(
      "div",
      { className: "measure-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (open || qubitCount() == null) return;
            measureOpen = true;
            replaceChip(event.currentTarget, measureChip(block));
          },
        },
        el("strong", {}, block.title),
        el("span", { className: "measure-detail" }, measureDetail(count)),
      ),
      el(
        "div",
        { className: "measure-actions" },
        open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  measureOpen = false;
                  replaceChip(event.currentTarget, measureChip(block));
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${block.title}`,
            onclick: (event) => {
              event.stopPropagation();
              clearLane("measure");
            },
          },
          "×",
        ),
      ),
    ),
    open ? measureFields() : null,
    open && block.id === "counts" ? countsField() : null,
  );
}

function pathMessage(preview) {
  const missing = missingPaths();
  const tail = preview ? " to preview the script." : ".";
  if (missing.length === 2) return `Enter a save path and an export path${tail}`;
  if (missing[0] === "export") return `Enter an export path${tail}`;
  return `Enter a save path${tail}`;
}

function thenSummary() {
  const phrases = placedThens.map((id) => blockById("then", id)?.phrase).filter(Boolean);
  const nodes = [];
  phrases.forEach((phrase, index) => {
    if (index) nodes.push(index === phrases.length - 1 ? " and " : ", ");
    nodes.push(el("strong", {}, phrase));
  });
  return nodes;
}

function methodPhrase(entry) {
  const title = blockById("simulator", entry.id)?.title;
  if (!title) return null;
  const backend = blockById("backend", entry.backend);
  if (!isReference(entry) && backend) return `${title} on ${backend.phrase}`;
  return title;
}

function simulatorSummary() {
  const titles = placedSims.map(methodPhrase).filter(Boolean);
  if (!titles.length) return [];
  if (titles.length === 1) return [el("strong", {}, titles[0])];
  const nodes = [el("strong", {}, titles[0]), ", benchmarked against "];
  titles.slice(1).forEach((title, index, list) => {
    if (index) nodes.push(index === list.length - 1 ? " and " : ", ");
    nodes.push(el("strong", {}, title));
  });
  return nodes;
}

function laneById(laneId) {
  return LANES.find((lane) => lane.id === laneId);
}

function repaintSlot(laneId) {
  const current = document.querySelector(`.slot[data-slot="${laneId}"]`);
  const lane = laneById(laneId);
  if (current && lane) current.replaceWith(slotComponent(lane));
}

function repaintPalette(laneId) {
  const current = document.querySelector(`.lane[data-palette="${laneId}"]`);
  const lane = laneById(laneId);
  if (!current || !lane) return;
  current.replaceWith(paletteComponent(lane, (blockId) => place(lane.id, blockId)));
}

function commitLane(laneId, palette) {
  repaintSlot(laneId);
  if (palette) repaintPalette(laneId);
  refreshHamiltonianChips();
  refreshLocalHamiltonianChips();
  refreshSummaryAndPreview();
  clearResults();
}

function place(laneId, blockId) {
  if (running) return;
  const block = blockById(laneId, blockId);
  if (laneId === "model" && modelChoiceBlocked(block)) return;
  if (laneId === "simulator") {
    placedSims.push({
      id: blockId,
      key: ++simKey,
      params: freshParams(blockId),
      open: true,
      backend: null,
      shots: DEFAULT_SHOTS,
      shotsOpen: false,
    });
    selection.simulator = placedSims[0].id;
  } else if (laneId === "model" && block?.adds) {
    modelTerms.push({ id: blockId, key: ++modelTermKey, matrix: "", sites: [] });
  }
  else if (laneId === "model" && blockId === "preexisting") {
    selection.model = "preexisting";
    if (!preexistingId) preexistingId = modelFactories[0]?.id ?? null;
    preexistingOpen = true;
  } else if (laneId === "state") {
    selection.state = blockId;
    stateOpen = true;
  } else if (laneId === "measure") {
    selection.measure = blockId;
    measureOpen = qubitCount() != null;
  } else if (laneId === "then") {
    if (!placedThens.includes(blockId)) placedThens.push(blockId);
    selection.then = placedThens[0] ?? null;
    if (blockId === "save") saveOpen = true;
    if (blockId === "export") exportOpen = true;
  } else selection[laneId] = blockId;
  syncModelQubits();
  syncStateQubits();
  dragging = null;
  releaseStatusHold();
  commitLane(laneId, laneId === "model");
}

function removeThen(id) {
  if (running) return;
  const index = placedThens.indexOf(id);
  if (index >= 0) placedThens.splice(index, 1);
  selection.then = placedThens[0] ?? null;
  releaseStatusHold();
  commitLane("then");
}

function postedSelection() {
  const posted = { ...selection };
  delete posted.backend;
  return posted;
}

function attachBackend(backendId, key) {
  if (running) return;
  const backend = blockById("backend", backendId);
  if (!backend) return;
  const target =
    key == null
      ? placedSims.find((entry) => !isReference(entry) && !entry.backend && backendFits(entry, backendId))
      : placedSims.find((entry) => entry.key === key);
  if (!target || isReference(target) || !backendFits(target, backendId)) {
    const open = placedSims.filter((entry) => !isReference(entry) && (key == null ? !entry.backend : entry.key === key));
    const blocked = open.find((entry) => blockById("simulator", entry.id)?.samples && !backend.shots);
    const title = blocked ? blockById("simulator", blocked.id)?.title : null;
    if (title) statusHold = `${title} needs a backend with a shot budget.`;
    else if (!placedSims.some((entry) => !isReference(entry))) statusHold = "Place a simulator before its backend.";
    else statusHold = "Snap a backend onto an open simulator.";
    dragging = null;
    document.querySelectorAll?.(".is-over").forEach((node) => node.classList.remove("is-over"));
    setStatus(statusHold);
    return;
  }
  target.backend = backendId;
  if (backend.fields?.length) {
    target.backendFields = { ...(target.backendFields ?? {}) };
    for (const field of backend.fields) {
      if (!String(target.backendFields[field.name] ?? "").trim()) target.backendFields[field.name] = field.default;
    }
  }
  if (backend.shots) {
    if (!positiveIntText(String(target.shots ?? "").trim())) target.shots = DEFAULT_SHOTS;
    target.shotsOpen = true;
    target.backendOpen = false;
  } else if (backend.fields?.length) {
    target.shotsOpen = false;
    target.backendOpen = true;
  } else {
    target.shotsOpen = false;
    target.backendOpen = false;
  }
  dragging = null;
  releaseStatusHold();
  commitLane("simulator");
}

function removeBackend(key) {
  if (running) return;
  const entry = placedSims.find((item) => item.key === key);
  if (!entry) return;
  entry.backend = null;
  entry.shotsOpen = false;
  entry.backendOpen = false;
  releaseStatusHold();
  commitLane("simulator");
}

function removeSimulator(key) {
  if (running) return;
  const index = placedSims.findIndex((entry) => entry.key === key);
  if (index >= 0) placedSims.splice(index, 1);
  selection.simulator = placedSims[0]?.id ?? null;
  releaseStatusHold();
  commitLane("simulator");
}

function removeTerm(key) {
  if (running) return;
  const index = modelTerms.findIndex((term) => term.key === key);
  if (index >= 0) modelTerms.splice(index, 1);
  if (!modelTerms.some((term) => term.id === "hamiltonian") && qubitsSource === "hamiltonian") {
    settings.qubits = "";
    qubitsSource = null;
    syncMeasureChip();
    writeQubitField();
  } else syncHamiltonianQubits();
  releaseStatusHold();
  commitLane("model", true);
}

function clearLane(laneId) {
  if (running) return;
  if (laneId === "simulator") placedSims.splice(0, placedSims.length);
  if (laneId === "then") placedThens.splice(0, placedThens.length);
  if (laneId === "state") stateOpen = false;
  if (laneId === "measure") {
    measureOpen = false;
    measureSites = null;
  }
  if (laneId === "state" && qubitsSource === "state" && settings.qubits !== "") qubitsSource = "user";
  if (laneId === "model" && qubitsSource === "hamiltonian") {
    settings.qubits = "";
    qubitsSource = null;
    syncMeasureChip();
    writeQubitField();
  }
  if (laneId === "model" && qubitsSource === "model") {
    selection.model = null;
    syncModelQubits();
  }
  selection[laneId] = null;
  releaseStatusHold();
  commitLane(laneId, laneId === "model");
}

function copyStrings(value) {
  const copy = {};
  if (!value || typeof value !== "object") return copy;
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === "string") copy[key] = item;
  }
  return copy;
}

function storedText(value, fallback) {
  return typeof value === "string" ? value : fallback;
}

function storedSites(value) {
  if (!Array.isArray(value)) return null;
  return value.filter((site) => Number.isInteger(site));
}

function knownBlock(laneId, blockId) {
  return typeof blockId === "string" && Boolean(blockById(laneId, blockId));
}

function boardSnapshot() {
  return {
    version: BOARD_VERSION,
    server: serverSession,
    selection: {
      state: selection.state,
      model: selection.model,
      simulator: selection.simulator,
      backend: selection.backend,
      measure: selection.measure,
      then: selection.then,
    },
    settings: { qubits: settings.qubits, total: settings.total },
    basisBits,
    grayBits,
    angleText,
    amplitudeText,
    qubitsSource,
    preexistingId,
    emitterText,
    cavityText,
    hoppingText,
    factoryText: copyStrings(factoryText),
    modelTerms: modelTerms.map((term) => ({
      id: term.id,
      matrix: typeof term.matrix === "string" ? term.matrix : "",
      sites: Array.isArray(term.sites) ? term.sites.filter((site) => Number.isInteger(site)) : [],
    })),
    placedSims: placedSims.map((entry) => ({
      id: entry.id,
      params: copyStrings(entry.params),
      backend: entry.backend ?? null,
      shots: typeof entry.shots === "string" ? entry.shots : DEFAULT_SHOTS,
      backendFields: entry.backendFields ? copyStrings(entry.backendFields) : null,
    })),
    placedThens: [...placedThens],
    savePath,
    exportPath,
    measureSites: Array.isArray(measureSites) ? [...measureSites] : null,
    countsExpression,
  };
}

function applyBoard(snapshot) {
  if (!snapshot || typeof snapshot !== "object" || snapshot.version !== BOARD_VERSION) return false;
  if (!snapshot.selection || typeof snapshot.selection !== "object") return false;
  if (!snapshot.settings || typeof snapshot.settings !== "object") return false;

  let nextPreexisting = typeof snapshot.preexistingId === "string" ? snapshot.preexistingId : null;
  if (nextPreexisting && !modelFactories.some((item) => item.id === nextPreexisting)) nextPreexisting = null;
  let nextModel = null;
  if (snapshot.selection.model === "preexisting") nextModel = nextPreexisting ? "preexisting" : null;
  else if (typeof snapshot.selection.model === "string" && snapshot.selection.model) nextModel = snapshot.selection.model;

  const nextTerms = [];
  if (nextModel !== "preexisting" && Array.isArray(snapshot.modelTerms)) {
    for (const term of snapshot.modelTerms) {
      if (!term || !knownBlock("model", term.id) || !blockById("model", term.id)?.adds) continue;
      nextTerms.push({
        id: term.id,
        matrix: typeof term.matrix === "string" ? term.matrix : "",
        sites: storedSites(term.sites) ?? [],
      });
    }
  }

  const nextSims = [];
  if (Array.isArray(snapshot.placedSims)) {
    for (const entry of snapshot.placedSims) {
      if (!entry || !knownBlock("simulator", entry.id)) continue;
      const params = copyStrings(entry.params);
      const row = {
        id: entry.id,
        params: Object.keys(params).length ? params : freshParams(entry.id),
        open: false,
        backend: null,
        shots: storedText(entry.shots, DEFAULT_SHOTS),
        shotsOpen: false,
        backendOpen: false,
      };
      if (typeof entry.backend === "string" && backendFits(row, entry.backend)) {
        row.backend = entry.backend;
        if (entry.backendFields && typeof entry.backendFields === "object" && !Array.isArray(entry.backendFields)) {
          row.backendFields = copyStrings(entry.backendFields);
        }
      }
      nextSims.push(row);
    }
  }

  const nextThens = [];
  if (Array.isArray(snapshot.placedThens)) {
    for (const id of snapshot.placedThens) {
      if (knownBlock("then", id) && !nextThens.includes(id)) nextThens.push(id);
    }
  }

  const sources = ["user", "state", "hamiltonian", "model"];
  selection.state = knownBlock("state", snapshot.selection.state) ? snapshot.selection.state : null;
  selection.model = nextModel;
  selection.simulator = nextSims[0]?.id ?? null;
  selection.backend = null;
  selection.measure = knownBlock("measure", snapshot.selection.measure) ? snapshot.selection.measure : null;
  selection.then = nextThens[0] ?? null;
  settings.qubits = storedText(snapshot.settings.qubits, "");
  settings.total = storedText(snapshot.settings.total, "");
  basisBits = storedText(snapshot.basisBits, "");
  grayBits = storedText(snapshot.grayBits, "");
  angleText = storedText(snapshot.angleText, "");
  amplitudeText = storedText(snapshot.amplitudeText, "");
  qubitsSource = sources.includes(snapshot.qubitsSource) ? snapshot.qubitsSource : null;
  preexistingId = nextPreexisting;
  emitterText = storedText(snapshot.emitterText, "1");
  cavityText = storedText(snapshot.cavityText, "1");
  hoppingText = storedText(snapshot.hoppingText, "0");
  factoryText =
    snapshot.factoryText && typeof snapshot.factoryText === "object" && !Array.isArray(snapshot.factoryText)
      ? copyStrings(snapshot.factoryText)
      : {};
  modelTerms.splice(
    0,
    modelTerms.length,
    ...nextTerms.map((term) => ({ ...term, key: ++modelTermKey })),
  );
  placedSims.splice(
    0,
    placedSims.length,
    ...nextSims.map((entry) => ({ ...entry, key: ++simKey })),
  );
  placedThens.splice(0, placedThens.length, ...nextThens);
  savePath = storedText(snapshot.savePath, DEFAULT_SAVE_PATH);
  exportPath = storedText(snapshot.exportPath, DEFAULT_EXPORT_PATH);
  measureSites = storedSites(snapshot.measureSites);
  countsExpression = storedText(snapshot.countsExpression, "");
  stateOpen = false;
  measureOpen = false;
  saveOpen = false;
  exportOpen = false;
  preexistingOpen = false;
  return true;
}

function forgetBoard() {
  try {
    localStorage.removeItem(BOARD_KEY);
  } catch {
    // Storage can be unavailable.
  }
}

function restoreBoard() {
  let raw = null;
  try {
    raw = localStorage.getItem(BOARD_KEY);
  } catch {
    return;
  }
  if (!raw || !serverSession) {
    if (raw) forgetBoard();
    return;
  }
  try {
    const snapshot = JSON.parse(raw);
    if (!snapshot || snapshot.server !== serverSession) {
      forgetBoard();
      return;
    }
    applyBoard(snapshot);
  } catch {
    forgetBoard();
  }
}

function rememberBoard() {
  if (!boardReady || !serverSession) return;
  try {
    localStorage.setItem(BOARD_KEY, JSON.stringify(boardSnapshot()));
  } catch {
    // Storage can be unavailable. The page still runs.
  }
}

function emptyBoard() {
  if (running) return;
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
  releaseStatusHold();
  const board = document.querySelector(".board");
  if (board) draw(board);
}

async function loadSession() {
  try {
    const response = await fetch("/session");
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok || typeof payload.id !== "string" || !payload.id) return null;
    return payload.id;
  } catch {
    return null;
  }
}

function mount(root) {
  const board = el("section", { className: "board" });
  root.append(board);
  draw(board);
}

async function loadLane(path, lane, key) {
  try {
    const response = await fetch(path);
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    const items = payload[key];
    if (!response.ok || !Array.isArray(items)) {
      laneNotes[lane] = payload.error || `Could not load ${key}.`;
      BLOCKS[lane] = [];
      selection[lane] = null;
      return;
    }
    if (lane === "model") {
      modelFactories = items.filter((item) => !item.adds);
      BLOCKS.model = [
        {
          id: "preexisting",
          title: "Preexisting model",
          detail: "Choose a built-in model",
          phrase: "a preexisting model",
        },
        ...items.filter((item) => item.adds),
      ];
      if (preexistingId && !modelFactories.some((item) => item.id === preexistingId)) preexistingId = null;
    } else BLOCKS[lane] = items;
    laneNotes[lane] = "";
    if (selection[lane] != null && !blockById(lane, selection[lane])) selection[lane] = null;
  } catch {
    laneNotes[lane] = `Could not load ${key}.`;
    BLOCKS[lane] = [];
    selection[lane] = null;
  }
}

const builder = document.querySelector("#builder");
if (builder) {
  Promise.all([
    loadLane("/models", "model", "models"),
    loadLane("/simulators", "simulator", "simulators"),
    loadLane("/backends", "backend", "backends"),
    loadSession(),
  ]).then((results) => {
    serverSession = results[3];
    restoreBoard();
    boardReady = true;
    mount(builder);
  });
}
