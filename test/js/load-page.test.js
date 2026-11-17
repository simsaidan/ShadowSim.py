const assert = require("node:assert/strict");
const { test } = require("node:test");
const { catalog, loadPage } = require("./load-page");

test("catalog exports the builder page lists", () => {
  const exported = catalog();
  assert.ok(exported.states.some((item) => item.id === "basis"));
  assert.ok(exported.measures.some((item) => item.id === "z"));
  assert.ok(exported.actions.some((item) => item.id === "plot"));
  assert.equal(Number.isInteger(exported.limits.timeSteps), true);
});

test("loadPage runs the builder against a document", () => {
  const { window, page, writes } = loadPage();
  assert.equal(page.applyLimits(catalog().limits), true);
  assert.equal(page.state.limits.timeSteps, catalog().limits.timeSteps);
  window.localStorage.setItem("shadowsim.builder.board", "{}");
  assert.equal(window.localStorage.getItem("shadowsim.builder.board"), "{}");
  const settings = page.settingsComponent();
  assert.equal(settings.querySelector(".run").localName, "button");
  page.state.selection.state = "basis";
  assert.equal(page.state.selection.state, "basis");
  page.state.running = true;
  assert.equal(page.state.running, true);
  let fired = false;
  const id = window.setTimeout(() => {
    fired = true;
  });
  assert.equal(fired, true);
  assert.equal(id, 1);
  window.clearTimeout(id);
  window.navigator.clipboard.writeText("script");
  assert.deepEqual(writes, ["script"]);
  window.close();
});
