const { catalog, loadPage } = require("./load-page");
const { click, installDownloads, setChange, setChecked, settle, typeInto } = require("./dom");

const QUTIP_SETUP = [
  "{name} = QutipSimulator({hamiltonians}, {lindblads}, state,",
  "                    e_ops, num_qubits={qubits},",
  "                    total_time={total}, time_steps={time_steps})",
].join("\n");

const CIRCUIT_SETUP = [
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
].join("\n");

function prepare() {
  const loaded = loadPage();
  const exported = catalog();
  const { page } = loaded;
  if (!page.applyLimits(exported.limits)) throw new Error("missing limits");
  page.state.blocks.state = structuredClone(exported.states);
  page.state.blocks.measure = structuredClone(exported.measures);
  page.state.blocks.then = structuredClone(exported.actions);
  return loaded;
}

function resetPage(page) {
  page.state.selection.state = null;
  page.state.selection.model = null;
  page.state.selection.simulator = null;
  page.state.selection.backend = null;
  page.state.selection.measure = null;
  page.state.selection.then = null;
  page.state.settings.qubits = "";
  page.state.settings.total = "";
  for (const key of Object.keys(page.state.stateText)) delete page.state.stateText[key];
  page.state.qubitsSource = null;
  page.state.preexistingId = null;
  page.state.factoryText = {};
  page.state.modelTerms.splice(0, page.state.modelTerms.length);
  page.state.placedSims.splice(0, page.state.placedSims.length);
  page.state.placedThens.splice(0, page.state.placedThens.length);
  for (const key of Object.keys(page.state.actionText)) delete page.state.actionText[key];
  for (const key of Object.keys(page.state.pathOpen)) delete page.state.pathOpen[key];
  for (const block of page.state.blocks.then) {
    if (block.field?.kind === "path") page.state.actionText[block.id] = block.field.default;
  }
  page.state.measureSites = null;
  for (const key of Object.keys(page.state.expressionText)) delete page.state.expressionText[key];
  page.state.stateOpen = false;
  page.state.measureOpen = false;
  page.state.preexistingOpen = false;
  page.state.boardReady = false;
}

function fillIsing(page) {
  resetPage(page);
  page.state.blocks.simulator = [
    {
      id: "qutip",
      title: "QuTiP",
      observables: true,
      detail: "Reference",
      setup: QUTIP_SETUP,
      fields: [
        {
          name: "time_steps",
          label: "Time steps",
          kind: "integer",
          default: "11",
          minimum: 1,
          maximum: page.state.limits.timeSteps,
        },
      ],
    },
  ];
  page.state.blocks.model = [
    { id: "preexisting", title: "Preexisting model", detail: "Choose a built-in model" },
  ];
  page.state.modelFactories = [
    { id: "ising", title: "Ising", qubits: true, setup: "model = ising(n_qubits={qubits})" },
  ];
  page.state.preexistingId = "ising";
  page.state.selection.state = "basis";
  page.state.selection.model = "preexisting";
  page.state.selection.simulator = "qutip";
  page.state.selection.then = "plot";
  page.state.stateText.basis = "01";
  page.state.settings.qubits = "2";
  page.state.settings.total = "1";
  page.state.qubitsSource = "state";
  page.state.actionText.save = "results/kept";
  page.state.placedSims.push({ id: "qutip", key: 3, open: true, params: { time_steps: "11" } });
  page.state.placedThens.push("plot");
  page.useFactoryMeasure();
}

function fillCircuit(page) {
  fillIsing(page);
  page.state.blocks.simulator = [
    {
      id: "trotterization",
      title: "Trotterization",
      observables: false,
      detail: "",
      setup: CIRCUIT_SETUP,
      fields: [
        {
          name: "time_steps",
          label: "Time steps",
          kind: "integer",
          default: "11",
          minimum: 1,
          maximum: page.state.limits.timeSteps,
        },
        {
          name: "num_steps",
          label: "Product steps",
          kind: "integer",
          default: "4",
          minimum: 1,
          maximum: page.state.limits.numSteps,
        },
        {
          name: "trotter_depth",
          label: "Trotter depth",
          kind: "integer",
          default: "1",
          minimum: 1,
          maximum: page.state.limits.trotterDepth,
        },
        { name: "order", label: "Order", kind: "choice", default: "1", choices: ["1", "2"] },
        { name: "seed", label: "Seed", kind: "integer", default: "0" },
      ],
    },
  ];
  page.state.blocks.backend = [
    {
      id: "aer",
      phrase: "Aer",
      shots: true,
      setup: "circuit_backend = AerCircuitBackend(shots={shots})",
    },
  ];
  page.state.blocks.model = [
    { id: "preexisting", title: "Preexisting model", detail: "" },
    { id: "hamiltonian", title: "Hamiltonian", adds: true, detail: "" },
  ];
  page.state.selection.simulator = "trotterization";
  page.state.placedSims.splice(0, page.state.placedSims.length, {
    id: "trotterization",
    key: 1,
    params: { time_steps: "11", num_steps: "4", trotter_depth: "1", seed: "0", order: "1" },
    backend: "aer",
    shots: "256",
  });
}

function mount(window) {
  const board = window.document.createElement("section");
  board.className = "board";
  window.document.documentElement.append(board);
  return board;
}

function labeled(root, label) {
  return root.querySelector(`input[aria-label="${label}"], select[aria-label="${label}"]`);
}

function chipByClass(root, kind) {
  return [...root.querySelectorAll(".chip")].find((node) => node.classList.contains(kind));
}

function active(root) {
  return root.ownerDocument.activeElement;
}

function openChip(root, kind) {
  const chip = chipByClass(root, kind);
  click(chip.children[0].children[0]);
  return chipByClass(root, kind);
}

function resultsNode(window) {
  const panel = window.document.querySelector('.panel[aria-label="Results"]');
  return panel.querySelector(":scope > .placeholder, :scope > .chart, :scope > .results");
}

function showingPlaceholder(window) {
  const node = resultsNode(window);
  return (
    node.className === "placeholder" && node.textContent === "Run a simulation to see results here."
  );
}

function staleBanner(window) {
  const node = resultsNode(window);
  return node?.querySelector(":scope > .stale") ?? null;
}

function operatorAlert(chip) {
  const alert = chip.querySelector(".chip-alert");
  const field = chip.querySelector("textarea");
  const describedby = field?.getAttribute("aria-describedby") ?? null;
  return {
    label: alert.getAttribute("aria-label") || null,
    title: alert.getAttribute("title") || null,
    hidden: alert.hidden === true,
    linked: describedby != null && describedby === alert.getAttribute("id"),
    describedby,
  };
}

function toggleSite(chip, site, checked) {
  const kind = chip.classList.contains("lindblad") ? "Lindblad" : "Local";
  const box = chip.querySelector(`[aria-label="${kind} qubit ${site}"]`);
  setChecked(box, checked);
}

function optionValue(select) {
  const option = [...select.children].find((child) => child.hasAttribute("selected"));
  return option ? option.getAttribute("value") : null;
}

module.exports = {
  active,
  catalog,
  chipByClass,
  click,
  fillCircuit,
  fillIsing,
  installDownloads,
  labeled,
  mount,
  openChip,
  operatorAlert,
  optionValue,
  prepare,
  resetPage,
  resultsNode,
  setChange,
  setChecked,
  settle,
  showingPlaceholder,
  staleBanner,
  toggleSite,
  typeInto,
};
