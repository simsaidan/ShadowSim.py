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
  page.BLOCKS.state = structuredClone(exported.states);
  page.BLOCKS.measure = structuredClone(exported.measures);
  page.BLOCKS.then = structuredClone(exported.actions);
  return loaded;
}

function resetPage(page) {
  page.selection.state = null;
  page.selection.model = null;
  page.selection.simulator = null;
  page.selection.backend = null;
  page.selection.measure = null;
  page.selection.then = null;
  page.settings.qubits = "";
  page.settings.total = "";
  for (const key of Object.keys(page.stateText)) delete page.stateText[key];
  page.qubitsSource = null;
  page.preexistingId = null;
  page.factoryText = {};
  page.modelTerms.splice(0, page.modelTerms.length);
  page.placedSims.splice(0, page.placedSims.length);
  page.placedThens.splice(0, page.placedThens.length);
  for (const key of Object.keys(page.actionText)) delete page.actionText[key];
  for (const key of Object.keys(page.pathOpen)) delete page.pathOpen[key];
  for (const block of page.BLOCKS.then) {
    if (block.field?.kind === "path") page.actionText[block.id] = block.field.default;
  }
  page.measureSites = null;
  for (const key of Object.keys(page.expressionText)) delete page.expressionText[key];
  page.stateOpen = false;
  page.measureOpen = false;
  page.preexistingOpen = false;
  page.boardReady = false;
}

function fillIsing(page) {
  resetPage(page);
  page.BLOCKS.simulator = [
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
          maximum: page.limits.timeSteps,
        },
      ],
    },
  ];
  page.BLOCKS.model = [
    { id: "preexisting", title: "Preexisting model", detail: "Choose a built-in model" },
  ];
  page.modelFactories = [
    { id: "ising", title: "Ising", qubits: true, setup: "model = ising(n_qubits={qubits})" },
  ];
  page.preexistingId = "ising";
  page.selection.state = "basis";
  page.selection.model = "preexisting";
  page.selection.simulator = "qutip";
  page.selection.then = "plot";
  page.stateText.basis = "01";
  page.settings.qubits = "2";
  page.settings.total = "1";
  page.qubitsSource = "state";
  page.actionText.save = "results/kept";
  page.placedSims.push({ id: "qutip", key: 3, open: true, params: { time_steps: "11" } });
  page.placedThens.push("plot");
  page.useFactoryMeasure();
}

function fillCircuit(page) {
  fillIsing(page);
  page.BLOCKS.simulator = [
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
          maximum: page.limits.timeSteps,
        },
        {
          name: "num_steps",
          label: "Product steps",
          kind: "integer",
          default: "4",
          minimum: 1,
          maximum: page.limits.numSteps,
        },
        {
          name: "trotter_depth",
          label: "Trotter depth",
          kind: "integer",
          default: "1",
          minimum: 1,
          maximum: page.limits.trotterDepth,
        },
        { name: "order", label: "Order", kind: "choice", default: "1", choices: ["1", "2"] },
        { name: "seed", label: "Seed", kind: "integer", default: "0" },
      ],
    },
  ];
  page.BLOCKS.backend = [
    {
      id: "aer",
      phrase: "Aer",
      shots: true,
      setup: "circuit_backend = AerCircuitBackend(shots={shots})",
    },
  ];
  page.BLOCKS.model = [
    { id: "preexisting", title: "Preexisting model", detail: "" },
    { id: "hamiltonian", title: "Hamiltonian", adds: true, detail: "" },
  ];
  page.selection.simulator = "trotterization";
  page.placedSims.splice(0, page.placedSims.length, {
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

function operatorAlert(chip) {
  const alert = chip.querySelector(".basis-alert");
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
  toggleSite,
  typeInto,
};
