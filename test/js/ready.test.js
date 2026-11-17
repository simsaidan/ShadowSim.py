const assert = require("node:assert/strict");
const { test } = require("node:test");
const { catalog, loadPage } = require("./load-page");

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
  page.preexistingId = null;
  page.modelFactories = [];
  page.modelTerms.splice(0, page.modelTerms.length);
  page.placedSims.splice(0, page.placedSims.length);
  page.placedThens.splice(0, page.placedThens.length);
  page.running = false;
}

function fillIsing(page, qubits, total) {
  resetPage(page);
  page.BLOCKS.simulator = [
    {
      id: "qutip",
      observables: true,
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
  page.modelFactories = [
    { id: "ising", title: "Ising", qubits: true, setup: "model = ising(n_qubits={qubits})" },
  ];
  page.preexistingId = "ising";
  page.selection.state = "basis";
  page.selection.model = "preexisting";
  page.selection.simulator = "qutip";
  page.selection.measure = "z";
  page.selection.then = "plot";
  page.stateText.basis = "00";
  page.settings.qubits = qubits;
  page.settings.total = total;
  page.placedSims.push({ id: "qutip", key: 1, params: { time_steps: "11" } });
  page.placedThens.push("plot");
}

function pageState({ complete, qubits = "", total = "", accept = false }) {
  const { window, page } = loadPage();
  const exported = catalog();
  assert.equal(page.applyLimits(exported.limits), true);
  page.BLOCKS.state = structuredClone(exported.states);
  page.BLOCKS.measure = structuredClone(exported.measures);
  page.BLOCKS.then = structuredClone(exported.actions);
  if (complete) fillIsing(page, qubits, total);
  else resetPage(page);
  if (accept) page.applyCheck();
  const settings = page.settingsComponent();
  window.document.body.append(settings);
  page.syncRunButton();
  const button = settings.querySelector(".run");
  const state = {
    status: page.statusMessage(),
    ready: window.checks.settingsReady(page.currentPage()),
    label: button.textContent,
    renderedDisabled: button.hasAttribute("disabled"),
    syncedDisabled: button.disabled === true,
  };
  window.close();
  return state;
}

function assertDisabled(state, status) {
  assert.equal(state.label, "Run simulation");
  assert.equal(state.status, status);
  assert.equal(state.ready, false);
  assert.equal(state.renderedDisabled, true);
  assert.equal(state.syncedDisabled, true);
}

const invalid = [
  ["0", "1", "Qubits must be an integer of at least 2."],
  ["-1", "1", "Qubits must be an integer of at least 2."],
  ["1.5", "1", "Qubits must be an integer of at least 2."],
  ["1", "1", "Qubits must be an integer of at least 2."],
  ["2", "0", "Total time must be a positive number."],
  ["2", "-1", "Total time must be a positive number."],
];

for (const [qubits, total, status] of invalid) {
  test(`invalid numbers ${qubits} qubits and ${total} time disable Run`, () => {
    assertDisabled(pageState({ complete: true, qubits, total }), status);
  });
}

test("an Ising qubit cap waits for the check", () => {
  const state = pageState({ complete: true, qubits: "16", total: "1" });
  assert.equal(state.label, "Run simulation");
  assert.equal(state.status, "Checking the selection.");
  assert.equal(state.ready, true);
  assert.equal(state.renderedDisabled, true);
  assert.equal(state.syncedDisabled, true);
});

test("a complete selection waits for the check", () => {
  const state = pageState({ complete: true, qubits: "2", total: "1" });
  assert.equal(state.label, "Run simulation");
  assert.equal(state.status, "Checking the selection.");
  assert.equal(state.ready, true);
  assert.equal(state.renderedDisabled, true);
  assert.equal(state.syncedDisabled, true);
});

test("a complete selection enables Run", () => {
  const state = pageState({ complete: true, qubits: "2", total: "1", accept: true });
  assert.equal(state.label, "Run simulation");
  assert.equal(state.status, "Ready to run.");
  assert.equal(state.ready, true);
  assert.equal(state.renderedDisabled, false);
  assert.equal(state.syncedDisabled, false);
});

test("an incomplete form disables Run", () => {
  const state = pageState({ complete: false });
  assert.equal(state.label, "Run simulation");
  assert.equal(state.status, "Place a block in each slot.");
  assert.equal(state.ready, false);
  assert.equal(state.renderedDisabled, true);
  assert.equal(state.syncedDisabled, true);
});
