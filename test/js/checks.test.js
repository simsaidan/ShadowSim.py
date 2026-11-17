const assert = require("node:assert/strict");
const { test } = require("node:test");
const checks = require("../../shadowsim/cli/site/checks.js");
const {
  QUTIP_SETUP,
  chip,
  circuitFields,
  circuitPage,
  circuitSetup,
  countsPage,
  isingParams,
  layoutParams,
  qutipFields,
  qutipPage,
  withAerGates,
} = require("./pages");

function includes(text, needle) {
  assert.equal(typeof text, "string");
  assert.ok(text.includes(needle), needle);
}

function excludes(text, needle) {
  assert.equal(text.includes(needle), false, needle);
}

for (const total of ["0", "-1"]) {
  test(`a total time of ${total} is not ready`, () => {
    const page = qutipPage();
    page.settings.total = total;
    assert.equal(checks.settingsReady(page), false);
    assert.equal(checks.runAllowed(page), false);
  });
}

test("fractional qubits are not ready", () => {
  const page = qutipPage();
  page.settings.qubits = "1.5";
  assert.equal(checks.settingsReady(page), false);
  assert.equal(checks.runAllowed(page), false);
});

for (const qubits of ["15", "16"]) {
  test(`an Ising register of ${qubits} qubits is not capped on the page`, () => {
    const page = qutipPage();
    page.settings.qubits = qubits;
    assert.equal(checks.qubitProblem(page, false), null);
  });
}

test("a missing simulator is not a reference", () => {
  const page = qutipPage();
  assert.equal(checks.isReference(page, { id: "qutip" }), true);
  page.blocks.simulator = [];
  assert.equal(checks.isReference(page, { id: "qutip" }), false);
});

test("added operators preview uses full hamiltonians", () => {
  const page = qutipPage();
  page.settings.qubits = "1";
  page.stateText.basis = "0";
  page.selection.model = "hamiltonian";
  page.blocks.model = [
    { id: "hamiltonian", stem: "added_hamiltonian", symbol: "Hamiltonian", adds: true },
  ];
  page.modelTerms = [{ id: "hamiltonian", matrix: "[[1, 0], [0, -1]]" }];
  const text = checks.previewText(page);
  includes(text, "full_hamiltonians = [added_hamiltonian]");
  includes(text, "QutipSimulator(full_hamiltonians, lindblads_full, state,");
  excludes(text, "qutip_hamiltonians");
});

test("qutip without a backend is ready", () => {
  const page = qutipPage();
  assert.equal(page.selection.backend, null);
  assert.equal(checks.runAllowed(page), true);
});

test("hybrid wml omits trotter controls", () => {
  const page = circuitPage();
  const block = page.blocks.simulator[0];
  block.id = "hybridwml";
  block.samples = true;
  block.fields = [
    chip("time_steps", "Time steps", "11", "timeSteps"),
    chip("num_steps", "Product steps", "4", "numSteps"),
    chip("seed", "Seed", "0"),
  ];
  block.setup =
    "{name} = HybridWMLSimulator(\n" +
    "    {hamiltonians},\n" +
    "    {lindblads},\n" +
    "    state,\n" +
    "    num_qubits={qubits},\n" +
    "    total_time={total},\n" +
    "    time_steps={time_steps},\n" +
    "    num_steps={num_steps},\n" +
    "    seed={seed}{basis},\n" +
    "    circuit_backend={backend},\n" +
    ")";
  const entry = page.placedSims[0];
  entry.id = "hybridwml";
  entry.params.trotter_depth = "0";
  entry.params.order = "9";
  page.selection.simulator = "hybridwml";
  assert.equal(checks.simParamProblem(page, false), null);
  assert.equal(checks.simParamsReady(page), true);
  const body = checks.entryBody(page, entry);
  assert.equal(body.arguments.num_steps, "4");
  assert.equal(body.arguments.seed, "0");
  assert.equal("trotter_depth" in body.arguments, false);
  assert.equal("order" in body.arguments, false);
  const preview = checks.previewText(page);
  includes(preview, "HybridWMLSimulator");
  excludes(preview, "trotter_depth");
});

test("a circuit simulator without a backend is not ready", () => {
  const page = circuitPage();
  assert.equal(checks.runAllowed(page), true);
  page.placedSims[0].backend = null;
  assert.equal(checks.runAllowed(page), false);
  assert.equal(checks.socketStatus(page, false), "Snap a backend onto each simulator.");
});

test("a circuit row without shots is not ready", () => {
  const page = circuitPage();
  page.placedSims[0].shots = "";
  assert.equal(checks.shotsReady(page), false);
  assert.equal(checks.runAllowed(page), false);
});

test("page workload maxima stay ready", () => {
  const qutip = qutipPage();
  qutip.placedSims[0].params.time_steps = String(qutip.maxTimeSteps);
  assert.equal(checks.runAllowed(qutip), true);
  assert.equal(checks.simParamProblem(qutip, false), null);
  const circuit = circuitPage();
  circuit.placedSims[0].params.time_steps = String(circuit.maxTimeSteps);
  circuit.placedSims[0].params.num_steps = String(circuit.maxNumSteps);
  circuit.placedSims[0].params.trotter_depth = String(circuit.maxTrotterDepth);
  circuit.placedSims[0].shots = String(circuit.maxShots);
  assert.equal(checks.runAllowed(circuit), true);
  assert.equal(checks.simParamProblem(circuit, false), null);
  assert.equal(checks.shotsProblem(circuit, false), null);
});

test("oversize simulator parameters block the run", () => {
  const page = qutipPage();
  const timeSteps = page.maxTimeSteps;
  page.placedSims[0].params.time_steps = String(timeSteps + 1);
  assert.equal(checks.runAllowed(page), false);
  assert.equal(checks.simParamProblem(page, false), `Time steps must be from 1 to ${timeSteps}.`);
  assert.equal(
    checks.simParamProblem(page, true),
    `Time steps must be from 1 to ${timeSteps} to preview the script.`,
  );
  const circuit = circuitPage();
  const numSteps = circuit.maxNumSteps;
  circuit.placedSims[0].params.num_steps = String(numSteps + 1);
  assert.equal(checks.runAllowed(circuit), false);
  assert.equal(
    checks.simParamProblem(circuit, false),
    `Product steps must be from 1 to ${numSteps}.`,
  );
  circuit.placedSims[0].params.num_steps = String(numSteps);
  const depth = circuit.maxTrotterDepth;
  circuit.placedSims[0].params.trotter_depth = String(depth + 1);
  assert.equal(checks.simParamProblem(circuit, false), `Trotter depth must be from 1 to ${depth}.`);
  circuit.placedSims[0].params.trotter_depth = "1";
  const shots = circuit.maxShots;
  circuit.placedSims[0].shots = String(shots + 1);
  assert.equal(checks.shotsReady(circuit), false);
  assert.equal(checks.shotsProblem(circuit, false), `Shots must be from 1 to ${shots}.`);
  assert.equal(
    checks.shotsProblem(circuit, true),
    `Shots must be from 1 to ${shots} to preview the script.`,
  );
  circuit.placedSims[0].shots = `1${"0".repeat(20)}`;
  assert.equal(checks.shotsProblem(circuit, false), `Shots must be from 1 to ${shots}.`);
});

test("split-j rejects a backend without shots", () => {
  const page = circuitPage();
  page.blocks.simulator = [
    { id: "splitjmatrix", title: "SplitJMatrix", observables: false, samples: true },
    { id: "trotterization", title: "Trotterization", observables: false, samples: false },
  ];
  page.blocks.backend.push({
    id: "paulipropagation",
    phrase: "PauliPropagation",
    shots: false,
    setup: "circuit_backend = PauliPropagationBackend()",
  });
  const splitJ = { id: "splitjmatrix" };
  const trotter = { id: "trotterization" };
  assert.equal(checks.backendFits(page, splitJ, "paulipropagation"), false);
  assert.equal(checks.backendFits(page, splitJ, "aer"), true);
  assert.equal(checks.backendFits(page, trotter, "paulipropagation"), true);
  page.blocks.simulator.push({ id: "qutip", observables: true });
  assert.equal(checks.backendFits(page, { id: "qutip" }, "aer"), false);
});

test("preview names a backend for each circuit row", () => {
  const page = circuitPage();
  page.blocks.simulator = [
    {
      id: "trotterization",
      title: "Trotterization",
      observables: false,
      samples: false,
      setup: circuitSetup("TrotterizationSimulator"),
      fields: circuitFields(),
    },
    {
      id: "splitjmatrix",
      title: "SplitJMatrix",
      observables: false,
      samples: true,
      setup: circuitSetup("SplitJMatrixSimulator"),
      fields: circuitFields(),
    },
  ];
  page.blocks.backend.push({
    id: "paulipropagation",
    phrase: "PauliPropagation",
    shots: false,
    setup:
      "circuit_backend = PauliPropagationBackend(max_weight={max_weight}, min_abs_coeff={min_abs_coeff})",
    fields: [
      { name: "max_weight", label: "Max weight", default: "inf", allow_inf: true },
      { name: "min_abs_coeff", label: "Min coefficient", default: "1e-10", allow_inf: false },
    ],
  });
  const first = page.placedSims[0];
  first.backend = "paulipropagation";
  first.backendFields = { max_weight: "inf", min_abs_coeff: "1e-10" };
  const second = {
    id: "splitjmatrix",
    params: { ...first.params },
    backend: "aer",
    shots: "128",
  };
  page.placedSims = [first, second];
  const text = checks.previewText(page);
  includes(text, "from shadowsim.backends import PauliPropagationBackend, AerCircuitBackend");
  includes(
    text,
    'circuit_backend_1 = PauliPropagationBackend(max_weight=float("inf"), min_abs_coeff=1e-10)',
  );
  includes(text, "circuit_backend_2 = AerCircuitBackend(shots=128)");
  includes(text, "circuit_backend=circuit_backend_1");
  includes(text, "circuit_backend=circuit_backend_2");
  const posted = checks.entryBody(page, first);
  assert.equal(posted.backend.id, "paulipropagation");
  assert.equal(posted.backend.arguments.max_weight, "inf");
  assert.equal(posted.backend.arguments.min_abs_coeff, "1e-10");
  assert.equal("shots" in posted.backend.arguments, false);
  first.backendFields = { max_weight: "", min_abs_coeff: "1e-10" };
  assert.equal(checks.backendFieldsReady(page), false);
  assert.equal(checks.runAllowed(page), false);
  assert.equal(
    checks.backendFieldStatus(page, false),
    "Enter a max weight and a minimum coefficient.",
  );
  assert.equal(
    checks.backendFieldStatus(page, true),
    "Enter a max weight and a minimum coefficient to preview the script.",
  );
  assert.deepEqual(checks.entryBody(page, second), {
    id: "splitjmatrix",
    arguments: {
      time_steps: "11",
      num_steps: "4",
      trotter_depth: "1",
      seed: "0",
      order: "1",
    },
    backend: { id: "aer", arguments: { shots: "128" } },
  });
});

test("blank aer gates preview as none", () => {
  const page = withAerGates(circuitPage());
  assert.equal(checks.backendFieldsReady(page), true);
  assert.equal(checks.runAllowed(page), true);
  const text = checks.previewText(page);
  includes(text, "circuit_backend_1 = AerCircuitBackend(shots=256, basis_gates=None)");
  assert.equal(checks.entryBody(page, page.placedSims[0]).backend.arguments.basis_gates, "");
});

test("typed aer gates are previewed and posted", () => {
  const page = withAerGates(circuitPage());
  page.placedSims[0].backendFields = { basis_gates: "RX, ry, rx, cx" };
  const text = checks.previewText(page);
  includes(text, 'basis_gates=["rx", "ry", "cx"]');
  assert.equal(
    checks.entryBody(page, page.placedSims[0]).backend.arguments.basis_gates,
    "RX, ry, rx, cx",
  );
});

test("unknown aer gates block the run and the preview", () => {
  const page = withAerGates(circuitPage());
  page.placedSims[0].backendFields = { basis_gates: "foo" };
  assert.equal(checks.backendFieldsReady(page), false);
  assert.equal(checks.runAllowed(page), false);
  assert.equal(checks.previewText(page), "");
  assert.equal(checks.backendFieldStatus(page, false), "Unknown gate foo.");
  assert.equal(checks.backendFieldStatus(page, true), "Unknown gate foo to preview the script.");
  page.placedSims[0].backendFields = { basis_gates: ",,," };
  assert.equal(checks.backendFieldStatus(page, false), "Enter gate names separated by commas.");
});

test("preview numbers a backend with its row", () => {
  const page = circuitPage();
  page.blocks.simulator.unshift({
    id: "qutip",
    title: "QuTiP",
    observables: true,
    setup: QUTIP_SETUP,
    fields: qutipFields(),
  });
  page.placedSims.unshift({ id: "qutip", params: { time_steps: "11" } });
  page.selection.simulator = "qutip";
  const text = checks.previewText(page);
  excludes(text, "circuit_backend_1");
  includes(text, "circuit_backend_2 = AerCircuitBackend(shots=256)");
  includes(text, "circuit_backend=circuit_backend_2");
  assert.deepEqual(checks.entryBody(page, page.placedSims[0]), {
    id: "qutip",
    arguments: { time_steps: "11" },
    backend: null,
  });
});

test("a single export includes the metrics call", () => {
  const page = qutipPage();
  page.selection.then = "export";
  page.placedThens = ["export"];
  page.actionText.export = "results";
  const text = checks.previewText(page);
  includes(text, "save_resource_metrics(sim, result.runtime, output_dir=");
  excludes(text, "save_error_metrics");
});

test("a benchmark export includes save error metrics", () => {
  const page = qutipPage();
  page.selection.then = "export";
  page.placedThens = ["export"];
  page.actionText.export = "results/metrics.json";
  page.placedSims = [
    { id: "qutip", params: { time_steps: "11" } },
    { id: "qutip", params: { time_steps: "11" } },
  ];
  const text = checks.previewText(page);
  includes(text, 'benchmark.save_error_metrics(path="results/metrics.json")');
});

test("tavis-cummings-hubbard preview uses cavities and hopping", () => {
  const page = qutipPage();
  page.preexistingId = "tavis_cummings_hubbard";
  page.factoryText = { n_emitters: "1", n_cavities: "2", nu: "1.5" };
  page.stateText.basis = "000000";
  page.modelFactories = [
    {
      id: "tavis_cummings_hubbard",
      title: "Tavis-Cummings-Hubbard",
      qubits: false,
      setup: "model = tavis_cummings_hubbard()",
      params: layoutParams("n_emitters", "n_cavities", "nu"),
    },
  ];
  assert.equal(checks.factorySetsQubits(page), true);
  assert.equal(checks.fixedFactoryQubits(page), null);
  page.checkedQubits = 6;
  assert.equal(checks.fixedFactoryQubits(page), 6);
  const text = checks.previewText(page);
  includes(text, "from shadowsim.models import tavis_cummings_hubbard");
  includes(text, "model = tavis_cummings_hubbard(n_emitters=1, n_cavities=2, nu=1.5)");
  page.factoryText = { n_emitters: "6", n_cavities: "2", nu: "1.5" };
  page.checkedQubits = null;
  assert.equal(checks.fixedFactoryQubits(page), null);
  assert.equal(checks.emitterProblem(page), false);
  assert.equal(checks.factoryAlert(page), null);
});

test("jaynes-cummings-hubbard preview uses cavities and hopping", () => {
  const page = qutipPage();
  page.preexistingId = "jaynes_cummings_hubbard";
  page.factoryText = { n_cavities: "2", nu: "1.5" };
  page.stateText.basis = "000000";
  page.modelFactories = [
    {
      id: "jaynes_cummings_hubbard",
      title: "Jaynes-Cummings-Hubbard",
      qubits: false,
      setup: "model = jaynes_cummings_hubbard()",
      params: layoutParams("n_cavities", "nu"),
    },
  ];
  assert.equal(checks.factorySetsQubits(page), true);
  assert.equal(checks.fixedFactoryQubits(page), null);
  page.checkedQubits = 6;
  assert.equal(checks.fixedFactoryQubits(page), 6);
  const text = checks.previewText(page);
  includes(text, "from shadowsim.models import jaynes_cummings_hubbard");
  includes(text, "model = jaynes_cummings_hubbard(n_cavities=2, nu=1.5)");
  excludes(text, "n_emitters");
  page.factoryText = { n_cavities: "6", nu: "1.5" };
  page.checkedQubits = null;
  assert.equal(checks.fixedFactoryQubits(page), null);
  assert.equal(checks.emitterProblem(page), false);
  assert.equal(checks.factoryAlert(page), null);
});

test("preview imports are explicit", () => {
  const qutip = checks.previewText(qutipPage());
  includes(qutip, "from shadowsim.encoding import ComputationalBasisEncoding");
  includes(qutip, "from shadowsim.simulators import QutipSimulator\n");
  includes(qutip, "sim = QutipSimulator(model.full_hamiltonians, model.c_ops_full, state,");
  includes(qutip, "time_steps=11)");
  excludes(qutip, "expectation_z");
  excludes(qutip, "import *");

  const circuit = checks.previewText(circuitPage());
  includes(circuit, "from shadowsim.simulators import Measurement, TrotterizationSimulator");
  excludes(circuit, "Measurement.expectation");
  includes(
    circuit,
    'measurements = [Measurement((i,), \'(counts["0"] - counts["1"]) / shots\', ' +
      'f"expectation on {i}") for i in range(model.num_qubits)]',
  );
  excludes(circuit, "measurement_groups");
  excludes(circuit, "reducers");
  excludes(circuit, "import *");

  const measured = circuitPage();
  measured.selection.measure = "x";
  measured.measureSites = [1];
  measured.blocks.measure.push({
    id: "x",
    title: "X expectation",
    phrase: "X expectation on each qubit",
  });
  const text = checks.previewText(measured);
  includes(text, 'basis="ZX"');
  excludes(text, "Measurement.expectation");
  includes(
    text,
    'measurements = [Measurement((1,), \'(counts["0"] - counts["1"]) / shots\', "expectation on 1")]',
  );
  assert.ok(
    text.endsWith("sim.simulate()\nresult = sim.measure(measurements)\nsim.plot_results()"),
  );

  measured.selection.measure = "y";
  const rotated = checks.previewText(measured);
  includes(rotated, 'basis="ZY"');
});

test("a model measurement previews the factory lists", () => {
  const block = {
    id: "model",
    title: "Model measurements",
    detail: "The model's measurements",
    phrase: "The model's measurements",
    kind: "model",
  };
  const qutip = qutipPage();
  qutip.blocks.measure = [...qutip.blocks.measure, block];
  qutip.selection.measure = "model";
  qutip.measureSites = [];
  const text = checks.previewText(qutip);
  includes(text, "e_ops = model.e_ops");
  excludes(text, "Operator(");
  assert.equal(checks.measureSitesReady(qutip), true);
  assert.equal(checks.runAllowed(qutip), true);

  const circuit = circuitPage();
  circuit.blocks.measure = [...circuit.blocks.measure, block];
  circuit.selection.measure = "model";
  const preview = checks.previewText(circuit);
  includes(preview, "measurements = model.measurements");
  excludes(preview, "basis=");
  excludes(preview, "Measurement");
  includes(preview, "from shadowsim.simulators import TrotterizationSimulator");
});

test("preview uses the catalog class", () => {
  const page = circuitPage();
  page.blocks.simulator = [
    {
      id: "custom",
      title: "Custom",
      observables: false,
      setup: circuitSetup("CustomSimulator"),
      fields: circuitFields(),
    },
  ];
  page.selection.simulator = "custom";
  page.placedSims[0].id = "custom";
  const text = checks.previewText(page);
  includes(text, "from shadowsim.simulators import CustomSimulator, Measurement");
  includes(text, "sim = CustomSimulator(");
  includes(text, "time_steps=11");
  includes(text, "circuit_backend=circuit_backend_1");
  excludes(text, "SplitJMatrixSimulator");
  excludes(text, "TrotterizationSimulator");
});

const expressions = [
  ['counts["01"] / shots', 2, null],
  ["-(counts['1'] - counts['0']) ** 2 / shots + 1e-3", 1, null],
  ["2 ** -counts['1'] * .5", 1, null],
  ["  ", 1, "Enter a counts expression."],
  ["1".repeat(1001), 1, "Expression must be at most 1000 characters."],
  ['counts["0"]', 2, "Counts keys must be 2 characters of 0 and 1."],
  ['counts["2"]', 1, "Counts keys must be 1 characters of 0 and 1."],
  ["__import__('os')", 1, "BAD"],
  ["shots shots", 1, "BAD"],
  ["counts[0]", 1, "BAD"],
  ["counts['0'", 1, "BAD"],
  ["(shots", 1, "BAD"],
  ["shots +", 1, "BAD"],
  ["shots * ", 1, "BAD"],
  ["1 % 2", 1, "BAD"],
  ['counts["0\\"]', 1, "BAD"],
  ["", 1, "Enter a counts expression."],
];

for (const [expression, width, problem] of expressions) {
  const label =
    expression.length > 40 ? `${expression.length} characters` : JSON.stringify(expression);
  test(`expression problem mirrors Python for ${label}`, () => {
    const allowed = 'Use numbers, shots, counts["01"], parentheses, and + - * / **.';
    const expected = problem === "BAD" ? allowed : problem;
    assert.equal(checks.expressionProblem(countsPage(), expression, width), expected);
  });
}

test("counts needs aer and a valid expression", () => {
  const page = countsPage();
  assert.equal(checks.countsProblem(page), null);
  assert.equal(checks.runAllowed(page), true);

  page.expressionText = { counts: 'counts["1"] / shots' };
  assert.equal(checks.countsProblem(page), "Counts keys must be 2 characters of 0 and 1.");
  assert.equal(
    checks.countsStatus(page, true),
    "Counts keys must be 2 characters of 0 and 1 to preview the script.",
  );
  assert.equal(checks.runAllowed(page), false);
  assert.equal(checks.previewText(page), "");

  page.measureSites = [1];
  assert.equal(checks.countsProblem(page), null);
  page.measureSites = [];
  assert.equal(checks.countsProblem(page), null);
  page.settings.qubits = "";
  assert.equal(checks.countsProblem(page), null);

  const qutip = qutipPage();
  qutip.blocks.measure.push({ id: "counts", title: "Counts", phrase: "Counts on all qubits" });
  qutip.selection.measure = "counts";
  qutip.expressionText = { counts: 'counts["01"] / shots' };
  assert.equal(checks.countsProblem(qutip), "Counts needs a backend with a shot budget.");

  const pauli = countsPage();
  pauli.blocks.backend.push({ id: "paulipropagation", phrase: "PauliPropagation", shots: false });
  pauli.placedSims[0].backend = "paulipropagation";
  assert.equal(checks.countsProblem(pauli), "Counts needs a backend with a shot budget.");
  assert.equal(checks.countsStatus(qutipPage(), false), null);
});

test("counts preview names the qubits and expression", () => {
  let page = countsPage("counts['1'] / shots");
  page.measureSites = [1];
  let text = checks.previewText(page);
  includes(text, "measurements = [Measurement((1,), \"counts['1'] / shots\")]");

  page = countsPage();
  text = checks.previewText(page);
  includes(text, "measurements = [Measurement((0, 1), 'counts[\"01\"] / shots')]");
});

test("benchmark preview measures each circuit simulator", () => {
  const page = circuitPage();
  page.blocks.simulator.push({
    id: "qutip",
    title: "QuTiP",
    observables: true,
    setup: QUTIP_SETUP,
    fields: qutipFields(),
  });
  page.placedSims.unshift({ id: "qutip", params: { time_steps: "11" } });
  const text = checks.previewText(page);
  includes(text, "benchmark.run()\nsim_2.measure(measurements)\nbenchmark.save_result_plot()");
  excludes(text, "sim_1.measure");
});

test("matrix size uses the page qubit cap", () => {
  const page = qutipPage();
  page.maxOperatorQubits = 1;
  const identity = "[[1, 0], [0, 1]]";
  assert.equal(checks.squareMatrix(page, identity).qubits, 1);
  const wider = "[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]";
  assert.deepEqual(checks.squareMatrix(page, wider), { problem: "At most 1 qubit." });
});

test("integer fields use the catalog minimum", () => {
  const page = qutipPage();
  page.preexistingId = "tavis_cummings";
  page.modelFactories = [
    {
      id: "tavis_cummings",
      title: "Tavis-Cummings",
      qubits: false,
      setup: "model = tavis_cummings()",
      params: layoutParams("n_emitters"),
    },
  ];
  page.factoryText = { n_emitters: "" };
  assert.equal(checks.factoryAlert(page), "Enter an integer of at least 1 for Emitters");
  assert.equal(checks.emitterProblem(page), true);
  page.factoryText = { n_emitters: "2" };
  assert.equal(checks.factoryAlert(page), null);
  assert.equal(checks.emitterProblem(page), false);
  page.modelFactories[0].params[0].minimum = 2;
  page.factoryText = { n_emitters: "1" };
  assert.equal(checks.factoryAlert(page), "Enter an integer of at least 2 for Emitters");
});

test("hamiltonian problems use different messages", () => {
  const page = qutipPage();
  page.settings.qubits = "1";
  const nonhermitian = checks.hamiltonianProblem(page, {
    id: "hamiltonian",
    matrix: "[[1, 1], [0, 1]]",
  });
  page.settings.qubits = "2";
  const wrongSize = checks.hamiltonianProblem(page, {
    id: "hamiltonian",
    matrix: "[[1, 0], [0, -1]]",
  });
  assert.equal(nonhermitian, "Matrix must be Hermitian.");
  assert.equal(wrongSize, "Must be 4×4 for 2 qubits.");
  assert.notEqual(nonhermitian, wrongSize);
});

test("ising preview includes factory arguments", () => {
  const page = qutipPage();
  page.modelFactories[0].params = isingParams();
  const text = checks.previewText(page);
  includes(
    text,
    'model = ising(n_qubits=2, J=1.0, h=0.0, field="transverse", topology="chain", boundary="open")',
  );
  excludes(text, "edges=");

  page.settings.qubits = "4";
  page.stateText.basis = "0000";
  page.factoryText = { J: "0.5", edges: "0-1, 1-2" };
  const edited = checks.previewText(page);
  includes(edited, "J=0.5");
  includes(edited, "edges=[(0, 1), (1, 2)]");
  includes(edited, 'boundary="open"');
});

test("bad ising arguments block the run", () => {
  const page = qutipPage();
  page.modelFactories[0].params = isingParams();
  page.factoryText = { J: "0", h: "0" };
  assert.equal(checks.factoryAlert(page), null);
  assert.equal(checks.runAllowed(page), true);

  page.factoryText = { edges: "nope" };
  assert.equal(checks.factoryAlert(page), "Enter edges as pairs such as 0-1, 1-2");
  assert.equal(checks.runAllowed(page), false);

  page.settings.qubits = "4";
  page.stateText.basis = "0000";
  page.factoryText = { boundary: "periodic", edges: "0-1" };
  assert.equal(checks.factoryAlert(page), null);
  assert.equal(checks.runAllowed(page), true);

  page.settings.qubits = "2";
  page.stateText.basis = "00";
  page.factoryText = { boundary: "periodic" };
  assert.equal(checks.factoryAlert(page), null);
  assert.equal(checks.runAllowed(page), true);
});

test("a per-emitter list must match the emitter count", () => {
  const page = qutipPage();
  page.preexistingId = "tavis_cummings";
  page.stateText.basis = "0000";
  page.modelFactories = [
    {
      id: "tavis_cummings",
      title: "Tavis-Cummings",
      qubits: false,
      setup: "model = tavis_cummings()",
      params: [
        { name: "omega_c", label: "omega_c", kind: "number", default: "245000" },
        { name: "omega_e", label: "omega_e", kind: "number_or_list", default: "245000" },
        { name: "kappa", label: "kappa", kind: "number", default: "1" },
        { name: "gamma", label: "gamma", kind: "number_or_list", default: "1" },
        { name: "g", label: "g", kind: "number_or_list", default: "100" },
        ...layoutParams("n_emitters"),
      ],
    },
  ];
  page.factoryText = { n_emitters: "2", g: "10, 20" };
  const text = checks.previewText(page);
  includes(text, "model = tavis_cummings(omega_c=245000.0");
  includes(text, "g=[10.0, 20.0], n_emitters=2");

  page.factoryText = { n_emitters: "2", g: "1, 2, 3" };
  assert.equal(checks.factoryAlert(page), null);
  assert.equal(checks.runAllowed(page), true);
  const listed = checks.previewText(page);
  includes(listed, "g=[1.0, 2.0, 3.0]");

  page.factoryText = { n_emitters: "" };
  assert.equal(checks.factoryAlert(page), "Enter an integer of at least 1 for Emitters");
  assert.equal(checks.runAllowed(page), false);
});

test("hubbard preview keeps structure and factory arguments", () => {
  const page = qutipPage();
  page.preexistingId = "tavis_cummings_hubbard";
  page.stateText.basis = "000000";
  page.factoryText = { omega_c: "10", n_emitters: "1", n_cavities: "2", nu: "1.5" };
  page.modelFactories = [
    {
      id: "tavis_cummings_hubbard",
      title: "Tavis-Cummings-Hubbard",
      qubits: false,
      setup: "model = tavis_cummings_hubbard()",
      params: [
        { name: "omega_c", label: "omega_c", kind: "number", default: "245000" },
        { name: "g", label: "g", kind: "number_or_list", default: "100" },
        ...layoutParams("n_emitters", "n_cavities", "nu"),
      ],
    },
  ];
  const text = checks.previewText(page);
  includes(
    text,
    "model = tavis_cummings_hubbard(omega_c=10.0, g=100.0, n_emitters=1, n_cavities=2, nu=1.5)",
  );
});

function expectProblem(page, message, previewMessage) {
  assert.deepEqual(checks.firstProblem(page), { message, previewMessage });
  assert.equal(checks.runAllowed(page), false);
}

test("firstProblem reports each problem in order", () => {
  const page = withAerGates(circuitPage());
  const timeSteps = page.maxTimeSteps;
  const shots = page.maxShots;
  page.selection.model = "hamiltonian";
  page.modelTerms = [{ id: "hamiltonian", matrix: "[[1, 0], [0, -1]]" }];
  page.preexistingId = "tavis_cummings";
  page.modelFactories = [
    {
      id: "tavis_cummings",
      title: "Tavis-Cummings",
      qubits: false,
      setup: "model = tavis_cummings()",
      params: layoutParams("n_emitters"),
    },
  ];
  page.factoryText = { n_emitters: "" };
  page.checkedQubits = 3;
  page.stateText.basis = "00";
  page.settings.qubits = "2";
  page.settings.total = "";
  page.selection.measure = "counts";
  page.measureSites = [];
  page.expressionText = { counts: "" };
  page.placedThens = ["plot", "save"];
  page.actionText.save = "";
  const params = {
    time_steps: String(timeSteps + 1),
    num_steps: "4",
    trotter_depth: "1",
    seed: "0",
    order: "1",
  };
  page.placedSims = [
    {
      id: "trotterization",
      params: { ...params },
      backend: null,
      shots: String(shots + 1),
      backendFields: { basis_gates: "foo" },
    },
    {
      id: "trotterization",
      params: { ...params, time_steps: "" },
      backend: null,
      shots: "",
      backendFields: { basis_gates: "foo" },
    },
  ];

  expectProblem(page, "Enter a valid operator.", "Enter a valid operator to preview the script.");
  page.selection.model = "preexisting";
  expectProblem(
    page,
    "Snap a backend onto each simulator.",
    "Snap a backend onto each simulator to preview the script.",
  );
  page.selection.state = null;
  expectProblem(
    page,
    "Place a block in each slot.",
    "Place a block in each slot to preview the script.",
  );

  page.selection.state = "basis";
  for (const entry of page.placedSims) entry.backend = "aer";
  expectProblem(
    page,
    "Enter an integer of at least 1 for Emitters.",
    "Enter an integer of at least 1 for Emitters to preview the script.",
  );
  page.factoryText = { n_emitters: "1" };
  expectProblem(
    page,
    "Enter a 3-bit basis string.",
    "Enter a 3-bit basis string to preview the script.",
  );
  page.stateText.basis = "";
  expectProblem(
    page,
    "Enter a bit string and total time.",
    "Enter a bit string and total time to preview the script.",
  );
  page.stateText.basis = "00";
  page.checkedQubits = 2;
  expectProblem(page, "Enter a total time.", "Enter a total time to preview the script.");
  page.settings.total = "1";
  expectProblem(
    page,
    `Time steps must be from 1 to ${timeSteps}.`,
    `Time steps must be from 1 to ${timeSteps} to preview the script.`,
  );
  page.placedSims[0].params.time_steps = "11";
  expectProblem(
    page,
    "Enter simulator parameters.",
    "Enter simulator parameters to preview the script.",
  );
  page.placedSims[1].params.time_steps = "5";
  expectProblem(
    page,
    "Use the same number of time steps for every simulator.",
    "Use the same number of time steps to preview the script.",
  );
  page.placedSims[1].params.time_steps = "11";
  expectProblem(page, "Pick at least one qubit.", "Pick at least one qubit to preview the script.");
  page.measureSites = [0];
  expectProblem(
    page,
    "Enter a counts expression.",
    "Enter a counts expression to preview the script.",
  );
  page.expressionText = { counts: 'counts["0"] / shots' };
  expectProblem(
    page,
    `Shots must be from 1 to ${shots}.`,
    `Shots must be from 1 to ${shots} to preview the script.`,
  );
  page.placedSims[0].shots = "256";
  expectProblem(page, "Enter a shot count.", "Enter a shot count to preview the script.");
  page.placedSims[1].shots = "256";
  expectProblem(page, "Unknown gate foo.", "Unknown gate foo to preview the script.");
  for (const entry of page.placedSims) entry.backendFields = { basis_gates: "" };
  expectProblem(page, "Enter a save path.", "Enter a save path to preview the script.");
  page.actionText.save = "results/run1";
  assert.equal(checks.firstProblem(page), null);
  assert.equal(checks.runAllowed(page), true);
});
