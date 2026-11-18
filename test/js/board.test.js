const assert = require("node:assert/strict");
const { test } = require("node:test");
const {
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
} = require("./board");

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function cell(board, selector) {
  const node = board.querySelector(selector);
  return { column: node.style.gridColumn, row: node.style.gridRow };
}

test("placed blocks keep their grid cells", () => {
  const { window, page } = prepare();
  resetPage(page);
  page.state.blocks.model = [
    { id: "preexisting", title: "Preexisting model", detail: "Choose a built-in model" },
  ];
  const board = mount(window);
  page.draw(board);
  page.place("state", "basis");
  page.place("model", "preexisting");
  page.place("measure", "z");
  assert.deepEqual(cell(board, '.slot[data-slot="state"]'), { column: "1", row: "1" });
  assert.deepEqual(cell(board, '.slot[data-slot="model"]'), { column: "3", row: "1" });
  assert.deepEqual(cell(board, '.lane[data-palette="model"]'), { column: "3", row: "2" });
  assert.deepEqual(cell(board, '.slot[data-slot="simulator"]'), { column: "5", row: "1" });
  assert.deepEqual(cell(board, '.slot[data-slot="measure"]'), { column: "7", row: "1" });
  window.close();
});

test("factory fields keep edits and fall back to defaults", () => {
  const { window, page } = prepare();
  resetPage(page);
  page.state.blocks.model = [
    { id: "preexisting", title: "Preexisting model", detail: "Choose a built-in model" },
  ];
  page.state.modelFactories = [
    {
      id: "ising",
      title: "Ising",
      qubits: true,
      setup: "model = ising(n_qubits={qubits})",
      params: [
        { name: "J", label: "J", kind: "number", default: "1" },
        { name: "h", label: "h", kind: "number", default: "0" },
        {
          name: "field",
          label: "field",
          kind: "choice",
          default: "transverse",
          choices: ["classical", "transverse"],
        },
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
        {
          name: "edges",
          label: "edges",
          kind: "edges",
          default: "",
          disables: ["topology", "boundary"],
        },
      ],
    },
  ];
  const board = mount(window);
  page.draw(board);
  page.place("model", "preexisting");
  const control = (label) => board.querySelector(`[aria-label="${label}"]`);
  assert.deepEqual(
    {
      detail: board.querySelector(".preexisting-detail").textContent,
      J: control("J").getAttribute("value"),
      h: control("h").getAttribute("value"),
      field: optionValue(control("field")),
      topology: optionValue(control("topology")),
      boundary: optionValue(control("boundary")),
      edges: control("edges").getAttribute("value"),
      alertHidden: board.querySelector(".preexisting-alert").hasAttribute("hidden"),
    },
    {
      detail: "at least 2 qubits",
      J: "1",
      h: "0",
      field: "transverse",
      topology: "chain",
      boundary: "open",
      edges: "",
      alertHidden: true,
    },
  );
  typeInto(control("J"), "2");
  typeInto(control("edges"), "0-1, 1-2");
  assert.equal(control("topology").disabled, true);
  assert.equal(control("boundary").disabled, true);
  typeInto(control("edges"), "");
  setChange(control("boundary"), "periodic");
  assert.equal(control("edges").disabled, true);
  const body = page.runRequest();
  page.state.factoryText = { J: "9", h: "4" };
  page.applyDocument(body);
  const hParam = page.state.modelFactories[0].params.find((param) => param.name === "h");
  assert.equal(body.model.arguments.J, "2");
  assert.equal(body.model.arguments.edges, "");
  assert.equal(body.model.arguments.boundary, "periodic");
  assert.equal(body.model.arguments.h, "0");
  assert.equal(page.state.factoryText.J, "2");
  assert.equal(page.state.factoryText.h, "0");
  assert.equal(page.paramText(hParam), "0");
  assert.deepEqual(plain(page.runRequest().model.arguments), {
    J: "2",
    h: "0",
    field: "transverse",
    topology: "chain",
    boundary: "periodic",
    edges: "",
    n_qubits: "",
  });
  window.close();
});

test("an accepted run is what gets stored", async () => {
  const { window, page } = prepare();
  fillIsing(page);
  const surface = window.document.createElement("div");
  page.draw(surface);
  const storedEarly = window.localStorage.getItem("shadowsim.builder.board");
  page.state.boardReady = true;
  page.draw(surface);
  const storedBeforeAccept = window.localStorage.getItem("shadowsim.builder.board");
  const accepted = page.applyCheck();
  const stored = window.localStorage.getItem("shadowsim.builder.board");
  const body = JSON.stringify(page.runRequest());
  page.state.settings.total = "4";
  page.update(() => {});
  const duringEdit = window.localStorage.getItem("shadowsim.builder.board");
  const checks = [];
  window.fetch = async (url, options) => {
    checks.push({
      url,
      method: options?.method,
      contentType: options?.headers?.["Content-Type"],
      body: options?.body,
    });
    return { ok: true, json: async () => ({ qubits: 2 }) };
  };
  resetPage(page);
  page.state.boardReady = true;
  await page.restoreBoard();
  assert.equal(storedEarly, null);
  assert.equal(storedBeforeAccept, null);
  assert.equal(accepted, true);
  assert.equal(stored === body, true);
  assert.equal(duringEdit === stored, true);
  const document = JSON.parse(stored);
  assert.deepEqual(Object.keys(document).sort(), [
    "actions",
    "measure",
    "model",
    "simulators",
    "state",
    "total",
    "version",
  ]);
  assert.equal(document.version, 1);
  assert.equal(document.total, "1");
  assert.deepEqual(document.state, { id: "basis", value: "01" });
  assert.equal("server" in document, false);
  assert.deepEqual(checks, [
    { url: "/runs/check", method: "POST", contentType: "application/json", body: stored },
  ]);
  assert.equal(JSON.stringify(page.runRequest()) === stored, true);
  assert.equal(page.state.selection.state, "basis");
  assert.equal(page.state.stateText.basis || "", "01");
  window.close();
});

test("a preexisting model measures what the factory records", async () => {
  const { window, page } = prepare();
  const measures = structuredClone(page.state.blocks.measure);
  fillIsing(page);
  page.state.blocks.model = [
    { id: "preexisting", title: "Preexisting model", detail: "Choose a built-in model" },
    { id: "hamiltonian", title: "Hamiltonian", adds: true, symbol: "Operator" },
  ];
  page.state.blocks.measure = measures;
  page.state.selection.measure = null;
  page.state.measureSites = null;
  const board = mount(window);
  page.draw(board);
  const checks = [];
  window.fetch = async (_url, options) => {
    const posted = JSON.parse(options.body);
    checks.push(posted.measure);
    const count = Number(posted.model.arguments.n_qubits);
    const measurements = [];
    for (let index = 0; index < count; index += 1) {
      measurements.push({ label: `expectation on ${index}`, qubits: [index] });
    }
    return { ok: true, json: async () => ({ qubits: count, measurements }) };
  };
  page.place("model", "preexisting");
  await settle();
  const chip = () => board.querySelector(".chip.measure");
  const detailOf = () => chip().querySelector(".measure-detail").textContent;
  const boxes = () => [...chip().querySelectorAll('input[type="checkbox"]')];
  assert.deepEqual(plain(page.state.blocks.measure.map((block) => block.id)), ["model"]);
  assert.deepEqual(plain(page.runRequest().measure), { id: "model" });
  assert.equal(detailOf(), "expectation on 0; expectation on 1");
  assert.equal(boxes().length, 0);
  assert.equal(page.state.measureOpen, false);
  assert.deepEqual(checks[0], { id: "model" });

  page.state.settings.qubits = "3";
  page.update(() => {});
  await settle();
  assert.deepEqual(plain(page.runRequest().measure), { id: "model" });
  assert.equal(detailOf(), "expectation on 0; expectation on 1; expectation on 2");
  assert.equal(checks.length, 2);

  page.clearLane("measure");
  assert.equal(page.state.selection.measure, null);
  assert.deepEqual(plain(page.state.blocks.measure.map((block) => block.id)), ["model"]);
  assert.equal(Boolean(chip()), false);

  page.place("measure", "model");
  assert.equal(page.state.selection.measure, "model");
  assert.equal(page.state.measureOpen, false);
  assert.equal(boxes().length, 0);
  assert.deepEqual(plain(page.runRequest().measure), { id: "model" });

  page.clearLane("model");
  const palette = catalog().measures.map((item) => item.id);
  assert.equal(page.state.selection.model, null);
  assert.equal(page.state.selection.measure, null);
  assert.deepEqual(plain(page.state.blocks.measure.map((block) => block.id)), palette);
  assert.equal(palette.includes("y"), true);

  page.place("model", "hamiltonian");
  assert.equal(page.state.selection.measure, null);
  assert.deepEqual(plain(page.state.blocks.measure.map((block) => block.id)), palette);
  assert.deepEqual(plain(page.state.modelTerms.map((term) => term.id)), ["hamiltonian"]);
  window.close();
});

test("a saved catalog measurement is read as the model", async () => {
  const { window, page } = prepare();
  fillIsing(page);
  const legacy = {
    version: 1,
    total: "1",
    state: { id: "basis", value: "01" },
    model: { id: "ising", arguments: { n_qubits: "2" } },
    simulators: [{ id: "qutip", arguments: { time_steps: "11" } }],
    measure: { id: "z", sites: [0] },
    actions: { ids: ["plot"] },
  };
  const checks = [];
  window.fetch = async (_url, options) => {
    checks.push(JSON.parse(options.body).measure);
    return {
      ok: true,
      json: async () => ({
        qubits: 2,
        measurements: [
          { label: "expectation on 0", qubits: [0] },
          { label: "expectation on 1", qubits: [1] },
        ],
      }),
    };
  };
  window.localStorage.setItem("shadowsim.builder.board", JSON.stringify(legacy));
  await page.restoreBoard();
  assert.deepEqual(checks[0], { id: "model" });
  assert.equal(page.state.selection.measure, "model");
  assert.deepEqual(plain(page.runRequest().measure), { id: "model" });
  assert.equal(page.state.measureSites, null);
  assert.equal(page.state.blocks.measure[0]?.detail, "expectation on 0; expectation on 1");
  assert.deepEqual(plain(page.state.blocks.measure.map((block) => block.id)), ["model"]);
  window.close();
});

test("the counts chip edits the expression", async () => {
  const { window, page } = prepare();
  fillCircuit(page);
  page.state.blocks.measure = structuredClone(catalog().measures).filter(
    (block) => block.id === "counts",
  );
  page.state.selection.measure = "counts";
  page.state.measureSites = null;
  const board = mount(window);
  page.draw(board);
  openChip(board, "measure");
  const input = labeled(board, "Counts expression");
  const hint = () => board.querySelector(".counts-hint").textContent;
  assert.equal(page.statusMessage(), "Enter a counts expression.");
  assert.equal(hint(), "Keys list qubits 0, 1 in that order. shots is the total.");
  assert.equal(input.getAttribute("placeholder"), 'counts["00"] / shots');
  typeInto(input, ' counts["01"] / shots ');
  assert.equal(page.statusMessage(), "Checking the selection.");
  const typedRequest = page.runRequest().measure.expression;
  assert.equal(typedRequest, 'counts["01"] / shots');
  setChecked(labeled(board, "Qubit 1"), false);
  assert.equal(page.statusMessage(), "Counts keys must be 1 characters of 0 and 1.");
  assert.equal(hint(), "Keys list qubit 0 in that order. shots is the total.");
  assert.equal(input.placeholder, 'counts["0"] / shots');
  page.state.selection.model = null;
  page.state.blocks.model = [
    { id: "preexisting", title: "Preexisting model", detail: "Choose a built-in model" },
    { id: "hamiltonian", title: "Hamiltonian", adds: true, symbol: "Operator" },
  ];
  page.state.modelTerms.push({
    id: "hamiltonian",
    key: 1,
    matrix: "[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]",
    sites: [],
  });
  const body = JSON.stringify(page.runRequest());
  page.emptyBoard();
  assert.equal(page.state.expressionText.counts ?? "", "");
  window.fetch = async () => ({ ok: true, json: async () => ({ qubits: 2 }) });
  window.localStorage.setItem("shadowsim.builder.board", body);
  await page.restoreBoard();
  assert.equal(JSON.parse(body).measure.expression, typedRequest);
  assert.equal(page.state.expressionText.counts ?? "", typedRequest);
  assert.equal(JSON.stringify(page.runRequest()) === body, true);
  page.state.selection.measure = "z";
  assert.equal(Object.hasOwn(page.runRequest().measure, "expression"), false);
  window.close();
});

test("a new server keeps the saved document", async () => {
  const { window, page } = prepare();
  fillIsing(page);
  page.state.boardReady = true;
  page.applyCheck();
  const saved = window.localStorage.getItem("shadowsim.builder.board");
  resetPage(page);
  page.state.boardReady = true;
  window.fetch = async () => ({ ok: true, json: async () => ({ qubits: 2 }) });
  await page.restoreBoard();
  const stored = window.localStorage.getItem("shadowsim.builder.board");
  assert.notEqual(saved, null);
  assert.equal(stored, saved);
  assert.equal(JSON.parse(stored).version, 1);
  assert.equal("server" in JSON.parse(stored), false);
  assert.equal(page.state.selection.state, "basis");
  assert.equal(page.state.stateText.basis || "", "01");
  assert.equal(JSON.stringify(page.runRequest()) === saved, true);
  window.close();
});

test("clear empties the board", () => {
  const { window, page } = prepare();
  fillIsing(page);
  page.state.boardReady = true;
  page.applyCheck();
  const saved = window.localStorage.getItem("shadowsim.builder.board");
  page.state.running = true;
  page.emptyBoard();
  assert.equal(page.state.selection.state, "basis");
  assert.equal(window.localStorage.getItem("shadowsim.builder.board"), saved);
  page.state.running = false;
  mount(window);
  const settings = page.settingsComponent();
  click(settings.querySelector(".clear"));
  assert.notEqual(saved, null);
  assert.equal(page.state.selection.state, null);
  assert.equal(page.state.settings.qubits, "");
  assert.equal(page.state.stateText.basis || "", "");
  assert.equal(page.state.placedSims.length, 0);
  assert.equal(page.state.modelTerms.length, 0);
  assert.equal(page.state.placedThens.length, 0);
  assert.equal(page.state.preexistingId, null);
  assert.equal(window.localStorage.getItem("shadowsim.builder.board"), null);
  window.close();
});

test("an old saved board is dropped on startup", async () => {
  const { window, page } = prepare();
  const checks = [];
  window.fetch = async () => {
    checks.push(true);
    return { ok: false, json: async () => ({ error: "unknown field amplitudeText" }) };
  };
  window.localStorage.setItem(
    "shadowsim.builder.board",
    JSON.stringify({
      version: 1,
      selection: { state: "amplitude" },
      settings: { qubits: "1", total: "1" },
      amplitudeText: "1, 0",
    }),
  );
  await page.restoreBoard();
  assert.equal(checks.length, 0);
  assert.equal(window.localStorage.getItem("shadowsim.builder.board"), null);
  assert.equal(page.state.statusHold, null);
  assert.equal(page.state.selection.state, null);
  window.close();
});

test("a bad saved document does not fill the board", async () => {
  const { window, page } = prepare();
  fillIsing(page);
  const before = page.state.selection.state;
  const checks = [];
  window.fetch = async (url, options) => {
    checks.push({ url, body: options?.body });
    return { ok: false, json: async () => ({ error: "unknown version 2" }) };
  };
  window.localStorage.setItem("shadowsim.builder.board", "{");
  await page.restoreBoard();
  const malformed = {
    state: page.state.selection.state,
    stored: window.localStorage.getItem("shadowsim.builder.board"),
    checks: checks.length,
  };
  resetPage(page);
  const rejected = JSON.stringify({ version: 2 });
  window.localStorage.setItem("shadowsim.builder.board", rejected);
  await page.restoreBoard();
  assert.equal(before, "basis");
  assert.deepEqual(malformed, { state: "basis", stored: null, checks: 0 });
  assert.equal(page.state.statusHold, "unknown version 2");
  assert.equal(page.state.selection.state, null);
  assert.equal(page.state.stateText.basis || "", "");
  assert.deepEqual(JSON.parse(window.localStorage.getItem("shadowsim.builder.board")), {
    version: 2,
  });
  assert.deepEqual(checks[0], { url: "/runs/check", body: rejected });
  window.close();
});

test("a rejected check leaves the board", async () => {
  const { window, page } = prepare();
  fillCircuit(page);
  const before = JSON.stringify(page.runRequest());
  window.localStorage.setItem(
    "shadowsim.builder.board",
    JSON.stringify({ version: 1, simulators: [{ id: "missing" }] }),
  );
  window.fetch = async () => ({
    ok: false,
    json: async () => ({ error: "unknown simulator missing" }),
  });
  await page.restoreBoard();
  assert.equal(page.state.selection.state, "basis");
  assert.equal(JSON.stringify(page.runRequest()) === before, true);
  assert.equal(page.state.statusHold, "unknown simulator missing");
  assert.deepEqual(JSON.parse(window.localStorage.getItem("shadowsim.builder.board")).simulators, [
    { id: "missing" },
  ]);
  window.close();
});

test("operator alerts name the current problem", () => {
  const { window, page } = prepare();
  resetPage(page);
  page.state.blocks.model = [
    { id: "hamiltonian", title: "Hamiltonian", adds: true, detail: "" },
    { id: "local_hamiltonian", title: "Local Hamiltonian", adds: true, detail: "" },
    { id: "lindblad", title: "Lindblad", adds: true, detail: "" },
  ];
  page.state.selection.state = "basis";
  page.state.stateText.basis = "00";
  page.state.settings.qubits = "2";
  page.state.qubitsSource = "state";
  const board = mount(window);
  page.draw(board);
  page.place("model", "hamiltonian");
  const matrix = board.querySelector(".chip.hamiltonian textarea");
  typeInto(matrix, "[[1, 1], [0, 1]]");
  const nonhermitian = operatorAlert(board.querySelector(".chip.hamiltonian"));
  typeInto(matrix, "[[1, 0], [0, -1]]");
  const wrongSize = operatorAlert(board.querySelector(".chip.hamiltonian"));
  page.state.stateText.basis = "0";
  page.update(() => {}, { deriveState: true });
  typeInto(matrix, "[[1, 0], [0, -1]]");
  const validHamiltonian = operatorAlert(board.querySelector(".chip.hamiltonian"));
  page.state.stateText.basis = "000";
  page.update(() => {}, { deriveState: true });
  page.place("model", "local_hamiltonian");
  page.place("model", "lindblad");
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
  const shown = {
    nonhermitian: "Matrix must be Hermitian.",
    wrongSize: "Must be 4×4 for 2 qubits.",
    emptyLocal: "Pick at least one qubit.",
    splitLocal: "Qubits must be contiguous.",
    splitLindblad: "Qubits must be contiguous.",
  };
  const alerts = { nonhermitian, wrongSize, emptyLocal, splitLocal, splitLindblad };
  for (const [key, label] of Object.entries(shown)) {
    assert.equal(alerts[key].label, label);
    assert.equal(alerts[key].title, label);
    assert.equal(alerts[key].hidden, false);
    assert.equal(alerts[key].linked, true);
  }
  for (const alert of [validHamiltonian, validLocal]) {
    assert.equal(alert.hidden, true);
    assert.equal(alert.linked, false);
    assert.equal(alert.describedby, null);
  }
  const removeLabel = (chip) => chip.querySelector("button.remove").getAttribute("aria-label");
  assert.equal(removeLabel(board.querySelector(".chip.hamiltonian")), "Remove Hamiltonian");
  assert.equal(removeLabel(local()), "Remove local Hamiltonian");
  assert.equal(removeLabel(lindblad()), "Remove Lindblad operator");
  window.close();
});

test("the Aer card edits gates beside shots", () => {
  const { window, page } = prepare();
  fillCircuit(page);
  page.state.blocks.backend[0].setup =
    "circuit_backend = AerCircuitBackend(shots={shots}, basis_gates={basis_gates})";
  page.state.blocks.backend[0].fields = [
    {
      name: "basis_gates",
      label: "Gates",
      default: "",
      allow_inf: false,
      kind: "gates",
      choices: ["cx", "h", "rx", "ry", "rz"],
    },
  ];
  const board = mount(window);
  page.draw(board);
  const chip = openChip(board, "backend");
  const gates = labeled(board, "Gates");
  page.applyCheck();
  assert.equal(Boolean(labeled(board, "Shots")), true);
  assert.equal(page.statusMessage(), "Ready to run.");
  assert.equal(page.previewText().includes("basis_gates=None"), true);
  typeInto(gates, "RX, ry, RX");
  page.applyCheck();
  assert.equal(page.state.placedSims[0].backendFields.basis_gates, "rx, ry, rx");
  assert.equal(chip.querySelector(".backend-detail").textContent, "256 shots, rx, ry");
  assert.equal(page.previewText().includes('basis_gates=["rx", "ry"]'), true);
  typeInto(gates, "foo");
  assert.equal(page.statusMessage(), "Unknown gate foo.");
  assert.equal(page.previewText(), "");
  typeInto(gates, ",,,");
  assert.equal(page.statusMessage(), "Enter gate names separated by commas.");
  window.close();
});

test("edits keep the chart until the run changes", () => {
  const { window, page } = prepare();
  fillCircuit(page);
  const board = mount(window);
  page.draw(board);
  const total = labeled(board, "Total time");
  let chart = window.document.createElement("div");
  chart.className = "chart";
  page.setResults(chart);
  page.state.shownRun = page.shownRunKey();
  openChip(board, "basis");
  assert.equal(resultsNode(window) === chart, true);
  assert.equal(labeled(board, "Total time") === total, true);
  click(chipByClass(board, "basis").querySelector(".done"));
  assert.equal(resultsNode(window) === chart, true);
  assert.equal(labeled(board, "Total time") === total, true);
  typeInto(total, "4");
  assert.equal(showingPlaceholder(window), true);
  assert.equal(labeled(board, "Total time") === total, true);
  assert.equal(page.state.settings.total, "4");

  chart = window.document.createElement("div");
  chart.className = "chart";
  page.setResults(chart);
  page.state.shownRun = page.shownRunKey();
  openChip(board, "backend");
  const shots = labeled(board, "Shots");
  assert.equal(resultsNode(window) === chart, true);
  typeInto(shots, "128");
  assert.equal(showingPlaceholder(window), true);
  assert.equal(labeled(board, "Shots") === shots, true);
  assert.equal(page.state.placedSims[0].shots, "128");

  chart = window.document.createElement("div");
  chart.className = "chart";
  page.setResults(chart);
  page.state.shownRun = page.shownRunKey();
  page.place("then", "save");
  assert.equal(resultsNode(window) === chart, true);
  assert.equal(labeled(board, "Total time") === total, true);
  assert.equal(page.state.placedThens.includes("save"), true);
  typeInto(labeled(board, "Save path"), "results/kept");
  assert.equal(resultsNode(window) === chart, true);
  assert.equal(page.state.actionText.save, "results/kept");
  page.place("then", "export");
  assert.equal(resultsNode(window) === chart, true);
  assert.equal(page.state.placedThens.includes("export"), true);
  page.removeThen("save");
  assert.equal(resultsNode(window) === chart, true);
  assert.equal(page.state.placedThens.includes("save"), false);
  page.removeThen("plot");
  assert.equal(resultsNode(window) === chart, true);
  assert.equal(page.state.placedThens.includes("plot"), false);

  chart = window.document.createElement("div");
  chart.className = "chart";
  page.setResults(chart);
  page.state.shownRun = page.shownRunKey();
  page.attachBackend("aer");
  assert.equal(resultsNode(window) === chart, true);
  window.close();
});

async function settleWrites(page) {
  for (let step = 0; step < 40; step += 1) {
    await Promise.resolve();
    if (!page.state.writeInFlight && page.state.pendingWrite == null && !page.state.checkInFlight) {
      return;
    }
  }
}

test("save and export write the shown result", async () => {
  const { window, page } = prepare();
  fillCircuit(page);
  const board = mount(window);
  page.draw(board);
  const posts = [];
  window.fetch = async (url, options) => {
    const path = String(url);
    if (path.endsWith("/runs/check")) {
      return { ok: true, json: async () => ({ qubits: 2 }) };
    }
    if (path.endsWith("/runs/write")) {
      posts.push(JSON.parse(options.body));
      const actions = JSON.parse(options.body).actions;
      const payload = {};
      if (actions.ids.includes("save")) payload.saved = [actions.save_path];
      if (actions.ids.includes("export")) payload.exported = `${actions.export_path}/metrics.json`;
      return { ok: true, json: async () => payload };
    }
    throw new Error(`unexpected ${path}`);
  };
  const chart = window.document.createElement("div");
  chart.className = "chart";
  page.setResults(chart);
  page.state.shownRun = page.shownRunKey();
  page.state.shownPayload = { times: [0], observables: [[1]] };

  page.place("then", "save");
  await settleWrites(page);
  assert.equal(posts.length, 1);
  assert.deepEqual(posts[0].actions.ids.filter((id) => id === "save" || id === "export"), [
    "save",
  ]);
  assert.equal(posts[0].actions.save_path, "results/kept");
  assert.equal(resultsNode(window).querySelector(".chart") === chart, true);
  assert.equal(resultsNode(window).querySelector(".hint").textContent, "Saved to results/kept");

  posts.length = 0;
  typeInto(labeled(board, "Save path"), "results/other");
  await settleWrites(page);
  assert.equal(posts.length, 0);
  assert.equal(resultsNode(window).querySelector(".chart") === chart, true);

  click(chipByClass(board, "save").querySelector(".done"));
  await settleWrites(page);
  assert.equal(posts.length, 1);
  assert.equal(posts[0].actions.save_path, "results/other");
  assert.equal(resultsNode(window).querySelector(".hint").textContent, "Saved to results/other");

  posts.length = 0;
  openChip(board, "save");
  click(chipByClass(board, "save").querySelector(".done"));
  await settleWrites(page);
  assert.equal(posts.length, 0);

  page.place("then", "export");
  await settleWrites(page);
  assert.equal(posts.length, 1);
  assert.equal(posts[0].actions.ids.includes("export"), true);
  assert.equal(
    resultsNode(window).querySelector(".hint").textContent,
    "Saved to results/other. Exported to results/metrics.json",
  );
  assert.equal(resultsNode(window).querySelector(".chart") === chart, true);
  window.close();
});

test("copy writes the script only when one is shown", () => {
  const { window, page, writes } = prepare();
  resetPage(page);
  const empty = page.panelsComponent().querySelector(".copy");
  click(empty);
  assert.equal(empty.hasAttribute("disabled"), true);
  assert.equal(writes.length, 0);
  fillIsing(page);
  page.applyCheck();
  const full = page.panelsComponent().querySelector(".copy");
  click(full);
  assert.equal(full.hasAttribute("disabled"), false);
  assert.equal(writes[0] ?? null, page.previewText());
  assert.equal(
    writes[0].includes("from shadowsim.encoding import ComputationalBasisEncoding"),
    true,
  );
  assert.equal(writes[0].includes("import *"), false);
  window.close();
});

test("copy board writes the document while the script is empty", () => {
  const { window, page, writes } = prepare();
  resetPage(page);
  const board = mount(window);
  page.draw(board);
  const panel = () => window.document.querySelector('.panel[aria-label="Code preview"]');
  const scriptButton = () => panel().querySelector(".copy");
  const boardButton = () => panel().querySelector(".copy-board");
  const shown = () => panel().querySelector(".board-json").textContent;
  click(scriptButton());
  assert.equal(scriptButton().hasAttribute("disabled"), true);
  assert.equal(writes.length, 0);
  click(boardButton());
  const emptyWrite = writes[0] ?? null;
  assert.equal(boardButton().getAttribute("aria-label"), "Copy board");
  assert.equal(emptyWrite, shown());
  const empty = JSON.parse(emptyWrite);
  assert.equal(empty.version, 1);
  assert.equal("server" in empty, false);
  fillIsing(page);
  page.applyCheck(2);
  const before = writes.length;
  click(boardButton());
  const acceptedWrite = writes[before] ?? null;
  assert.equal(scriptButton().hasAttribute("disabled"), false);
  assert.equal(acceptedWrite, shown());
  assert.equal(acceptedWrite, page.state.acceptedBody);
  const accepted = JSON.parse(acceptedWrite);
  assert.equal("server" in accepted, false);
  assert.deepEqual(accepted.state, { id: "basis", value: "01" });
  window.close();
});

test("export and import round-trip the board", async () => {
  const { window, page } = prepare();
  const downloads = installDownloads(window);
  fillIsing(page);
  page.state.boardReady = true;
  const board = mount(window);
  page.draw(board);
  const exportButton = () => board.querySelector(".export-board");
  assert.equal(exportButton().hasAttribute("disabled"), true);
  page.applyCheck(2);
  const file = JSON.stringify(page.runRequest());
  assert.equal(exportButton().hasAttribute("disabled"), false);
  click(exportButton());
  const blob = downloads.find((item) => item.blob);
  const link = downloads.find((item) => item.name != null);
  resetPage(page);
  fillIsing(page);
  page.state.settings.total = "9";
  page.draw(board);
  const kept = window.localStorage.getItem("shadowsim.builder.board");
  const keptState = page.state.selection.state;
  const keptTotal = page.state.settings.total;
  async function choose(text) {
    const input = window.document.querySelector(".board-file-input");
    Object.defineProperty(input, "files", {
      configurable: true,
      value: [{ text: async () => text }],
    });
    input.dispatchEvent(new window.Event("change"));
    await settle();
  }
  window.fetch = async () => ({ ok: false, json: async () => ({ error: "unknown version 2" }) });
  await choose("{");
  const malformed = {
    status: page.state.statusHold,
    state: page.state.selection.state,
    total: page.state.settings.total,
    stored: window.localStorage.getItem("shadowsim.builder.board") === kept,
  };
  await choose(JSON.stringify({ version: 2 }));
  const rejected = {
    status: page.state.statusHold,
    state: page.state.selection.state,
    total: page.state.settings.total,
    stored: window.localStorage.getItem("shadowsim.builder.board") === kept,
    present: window.localStorage.getItem("shadowsim.builder.board") != null,
  };
  let posted = null;
  window.fetch = async (_url, options) => {
    posted = options?.body;
    return { ok: true, json: async () => ({ qubits: 2 }) };
  };
  await choose(file);
  const stored = window.localStorage.getItem("shadowsim.builder.board");
  assert.equal(await blob.blob.text(), file);
  assert.equal(blob.type, "application/json");
  assert.equal(link.name, "shadowsim-board.json");
  assert.equal(posted === file, true);
  assert.equal(JSON.stringify(page.runRequest()) === file, true);
  assert.equal(page.state.selection.state, "basis");
  assert.equal(page.state.stateText.basis || "", "01");
  assert.equal(JSON.parse(file).total, "1");
  assert.equal(keptState, "basis");
  assert.equal(keptTotal, "9");
  assert.deepEqual(malformed, {
    status: "The selection was rejected.",
    state: "basis",
    total: "9",
    stored: true,
  });
  assert.deepEqual(rejected, {
    status: "unknown version 2",
    state: "basis",
    total: "9",
    stored: true,
    present: true,
  });
  assert.equal(stored, file);
  const parsed = JSON.parse(stored);
  assert.equal(parsed.version, 1);
  assert.equal("server" in parsed, false);
  assert.deepEqual(parsed.state, { id: "basis", value: "01" });
  assert.equal(parsed.total, "1");
  window.close();
});

test("different time-step defaults are flagged on the method fields", () => {
  const { window, page } = prepare();
  resetPage(page);
  const field = (defaultValue) => ({
    name: "time_steps",
    label: "Time steps",
    kind: "integer",
    default: defaultValue,
    minimum: 1,
    maximum: page.state.limits.timeSteps,
  });
  page.state.blocks.simulator = [
    {
      id: "qutip",
      title: "QuTiP",
      detail: "Reference",
      observables: true,
      fields: [field("101")],
    },
    {
      id: "trotterization",
      title: "Trotterization",
      detail: "Product formula",
      observables: false,
      fields: [field("11")],
    },
  ];
  const board = mount(window);
  page.draw(board);
  const steps = () => [...board.querySelectorAll('input[aria-label="Time steps"]')];
  const alerts = () => [...board.querySelectorAll(".chip.simulator .chip-alert")];
  const message = "Use the same number of time steps for every simulator.";

  page.place("simulator", "qutip");
  assert.equal(steps().length, 1);
  assert.equal(steps()[0].hasAttribute("aria-invalid"), false);
  assert.equal(alerts()[0].hidden, true);
  assert.equal(page.statusMessage(), "Place a block in the Initial state slot.");

  page.place("simulator", "trotterization");
  assert.equal(steps().length, 2);
  for (const input of steps()) {
    assert.equal(input.getAttribute("aria-invalid"), "true");
    assert.equal(input.getAttribute("title"), message);
    const alert = input.ownerDocument.getElementById(input.getAttribute("aria-describedby"));
    assert.equal(alert.hidden, false);
    assert.equal(alert.getAttribute("aria-label"), message);
  }
  assert.equal(page.statusMessage(), "Place a block in the Initial state slot.");

  click(board.querySelector(".chip.simulator .done"));
  const closed = board.querySelector(".chip.simulator");
  assert.equal(closed.querySelector('input[aria-label="Time steps"]'), null);
  assert.equal(closed.querySelector(".chip-alert").hidden, false);

  typeInto(steps()[0], "101");
  for (const input of steps()) assert.equal(input.hasAttribute("aria-invalid"), false);
  for (const alert of alerts()) assert.equal(alert.hidden, true);
  window.close();
});
