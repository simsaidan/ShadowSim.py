const assert = require("node:assert/strict");
const { test } = require("node:test");
const { catalog, loadPage } = require("./load-page");
const { mount } = require("./board");

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function waitFor(predicate) {
  for (let step = 0; step < 50; step += 1) {
    if (predicate()) return;
    await Promise.resolve();
  }
  throw new Error("timed out waiting for condition");
}

function paletteText(board, lane) {
  return board.querySelector(`.lane[data-palette="${lane}"]`)?.textContent ?? "";
}

test("loading palettes render before catalog fetches resolve", () => {
  const { window, page } = loadPage();
  assert.equal(page.applyLimits(catalog().limits), true);
  for (const lane of Object.keys(page.state.laneStatus)) page.state.laneStatus[lane] = "loading";
  const board = mount(window);
  page.draw(board);
  assert.match(paletteText(board, "model"), /Loading models…/);
  assert.match(paletteText(board, "state"), /Loading states…/);
  assert.match(paletteText(board, "simulator"), /Loading simulators…/);
  assert.match(paletteText(board, "simulator"), /Loading backends…/);
  assert.match(paletteText(board, "measure"), /Loading measurements…/);
  assert.match(paletteText(board, "then"), /Loading actions…/);
  assert.equal(board.querySelector('.lane[data-palette="model"] .cards'), null);
  assert.equal(board.querySelector(".block"), null);
  assert.equal(board.querySelector('.slot[data-slot="model"] .hint'), null);
  assert.equal(board.querySelector('.slot[data-slot="model"] .chip'), null);
  window.close();
});

test("a failed lane shows its own error state", () => {
  const { window, page } = loadPage();
  assert.equal(page.applyLimits(catalog().limits), true);
  page.state.laneStatus.model = "error";
  page.state.laneNotes.model = "Could not load models.";
  const board = mount(window);
  page.draw(board);
  const note = board.querySelector('.lane[data-palette="model"] .hint');
  assert.equal(note?.textContent, "Could not load models.");
  assert.equal(board.querySelector('.lane[data-palette="model"] .placeholder'), null);
  window.close();
});

test("startBuilder paints the board before the first fetch resolves", async () => {
  const { window, page } = loadPage();
  const gates = Object.fromEntries(
    ["models", "simulators", "backends", "states", "measurements", "actions", "limits"].map(
      (key) => [key, deferred()],
    ),
  );
  window.fetch = async (url) => {
    const name = String(url).replace(/^\//, "");
    await gates[name].promise;
    if (name === "limits") return { ok: true, json: async () => catalog().limits };
    if (name === "models") {
      return {
        ok: true,
        json: async () => ({
          models: [{ id: "hamiltonian", title: "Hamiltonian", adds: true, detail: "" }],
        }),
      };
    }
    if (name === "simulators") return { ok: true, json: async () => ({ simulators: [] }) };
    if (name === "backends") return { ok: true, json: async () => ({ backends: [] }) };
    if (name === "states") {
      return { ok: true, json: async () => ({ states: structuredClone(catalog().states) }) };
    }
    if (name === "measurements") {
      return {
        ok: true,
        json: async () => ({ measurements: structuredClone(catalog().measures) }),
      };
    }
    if (name === "actions") {
      return { ok: true, json: async () => ({ actions: structuredClone(catalog().actions) }) };
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  const root = window.document.createElement("div");
  window.document.body.append(root);
  page.startBuilder(root);
  const board = root.querySelector(".board");
  assert.ok(board);
  assert.match(paletteText(board, "model"), /Loading models…/);
  assert.equal(page.state.limits, null);
  assert.equal(page.statusMessage(), "Loading limits…");

  gates.limits.resolve();
  await waitFor(() => page.state.limits != null);
  assert.match(paletteText(board, "model"), /Loading models…/);

  gates.models.resolve();
  await waitFor(() => page.state.laneStatus.model === "ready");
  assert.match(paletteText(board, "model"), /Preexisting model/);
  assert.match(paletteText(board, "model"), /Hamiltonian/);
  assert.equal(board.querySelector('.lane[data-palette="model"] .placeholder'), null);
  assert.match(paletteText(board, "state"), /Loading states…/);

  for (const key of ["simulators", "backends", "states", "measurements", "actions"]) {
    gates[key].resolve();
  }
  await waitFor(() => page.state.boardReady);
  assert.equal(page.state.laneStatus.state, "ready");
  assert.match(paletteText(board, "state"), /Basis state/);
  window.close();
});

test("startBuilder keeps the board visible when limits fail", async () => {
  const { window, page } = loadPage();
  window.fetch = async (url) => {
    if (url === "/limits") return { ok: false, json: async () => ({}) };
    const key = String(url).replace(/^\//, "");
    if (key === "measurements") return { ok: true, json: async () => ({ measurements: [] }) };
    return { ok: true, json: async () => ({ [key]: [] }) };
  };
  const root = window.document.createElement("div");
  window.document.body.append(root);
  page.startBuilder(root);
  await waitFor(() => page.state.statusHold === "Could not load limits.");
  assert.ok(root.querySelector(".board"));
  assert.equal(page.state.boardReady, false);
  assert.equal(root.querySelector(".status-live")?.textContent, "Could not load limits.");
  window.close();
});
