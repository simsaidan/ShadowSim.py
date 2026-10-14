/* Builder page components. Placement is local to the page; Run does not call a backend. */

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
    hint: "The physics to simulate",
    pick: "Pick a model",
    tone: "teal",
  },
  {
    id: "simulator",
    title: "Simulator",
    hint: "The algorithm that runs it",
    pick: "Pick a simulator",
    tone: "blue",
  },
  {
    id: "then",
    title: "Then",
    hint: "What to do with the results",
    pick: "Pick a then",
    tone: "rose",
  },
];

const BLOCKS = {
  state: [
    { id: "basis", title: "Basis state", detail: "Start in |10>", phrase: "Basis state" },
    { id: "gray", title: "Gray code", detail: "Gray-coded bit string", phrase: "Gray code" },
    { id: "angle", title: "Angle", detail: "Rotation angles per qubit", phrase: "Angle" },
    { id: "amplitude", title: "Amplitude", detail: "Custom amplitudes, auto-padded", phrase: "Amplitude" },
  ],
  model: [
    {
      id: "tfim",
      title: "Transverse-field Ising",
      detail: "Closed chain, 4 qubits",
      phrase: "Transverse-field Ising",
    },
    { id: "classical", title: "Classical Ising", detail: "Closed chain, Z field", phrase: "Classical Ising" },
    { id: "tavis", title: "Tavis-Cummings", detail: "Open cavity with emitters", phrase: "Tavis-Cummings" },
  ],
  simulator: [
    { id: "qutip", title: "QuTiP", detail: "Classical reference. Open or closed", phrase: "QuTiP" },
    { id: "splitj", title: "Split JMatrix", detail: "Quantum-inspired. Open or closed", phrase: "Split JMatrix" },
    { id: "trotter", title: "Trotterization", detail: "Quantum-inspired. Closed only", phrase: "Trotterization" },
  ],
  then: [
    { id: "plot", title: "Plot results", detail: "Curves for each observable", phrase: "plot results" },
    {
      id: "compare",
      title: "Compare to QuTiP",
      detail: "Error metrics vs the reference",
      phrase: "compare to QuTiP",
    },
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

const STATE_LINES = {
  basis: "state = ComputationalBasisEncoding(2).encode([1, 0])",
  gray: "state = GrayEncoding(2).encode([1, 0])",
  angle: "state = AngleEncoding().encode([np.pi / 2, np.pi / 4])",
  amplitude: "state = AmplitudeEncoding().encode([1.0, 0.5, 0.25])",
};

const MODEL_LINES = {
  tfim: 'model = ising(n_qubits=4, J=1.0, h=0.5, field="transverse")',
  classical: 'model = ising(n_qubits=4, J=1.0, h=0.5, field="classical")',
  tavis: "model = tavis_cummings()",
};

const QUTIP_CALL = `sim = QutipSimulator(model.full_hamiltonians, model.c_ops_full, state,
                    model.e_ops, num_qubits=model.num_qubits,
                    total_time=2.0, time_steps=101)`;

const selection = {
  state: "basis",
  model: "tfim",
  simulator: "qutip",
  then: "save",
};

let dragging = null;

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

function isComplete() {
  return LANES.every((lane) => blockById(lane.id, selection[lane.id]));
}

function circuitCall(simulatorId) {
  if (simulatorId === "qutip") return QUTIP_CALL;
  const name = simulatorId === "splitj" ? "SplitJMatrixSimulator" : "TrotterizationSimulator";
  return `sim = ${name}(
    model.local_hamiltonians,
    model.c_ops_local,
    state,
    num_qubits=model.num_qubits,
    total_time=2.0,
    time_steps=101,
    num_steps=20,
    reducers=list(model.reducers),
)`;
}

function referenceCall() {
  return QUTIP_CALL.replace("sim = ", "reference = ");
}

function previewText() {
  if (!isComplete()) return "";
  const lines = [
    "import numpy as np",
    "from shadowsim.encoding import *",
    "from shadowsim.models import ising, tavis_cummings",
    "from shadowsim.simulators import *",
  ];
  if (selection.then === "compare" || selection.then === "export") {
    lines.push("from shadowsim.benchmarking import Benchmark");
  }
  lines.push("", STATE_LINES[selection.state], "", MODEL_LINES[selection.model], "", circuitCall(selection.simulator), "");
  if (selection.then === "plot") lines.push("sim.simulate()", "sim.plot_results()");
  else if (selection.then === "save") lines.push('sim.simulate().save("results/run1")');
  else if (selection.then === "compare") lines.push(referenceCall(), "Benchmark(reference, sim).run()");
  else lines.push(referenceCall(), 'Benchmark(reference, sim).save_error_metrics(output_dir="results")');
  return lines.join("\n");
}

function blockCard(lane, block, { inSlot, onPlace, onRemove }) {
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
      draggable: "true",
      "data-lane": lane.id,
      "data-block": block.id,
      ondragstart: (event) => {
        dragging = { lane: lane.id, id: block.id };
        event.dataTransfer.setData("text/plain", `${lane.id}:${block.id}`);
        event.dataTransfer.effectAllowed = "copy";
      },
      ondragend: () => {
        dragging = null;
      },
      onclick: () => onPlace(),
    },
    el("div", {}, el("strong", {}, block.title), el("span", {}, block.detail)),
  );
  return card;
}

function slotComponent(lane) {
  const chosen = blockById(lane.id, selection[lane.id]);
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
    chosen ? blockCard(lane, chosen, { inSlot: true, onRemove: () => clearLane(lane.id) }) : null,
  );
  return slot;
}

function paletteComponent(lane, onPlace) {
  return el(
    "section",
    { className: "lane", "data-palette": lane.id },
    el("h2", {}, lane.pick),
    el(
      "div",
      { className: "cards" },
      ...BLOCKS[lane.id].map((block) =>
        blockCard(lane, block, { inSlot: false, onPlace: () => onPlace(block.id) }),
      ),
    ),
  );
}

function summaryComponent() {
  if (!isComplete()) {
    return el("p", { className: "summary" }, "Place a block in each slot, then run.");
  }
  const state = blockById("state", selection.state);
  const model = blockById("model", selection.model);
  const simulator = blockById("simulator", selection.simulator);
  const action = blockById("then", selection.then);
  return el(
    "p",
    { className: "summary" },
    "Start from ",
    el("strong", {}, state.title),
    ", evolve the ",
    el("strong", {}, model.title),
    " model with ",
    el("strong", {}, simulator.title),
    ", then ",
    el("strong", {}, action.phrase),
    ".",
  );
}

function statusComponent() {
  const ready = isComplete();
  return el(
    "p",
    { className: ready ? "status ready" : "status", role: "status" },
    ready ? "Ready to run." : "Place a block in each slot.",
  );
}

function panelsComponent() {
  const code = previewText();
  return el(
    "div",
    { className: "panels" },
    el(
      "section",
      { className: "panel", "aria-label": "Code preview" },
      el("h2", {}, "Code preview"),
      code ? el("pre", {}, code) : el("p", { className: "placeholder" }, "Place a block in each slot to preview the script."),
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
    const chevron = el("div", { className: "chevron", "aria-hidden": "true" }, ">");
    chevron.style.gridColumn = String(2 + index * 2);
    chevron.style.gridRow = "1";
    layout.append(chevron);
  });
  const run = el("button", { className: "run", type: "button" }, "Run simulation");
  run.style.gridColumn = "9";
  run.style.gridRow = "1";
  layout.append(run);
  return layout;
}

function draw(board) {
  board.replaceChildren(
    el(
      "p",
      { className: "board-hint" },
      "Drag a block up into its slot, or tap it to place it. Blocks flow left to right.",
    ),
    layoutComponent(),
    summaryComponent(),
    statusComponent(),
    panelsComponent(),
  );
}

function place(laneId, blockId) {
  selection[laneId] = blockId;
  dragging = null;
  draw(document.querySelector(".board"));
}

function clearLane(laneId) {
  selection[laneId] = null;
  draw(document.querySelector(".board"));
}

function mount(root) {
  const board = el("section", { className: "board" });
  root.append(board);
  draw(board);
}

const builder = document.querySelector("#builder");
if (builder) mount(builder);
