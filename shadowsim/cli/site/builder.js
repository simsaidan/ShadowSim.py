/* Builder page. Model, simulator, and backend cards come from the package. */

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
    title: "Simulator",
    hint: "The first block is the reference",
    pick: "Add a simulator",
    tone: "blue",
  },
  {
    id: "backend",
    title: "Backend",
    hint: "Where the circuit runs",
    pick: "Pick a backend",
    tone: "violet",
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
const MAX_EMITTERS = 13;

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
let measureOpen = false;
let measureSites = null;
const DEFAULT_SHOTS = "256";
let shots = DEFAULT_SHOTS;
let shotsOpen = false;

let dragging = null;
let running = false;
let statusHold = null;
let runStartedAt = 0;
let runTimer = null;
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

function blockById(laneId, blockId) {
  return BLOCKS[laneId].find((block) => block.id === blockId) ?? null;
}

function chosenFactory() {
  return modelFactories.find((item) => item.id === preexistingId) ?? null;
}

function operatorsReady() {
  if (selection.model === "preexisting" || !modelTerms.length) return false;
  if (modelTerms.some((term) => termProblem(term))) return false;
  return modelTerms.some((term) => term.id === "hamiltonian" || term.id === "local_hamiltonian");
}

function usingAddedOperators() {
  return selection.model !== "preexisting" && modelTerms.length > 0;
}

function termProblem(term) {
  if (term.id === "hamiltonian") return hamiltonianProblem(term);
  if (term.id === "local_hamiltonian") return localHamiltonianProblem(term);
  if (term.id === "lindblad") return lindbladProblem(term);
  return "Unknown operator.";
}

function otherSlotsPlaced() {
  return LANES.every((lane) => lane.id === "model" || blockById(lane.id, selection[lane.id]));
}

function operatorStatus(preview) {
  if (!otherSlotsPlaced() || !usingAddedOperators() || operatorsReady()) return null;
  const tail = preview ? " to preview the script." : ".";
  const hasHamiltonian = modelTerms.some((term) => term.id === "hamiltonian" || term.id === "local_hamiltonian");
  return hasHamiltonian ? `Enter a valid operator${tail}` : `Enter a Hamiltonian${tail}`;
}

function isComplete() {
  return LANES.every((lane) => {
    if (lane.id === "model" && selection.model === "preexisting") return Boolean(chosenFactory());
    if (lane.id === "model") return operatorsReady();
    return blockById(lane.id, selection[lane.id]);
  });
}

function settingNumber(key) {
  if (settings[key] === "") return null;
  const value = Number(settings[key]);
  return Number.isFinite(value) ? value : null;
}

function formatSetting(key) {
  const value = settingNumber(key);
  if (value == null) return null;
  return Object.is(value, -0) ? "0" : String(value);
}

function qubitPhrase() {
  const label = formatSetting("qubits");
  if (label == null) return null;
  return Number(label) === 1 ? "1 qubit" : `${label} qubits`;
}

function pyFloat(value) {
  return Number.isInteger(value) ? `${value}.0` : String(value);
}

function stateOwnsQubits() {
  return Object.hasOwn(STATE_LIMITS, selection.state);
}

function numberList(raw, maxCount) {
  const text = raw.trim();
  if (!text || text.endsWith(",")) return null;
  const parts = text.split(",").map((part) => part.trim());
  if (!parts.length || parts.length > maxCount) return null;
  const values = [];
  for (const part of parts) {
    if (!/^-?(?:\d+(?:\.\d+)?|\.\d+)$/.test(part)) return null;
    values.push(Number(part));
  }
  return values;
}

function amplitudeQubits(count) {
  let padded = 1;
  while (padded < count) padded *= 2;
  return Math.log2(Math.max(2, padded));
}

function stateValues() {
  if (selection.state === "angle") return numberList(angleText, STATE_LIMITS.angle);
  if (selection.state === "amplitude") return numberList(amplitudeText, STATE_LIMITS.amplitude);
  return null;
}

function emitterCount() {
  const text = emitterText.trim();
  if (!positiveIntText(text)) return null;
  const count = Number(text);
  return count <= MAX_EMITTERS ? count : null;
}

function cavityModelSelected() {
  return (
    selection.model === "preexisting" &&
    (preexistingId === "jaynes_cummings" || preexistingId === "tavis_cummings")
  );
}

function fixedFactoryQubits() {
  if (selection.model !== "preexisting") return null;
  if (preexistingId === "jaynes_cummings") return 3;
  if (preexistingId === "tavis_cummings") {
    const count = emitterCount();
    return count == null ? null : 2 + count;
  }
  return null;
}

function emitterProblem() {
  return selection.model === "preexisting" && preexistingId === "tavis_cummings" && emitterCount() == null;
}

function stateImpliedQubits() {
  if (selection.state === "basis") return basisBits ? basisBits.length : null;
  if (selection.state === "gray") return grayBits ? grayBits.length : null;
  if (selection.state === "angle") return numberList(angleText, STATE_LIMITS.angle)?.length ?? null;
  if (selection.state === "amplitude") {
    const values = numberList(amplitudeText, STATE_LIMITS.amplitude);
    if (values && values.some((value) => value !== 0)) return amplitudeQubits(values.length);
  }
  return null;
}

function stateSizeProblem() {
  const expected = fixedFactoryQubits();
  if (expected == null) return null;
  const actual = stateImpliedQubits();
  if (actual == null || actual === expected) return null;
  return expected;
}

function stateSizeStatus(preview) {
  const expected = stateSizeProblem();
  const tail = preview ? " to preview the script." : ".";
  if (selection.state === "basis") return `Enter a ${expected}-bit basis string${tail}`;
  if (selection.state === "gray") return `Enter a ${expected}-bit Gray code string${tail}`;
  if (selection.state === "angle") return `Enter ${expected} angles${tail}`;
  return `Enter amplitudes for ${expected} qubits${tail}`;
}

function stateInputProblem() {
  if (stateSizeProblem() != null) return "size";
  if (selection.state === "basis") return basisBits === "" ? "basis" : null;
  if (selection.state === "gray") return grayBits === "" ? "gray" : null;
  if (selection.state === "angle") return numberList(angleText, STATE_LIMITS.angle) ? null : "angle";
  if (selection.state === "amplitude") {
    const values = numberList(amplitudeText, STATE_LIMITS.amplitude);
    if (!values || values.every((value) => value === 0)) return "amplitude";
  }
  return null;
}

function positiveIntText(value) {
  return /^[1-9]\d*$/.test(value);
}

function freshParams(id) {
  if (id === "qutip") return { timeSteps: "101" };
  const params = { timeSteps: "11", numSteps: "4", trotterDepth: "1", seed: "0", order: "1" };
  return params;
}

function entryParamsReady(entry) {
  const params = entry.params;
  if (!positiveIntText(params.timeSteps)) return false;
  if (entry.id === "qutip") return true;
  if (!positiveIntText(params.numSteps) || !positiveIntText(params.trotterDepth)) return false;
  if (!/^-?\d+$/.test(params.seed)) return false;
  return params.order === "1" || params.order === "2";
}

function simParamsReady() {
  return placedSims.every(entryParamsReady);
}

function sameTimeGrid() {
  if (placedSims.length < 2) return true;
  const steps = placedSims[0].params.timeSteps;
  return placedSims.every((entry) => entry.params.timeSteps === steps);
}

function hasThen(id) {
  return placedThens.includes(id);
}

function missingPaths() {
  const missing = [];
  if (hasThen("save") && savePath.trim() === "") missing.push("save");
  if (hasThen("export") && exportPath.trim() === "") missing.push("export");
  return missing;
}

function savePathReady() {
  return missingPaths().length === 0;
}

function qubitCount() {
  const value = settingNumber("qubits");
  if (value == null || !Number.isInteger(value) || value < 1) return null;
  return value;
}

function selectedSites(count) {
  if (count == null) return [];
  if (measureSites == null) return Array.from({ length: count }, (_, index) => index);
  return measureSites.filter((site) => Number.isInteger(site) && site >= 0 && site < count);
}

function usesShots() {
  return Boolean(blockById("backend", selection.backend)?.shots);
}

function shotsReady() {
  return !usesShots() || positiveIntText(shots.trim());
}

function measureSitesReady() {
  const count = qubitCount();
  if (!selection.measure || count == null) return true;
  return selectedSites(count).length > 0;
}

function pyString(value) {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function settingsReady() {
  return (
    qubitPhrase() != null &&
    settingNumber("total") != null &&
    stateInputProblem() == null &&
    simParamsReady() &&
    sameTimeGrid() &&
    savePathReady() &&
    measureSitesReady() &&
    shotsReady() &&
    !emitterProblem() &&
    (!usingAddedOperators() || operatorsReady())
  );
}

function stateLine() {
  if (selection.state === "basis" || selection.state === "gray") {
    const bits = selection.state === "basis" ? basisBits : grayBits;
    const name = selection.state === "basis" ? "ComputationalBasisEncoding" : "GrayEncoding";
    return `state = ${name}(${bits.length}).encode([${[...bits].join(", ")}])`;
  }
  const values = stateValues();
  if (!values) return "";
  const rendered = values.map(pyFloat).join(", ");
  if (selection.state === "angle") return `state = AngleEncoding().encode([${rendered}])`;
  if (selection.state === "amplitude") return `state = AmplitudeEncoding().encode([${rendered}])`;
  return "";
}

function fillSetup(block, name) {
  const qubits = settingNumber("qubits");
  const total = settingNumber("total");
  return block.setup
    .replaceAll("{name}", name)
    .replaceAll("{qubits}", qubits == null ? "" : String(Math.round(qubits)))
    .replaceAll("{total}", total == null ? "" : pyFloat(total))
    .replaceAll("{shots}", shots.trim());
}

function modelLine() {
  const factory = chosenFactory();
  if (selection.model === "preexisting" && preexistingId === "tavis_cummings" && emitterCount() != null) {
    return `model = tavis_cummings(n_emitters=${emitterCount()})`;
  }
  if (selection.model === "preexisting" && factory) return fillSetup(factory, "");
  return usingAddedOperators() ? addedOperatorLines() : "";
}

function matrixLiteral(term) {
  const parsed = term.id === "lindblad" ? squareMatrix(term.matrix ?? "") : inspectMatrix(term.matrix ?? "");
  const rows = parsed.matrix.map((row) => `[${row.map(pyComplex).join(", ")}]`).join(", ");
  return `np.array([${rows}], dtype=complex)`;
}

function addedOperatorLines() {
  const count = qubitCount();
  const seen = {};
  const lines = [];
  const qutip = [];
  const circuit = [];
  const lindblads = [];
  modelTerms.forEach((term) => {
    const block = blockById("model", term.id);
    if (!block || termProblem(term)) return;
    seen[term.id] = (seen[term.id] || 0) + 1;
    const suffix = seen[term.id] === 1 ? "" : `_${seen[term.id]}`;
    const name = `${block.stem}${suffix}`;
    const matrix = matrixLiteral(term);
    if (term.id === "hamiltonian") {
      lines.push(`${name} = Hamiltonian(${matrix})`);
      qutip.push(name);
      circuit.push(`${name}.to_local_hamiltonian()`);
    } else if (term.id === "local_hamiltonian") {
      const sites = localSites(term, count).join(", ");
      lines.push(`${name} = LocalHamiltonian(${matrix}, [${sites}])`);
      qutip.push(name);
      circuit.push(name);
    } else if (term.id === "lindblad") {
      const sites = localSites(term, count).join(", ");
      lines.push(`${name} = LocalOperator(${matrix}, [${sites}])`);
      lindblads.push(name);
    }
  });
  lines.push(`qutip_hamiltonians = [${qutip.join(", ")}]`);
  lines.push(`circuit_hamiltonians = [${circuit.join(", ")}]`);
  lines.push(`lindblads = [${lindblads.join(", ")}]`);
  lines.push(`lindblads_full = [op.to_full_operator(${count}) for op in lindblads]`);
  return lines.join("\n");
}

function postedTerms() {
  if (!operatorsReady()) return undefined;
  return modelTerms.map((term) => {
    const parsed = term.id === "lindblad" ? squareMatrix(term.matrix ?? "") : inspectMatrix(term.matrix ?? "");
    const body = {
      id: term.id,
      matrix: parsed.matrix.map((row) => row.map((value) => [value.re, value.im])),
    };
    if (term.id !== "hamiltonian") body.sites = localSites(term, qubitCount());
    return body;
  });
}

function pyComplex(value) {
  if (value.im === 0) return pyFloat(value.re);
  const imag = `${pyFloat(Math.abs(value.im))}j`;
  const signed = value.im < 0 ? `-${imag}` : imag;
  if (value.re === 0) return signed;
  return `(${pyFloat(value.re)}${value.im < 0 ? "" : "+"}${signed})`;
}

function termLines() {
  if (usingAddedOperators()) return [];
  const seen = {};
  return modelTerms.flatMap((term) => {
    const block = blockById("model", term.id);
    if (!block) return [];
    seen[term.id] = (seen[term.id] || 0) + 1;
    const suffix = seen[term.id] === 1 ? "" : `_${seen[term.id]}`;
    const name = `${block.stem}${suffix}`;
    if (term.id === "lindblad") {
      if (lindbladProblem(term)) return [fillSetup(block, name)];
      const parsed = squareMatrix(term.matrix ?? "");
      const rows = parsed.matrix.map((row) => `[${row.map(pyComplex).join(", ")}]`).join(", ");
      const sites = localSites(term, qubitCount()).join(", ");
      return [`${name} = LocalOperator(np.array([${rows}], dtype=complex), [${sites}])`];
    }
    if (term.id !== "hamiltonian" && term.id !== "local_hamiltonian") return [fillSetup(block, name)];
    const inspected = inspectMatrix(term.matrix ?? "");
    const localProblem = term.id === "local_hamiltonian" && localHamiltonianProblem(term);
    if (inspected.problem || localProblem) return [fillSetup(block, name)];
    const rows = inspected.matrix.map((row) => `[${row.map(pyComplex).join(", ")}]`).join(", ");
    const matrix = `np.array([${rows}], dtype=complex)`;
    if (term.id === "hamiltonian") return [`${name} = Hamiltonian(${matrix})`];
    const sites = localSites(term, qubitCount()).join(", ");
    return [`${name} = LocalHamiltonian(${matrix}, [${sites}])`];
  });
}

function observableSetup() {
  const letter = selection.measure.toUpperCase();
  const count = qubitCount();
  const sites = selectedSites(count);
  if (count == null || sites.length === count) {
    const countName = systemQubits();
    return `e_ops = [Operator("I" * i + "${letter}" + "I" * (${countName} - i - 1))
         for i in range(${countName})]`;
  }
  const operators = sites.map((site) => {
    const label = `${"I".repeat(site)}${letter}${"I".repeat(count - site - 1)}`;
    return `Operator(${pyString(label)})`;
  });
  return `e_ops = [${operators.join(", ")}]`;
}

function systemQubits() {
  return usingAddedOperators() ? String(qubitCount()) : "model.num_qubits";
}

function qutipCall(name, params) {
  const hamiltonians = usingAddedOperators() ? "qutip_hamiltonians" : "model.full_hamiltonians";
  const lindblads = usingAddedOperators() ? "lindblads_full" : "model.c_ops_full";
  return `${name} = QutipSimulator(${hamiltonians}, ${lindblads}, state,
                    e_ops, num_qubits=${systemQubits()},
                    total_time=${pyFloat(settingNumber("total"))}, time_steps=${params.timeSteps})`;
}

function entryBody(entry) {
  const params = entry.params;
  const body = { simulator: entry.id, time_steps: params.timeSteps };
  if (entry.id === "qutip") return body;
  body.num_steps = params.numSteps;
  body.trotter_depth = params.trotterDepth;
  body.seed = params.seed;
  body.order = params.order;
  return body;
}

function simulatorCall(entry, name) {
  const params = entry.params;
  const block = blockById("simulator", entry.id);
  if (!params || !block) return "";
  if (block.observables) return qutipCall(name, params);
  const className = entry.id === "trotterization" ? "TrotterizationSimulator" : "SplitJMatrixSimulator";
  const offset = entry.id === "splitjmatrix" ? 1 : 0;
  const groups = selectedSites(qubitCount()).map((site) => `[${site + offset}]`);
  const orderLine = `,\n    order=${params.order}`;
  const expectation = selection.measure === "x" ? "expectation_x" : "expectation_z";
  const sites = selectedSites(qubitCount());
  const xLine = selection.measure === "x" ? `,\n    x_qubits=[${sites.join(", ")}]` : "";
  const hamiltonians = usingAddedOperators() ? "circuit_hamiltonians" : "model.local_hamiltonians";
  const lindblads = usingAddedOperators() ? "lindblads" : "model.c_ops_local";
  return `${name} = ${className}(
    ${hamiltonians},
    ${lindblads},
    state,
    num_qubits=${systemQubits()},
    total_time=${pyFloat(settingNumber("total"))},
    time_steps=${params.timeSteps},
    num_steps=${params.numSteps},
    trotter_depth=${params.trotterDepth}${orderLine},
    seed=${params.seed},
    measurement_groups=[${groups.join(", ")}],
    reducers=[${expectation}] * ${groups.length}${xLine},
    circuit_backend=circuit_backend,
)`;
}

function backendClass(backendId) {
  const setup = blockById("backend", backendId)?.setup ?? "";
  return setup.match(/circuit_backend = ([A-Za-z0-9_]+)/)?.[1] ?? "";
}

function backendSetup(backendId) {
  const block = blockById("backend", backendId);
  return block ? fillSetup(block, "") : "";
}

function previewText() {
  if (!isComplete() || !settingsReady()) return "";
  const lines = [
    "import numpy as np",
    "from shadowsim.encoding import *",
  ];
  if (selection.model === "preexisting") lines.push(`from shadowsim.models import ${preexistingId}`);
  else if (selection.model) lines.push(`from shadowsim.models import ${selection.model}`);
  lines.push("from shadowsim.simulators import *");
  const backendName = backendClass(selection.backend);
  if (placedSims.some((entry) => !blockById("simulator", entry.id)?.observables) && backendName) {
    lines.push(`from shadowsim.backends import ${backendName}`);
  }
  const symbols = [...new Set(modelTerms.map((term) => blockById("model", term.id)?.symbol).filter(Boolean))];
  if (placedSims.some((entry) => blockById("simulator", entry.id)?.observables)) symbols.push("Operator");
  if (modelTerms.some((term) => term.id === "lindblad" && !lindbladProblem(term))) symbols.push("LocalOperator");
  if (symbols.length) lines.push(`from shadowsim.core import ${symbols.join(", ")}`);
  const benchmark = placedSims.length >= 2;
  if (benchmark) lines.push("from shadowsim.benchmarking import Benchmark");
  const beforeSimulator = ["", stateLine(), "", modelLine(), ...termLines(), ""];
  if (placedSims.some((entry) => !blockById("simulator", entry.id)?.observables)) {
    beforeSimulator.push(backendSetup(selection.backend), "");
  }
  if (placedSims.some((entry) => blockById("simulator", entry.id)?.observables)) {
    beforeSimulator.push(observableSetup(), "");
  }
  const names = placedSims.map((_, index) => (benchmark ? `sim_${index + 1}` : "sim"));
  lines.push(...beforeSimulator, ...placedSims.map((entry, index) => simulatorCall(entry, names[index])), "");
  lines.push(...(benchmark ? benchmarkThenLines(names) : singleThenLines()));
  return lines.join("\n");
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
  if (preexistingId === "tavis_cummings") {
    const count = emitterCount();
    if (count == null) return "Set the emitter count";
    const qubits = 2 + count;
    return count === 1 ? `1 emitter, ${qubits} qubits` : `${count} emitters, ${qubits} qubits`;
  }
  return chosenFactory()?.title ?? "";
}

function refreshCavityModel() {
  syncModelQubits();
  const detail = document.querySelector(".preexisting-detail");
  if (detail) detail.textContent = preexistingDetail();
  const alert = document.querySelector(".preexisting-alert");
  if (alert) alert.hidden = !emitterProblem();
  if (selection.state) refreshStateChip(selection.state);
  else refreshSummaryAndPreview();
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
        draw(document.querySelector(".board"));
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
  return el(
    "div",
    { className: `chip tone-teal preexisting${preexistingOpen ? " is-editing" : ""}` },
    el(
      "div",
      { className: "preexisting-head" },
      el(
        "div",
        {
          onclick: () => {
            if (preexistingOpen) return;
            preexistingOpen = true;
            draw(document.querySelector(".board"));
          },
        },
        el("strong", {}, "Preexisting model"),
        el("span", { className: "preexisting-detail" }, preexistingDetail()),
      ),
      el(
        "div",
        { className: "preexisting-actions" },
        preexistingId === "tavis_cummings"
          ? el(
              "span",
              {
                className: "basis-alert preexisting-alert",
                role: "img",
                "aria-label": "Enter an emitter count from 1 to 13.",
                title: "Enter an emitter count from 1 to 13.",
                hidden: !emitterProblem(),
              },
              "!",
            )
          : null,
        preexistingOpen
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: () => {
                  preexistingOpen = false;
                  draw(document.querySelector(".board"));
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
    preexistingOpen && preexistingId === "tavis_cummings"
      ? el("label", { className: "preexisting-field" }, "Emitters", emitters)
      : null,
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
  if (qubitsInput && qubitsInput.value !== settings.qubits) qubitsInput.value = settings.qubits;
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
    } else qubitsSource = settings.qubits === "" ? null : "user";
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
    { className: `chip tone-gold ${options.id} is-editing` },
    el(
      "div",
      { className: "basis-head" },
      el("div", {}, el("strong", {}, options.title), el("span", { className: "basis-detail" }, stateDetail(options.id))),
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
    el("label", { className: "basis-field" }, options.field, input),
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
  if (entry.id !== "qutip") {
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
        "div",
        {
          onclick: () => {
            if (entry.open) return;
            entry.open = true;
            draw(document.querySelector(".board"));
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
                onclick: () => {
                  entry.open = false;
                  draw(document.querySelector(".board"));
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

function benchmarkThenLines(names) {
  const lines = [`benchmark = Benchmark(${names.join(", ")})`, "benchmark.run()"];
  if (hasThen("plot")) lines.push("benchmark.save_result_plot()");
  if (hasThen("save")) {
    names.forEach((name) => {
      lines.push(`${name}.last_result.save(${pyString(`${savePath.trim()}/${name}`)})`);
    });
  }
  if (hasThen("export")) lines.push(exportCall());
  return lines;
}

function singleThenLines() {
  const save = `result.save(${pyString(savePath.trim())})`;
  if (hasThen("save") && hasThen("plot")) return ["result = sim.simulate()", save, "sim.plot_results()"];
  if (hasThen("save")) return [`sim.simulate().save(${pyString(savePath.trim())})`];
  if (hasThen("plot")) return ["sim.simulate()", "sim.plot_results()"];
  return ["result = sim.simulate()"];
}

function exportCall() {
  const directory = exportPath.trim();
  const target = directory.endsWith(".json")
    ? `path=${pyString(directory)}`
    : `output_dir=${pyString(directory)}`;
  return `benchmark.save_error_metrics(${target})`;
}

function pathChip(block, options) {
  const shown = options.path.trim();
  return el(
    "div",
    { className: `chip tone-rose ${options.kind}${options.open ? " is-editing" : ""}` },
    el(
      "div",
      { className: `${options.kind}-head` },
      el(
        "div",
        {
          onclick: () => {
            if (options.open) return;
            options.setOpen(true);
            draw(document.querySelector(".board"));
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
                onclick: () => {
                  options.setOpen(false);
                  draw(document.querySelector(".board"));
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

function backendChip(block) {
  const samples = Boolean(block.shots);
  const editing = samples && shotsOpen;
  const shown = samples && positiveIntText(shots.trim()) ? `${shots.trim()} shots` : block.detail;
  return el(
    "div",
    { className: `chip tone-violet backend${editing ? " is-editing" : ""}` },
    el(
      "div",
      { className: "backend-head" },
      el(
        "div",
        {
          onclick: () => {
            if (!samples || editing) return;
            shotsOpen = true;
            draw(document.querySelector(".board"));
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
                onclick: () => {
                  shotsOpen = false;
                  draw(document.querySelector(".board"));
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
              clearLane("backend");
            },
          },
          "×",
        ),
      ),
    ),
    editing
      ? el(
          "label",
          { className: "backend-field" },
          "Shots",
          el("input", {
            type: "text",
            inputmode: "numeric",
            "aria-label": "Shots",
            value: shots,
            spellcheck: "false",
            oninput: (event) => {
              const next = event.target.value.replace(/\D/g, "");
              if (event.target.value !== next) event.target.value = next;
              shots = next;
              const detail = event.target.closest(".chip")?.querySelector(".backend-detail");
              if (detail) detail.textContent = positiveIntText(shots.trim()) ? `${shots.trim()} shots` : block.detail;
              refreshSummaryAndPreview();
            },
          }),
        )
      : null,
  );
}

function readNumber(source, index) {
  const match = source.slice(index).match(/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)/);
  if (!match) return null;
  return { value: Number(match[0]), next: index + match[0].length };
}

function skipSpaces(source, index) {
  while (/\s/.test(source[index] ?? "")) index += 1;
  return index;
}

function parseComplex(source, index) {
  const lone = source.slice(index).match(/^[+-]?j/i);
  const number = readNumber(source, index);
  if (lone && (!number || lone[0].length < number.next - index)) {
    return { re: 0, im: lone[0].startsWith("-") ? -1 : 1, next: index + lone[0].length };
  }
  if (!number) return null;
  let cursor = skipSpaces(source, number.next);
  if ((source[cursor] ?? "").toLowerCase() === "j") return { re: 0, im: number.value, next: cursor + 1 };
  const imag = source.slice(cursor).match(/^([+-])\s*(?:(\d+(?:\.\d*)?|\.\d+)\s*)?j/i);
  if (!imag) return { re: number.value, im: 0, next: number.next };
  const magnitude = imag[2] == null ? 1 : Number(imag[2]);
  return { re: number.value, im: imag[1] === "-" ? -magnitude : magnitude, next: cursor + imag[0].length };
}

function parseMatrix(text) {
  const source = text.trim();
  if (!source) return { error: "empty" };
  let index = 0;
  function skip() {
    while (/\s/.test(source[index] ?? "")) index += 1;
  }
  function parseList() {
    skip();
    if (source[index] !== "[") return null;
    index += 1;
    skip();
    const items = [];
    if (source[index] === "]") {
      index += 1;
      return items;
    }
    while (index < source.length) {
      skip();
      const item = source[index] === "[" ? parseList() : parseComplex(source, index);
      if (!item) return null;
      if (item.next) index = item.next;
      items.push(item.next ? { re: item.re, im: item.im } : item);
      skip();
      if (source[index] === ",") {
        index += 1;
        continue;
      }
      if (source[index] === "]") {
        index += 1;
        return items;
      }
      return null;
    }
    return null;
  }
  const value = parseList();
  skip();
  if (!value || index !== source.length || value.some((row) => !Array.isArray(row))) return { error: "shape" };
  const width = value.length;
  if (!width || value.some((row) => row.length !== width || row.some((cell) => Array.isArray(cell)))) {
    return { error: "shape" };
  }
  return { matrix: value };
}

function nearly(left, right) {
  return Math.abs(left - right) <= 1e-8 + 1e-5 * Math.max(Math.abs(left), Math.abs(right));
}

function isHermitian(matrix) {
  return matrix.every((row, rowIndex) =>
    row.every((value, columnIndex) => {
      const mirror = matrix[columnIndex][rowIndex];
      return nearly(value.re, mirror.re) && nearly(value.im, -mirror.im);
    }),
  );
}

function squareMatrix(text) {
  const parsed = parseMatrix(text ?? "");
  if (parsed.error === "empty") return { problem: "Enter a matrix." };
  if (parsed.error) return { problem: "Enter a square matrix." };
  const { matrix } = parsed;
  const size = matrix.length;
  if (size > 256) return { problem: "At most 8 qubits." };
  if (size < 2 || (size & (size - 1)) !== 0) return { problem: "Size must be a power of two." };
  return { matrix, qubits: Math.log2(size) };
}

function inspectMatrix(text) {
  const parsed = squareMatrix(text);
  if (parsed.problem) return parsed;
  if (!isHermitian(parsed.matrix)) return { problem: "Matrix must be Hermitian." };
  return parsed;
}

function fixedQubitCount() {
  if (stateOwnsQubits() || qubitsSource === "user") return qubitCount();
  return null;
}

function hamiltonianProblem(term) {
  const inspected = inspectMatrix(term.matrix);
  if (inspected.problem) return inspected.problem;
  const fixed = fixedQubitCount();
  if (fixed != null && inspected.qubits !== fixed) {
    const side = 2 ** fixed;
    const label = fixed === 1 ? "qubit" : "qubits";
    return `Must be ${side}×${side} for ${fixed} ${label}.`;
  }
  if (fixed == null && new Set(validHamiltonianQubits()).size > 1) return "Matrices must be the same size.";
  return null;
}

function validHamiltonianQubits() {
  return modelTerms.flatMap((term) => {
    if (term.id !== "hamiltonian") return [];
    const inspected = inspectMatrix(term.matrix);
    return inspected.problem ? [] : [inspected.qubits];
  });
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
  const qubitsInput = document.querySelector('input[aria-label="Qubits"]');
  if (qubitsInput && qubitsInput.value !== settings.qubits) qubitsInput.value = settings.qubits;
  refreshLocalHamiltonianChips();
}

function refreshHamiltonianChips() {
  document.querySelectorAll(".chip.hamiltonian").forEach((chip) => {
    const term = modelTerms.find((item) => item.key === Number(chip.dataset.key));
    if (!term) return;
    const detail = chip.querySelector(".hamiltonian-detail");
    const alert = chip.querySelector(".basis-alert");
    if (detail) detail.textContent = hamiltonianDetail(term);
    if (alert) alert.hidden = !hamiltonianProblem(term);
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
  const problem = hamiltonianProblem(term);
  return el(
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
        el(
          "span",
          {
            className: "basis-alert",
            role: "img",
            "aria-label": "Enter a Hermitian matrix",
            title: "Enter a Hermitian matrix",
            hidden: !problem,
          },
          "!",
        ),
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
}

function localSites(term, count) {
  return (term.sites ?? [])
    .filter((site) => Number.isInteger(site) && site >= 0 && site < count)
    .sort((left, right) => left - right);
}

function actedQubitProblem(term, parse) {
  const count = qubitCount();
  if (count == null) return "Set qubits first.";
  const sites = localSites(term, count);
  if (!sites.length) return "Pick at least one qubit.";
  if (sites[sites.length - 1] - sites[0] + 1 !== sites.length) return "Qubits must be contiguous.";
  const inspected = parse(term.matrix);
  if (inspected.problem) return inspected.problem;
  if (inspected.qubits !== sites.length) {
    const side = 2 ** sites.length;
    const label = sites.length === 1 ? "qubit" : "qubits";
    return `Must be ${side}×${side} for ${sites.length} ${label}.`;
  }
  return null;
}

function localHamiltonianProblem(term) {
  return actedQubitProblem(term, inspectMatrix);
}

function lindbladProblem(term) {
  return actedQubitProblem(term, squareMatrix);
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

function refreshLocalHamiltonianChips() {
  document.querySelectorAll(".chip.local-hamiltonian, .chip.lindblad").forEach((chip) => {
    const term = modelTerms.find((item) => item.key === Number(chip.dataset.key));
    if (!term) return;
    const count = qubitCount();
    if (count != null) term.sites = localSites(term, count);
    const open = count != null;
    chip.classList.toggle("is-editing", open);
    const detail = chip.querySelector(".hamiltonian-detail");
    const alert = chip.querySelector(".basis-alert");
    const problem = term.id === "lindblad" ? lindbladProblem(term) : localHamiltonianProblem(term);
    if (detail) detail.textContent = actedQubitDetail(term);
    if (alert) alert.hidden = !open || !problem;
    const fields = chip.querySelector(".local-fields");
    if (!open) {
      fields?.remove();
      return;
    }
    if (!fields) chip.append(localFields(term));
    else fields.querySelector(".measure-fields")?.replaceWith(localSiteFields(term));
  });
}

function actedQubitChip(term) {
  const open = qubitCount() != null;
  const lindblad = term.id === "lindblad";
  const problem = lindblad ? lindbladProblem(term) : localHamiltonianProblem(term);
  const title = lindblad ? "Add a Lindblad operator" : "Add a Local Hamiltonian";
  return el(
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
        el(
          "span",
          {
            className: "basis-alert",
            role: "img",
            "aria-label": lindblad ? "Enter a Lindblad operator" : "Enter a local Hamiltonian",
            title: lindblad ? "Enter a Lindblad operator" : "Enter a local Hamiltonian",
            hidden: !open || !problem,
          },
          "!",
        ),
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
    else if (lane.id === "backend") chips.push(backendChip(chosen));
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
      const chip = simulatorChip(entry);
      if (chip) chips.push(chip);
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

function slotComponent(lane) {
  const slot = el(
    "section",
    {
      className: `slot tone-${lane.tone}`,
      "data-slot": lane.id,
      ondragover: (event) => {
        if (!dragging || dragging.lane !== lane.id) return;
        event.preventDefault();
        slot.classList.add("is-over");
      },
      ondragleave: () => slot.classList.remove("is-over"),
      ondrop: (event) => {
        if (!dragging || dragging.lane !== lane.id) return;
        event.preventDefault();
        place(lane.id, dragging.id);
      },
    },
    el("h2", {}, lane.title),
    el("p", { className: "hint" }, lane.hint),
    ...slotChips(lane),
  );
  return slot;
}

function paletteComponent(lane, onPlace) {
  const note = laneNotes[lane.id] ? el("p", { className: "hint" }, laneNotes[lane.id]) : null;
  return el(
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
  );
}

function summaryComponent() {
  if (!isComplete()) {
    return el("p", { className: "summary" }, "Place a block in each slot, then run.");
  }
  const state = blockById("state", selection.state);
  const model = selection.model === "preexisting" ? chosenFactory() : null;
  const backend = blockById("backend", selection.backend);
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
    " on ",
    el("strong", {}, backend.phrase),
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
    el("button", {
      className: "run",
      type: "button",
      onclick: () => void (running ? cancelRun() : startRun()),
    }, running ? "Cancel" : "Run simulation"),
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
}

function statusMessage() {
  if (statusHold) return statusHold;
  if (!isComplete()) return operatorStatus(false) ?? "Place a block in each slot.";
  if (emitterProblem()) return "Enter an emitter count.";
  if (stateInputProblem() === "size") return stateSizeStatus(false);
  if (stateInputProblem() === "basis") return "Enter a basis bit string and total time.";
  if (stateInputProblem() === "gray") return "Enter a Gray code bit string and total time.";
  if (stateInputProblem() === "angle") return "Enter one angle per qubit and total time.";
  if (stateInputProblem() === "amplitude") return "Enter a non-zero amplitude list and total time.";
  if (qubitPhrase() == null || settingNumber("total") == null) return "Enter qubits and total time.";
  if (!simParamsReady()) return "Enter simulator parameters.";
  if (!sameTimeGrid()) return "Use the same number of time steps for every simulator.";
  if (!measureSitesReady()) return "Pick at least one qubit.";
  if (!shotsReady()) return "Enter a shot count.";
  if (!savePathReady()) return pathMessage(false);
  return "Ready to run.";
}

function statusComponent() {
  const ready = !statusHold && isComplete() && settingsReady();
  return el(
    "p",
    { className: ready ? "status ready" : "status", role: "status" },
    statusMessage(),
  );
}

function codeBody() {
  const code = previewText();
  if (code) return el("pre", {}, code);
  let message = operatorStatus(true) ?? "Place a block in each slot to preview the script.";
  if (isComplete()) {
    if (emitterProblem()) message = "Enter an emitter count to preview the script.";
    else if (stateInputProblem() === "size") message = stateSizeStatus(true);
    else if (stateInputProblem() === "basis") message = "Enter a basis bit string and total time to preview the script.";
    else if (stateInputProblem() === "gray") message = "Enter a Gray code bit string and total time to preview the script.";
    else if (stateInputProblem() === "angle") message = "Enter one angle per qubit and total time to preview the script.";
    else if (stateInputProblem() === "amplitude") {
      message = "Enter a non-zero amplitude list and total time to preview the script.";
    }
    else if (qubitPhrase() == null || settingNumber("total") == null) {
      message = "Enter qubits and total time to preview the script.";
    } else if (!simParamsReady()) message = "Enter simulator parameters to preview the script.";
    else if (!sameTimeGrid()) message = "Use the same number of time steps to preview the script.";
    else if (!measureSitesReady()) message = "Pick at least one qubit to preview the script.";
    else if (!shotsReady()) message = "Enter a shot count to preview the script.";
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

function formatAxis(value) {
  if (!Number.isFinite(value)) return "";
  if (Number.isInteger(value)) return String(value);
  return String(Math.round(value * 1000) / 1000);
}

function chartCurves(payload) {
  if (Array.isArray(payload.series) && payload.series.length) {
    const curves = [];
    for (const series of payload.series) {
      const observables = Array.isArray(series.observables) ? series.observables : [];
      observables.forEach((values, index) => curves.push({ label: `${series.name} ${index}`, values }));
    }
    return curves;
  }
  const observables = Array.isArray(payload.observables) ? payload.observables : [];
  return observables.map((values, index) => ({ label: `Observable ${index}`, values }));
}

function formatMetric(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return String(Math.round(number * 10000) / 10000);
}

function metricsComponent(errors) {
  if (!Array.isArray(errors) || !errors.length) return null;
  const items = [];
  for (const challenger of errors) {
    const name = String(challenger.challenger_id || "").replace(/_simulator$/, "");
    for (const observable of challenger.observables || []) {
      items.push(
        el(
          "li",
          {},
          `${name} observable ${observable.index}: max ${formatMetric(observable.linf)}, RMSE ${formatMetric(observable.rmse)}`,
        ),
      );
    }
  }
  return el("div", {}, el("p", { className: "hint" }, "Error against the first simulator"), el("ul", { className: "legend" }, ...items));
}

function savedNote(payload) {
  const notes = [];
  const saved = Array.isArray(payload.saved) ? payload.saved.filter((item) => typeof item === "string") : [];
  if (saved.length) notes.push(`Saved to ${saved.join(", ")}`);
  if (typeof payload.exported === "string" && payload.exported) notes.push(`Exported to ${payload.exported}`);
  if (!notes.length) return null;
  return el("p", { className: "hint" }, notes.join(". "));
}

function resultsComponent(payload) {
  const note = savedNote(payload);
  const metrics = metricsComponent(payload.errors);
  const chart = chartComponent(payload);
  if (!note && !metrics) return chart;
  return el("div", { className: "results" }, note, metrics, chart);
}

function chartComponent(payload) {
  const times = Array.isArray(payload.times) ? payload.times : [];
  const curves = chartCurves(payload);
  if (!times.length || !curves.length) {
    return el("p", { className: "placeholder" }, "The run returned no curves.");
  }
  const width = 640;
  const height = 220;
  const pad = 28;
  const first = Number(times[0]);
  const last = Number(times[times.length - 1]);
  let yMin = Infinity;
  let yMax = -Infinity;
  for (const curve of curves) {
    for (const value of curve.values) {
      const y = Number(value);
      if (!Number.isFinite(y)) continue;
      yMin = Math.min(yMin, y);
      yMax = Math.max(yMax, y);
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
  const sx = (time) => pad + ((Number(time) - first) / xSpan) * (width - pad * 2);
  const sy = (value) => height - pad - ((Number(value) - yMin) / ySpan) * (height - pad * 2);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "plot");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Observable curves");
  const axis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  axis.setAttribute("x1", String(pad));
  axis.setAttribute("x2", String(width - pad));
  axis.setAttribute("y1", String(height - pad));
  axis.setAttribute("y2", String(height - pad));
  svg.append(axis);
  curves.forEach((curve, index) => {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", CURVE_COLORS[index % CURVE_COLORS.length]);
    line.setAttribute("stroke-width", "2");
    line.setAttribute(
      "points",
      curve.values.map((value, point) => `${sx(times[point])},${sy(value)}`).join(" "),
    );
    svg.append(line);
  });
  const startLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  startLabel.setAttribute("x", String(pad));
  startLabel.setAttribute("y", String(height - 8));
  startLabel.textContent = formatAxis(first);
  const endLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  endLabel.setAttribute("x", String(width - pad));
  endLabel.setAttribute("y", String(height - 8));
  endLabel.setAttribute("text-anchor", "end");
  endLabel.textContent = formatAxis(last);
  svg.append(startLabel, endLabel);
  return el(
    "div",
    { className: "chart" },
    svg,
    el(
      "ul",
      { className: "legend" },
      ...curves.map((curve, index) =>
        el(
          "li",
          {},
          el("i", { style: `background:${CURVE_COLORS[index % CURVE_COLORS.length]}` }),
          curve.label,
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

function setRunButton(label) {
  const button = document.querySelector(".run");
  if (!button) return;
  button.disabled = false;
  button.textContent = label;
}

async function cancelRun() {
  if (!running) return;
  try {
    await fetch("/runs/cancel", { method: "POST" });
  } catch {
    // The run request stays open and reports the outcome.
  }
}

async function startRun() {
  if (running || !isComplete() || !settingsReady()) return;
  running = true;
  releaseStatusHold();
  runStartedAt = Date.now();
  setRunButton("Cancel");
  showRunningClock();
  runTimer = setInterval(showRunningClock, 1000);
  setResults(el("p", { className: "placeholder" }, "Running."));
  try {
    const response = await fetch("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...selection,
        model: selection.model === "preexisting" ? preexistingId : selection.model,
        qubits: settings.qubits,
        total: settings.total,
        basis: basisBits,
        gray: grayBits,
        angles: numberList(angleText, STATE_LIMITS.angle),
        amplitudes: numberList(amplitudeText, STATE_LIMITS.amplitude),
        sites: explicitSites(),
        ...(placedSims[0] ? entryBody(placedSims[0]) : {}),
        simulators: placedSims.map(entryBody),
        then: placedThens[0] ?? null,
        thens: [...placedThens],
        save_path: savePath.trim(),
        export_path: exportPath.trim(),
        shots: shots.trim(),
        terms: postedTerms(),
        ...(selection.model === "preexisting" && preexistingId === "tavis_cummings"
          ? { emitters: emitterCount() }
          : {}),
      }),
    });
    const payload = await response.json();
    if (payload.cancelled) {
      statusHold = "Cancelled.";
      setResults(el("p", { className: "placeholder" }, statusHold));
      return;
    }
    if (!response.ok) {
      statusHold = payload.error || "The run failed.";
      setResults(el("p", { className: "placeholder" }, statusHold));
      return;
    }
    releaseStatusHold();
    setResults(resultsComponent(payload));
  } catch {
    statusHold = "The run failed.";
    setResults(el("p", { className: "placeholder" }, statusHold));
  } finally {
    stopRunClock();
    running = false;
    setRunButton("Run simulation");
    if (statusHold) setStatus(statusHold);
    else setStatus(statusMessage(), isComplete() && settingsReady());
  }
}

function panelsComponent() {
  return el(
    "div",
    { className: "panels" },
    el(
      "section",
      { className: "panel", "aria-label": "Code preview" },
      el("h2", {}, "Code preview"),
      codeBody(),
    ),
    el(
      "section",
      { className: "panel", "aria-label": "Results" },
      el("h2", {}, "Results"),
      el("p", { className: "placeholder" }, "Run a simulation to see results here."),
    ),
  );
}

function layoutComponent() {
  const layout = el("div", { className: "layout" });
  LANES.forEach((lane, index) => {
    const column = String(1 + index * 2);
    const slot = slotComponent(lane);
    slot.style.gridColumn = column;
    slot.style.gridRow = "1";
    const palette = paletteComponent(lane, (blockId) => place(lane.id, blockId));
    palette.style.gridColumn = column;
    palette.style.gridRow = "2";
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
  board.replaceChildren(
    layoutComponent(),
    settingsComponent(),
    summaryComponent(),
    statusComponent(),
    panelsComponent(),
  );
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
            const detail = event.target.closest(".chip")?.querySelector(".measure-detail");
            if (detail) detail.textContent = measureDetail(qubitCount());
            refreshSummaryAndPreview();
          },
        }),
        String(site),
      ),
    );
  }
  return el("div", { className: "measure-fields" }, ...boxes);
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
    return;
  }
  if (!measureOpen) return;
  const fields = chip.querySelector(".measure-fields");
  const next = measureFields();
  if (fields) fields.replaceWith(next);
  else chip.append(next);
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
        "div",
        {
          onclick: () => {
            if (open || qubitCount() == null) return;
            measureOpen = true;
            draw(document.querySelector(".board"));
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
                onclick: () => {
                  measureOpen = false;
                  draw(document.querySelector(".board"));
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

function simulatorSummary() {
  const titles = placedSims.map((entry) => blockById("simulator", entry.id)?.title).filter(Boolean);
  if (!titles.length) return [];
  if (titles.length === 1) return [el("strong", {}, titles[0])];
  const nodes = [el("strong", {}, titles[0]), ", benchmarked against "];
  titles.slice(1).forEach((title, index, list) => {
    if (index) nodes.push(index === list.length - 1 ? " and " : ", ");
    nodes.push(el("strong", {}, title));
  });
  return nodes;
}

function place(laneId, blockId) {
  if (running) return;
  const block = blockById(laneId, blockId);
  if (laneId === "model" && modelChoiceBlocked(block)) return;
  if (laneId === "simulator") {
    placedSims.push({ id: blockId, key: ++simKey, params: freshParams(blockId), open: true });
    selection.simulator = placedSims[0].id;
  } else if (laneId === "model" && block?.adds) {
    modelTerms.push({ id: blockId, key: ++modelTermKey, matrix: "", sites: [] });
  }
  else if (laneId === "model" && blockId === "preexisting") {
    selection.model = "preexisting";
    if (!preexistingId) preexistingId = modelFactories[0]?.id ?? null;
    preexistingOpen = true;
  } else if (laneId === "measure") {
    selection.measure = blockId;
    measureOpen = qubitCount() != null;
  } else if (laneId === "backend") {
    selection.backend = blockId;
    shotsOpen = Boolean(block?.shots);
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
  draw(document.querySelector(".board"));
}

function removeThen(id) {
  if (running) return;
  const index = placedThens.indexOf(id);
  if (index >= 0) placedThens.splice(index, 1);
  selection.then = placedThens[0] ?? null;
  releaseStatusHold();
  draw(document.querySelector(".board"));
}

function removeSimulator(key) {
  if (running) return;
  const index = placedSims.findIndex((entry) => entry.key === key);
  if (index >= 0) placedSims.splice(index, 1);
  selection.simulator = placedSims[0]?.id ?? null;
  releaseStatusHold();
  draw(document.querySelector(".board"));
}

function removeTerm(key) {
  if (running) return;
  const index = modelTerms.findIndex((term) => term.key === key);
  if (index >= 0) modelTerms.splice(index, 1);
  if (!modelTerms.some((term) => term.id === "hamiltonian") && qubitsSource === "hamiltonian") {
    settings.qubits = "";
    qubitsSource = null;
  } else syncHamiltonianQubits();
  releaseStatusHold();
  draw(document.querySelector(".board"));
}

function clearLane(laneId) {
  if (running) return;
  if (laneId === "simulator") placedSims.splice(0, placedSims.length);
  if (laneId === "then") placedThens.splice(0, placedThens.length);
  if (laneId === "backend") shotsOpen = false;
  if (laneId === "measure") {
    measureOpen = false;
    measureSites = null;
  }
  if (laneId === "state" && qubitsSource === "state" && settings.qubits !== "") qubitsSource = "user";
  if (laneId === "model" && qubitsSource === "hamiltonian") {
    settings.qubits = "";
    qubitsSource = null;
  }
  if (laneId === "model" && qubitsSource === "model") {
    selection.model = null;
    syncModelQubits();
  }
  selection[laneId] = null;
  releaseStatusHold();
  draw(document.querySelector(".board"));
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
  ]).then(() => mount(builder));
}
