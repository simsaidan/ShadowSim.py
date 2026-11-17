const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "../..");
const checksSource = fs.readFileSync(path.join(root, "shadowsim/cli/site/checks.js"), "utf8");
const builderSource = fs.readFileSync(path.join(root, "shadowsim/cli/site/builder.js"), "utf8");

let cachedCatalog = null;

function catalog() {
  if (cachedCatalog) return cachedCatalog;
  const stdout = execFileSync(
    "uv",
    ["run", "python", path.join(root, "scripts/export_builder_page.py")],
    { cwd: root, encoding: "utf8" },
  );
  cachedCatalog = JSON.parse(stdout);
  return cachedCatalog;
}

function bindingsFooter(source) {
  const names = [];
  const lets = new Set();
  for (const line of source.split("\n")) {
    const found = /^(?:async function|function|const|let) ([A-Za-z_$][\w$]*)/.exec(line);
    if (!found) continue;
    names.push(found[1]);
    // let bindings change, and the tests replace some function declarations.
    // const bindings stay as they are.
    if (!line.startsWith("const ")) lets.add(found[1]);
  }
  const fields = names.map((name) => {
    if (!lets.has(name)) return name;
    return `get ${name}() { return ${name}; }, set ${name}(value) { ${name} = value; }`;
  });
  return `return {\n${fields.join(",\n")}\n};`;
}

const footer = bindingsFooter(builderSource);

function installImmediateTimers(window) {
  // The page tests run scheduled work inline. setInterval stays idle so the
  // run clock does not keep the process alive.
  window.setTimeout = (fn) => {
    fn();
    return 1;
  };
  window.clearTimeout = () => {};
  window.setInterval = () => 1;
  window.clearInterval = () => {};
}

function installClipboard(window) {
  const writes = [];
  Object.defineProperty(window.navigator, "clipboard", {
    configurable: true,
    enumerable: true,
    value: {
      writeText(text) {
        writes.push(String(text));
        return Promise.resolve();
      },
    },
  });
  return writes;
}

function loadPage() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    url: "http://127.0.0.1/",
    // outside-only exposes document to window.eval. Inline scripts stay inert.
    runScripts: "outside-only",
  });
  const { window } = dom;
  installImmediateTimers(window);
  // The old harness had no fetch. scheduleCheck skips the request until a test installs one.
  window.fetch = undefined;
  const writes = installClipboard(window);
  const source = `(function () {\n${checksSource}\n${builderSource}\n${footer}\n})()`;
  const page = window.eval(source);
  return { window, page, writes };
}

module.exports = { catalog, loadPage };
