const { catalog } = require("./load-page");

const LANES = [
  { id: "state", title: "Initial state" },
  { id: "model", title: "Model" },
  { id: "simulator", title: "Method" },
  { id: "measure", title: "Measure" },
  { id: "then", title: "Then" },
];

const QUTIP_SETUP =
  "{name} = QutipSimulator({hamiltonians}, {lindblads}, state,\n" +
  "                    e_ops, num_qubits={qubits},\n" +
  "                    total_time={total}, time_steps={time_steps})";

function circuitSetup(className) {
  return (
    `{name} = ${className}(\n` +
    "    {hamiltonians},\n" +
    "    {lindblads},\n" +
    "    state,\n" +
    "    num_qubits={qubits},\n" +
    "    total_time={total},\n" +
    "    time_steps={time_steps},\n" +
    "    num_steps={num_steps},\n" +
    "    trotter_depth={trotter_depth},\n" +
    "    order={order},\n" +
    "    seed={seed}{basis},\n" +
    "    circuit_backend={backend},\n" +
    ")"
  );
}

function chip(name, label, defaultValue, maximumKey = null, choices = null) {
  if (choices != null) {
    return { name, label, kind: "choice", default: defaultValue, choices };
  }
  const field = { name, label, kind: "integer", default: defaultValue };
  if (maximumKey != null) {
    field.minimum = 1;
    field.maximum = catalog().limits[maximumKey];
  }
  return field;
}

function qutipFields() {
  return [chip("time_steps", "Time steps", "11", "timeSteps")];
}

function circuitFields() {
  return [
    ...qutipFields(),
    chip("num_steps", "Product steps", "4", "numSteps"),
    chip("trotter_depth", "Trotter depth", "1", "trotterDepth"),
    chip("order", "Order", "1", null, ["1", "2"]),
    chip("seed", "Seed", "0"),
  ];
}

function pageCaps() {
  const payload = catalog().limits;
  return {
    stateLimits: structuredClone(payload.states),
    maxOperatorQubits: payload.operatorQubits,
    maxTimeSteps: payload.timeSteps,
    maxNumSteps: payload.numSteps,
    maxTrotterDepth: payload.trotterDepth,
    maxShots: payload.shots,
  };
}

function qutipPage() {
  const exported = catalog();
  return {
    lanes: structuredClone(LANES),
    blocks: {
      state: structuredClone(exported.states),
      model: [],
      simulator: [
        {
          id: "qutip",
          title: "QuTiP",
          observables: true,
          setup: QUTIP_SETUP,
          fields: qutipFields(),
        },
      ],
      backend: [
        {
          id: "aer",
          phrase: "Aer",
          shots: true,
          setup: "circuit_backend = AerCircuitBackend(shots={shots})",
        },
      ],
      measure: structuredClone(exported.measures),
      then: structuredClone(exported.actions),
    },
    selection: {
      state: "basis",
      model: "preexisting",
      simulator: "qutip",
      backend: null,
      measure: "z",
      then: "plot",
    },
    settings: { qubits: "2", total: "1" },
    modelTerms: [],
    modelFactories: [
      { id: "ising", title: "Ising", qubits: true, setup: "model = ising(n_qubits={qubits})" },
    ],
    preexistingId: "ising",
    stateText: { basis: "00" },
    placedSims: [{ id: "qutip", params: { time_steps: "11" } }],
    placedThens: ["plot"],
    actionText: { save: "results/run1", export: "results" },
    expressionText: {},
    measureSites: null,
    shots: "256",
    qubitsSource: null,
    ...pageCaps(),
  };
}

function circuitPage() {
  const page = qutipPage();
  page.blocks.simulator = [
    {
      id: "trotterization",
      title: "Trotterization",
      observables: false,
      setup: circuitSetup("TrotterizationSimulator"),
      fields: circuitFields(),
    },
  ];
  page.selection.simulator = "trotterization";
  page.placedSims = [
    {
      id: "trotterization",
      params: {
        time_steps: "11",
        num_steps: "4",
        trotter_depth: "1",
        seed: "0",
        order: "1",
      },
      backend: "aer",
      shots: "256",
    },
  ];
  return page;
}

function withAerGates(page) {
  const aer = page.blocks.backend[0];
  aer.setup = "circuit_backend = AerCircuitBackend(shots={shots}, basis_gates={basis_gates})";
  aer.fields = [
    {
      name: "basis_gates",
      label: "Gates",
      default: "",
      allow_inf: false,
      kind: "gates",
      choices: ["cx", "rx", "ry", "rz", "u"],
    },
  ];
  page.placedSims[0].backendFields = { basis_gates: "" };
  return page;
}

function layoutParams(...names) {
  const fields = {
    n_emitters: {
      name: "n_emitters",
      label: "Emitters",
      kind: "integer",
      default: "1",
      minimum: 1,
    },
    n_cavities: {
      name: "n_cavities",
      label: "Cavities",
      kind: "integer",
      default: "1",
      minimum: 1,
    },
    nu: { name: "nu", label: "Hopping", kind: "number", default: "0" },
  };
  return names.map((name) => fields[name]);
}

function isingParams() {
  return [
    { name: "J", label: "J", kind: "number", default: "1" },
    { name: "h", label: "h", kind: "number", default: "0" },
    {
      name: "field",
      label: "field",
      kind: "choice",
      default: "transverse",
      choices: ["classical", "transverse"],
    },
    { name: "topology", label: "topology", kind: "choice", default: "chain", choices: ["chain"] },
    {
      name: "boundary",
      label: "boundary",
      kind: "choice",
      default: "open",
      choices: ["open", "periodic"],
    },
    { name: "edges", label: "edges", kind: "edges", default: "" },
  ];
}

function countsPage(expression = 'counts["01"] / shots') {
  const page = circuitPage();
  page.blocks.measure.push({ id: "counts", title: "Counts", phrase: "Counts on all qubits" });
  page.selection.measure = "counts";
  page.expressionText = { counts: expression };
  return page;
}

module.exports = {
  QUTIP_SETUP,
  chip,
  circuitFields,
  circuitSetup,
  countsPage,
  circuitPage,
  isingParams,
  layoutParams,
  qutipFields,
  qutipPage,
  withAerGates,
};
