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
    hint: "Combine any of the blocks below",
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
    pick: "Pick a then",
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
    { id: "z", title: "Pauli Z", detail: "Z on every qubit", phrase: "Pauli Z on every qubit" },
    { id: "x", title: "Pauli X", detail: "X on every qubit", phrase: "Pauli X on every qubit" },
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

const settings = { qubits: "", total: "" };
let basisBits = "";

let dragging = null;
let running = false;
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

function isComplete() {
  return LANES.every((lane) => {
    if (lane.id === "model" && selection.model === "preexisting") return Boolean(chosenFactory());
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

function needsBasisBits() {
  return selection.state === "basis" && basisBits === "";
}

function settingsReady() {
  return qubitPhrase() != null && settingNumber("total") != null && !needsBasisBits();
}

function stateLine() {
  if (selection.state !== "basis") return STATE_LINES[selection.state];
  const bits = [...basisBits].join(", ");
  return `state = ComputationalBasisEncoding(${basisBits.length}).encode([${bits}])`;
}

function fillSetup(block, name) {
  const qubits = settingNumber("qubits");
  const total = settingNumber("total");
  return block.setup
    .replaceAll("{name}", name)
    .replaceAll("{qubits}", qubits == null ? "" : String(Math.round(qubits)))
    .replaceAll("{total}", total == null ? "" : pyFloat(total));
}

function modelLine() {
  const factory = chosenFactory();
  return selection.model === "preexisting" && factory ? fillSetup(factory, "") : "";
}

function termLines() {
  const seen = {};
  return modelTerms.flatMap((term) => {
    const block = blockById("model", term.id);
    if (!block) return [];
    seen[term.id] = (seen[term.id] || 0) + 1;
    const suffix = seen[term.id] === 1 ? "" : `_${seen[term.id]}`;
    return [fillSetup(block, `${block.stem}${suffix}`)];
  });
}

function observableSetup() {
  const letter = selection.measure.toUpperCase();
  return `e_ops = [Operator("I" * i + "${letter}" + "I" * (model.num_qubits - i - 1))
         for i in range(model.num_qubits)]`;
}

function qutipCall(name) {
  return `${name} = QutipSimulator(model.full_hamiltonians, model.c_ops_full, state,
                    e_ops, num_qubits=model.num_qubits,
                    total_time=${pyFloat(settingNumber("total"))}, time_steps=101)`;
}

function backendSetup(backendId) {
  const block = blockById("backend", backendId);
  return block ? block.setup : "";
}

function circuitCall(simulatorId) {
  const block = blockById("simulator", simulatorId);
  return block ? fillSetup(block, "sim") : "";
}

function referenceCall() {
  const reference = BLOCKS.simulator.find((block) => block.observables);
  return reference ? fillSetup(reference, "reference") : qutipCall("reference");
}

function previewText() {
  if (!isComplete() || !settingsReady()) return "";
  const lines = [
    "import numpy as np",
    "from shadowsim.encoding import *",
    `from shadowsim.models import ${selection.model === "preexisting" ? preexistingId : selection.model}`,
    "from shadowsim.simulators import *",
  ];
  const symbols = [...new Set(modelTerms.map((term) => blockById("model", term.id)?.symbol).filter(Boolean))];
  if (symbols.length) lines.push(`from shadowsim.core import ${symbols.join(", ")}`);
  if (selection.then === "compare" || selection.then === "export") {
    lines.push("from shadowsim.benchmarking import Benchmark");
  }
  const simulator = blockById("simulator", selection.simulator);
  const beforeSimulator = ["", stateLine(), "", modelLine(), ...termLines(), ""];
  if (simulator && !simulator.observables) beforeSimulator.push(backendSetup(selection.backend), "");
  if (simulator && simulator.observables) beforeSimulator.push(observableSetup(), "");
  lines.push(...beforeSimulator, circuitCall(selection.simulator), "");
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

function preexistingChip() {
  const factory = chosenFactory();
  const select = el(
    "select",
    {
      "aria-label": "Model",
      onchange: (event) => {
        preexistingId = event.target.value;
        const detail = event.target.closest(".chip")?.querySelector(".preexisting-detail");
        const chosen = chosenFactory();
        if (detail && chosen) detail.textContent = chosen.title;
        refreshSummaryAndPreview();
      },
    },
    ...modelFactories.map((item) =>
      el("option", { value: item.id, selected: item.id === factory?.id }, item.title),
    ),
  );
  return el(
    "div",
    { className: "chip tone-teal preexisting" },
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
        el("span", { className: "preexisting-detail" }, factory?.title ?? ""),
      ),
      el(
        "div",
        { className: "preexisting-actions" },
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
  );
}

function applyBasisBits(raw) {
  basisBits = raw.replace(/[^01]/g, "").slice(0, 15);
  settings.qubits = basisBits ? String(basisBits.length) : "";
  const qubitsInput = document.querySelector('input[aria-label="Qubits"]');
  if (qubitsInput && qubitsInput.value !== settings.qubits) qubitsInput.value = settings.qubits;
  const detail = document.querySelector(".basis-detail");
  if (detail) detail.textContent = basisBits ? `Start in |${basisBits}>` : "0s and 1s, up to 15";
  const alert = document.querySelector(".basis-alert");
  if (alert) alert.hidden = Boolean(basisBits);
  refreshSummaryAndPreview();
}

function basisChip() {
  const input = el("input", {
    type: "text",
    inputmode: "numeric",
    maxlength: "15",
    "aria-label": "Basis bits",
    value: basisBits,
    spellcheck: "false",
    autocomplete: "off",
    oninput: (event) => {
      const next = event.target.value.replace(/[^01]/g, "").slice(0, 15);
      if (event.target.value !== next) event.target.value = next;
      applyBasisBits(next);
    },
  });
  return el(
    "div",
    { className: "chip tone-gold basis" },
    el(
      "div",
      { className: "basis-head" },
      el(
        "div",
        {},
        el("strong", {}, "Basis state"),
        el("span", { className: "basis-detail" }, basisBits ? `Start in |${basisBits}>` : "0s and 1s, up to 15"),
      ),
      el(
        "div",
        { className: "basis-actions" },
        el(
          "span",
          {
            className: "basis-alert",
            role: "img",
            "aria-label": "Enter a bit string",
            title: "Enter a bit string",
            hidden: Boolean(basisBits),
          },
          "!",
        ),
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": "Remove Basis state",
            onclick: (event) => {
              event.stopPropagation();
              clearLane("state");
            },
          },
          "×",
        ),
      ),
    ),
    el("label", { className: "basis-field" }, "Bits", input),
  );
}

function slotChips(lane) {
  const chips = [];
  const chosen = blockById(lane.id, selection[lane.id]);
  if (chosen && !chosen.adds) {
    if (chosen.id === "preexisting") chips.push(preexistingChip());
    else if (chosen.id === "basis") chips.push(basisChip());
    else chips.push(blockCard(lane, chosen, { inSlot: true, onRemove: () => clearLane(lane.id) }));
  }
  if (lane.id !== "model") return chips;
  for (const term of modelTerms) {
    const block = blockById("model", term.id);
    if (!block) continue;
    chips.push(blockCard(lane, block, { inSlot: true, onRemove: () => removeTerm(term.key) }));
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
  const model = selection.model === "preexisting" ? chosenFactory() : blockById("model", selection.model);
  const simulator = blockById("simulator", selection.simulator);
  const backend = blockById("backend", selection.backend);
  const measure = blockById("measure", selection.measure);
  const action = blockById("then", selection.then);
  const qubits = qubitPhrase();
  const total = formatSetting("total");
  return el(
    "p",
    { className: "summary" },
    "Start from ",
    el("strong", {}, state.title),
    ", evolve the ",
    el("strong", {}, model.title),
    " model",
    ...termSummary(),
    " with ",
    el("strong", {}, simulator.title),
    " on ",
    el("strong", {}, backend.phrase),
    ", measure ",
    el("strong", {}, measure.phrase),
    ", then ",
    el("strong", {}, action.phrase),
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
        readonly: key === "qubits" && selection.state === "basis",
        oninput: (event) => {
          if (key === "qubits" && selection.state === "basis") return;
          settings[key] = event.target.value.trim();
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
    el("button", { className: "run", type: "button", onclick: () => void startRun() }, "Run simulation"),
  );
}

function refreshSummaryAndPreview() {
  const summary = document.querySelector(".summary");
  if (summary) summary.replaceWith(summaryComponent());
  if (!running) {
    const status = document.querySelector(".status");
    if (status) status.replaceWith(statusComponent());
  }
  const panel = document.querySelector('.panel[aria-label="Code preview"]');
  const body = panel?.querySelector("pre, .placeholder");
  if (body) body.replaceWith(codeBody());
}

function statusMessage() {
  if (!isComplete()) return "Place a block in each slot.";
  if (needsBasisBits()) return "Enter a basis bit string and total time.";
  if (!settingsReady()) return "Enter qubits and total time.";
  return "Ready to run.";
}

function statusComponent() {
  const ready = isComplete() && settingsReady();
  return el(
    "p",
    { className: ready ? "status ready" : "status", role: "status" },
    statusMessage(),
  );
}

function codeBody() {
  const code = previewText();
  if (code) return el("pre", {}, code);
  let message = "Place a block in each slot to preview the script.";
  if (isComplete()) {
    message = needsBasisBits()
      ? "Enter a basis bit string and total time to preview the script."
      : "Enter qubits and total time to preview the script.";
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
  const body = panel?.querySelector(":scope > .placeholder, :scope > .chart");
  if (body) body.replaceWith(node);
}

function formatAxis(value) {
  if (!Number.isFinite(value)) return "";
  if (Number.isInteger(value)) return String(value);
  return String(Math.round(value * 1000) / 1000);
}

function chartComponent(payload) {
  const times = Array.isArray(payload.times) ? payload.times : [];
  const curves = Array.isArray(payload.observables) ? payload.observables : [];
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
    for (const value of curve) {
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
      curve.map((value, point) => `${sx(times[point])},${sy(value)}`).join(" "),
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
      ...curves.map((_, index) =>
        el(
          "li",
          {},
          el("i", { style: `background:${CURVE_COLORS[index % CURVE_COLORS.length]}` }),
          `Observable ${index}`,
        ),
      ),
    ),
  );
}

async function startRun() {
  if (running || !isComplete() || !settingsReady()) return;
  running = true;
  const button = document.querySelector(".run");
  if (button) button.disabled = true;
  setStatus("Running.");
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
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      setResults(el("p", { className: "placeholder" }, payload.error || "The run failed."));
      return;
    }
    setResults(chartComponent(payload));
  } catch {
    setResults(el("p", { className: "placeholder" }, "The run failed."));
  } finally {
    running = false;
    const run = document.querySelector(".run");
    if (run) run.disabled = false;
    setStatus(statusMessage(), isComplete() && settingsReady());
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

function place(laneId, blockId) {
  if (running) return;
  const block = blockById(laneId, blockId);
  if (laneId === "model" && block?.adds) modelTerms.push({ id: blockId, key: ++modelTermKey });
  else if (laneId === "model" && blockId === "preexisting") {
    selection.model = "preexisting";
    if (!preexistingId) preexistingId = modelFactories[0]?.id ?? null;
    preexistingOpen = true;
  } else selection[laneId] = blockId;
  if (selection.state === "basis") settings.qubits = basisBits ? String(basisBits.length) : "";
  dragging = null;
  draw(document.querySelector(".board"));
}

function removeTerm(key) {
  if (running) return;
  const index = modelTerms.findIndex((term) => term.key === key);
  if (index >= 0) modelTerms.splice(index, 1);
  draw(document.querySelector(".board"));
}

function clearLane(laneId) {
  if (running) return;
  selection[laneId] = null;
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
