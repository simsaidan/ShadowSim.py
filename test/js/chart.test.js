const assert = require("node:assert/strict");
const { test } = require("node:test");
const { click, installDownloads } = require("./dom");
const { loadPage } = require("./load-page");

const loaded = loadPage();
const { page, window } = loaded;

function svgOf(root) {
  return root.querySelector("svg");
}

function polylines(root) {
  return [...svgOf(root).children].filter((node) => node.localName === "polyline");
}

function points(line) {
  const raw = line.getAttribute("points");
  assert.equal(raw.includes("NaN"), false);
  return raw.split(" ").map((pair) => {
    const [x, y] = pair.split(",");
    return [Number(x), Number(y)];
  });
}

function axisLabels(root) {
  const texts = [...svgOf(root).children].filter((node) => node.localName === "text");
  const yTicks = texts
    .filter((node) => node.getAttribute("data-axis") === "y")
    .map((node) => node.textContent);
  const xTicks = texts
    .filter((node) => node.getAttribute("data-axis") === "x")
    .map((node) => node.textContent);
  return [yTicks, xTicks];
}

function gridlines(root) {
  return [...svgOf(root).children].filter(
    (node) => node.localName === "line" && node.getAttribute("class") === "grid",
  );
}

function byClass(root, className) {
  return root.querySelector(`.${className}`);
}

function buttons(root) {
  return [...root.querySelectorAll("button")].filter(
    (node) => !node.closest(".legend") && !node.classList.contains("chart-table-toggle"),
  );
}

function pressed(root) {
  return [...root.querySelectorAll(".chart-switch button")]
    .filter((node) => node.getAttribute("aria-pressed") === "true")
    .map((node) => node.textContent);
}

function legend(root) {
  return [...byClass(root, "legend").querySelectorAll("button")].map((item) => item.textContent);
}

function legendPressed(root) {
  return [...byClass(root, "legend").querySelectorAll("button")].map((item) =>
    item.getAttribute("aria-pressed"),
  );
}

function lineTitles(root) {
  return polylines(root).map((line) => line.querySelector("title").textContent);
}

function swatches(root) {
  return [...byClass(root, "legend").querySelectorAll("button i")].map((item) => {
    const style = item.getAttribute("style");
    assert.equal(style.startsWith("background:"), true);
    return style.slice("background:".length);
  });
}

function press(root, labels) {
  for (const label of labels) {
    const button = buttons(root).find((node) => node.textContent === label);
    assert.ok(button, label);
    click(button);
  }
  return root;
}

function benchmark() {
  return {
    times: [0, 1],
    labels: ["⟨Z⟩ on 0", "⟨Z⟩ on 1"],
    saved: ["results/run1"],
    series: [
      {
        name: "QuTiP#1",
        labels: ["QuTiP#1 · ⟨Z⟩ on 0", "QuTiP#1 · ⟨Z⟩ on 1"],
        observables: [
          [2, 0],
          [1, 1],
        ],
      },
      {
        name: "QuTiP#2",
        labels: ["QuTiP#2 · ⟨Z⟩ on 0", "QuTiP#2 · ⟨Z⟩ on 1"],
        observables: [
          [0, 0],
          [1, 0],
        ],
      },
    ],
    errors: [
      {
        challenger_id: "qutip_simulator#2",
        observables: [
          { index: 0, linf: 2, rmse: 1.5 },
          { index: 1, linf: 1, rmse: 0.5 },
        ],
      },
    ],
    resources: [
      {
        simulator_id: "qutip_simulator#1",
        title: "QuTiP#1",
        wall_time_s: 0.41,
        shots_per_job: null,
        num_jobs: null,
        total_shots: null,
        depth: "N/A",
        width: "N/A",
        gate_count: "N/A",
        t_count: "N/A",
        toffoli_count: "N/A",
      },
      {
        simulator_id: "aer_simulator",
        wall_time_s: 1.2,
        shots_per_job: 256,
        num_jobs: 11,
        total_shots: 2816,
        depth: 4,
        width: 2,
        gate_count: 9,
        t_count: 1,
        toffoli_count: 2,
      },
    ],
  };
}

const resources =
  "QuTiP#1 0.41 s · aer 1.2 s, 256 shots × 11, depth 4, width 2, gates 9, T 1, Toffoli 2";

test("niceTicks covers a range with even steps", () => {
  assert.deepEqual([...page.niceTicks(-1, 1)], [-1, -0.5, 0, 0.5, 1]);
  assert.deepEqual([...page.niceTicks(0, 1)], [0, 0.2, 0.4, 0.6, 0.8, 1]);
  assert.deepEqual([...page.niceTicks(0, 2)], [0, 0.5, 1, 1.5, 2]);
  assert.deepEqual([...page.niceTicks(3, 3)], [2, 2.5, 3, 3.5, 4]);
  assert.deepEqual([...page.ticksInDomain(0, 1.25)], [0, 0.5, 1, 1.25]);
});

test("two observables show both curves and scales", () => {
  const chart = page.chartComponent({
    times: [0, 1.25],
    observables: [
      [1, -1],
      [0.25, 0.5],
    ],
  });
  assert.equal(polylines(chart).length, 2);
  const [yTicks, xTicks] = axisLabels(chart);
  assert.deepEqual(yTicks, ["-1", "-0.5", "0", "0.5", "1"]);
  assert.deepEqual(xTicks, ["0", "0.5", "1", "1.25"]);
  assert.equal(gridlines(chart).length, 5);
});

test("mismatched series drop missing points", () => {
  const chart = page.chartComponent({
    times: [0, 1, 2],
    observables: [
      [1, Number.NaN, 0, 9],
      [null, 1],
    ],
  });
  const lines = polylines(chart);
  assert.equal(lines.length, 2);
  const longer = points(lines[0]);
  const shorter = points(lines[1]);
  assert.equal(longer.length, 2);
  assert.equal(shorter.length, 1);
  assert.equal(longer[0][0] < shorter[0][0] && shorter[0][0] < longer[1][0], true);
  const [yTicks, xTicks] = axisLabels(chart);
  assert.deepEqual(yTicks, ["0", "0.2", "0.4", "0.6", "0.8", "1"]);
  assert.deepEqual(xTicks, ["0", "0.5", "1", "1.5", "2"]);
  assert.equal(gridlines(chart).length, 7);
});

test("six curves use six legend colors", () => {
  const chart = page.chartComponent({
    times: [0, 1],
    observables: Array.from({ length: 6 }, (_, index) => [index, index + 1]),
  });
  const strokes = polylines(chart).map((line) => line.getAttribute("stroke"));
  assert.equal(strokes.length, 6);
  assert.equal(new Set(strokes).size, 6);
  assert.deepEqual(swatches(chart), strokes);
});

test("labels name the curves and both axes", () => {
  const chart = page.chartComponent({
    times: [0, 1.25],
    observables: [
      [1, -1],
      [0.25, 0.5],
    ],
    labels: ["⟨Z⟩ on 0", "⟨Z⟩ on 1"],
  });
  assert.deepEqual(legend(chart), ["⟨Z⟩ on 0", "⟨Z⟩ on 1"]);
  assert.deepEqual(lineTitles(chart), ["⟨Z⟩ on 0", "⟨Z⟩ on 1"]);
  assert.equal(byClass(chart, "y-title").textContent, "⟨Z⟩");
  assert.equal(byClass(chart, "x-title").textContent, "Time");
  assert.equal(svgOf(chart).getAttribute("aria-label"), "⟨Z⟩ versus time");
  assert.equal(byClass(chart, "readout").textContent, "");
});

test("benchmark series keep their curve names", () => {
  const chart = page.chartComponent({
    times: [0, 1],
    labels: ["⟨X⟩ on 1"],
    series: [
      { name: "QuTiP#1", labels: ["QuTiP#1 · ⟨X⟩ on 1"], observables: [[1, 0]] },
      { name: "QuTiP#2", observables: [[0, 1]] },
    ],
  });
  assert.deepEqual(legend(chart), ["QuTiP#1 · ⟨X⟩ on 1", "QuTiP#2 · ⟨X⟩ on 1"]);
  assert.equal(byClass(chart, "y-title").textContent, "⟨X⟩");
});

test("hover readout names the nearest values", () => {
  const payload = {
    times: [0, 1, 2],
    observables: [
      [1, Number.NaN, 0],
      [null, 0.5, 1],
    ],
    labels: ["⟨Z⟩ on 0", "⟨Z⟩ on 1"],
  };
  assert.equal(page.plotFraction(56, 56, 612), 0);
  assert.equal(page.plotFraction(612, 56, 612), 1);
  assert.equal(page.plotFraction(55, 56, 612), null);
  assert.equal(page.nearestTimeIndex(payload, 0), 0);
  assert.equal(page.nearestTimeIndex(payload, 0.6), 1);
  assert.equal(page.nearestTimeIndex(payload, 1), 2);
  assert.equal(page.hoverReadout(payload, 1), "t = 1 · ⟨Z⟩ on 1 = 0.5");
  assert.equal(page.hoverReadout(payload, 0), "t = 0 · ⟨Z⟩ on 0 = 1");
  assert.equal(page.hoverReadout(payload, 3), "");
  assert.equal(
    page.hoverReadout(payload, 0, null, null, [{ label: "⟨Z⟩ on 1", values: [null, 0.5, 1] }]),
    "",
  );
  assert.equal(
    page.hoverReadout(payload, 2, null, null, [{ label: "⟨Z⟩ on 1", values: [null, 0.5, 1] }]),
    "t = 2 · ⟨Z⟩ on 1 = 1",
  );
});

test("hover draws a crosshair and point markers", () => {
  const chart = page.chartComponent({
    times: [0, 1, 2],
    observables: [
      [1, Number.NaN, 0],
      [null, 0.5, 1],
    ],
    labels: ["⟨Z⟩ on 0", "⟨Z⟩ on 1"],
  });
  const svg = svgOf(chart);
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 640, height: 220 });
  assert.equal(svg.querySelector(".crosshair"), null);
  assert.equal(svg.querySelectorAll(".marker").length, 0);

  svg.dispatchEvent(new window.PointerEvent("pointermove", { clientX: 56, clientY: 110 }));
  const crosshair = svg.querySelector(".crosshair");
  assert.ok(crosshair);
  assert.equal(crosshair.getAttribute("x1"), crosshair.getAttribute("x2"));
  assert.equal(crosshair.getAttribute("x1"), "56");
  const markers = [...svg.querySelectorAll(".marker")];
  assert.equal(markers.length, 1);
  assert.equal(markers[0].getAttribute("cx"), "56");
  assert.equal(byClass(chart, "readout").textContent, "t = 0 · ⟨Z⟩ on 0 = 1");

  svg.dispatchEvent(new window.PointerEvent("pointermove", { clientX: 334, clientY: 110 }));
  assert.equal(svg.querySelectorAll(".marker").length, 1);
  assert.equal(byClass(chart, "readout").textContent, "t = 1 · ⟨Z⟩ on 1 = 0.5");

  svg.dispatchEvent(new window.PointerEvent("pointerleave"));
  assert.equal(svg.querySelector(".crosshair"), null);
  assert.equal(svg.querySelectorAll(".marker").length, 0);
  assert.equal(byClass(chart, "readout").textContent, "");
});

test("show data table lists visible series", () => {
  const chart = page.chartComponent({
    times: [0, 1],
    observables: [
      [1, -1],
      [0, 1],
    ],
    labels: ["⟨Z⟩ on 0", "⟨Z⟩ on 1"],
  });
  const toggle = () => chart.querySelector(".chart-table-toggle");
  assert.equal(toggle().textContent, "Show data table");
  assert.equal(toggle().getAttribute("aria-expanded"), "false");
  assert.equal(chart.querySelector(".chart-table"), null);

  click(toggle());
  assert.equal(toggle().textContent, "Hide data table");
  assert.equal(toggle().getAttribute("aria-expanded"), "true");
  const table = chart.querySelector(".chart-table");
  assert.ok(table);
  assert.deepEqual(
    [...table.querySelectorAll("thead th")].map((node) => node.textContent),
    ["Time", "⟨Z⟩ on 0", "⟨Z⟩ on 1"],
  );
  assert.deepEqual(
    [...table.querySelectorAll("tbody tr")].map((row) =>
      [...row.children].map((cell) => cell.textContent),
    ),
    [
      ["0", "1", "0"],
      ["1", "-1", "1"],
    ],
  );

  click(byClass(chart, "legend").querySelectorAll("button")[0]);
  assert.deepEqual(
    [...chart.querySelectorAll(".chart-table thead th")].map((node) => node.textContent),
    ["Time", "⟨Z⟩ on 1"],
  );
  assert.deepEqual(
    [...chart.querySelectorAll(".chart-table tbody tr")].map((row) =>
      [...row.children].map((cell) => cell.textContent),
    ),
    [
      ["0", "0"],
      ["1", "1"],
    ],
  );

  click(toggle());
  assert.equal(chart.querySelector(".chart-table"), null);
  assert.equal(toggle().getAttribute("aria-expanded"), "false");
});

test("legend toggles hide and restore curves", () => {
  const chart = page.chartComponent({
    times: [0, 1],
    observables: [
      [1, -1],
      [0, 1],
    ],
    labels: ["⟨Z⟩ on 0", "⟨Z⟩ on 1"],
  });
  assert.equal(polylines(chart).length, 2);
  assert.deepEqual(legendPressed(chart), ["true", "true"]);
  assert.deepEqual(axisLabels(chart)[0], ["-1", "-0.5", "0", "0.5", "1"]);

  click(byClass(chart, "legend").querySelectorAll("button")[0]);
  assert.equal(polylines(chart).length, 1);
  assert.deepEqual(lineTitles(chart), ["⟨Z⟩ on 1"]);
  assert.deepEqual(legendPressed(chart), ["false", "true"]);
  assert.equal(byClass(chart, "legend").querySelector("button.off").textContent, "⟨Z⟩ on 0");
  assert.deepEqual(axisLabels(chart)[0], ["0", "0.2", "0.4", "0.6", "0.8", "1"]);
  assert.equal(polylines(chart)[0].getAttribute("stroke"), swatches(chart)[1]);

  const svg = svgOf(chart);
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 640, height: 220 });
  svg.dispatchEvent(new window.PointerEvent("pointermove", { clientX: 56, clientY: 110 }));
  assert.equal(byClass(chart, "readout").textContent, "t = 0 · ⟨Z⟩ on 1 = 0");
  assert.equal(svg.querySelectorAll(".marker").length, 1);

  click(byClass(chart, "legend").querySelectorAll("button")[0]);
  assert.equal(polylines(chart).length, 2);
  assert.deepEqual(legendPressed(chart), ["true", "true"]);
  assert.deepEqual(axisLabels(chart)[0], ["-1", "-0.5", "0", "0.5", "1"]);

  click(byClass(chart, "legend").querySelectorAll("button")[0]);
  click(byClass(chart, "legend").querySelectorAll("button")[1]);
  assert.equal(svgOf(chart), null);
  assert.equal(byClass(chart, "placeholder").textContent, "The run returned no curves.");
  assert.deepEqual(legendPressed(chart), ["false", "false"]);
  click(byClass(chart, "legend").querySelectorAll("button")[1]);
  assert.equal(polylines(chart).length, 1);
  assert.deepEqual(lineTitles(chart), ["⟨Z⟩ on 1"]);
});

test("one simulator has no switch", () => {
  const downloads = ["Download PNG", "Download CSV"];
  const bare = page.resultsComponent({
    times: [0, 1],
    observables: [[1, 0]],
    labels: ["⟨Z⟩ on 0"],
  });
  assert.equal(bare.className, "results");
  assert.deepEqual(
    buttons(bare).map((node) => node.textContent),
    downloads,
  );
  const timed = page.resultsComponent({
    times: [0, 1],
    observables: [[1, 0]],
    labels: ["⟨Z⟩ on 0"],
    resources: [
      {
        simulator_id: "qutip_simulator",
        wall_time_s: 0.42,
        shots_per_job: null,
        num_jobs: null,
        total_shots: null,
        depth: "N/A",
        width: "N/A",
        gate_count: "N/A",
        t_count: "N/A",
        toffoli_count: "N/A",
      },
    ],
  });
  assert.deepEqual(
    buttons(timed).map((node) => node.textContent),
    downloads,
  );
  assert.equal(byClass(timed, "resources").textContent, "0.42 s");
  const sampled = page.resultsComponent({
    times: [0, 1],
    observables: [[1, 0]],
    labels: ["⟨Z⟩ on 0"],
    resources: [
      {
        simulator_id: "trotterization_simulator",
        wall_time_s: 1.2,
        shots_per_job: 256,
        num_jobs: 101,
        total_shots: 25856,
        depth: 6,
        width: 2,
        gate_count: 14,
        t_count: 0,
        toffoli_count: 0,
      },
    ],
  });
  assert.equal(
    byClass(sampled, "resources").textContent,
    "1.2 s, 256 shots × 101, depth 6, width 2, gates 14, T 0, Toffoli 0",
  );
});

test("chart switches are toggle groups, not tabs", () => {
  const panel = page.resultsComponent(benchmark());
  const switches = [...panel.querySelectorAll(".chart-switch")];
  assert.deepEqual(
    switches.map((node) => [node.getAttribute("role"), node.getAttribute("aria-label")]),
    [
      ["group", "Observable"],
      ["group", "Chart"],
    ],
  );
  for (const button of switches.flatMap((node) => [...node.querySelectorAll("button")])) {
    assert.equal(button.getAttribute("role"), null);
    assert.equal(["true", "false"].includes(button.getAttribute("aria-pressed")), true);
  }
  assert.equal(panel.querySelector('[role="tab"], [role="tablist"]'), null);
});

test("the error switch replaces the curves and keeps the resource line", () => {
  const payload = benchmark();
  const curves = page.resultsComponent(payload);
  assert.deepEqual(
    buttons(curves).map((node) => node.textContent),
    [
      "All",
      "⟨Z⟩ on 0",
      "⟨Z⟩ on 1",
      "Curves",
      "QuTiP#1",
      "QuTiP#2",
      "Error",
      "Download PNG",
      "Download CSV",
    ],
  );
  assert.deepEqual(pressed(curves), ["All", "Curves"]);
  assert.deepEqual(legend(curves), [
    "QuTiP#1 · ⟨Z⟩ on 0",
    "QuTiP#1 · ⟨Z⟩ on 1",
    "QuTiP#2 · ⟨Z⟩ on 0",
    "QuTiP#2 · ⟨Z⟩ on 1",
  ]);
  assert.equal(byClass(curves, "hint").textContent, "Saved to results/run1");
  assert.equal(
    byClass(curves, "comparison").textContent,
    "QuTiP#2 vs QuTiP#1 · ⟨Z⟩ on 0: max 2, RMSE 1.5 · QuTiP#2 vs QuTiP#1 · ⟨Z⟩ on 1: max 1, RMSE 0.5",
  );
  assert.equal(byClass(curves, "panel-actions").children.length, 2);
  assert.equal(byClass(curves, "resources").textContent, resources);

  const error = press(page.resultsComponent(payload), ["Error"]);
  assert.deepEqual(pressed(error), ["All", "Error"]);
  assert.equal(byClass(error, "y-title").textContent, "Error vs QuTiP#1");
  assert.equal(svgOf(error).getAttribute("aria-label"), "Error vs QuTiP#1 versus time");
  assert.equal(polylines(error).length, 2);
  assert.deepEqual(lineTitles(error), ["QuTiP#2 · ⟨Z⟩ on 0", "QuTiP#2 · ⟨Z⟩ on 1"]);
  assert.deepEqual(legend(error), ["QuTiP#2 · ⟨Z⟩ on 0", "QuTiP#2 · ⟨Z⟩ on 1"]);
  assert.equal(
    byClass(error, "comparison").textContent,
    "QuTiP#2 vs QuTiP#1 · ⟨Z⟩ on 0: max 2, RMSE 1.5 · QuTiP#2 vs QuTiP#1 · ⟨Z⟩ on 1: max 1, RMSE 0.5",
  );
  const [yTicks] = axisLabels(error);
  assert.deepEqual(yTicks, ["0", "0.5", "1", "1.5", "2"]);
  const difference = points(polylines(error)[0]);
  assert.equal(difference[0][1] < difference[1][1], true);
  assert.equal(byClass(error, "resources").textContent, resources);
  assert.equal(byClass(error, "hint").textContent, "Saved to results/run1");
  assert.equal(
    page.hoverReadout(payload, 0, "error"),
    "t = 0 · QuTiP#2 · ⟨Z⟩ on 0 = 2 · QuTiP#2 · ⟨Z⟩ on 1 = 0",
  );
});

test("the observable switch shows one chart at a time", () => {
  const payload = benchmark();
  const one = press(page.resultsComponent(payload), ["⟨Z⟩ on 1"]);
  assert.deepEqual(pressed(one), ["⟨Z⟩ on 1", "Curves"]);
  assert.deepEqual(legend(one), ["QuTiP#1 · ⟨Z⟩ on 1", "QuTiP#2 · ⟨Z⟩ on 1"]);
  assert.equal(polylines(one).length, 2);

  const error = press(page.resultsComponent(payload), ["⟨Z⟩ on 1", "Error"]);
  assert.deepEqual(pressed(error), ["⟨Z⟩ on 1", "Error"]);
  assert.deepEqual(legend(error), ["QuTiP#2 · ⟨Z⟩ on 1"]);
  assert.deepEqual(lineTitles(error), ["QuTiP#2 · ⟨Z⟩ on 1"]);
  assert.equal(byClass(error, "resources").textContent, resources);

  const restored = press(page.resultsComponent(payload), ["⟨Z⟩ on 1", "All"]);
  assert.deepEqual(pressed(restored), ["All", "Curves"]);
  assert.equal(polylines(restored).length, 4);
  assert.equal(page.hoverReadout(payload, 0, "error", 1), "t = 0 · QuTiP#2 · ⟨Z⟩ on 1 = 0");
});

test("the simulator switch sits between curves and error", () => {
  const payload = benchmark();
  payload.series[0].name = "QuTiP";
  payload.series[1].name = "Split J";
  payload.series[0].labels = ["QuTiP · ⟨Z⟩ on 0", "QuTiP · ⟨Z⟩ on 1"];
  payload.series[1].labels = ["Split J · ⟨Z⟩ on 0", "Split J · ⟨Z⟩ on 1"];
  const panel = page.resultsComponent(payload);
  assert.deepEqual(
    buttons(panel)
      .filter((node) => node.getAttribute("data-view"))
      .map((node) => node.textContent),
    ["Curves", "QuTiP", "Split J", "Error"],
  );

  const one = press(page.resultsComponent(structuredClone(payload)), ["Split J"]);
  assert.deepEqual(pressed(one), ["All", "Split J"]);
  assert.deepEqual(legend(one), ["Split J · ⟨Z⟩ on 0", "Split J · ⟨Z⟩ on 1"]);
  assert.equal(byClass(one, "y-title").textContent, "⟨Z⟩");

  const focused = press(page.resultsComponent(structuredClone(payload)), ["⟨Z⟩ on 0", "QuTiP"]);
  assert.deepEqual(pressed(focused), ["⟨Z⟩ on 0", "QuTiP"]);
  assert.deepEqual(legend(focused), ["QuTiP · ⟨Z⟩ on 0"]);
  assert.equal(polylines(focused).length, 1);
});

test("axis tabs and legend share QuTiP and Trotter titles", () => {
  const payload = {
    times: [0, 1],
    labels: ["⟨Z⟩ on 0"],
    series: [
      {
        name: "QuTiP",
        labels: ["QuTiP · ⟨Z⟩ on 0"],
        observables: [[1, 0]],
      },
      {
        name: "Trotter",
        labels: ["Trotter · ⟨Z⟩ on 0"],
        observables: [[0.5, 0]],
      },
    ],
    errors: [
      {
        challenger_id: "trotterization_simulator",
        observables: [{ index: 0, linf: 0.5, rmse: 0.5 }],
      },
    ],
    resources: [
      {
        simulator_id: "qutip_simulator",
        title: "QuTiP",
        wall_time_s: 0.1,
        shots_per_job: null,
        num_jobs: null,
        total_shots: null,
        depth: "N/A",
        width: "N/A",
        gate_count: "N/A",
        t_count: "N/A",
        toffoli_count: "N/A",
      },
      {
        simulator_id: "trotterization_simulator",
        title: "Trotter",
        wall_time_s: 0.2,
        shots_per_job: 128,
        num_jobs: 2,
        total_shots: 256,
        depth: 4,
        width: 2,
        gate_count: 8,
        t_count: 0,
        toffoli_count: 0,
      },
    ],
  };
  const panel = page.resultsComponent(payload);
  assert.deepEqual(
    buttons(panel)
      .filter((node) => node.getAttribute("data-view"))
      .map((node) => node.textContent),
    ["Curves", "QuTiP", "Trotter", "Error"],
  );
  assert.deepEqual(legend(panel), ["QuTiP · ⟨Z⟩ on 0", "Trotter · ⟨Z⟩ on 0"]);
  assert.equal(byClass(panel, "comparison").textContent, "Trotter vs QuTiP: max 0.5, RMSE 0.5");
  assert.equal(
    byClass(panel, "resources").textContent,
    "QuTiP 0.1 s · Trotter 0.2 s, 128 shots × 2, depth 4, width 2, gates 8, T 0, Toffoli 0",
  );

  const error = press(page.resultsComponent(structuredClone(payload)), ["Error"]);
  assert.equal(byClass(error, "y-title").textContent, "Error vs QuTiP");
  assert.equal(svgOf(error).getAttribute("aria-label"), "Error vs QuTiP versus time");
  assert.deepEqual(legend(error), ["Trotter · ⟨Z⟩ on 0"]);
});

test("seriesCsv builds a table for the on-screen curves", () => {
  const payload = benchmark();
  assert.equal(
    page.seriesCsv(payload, "error", 1),
    ["t,QuTiP#2 · ⟨Z⟩ on 1", "0,0", "1,1"].join("\n"),
  );
  assert.equal(
    page.seriesCsv(
      {
        times: [0, 1],
        labels: ["a,b", 'quote "x"'],
        observables: [
          [1, 2],
          [3, 4],
        ],
      },
      null,
      null,
    ),
    ['t,"a,b","quote ""x"""', "0,1,3", "1,2,4"].join("\n"),
  );
});

test("results can download the PNG and CSV", async () => {
  const downloads = installDownloads(window);
  window.Image = class {
    set src(_value) {
      queueMicrotask(() => {
        if (typeof this.onload === "function") this.onload();
      });
    }
  };
  window.HTMLCanvasElement.prototype.getContext = () => ({
    fillStyle: "",
    fillRect() {},
    drawImage() {},
  });
  window.HTMLCanvasElement.prototype.toBlob = function toBlob(callback) {
    callback(new window.Blob(["png-bytes"], { type: "image/png" }));
  };

  const payload = benchmark();
  const panel = page.resultsComponent(payload);
  click(buttons(panel).find((node) => node.textContent === "Download PNG"));
  for (
    let step = 0;
    step < 10 && !downloads.some((item) => item.name === "shadowsim-figure.png");
    step++
  ) {
    await Promise.resolve();
  }
  const figureBlob = downloads.find((item) => item.type === "image/png");
  const figureLink = downloads.find((item) => item.name === "shadowsim-figure.png");
  assert.ok(figureBlob);
  assert.ok(figureLink);
  assert.equal(await figureBlob.blob.text(), "png-bytes");

  downloads.length = 0;
  press(panel, ["⟨Z⟩ on 1", "Error"]);
  click(buttons(panel).find((node) => node.textContent === "Download CSV"));
  const seriesBlob = downloads.find((item) => item.type === "text/csv");
  const seriesLink = downloads.find((item) => item.name === "shadowsim-series.csv");
  assert.ok(seriesBlob);
  assert.ok(seriesLink);
  assert.equal(await seriesBlob.blob.text(), ["t,QuTiP#2 · ⟨Z⟩ on 1", "0,0", "1,1"].join("\n"));
});

test.after(() => {
  window.close();
});
