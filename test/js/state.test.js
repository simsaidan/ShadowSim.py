const assert = require("node:assert/strict");
const { test } = require("node:test");
const { click } = require("./dom");
const { catalog, loadPage } = require("./load-page");

function describe(card) {
  const done = card.querySelector("button.done");
  const head = card.querySelector(".basis-head > button");
  return {
    editing: card.className.includes("is-editing"),
    done: done ? done.textContent : null,
    field: Boolean(card.querySelector("input")),
    detail: card.querySelector(".basis-detail")?.textContent ?? null,
    header: head ? head.localName : null,
    headerType: head ? head.getAttribute("type") : null,
    doneNode: done,
    head,
  };
}

test("the basis state card closes from Done", () => {
  const { window, page } = loadPage();
  const exported = catalog();
  assert.equal(page.applyLimits(exported.limits), true);
  page.state.blocks.state = structuredClone(exported.states);
  page.state.selection.state = "basis";
  page.state.stateText.basis = "10";
  page.state.stateOpen = true;
  const board = window.document.createElement("section");
  board.className = "board";
  window.document.body.append(board);
  page.draw(board);
  const open = describe(board.querySelector(".chip.state"));
  assert.deepEqual(
    { editing: open.editing, done: open.done, field: open.field, detail: open.detail },
    { editing: true, done: "Done", field: true, detail: "Start in |10>" },
  );

  let redraws = 0;
  page.draw = () => {
    redraws += 1;
  };
  click(open.doneNode);
  const closed = describe(board.querySelector(".chip.state"));
  click(closed.head);
  assert.equal(closed.editing, false);
  assert.equal(closed.done, null);
  assert.equal(closed.field, false);
  assert.equal(closed.detail, "Start in |10>");
  assert.equal(closed.header, "button");
  assert.equal(closed.headerType, "button");
  assert.equal(redraws, 0);

  const again = describe(board.querySelector(".chip.state"));
  assert.equal(
    page.state.stateOpen === true && again.editing === true && again.field === true,
    true,
  );

  page.state.stateOpen = false;
  page.place("state", "basis");
  assert.equal(page.state.selection.state === "basis" && page.state.stateOpen === true, true);
  page.clearLane("state");
  assert.equal(page.state.selection.state === null && page.state.stateOpen === false, true);

  page.state.stateOpen = true;
  const siblings = ["gray", "angle", "amplitude"].map((id) => {
    page.state.selection.state = id;
    const block = page.state.blocks.state.find((item) => item.id === id);
    return describe(page.stateFieldChip(block)).done;
  });
  assert.deepEqual(siblings, ["Done", "Done", "Done"]);
  window.close();
});
