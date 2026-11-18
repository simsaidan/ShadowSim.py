const assert = require("node:assert/strict");
const { test } = require("node:test");
const { active, click, mount, prepare, resetPage } = require("./board");

function simBlocks(page) {
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
      fields: [field("11")],
    },
    {
      id: "trotterization",
      title: "Trotterization",
      detail: "Product formula",
      observables: false,
      fields: [field("11")],
    },
  ];
}

test("opening a chip focuses its first field", () => {
  const { window, page } = prepare();
  resetPage(page);
  page.state.selection.state = "basis";
  page.state.stateText.basis = "01";
  page.state.stateOpen = false;
  const board = mount(window);
  page.draw(board);

  const header = board.querySelector(".chip.state.basis .chip-head > button");
  click(header);

  const field = board.querySelector(".chip.state.basis input[aria-label]");
  assert.equal(active(board), field);
  window.close();
});

test("Done focuses the chip header button", () => {
  const { window, page } = prepare();
  resetPage(page);
  page.state.selection.state = "basis";
  page.state.stateText.basis = "01";
  page.state.stateOpen = true;
  const board = mount(window);
  page.draw(board);

  click(board.querySelector(".chip.state.basis .done"));

  const header = board.querySelector(".chip.state.basis .chip-head > button");
  assert.equal(active(board), header);
  window.close();
});

test("placing a simulator focuses a field in the new chip", () => {
  const { window, page } = prepare();
  resetPage(page);
  simBlocks(page);
  const board = mount(window);
  page.draw(board);

  page.place("simulator", "qutip");

  const field = board.querySelector('.chip.simulator input[aria-label="Time steps"]');
  assert.ok(field);
  assert.equal(active(board), field);
  window.close();
});

test("removing a simulator focuses the next chip, then the slot heading", () => {
  const { window, page } = prepare();
  resetPage(page);
  simBlocks(page);
  const board = mount(window);
  page.draw(board);

  page.place("simulator", "qutip");
  page.place("simulator", "trotterization");
  const firstKey = page.state.placedSims[0].key;
  const secondKey = page.state.placedSims[1].key;

  page.removeSimulator(firstKey);
  const remaining = board.querySelector(`.chip.simulator[data-key="${secondKey}"]`);
  assert.ok(remaining);
  assert.equal(active(board), remaining);

  page.removeSimulator(secondKey);
  const heading = board.querySelector('.slot[data-slot="simulator"] > h2');
  assert.equal(active(board), heading);
  window.close();
});
