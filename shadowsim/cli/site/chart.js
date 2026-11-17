/* Chart for a finished run. */

import { el } from "./dom.js";

const CURVE_COLORS = ["#4c4cb8", "#1f7a6c", "#a67c1a", "#b66880", "#6a4ca8"];

function formatAxis(value) {
  if (!Number.isFinite(value)) return "";
  if (Number.isInteger(value)) return String(value);
  return String(Math.round(value * 1000) / 1000);
}

function chartCurves(payload) {
  const shared = Array.isArray(payload.labels) ? payload.labels : [];
  if (Array.isArray(payload.series) && payload.series.length) {
    const curves = [];
    for (const series of payload.series) {
      const observables = Array.isArray(series.observables) ? series.observables : [];
      const own = Array.isArray(series.labels) ? series.labels : [];
      observables.forEach((values, index) => {
        const named = typeof own[index] === "string" && own[index] ? own[index] : "";
        const common = typeof shared[index] === "string" ? shared[index] : "";
        const label = named || (common ? `${series.name} · ${common}` : `${series.name} ${index}`);
        curves.push({ label, values, index, simulator: series.name });
      });
    }
    return curves;
  }
  const observables = Array.isArray(payload.observables) ? payload.observables : [];
  return observables.map((values, index) => ({
    label:
      typeof shared[index] === "string" && shared[index] ? shared[index] : `Observable ${index}`,
    values,
    index,
  }));
}

function subtractSeries(reference, values) {
  const left = Array.isArray(reference) ? reference : [];
  const right = Array.isArray(values) ? values : [];
  const count = Math.max(left.length, right.length);
  const diff = [];
  for (let index = 0; index < count; index++) {
    const a = left[index];
    const b = right[index];
    if (a == null || b == null) {
      diff.push(null);
      continue;
    }
    const y = Number(a) - Number(b);
    diff.push(Number.isFinite(y) ? y : null);
  }
  return diff;
}

function errorCurves(payload) {
  const series = Array.isArray(payload.series) ? payload.series : [];
  if (series.length < 2) return [];
  const reference = Array.isArray(series[0].observables) ? series[0].observables : [];
  const errors = Array.isArray(payload.errors) ? payload.errors : [];
  const curves = [];
  series.slice(1).forEach((challenger, challengerIndex) => {
    const named = chartCurves({ labels: payload.labels, series: [challenger] });
    const observables = Array.isArray(challenger.observables) ? challenger.observables : [];
    const row = errors[challengerIndex];
    const metrics = row && Array.isArray(row.observables) ? row.observables : [];
    observables.forEach((values, index) => {
      const metric = metrics.find((item) => item && item.index === index) || null;
      curves.push({
        label: named[index] ? named[index].label : `${challenger.name} ${index}`,
        values: subtractSeries(reference[index], values),
        metric,
        index,
      });
    });
  });
  return curves;
}

function errorAxisTitle(payload) {
  const series = Array.isArray(payload.series) ? payload.series : [];
  const name = series[0]?.name ? String(series[0].name) : "reference";
  return `Error vs ${name}`;
}

function yAxisTitle(curves) {
  const letters = new Set();
  for (const curve of curves) {
    const match = String(curve.label).match(/⟨([A-Z])⟩/);
    if (match) letters.add(match[1]);
  }
  if (letters.size === 1) return `⟨${[...letters][0]}⟩`;
  return "Expectation";
}

function plotFraction(x, plotLeft, plotRight) {
  if (!Number.isFinite(x) || !Number.isFinite(plotLeft) || !Number.isFinite(plotRight)) return null;
  if (x < plotLeft || x > plotRight || plotRight === plotLeft) return null;
  return (x - plotLeft) / (plotRight - plotLeft);
}

function nearestTimeIndex(payload, fraction) {
  const times = Array.isArray(payload.times) ? payload.times : [];
  if (!times.length || !Number.isFinite(fraction)) return -1;
  const first = Number(times[0]);
  const last = Number(times[times.length - 1]);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return -1;
  const clamped = Math.min(1, Math.max(0, fraction));
  const target = first + clamped * (last - first);
  let best = -1;
  let bestDist = Infinity;
  for (let index = 0; index < times.length; index++) {
    const time = Number(times[index]);
    if (!Number.isFinite(time)) continue;
    const dist = Math.abs(time - target);
    if (dist < bestDist) {
      bestDist = dist;
      best = index;
    }
  }
  return best;
}

function shownCurves(payload, view, observable) {
  const curves = view === "error" ? errorCurves(payload) : chartCurves(payload);
  const simulator = view && view !== "curves" && view !== "error" ? view : null;
  const matched =
    simulator == null ? curves : curves.filter((curve) => curve.simulator === simulator);
  if (!Number.isInteger(observable)) return matched;
  return matched.filter((curve) => curve.index === observable);
}

function hoverReadout(payload, index, view, observable) {
  const times = Array.isArray(payload.times) ? payload.times : [];
  if (!Number.isInteger(index) || index < 0 || index >= times.length) return "";
  const time = Number(times[index]);
  if (!Number.isFinite(time)) return "";
  const parts = [];
  for (const curve of shownCurves(payload, view, observable)) {
    const values = Array.isArray(curve.values) ? curve.values : [];
    const raw = values[index];
    if (raw == null) continue;
    const value = Number(raw);
    if (!Number.isFinite(value)) continue;
    parts.push(`${curve.label} = ${formatAxis(value)}`);
  }
  if (!parts.length) return "";
  return [`t = ${formatAxis(time)}`, ...parts].join(" · ");
}

function formatMetric(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return String(Math.round(number * 10000) / 10000);
}

function legendText(curve) {
  const metric = curve.metric;
  if (!metric) return curve.label;
  const max = formatMetric(metric.linf);
  const rmse = formatMetric(metric.rmse);
  if (!max || !rmse) return curve.label;
  return `${curve.label}: max ${max}, RMSE ${rmse}`;
}

function resourceName(record) {
  if (record && typeof record.title === "string" && record.title) return record.title;
  const text = String(record?.simulator_id || "");
  const hash = text.indexOf("#");
  const base = hash === -1 ? text : text.slice(0, hash);
  const suffix = hash === -1 ? "" : text.slice(hash);
  const short = base.endsWith("_simulator") ? base.slice(0, -"_simulator".length) : base;
  return `${short}${suffix}`;
}

function resourceLine(resources) {
  if (!Array.isArray(resources) || !resources.length) return "";
  const several = resources.length > 1;
  const clauses = [];
  for (const record of resources) {
    if (!record || typeof record !== "object") continue;
    const time = formatSeconds(record.wall_time_s);
    const shots = shotBudget(record);
    const body = [time, shots, circuitMetrics(record)].filter(Boolean).join(", ");
    if (!body) continue;
    if (!several) {
      clauses.push(body);
      continue;
    }
    const name = resourceName(record);
    clauses.push(name ? `${name} ${body}` : body);
  }
  return clauses.join(" · ");
}

function formatSeconds(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return `${formatAxis(number)} s`;
}

function shotBudget(record) {
  const shots = record.shots_per_job;
  const jobs = record.num_jobs;
  if (!Number.isInteger(shots) || !Number.isInteger(jobs)) return "";
  return `${shots} shots × ${jobs}`;
}

function circuitMetrics(record) {
  const fields = [
    ["depth", "depth"],
    ["width", "width"],
    ["gate_count", "gates"],
    ["t_count", "T"],
    ["toffoli_count", "Toffoli"],
  ];
  return fields.map(([key, label]) => `${label} ${formatCircuitMetric(record[key])}`).join(", ");
}

function formatCircuitMetric(value) {
  if (typeof value === "number" && Number.isInteger(value)) return String(value);
  return "N/A";
}

function savedNote(payload) {
  const notes = [];
  const saved = Array.isArray(payload.saved)
    ? payload.saved.filter((item) => typeof item === "string")
    : [];
  if (saved.length) notes.push(`Saved to ${saved.join(", ")}`);
  if (typeof payload.exported === "string" && payload.exported)
    notes.push(`Exported to ${payload.exported}`);
  if (!notes.length) return null;
  return el("p", { className: "hint" }, notes.join(". "));
}

function observableChoices(payload) {
  const series = Array.isArray(payload.series) ? payload.series : [];
  if (series.length < 2) return [];
  let count = 0;
  for (const entry of series) {
    const observables = Array.isArray(entry.observables) ? entry.observables.length : 0;
    count = Math.max(count, observables);
  }
  if (count < 2) return [];
  const labels = Array.isArray(payload.labels) ? payload.labels : [];
  const choices = [{ key: "all", label: "All" }];
  for (let index = 0; index < count; index++) {
    const label =
      typeof labels[index] === "string" && labels[index] ? labels[index] : `Observable ${index}`;
    choices.push({ key: String(index), label });
  }
  return choices;
}

function chartViews(payload) {
  const series = Array.isArray(payload.series) ? payload.series : [];
  if (series.length < 2) return [];
  const views = [{ key: "curves", label: "Curves" }];
  for (const entry of series) {
    if (!entry?.name) continue;
    views.push({ key: String(entry.name), label: String(entry.name) });
  }
  views.push({ key: "error", label: "Error" });
  return views;
}

export function resultsComponent(payload) {
  const note = savedNote(payload);
  const views = chartViews(payload);
  const choices = observableChoices(payload);
  const host = el("div", { className: "chart-host" });
  let view = "curves";
  let observable = null;
  function draw() {
    host.replaceChildren(chartComponent(payload, view, observable));
    for (const button of viewButtons) {
      button.setAttribute(
        "aria-pressed",
        button.getAttribute("data-view") === view ? "true" : "false",
      );
    }
    for (const button of observableButtons) {
      const key = button.getAttribute("data-observable");
      const pressed = observable == null ? key === "all" : key === String(observable);
      button.setAttribute("aria-pressed", pressed ? "true" : "false");
    }
  }
  const viewButtons = views.map((choice) =>
    el(
      "button",
      {
        type: "button",
        role: "tab",
        "data-view": choice.key,
        "aria-pressed": choice.key === "curves" ? "true" : "false",
        onclick: () => {
          view = choice.key;
          draw();
        },
      },
      choice.label,
    ),
  );
  const observableButtons = choices.map((choice) =>
    el(
      "button",
      {
        type: "button",
        role: "tab",
        "data-observable": choice.key,
        "aria-pressed": choice.key === "all" ? "true" : "false",
        onclick: () => {
          observable = choice.key === "all" ? null : Number(choice.key);
          draw();
        },
      },
      choice.label,
    ),
  );
  draw();
  const line = resourceLine(payload.resources);
  const resources = line ? el("p", { className: "resources" }, line) : null;
  const observableSwitcher = observableButtons.length
    ? el(
        "div",
        { className: "chart-switch", role: "tablist", "aria-label": "Observable" },
        ...observableButtons,
      )
    : null;
  const viewSwitcher = viewButtons.length
    ? el(
        "div",
        { className: "chart-switch", role: "tablist", "aria-label": "Chart" },
        ...viewButtons,
      )
    : null;
  if (!note && !observableSwitcher && !viewSwitcher && !resources) return host.children[0];
  return el(
    "div",
    { className: "results" },
    note,
    observableSwitcher,
    viewSwitcher,
    host,
    resources,
  );
}

function curveColor(index, count) {
  if (count <= CURVE_COLORS.length) return CURVE_COLORS[index];
  const hue = Math.round((360 * index) / count);
  return `hsl(${hue} 58% 42%)`;
}

function finitePairs(times, values) {
  const pairs = [];
  if (!Array.isArray(values)) return pairs;
  const count = Math.min(times.length, values.length);
  for (let index = 0; index < count; index++) {
    const time = times[index];
    const value = values[index];
    if (time == null || value == null) continue;
    const x = Number(time);
    const y = Number(value);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    pairs.push([x, y]);
  }
  return pairs;
}

function chartComponent(payload, view, observable) {
  const times = Array.isArray(payload.times) ? payload.times : [];
  const error = view === "error";
  const curves = shownCurves(payload, view, observable);
  if (!times.length || !curves.length) {
    return el("p", { className: "placeholder" }, "The run returned no curves.");
  }
  const plotted = curves.map((curve) => finitePairs(times, curve.values));
  const width = 640;
  const height = 220;
  const pad = 28;
  const padLeft = 56;
  const first = Number(times[0]);
  const last = Number(times[times.length - 1]);
  let yMin = Infinity;
  let yMax = -Infinity;
  for (const pairs of plotted) {
    for (const [, value] of pairs) {
      yMin = Math.min(yMin, value);
      yMax = Math.max(yMax, value);
    }
  }
  if (!Number.isFinite(yMin) || !Number.isFinite(yMax)) {
    return el("p", { className: "placeholder" }, "The run returned no curves.");
  }
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }
  const xSpan = last - first || 1;
  const ySpan = yMax - yMin;
  const plotLeft = padLeft;
  const plotRight = width - pad;
  const sx = (time) => plotLeft + ((Number(time) - first) / xSpan) * (plotRight - plotLeft);
  const sy = (value) => height - pad - ((Number(value) - yMin) / ySpan) * (height - pad * 2);
  const yTitle = error ? errorAxisTitle(payload) : yAxisTitle(curves);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "plot");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${yTitle} versus time`);
  const axis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  axis.setAttribute("x1", String(padLeft));
  axis.setAttribute("x2", String(width - pad));
  axis.setAttribute("y1", String(height - pad));
  axis.setAttribute("y2", String(height - pad));
  const yAxis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  yAxis.setAttribute("x1", String(padLeft));
  yAxis.setAttribute("x2", String(padLeft));
  yAxis.setAttribute("y1", String(pad));
  yAxis.setAttribute("y2", String(height - pad));
  svg.append(axis, yAxis);
  plotted.forEach((pairs, index) => {
    if (!pairs.length) return;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", curveColor(index, curves.length));
    line.setAttribute("stroke-width", "2");
    line.setAttribute("points", pairs.map(([time, value]) => `${sx(time)},${sy(value)}`).join(" "));
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = curves[index].label;
    line.append(title);
    svg.append(line);
  });
  for (const tick of [yMin, (yMin + yMax) / 2, yMax]) {
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", String(padLeft - 6));
    label.setAttribute("y", String(sy(tick)));
    label.setAttribute("text-anchor", "end");
    label.setAttribute("dominant-baseline", "middle");
    label.textContent = formatAxis(tick);
    svg.append(label);
  }
  const startLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  startLabel.setAttribute("x", String(padLeft));
  startLabel.setAttribute("y", String(height - 8));
  startLabel.textContent = formatAxis(first);
  const endLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  endLabel.setAttribute("x", String(width - pad));
  endLabel.setAttribute("y", String(height - 8));
  endLabel.setAttribute("text-anchor", "end");
  endLabel.textContent = formatAxis(last);
  svg.append(startLabel, endLabel);
  const readout = el("p", { className: "readout" });
  svg.addEventListener("pointermove", (event) => {
    const rect = svg.getBoundingClientRect();
    if (!rect.width) return;
    const x = ((event.clientX - rect.left) / rect.width) * width;
    const fraction = plotFraction(x, plotLeft, plotRight);
    readout.textContent =
      fraction == null
        ? ""
        : hoverReadout(payload, nearestTimeIndex(payload, fraction), view, observable);
  });
  svg.addEventListener("pointerleave", () => {
    readout.textContent = "";
  });
  return el(
    "div",
    { className: "chart" },
    el(
      "div",
      { className: "plot-frame" },
      el("span", { className: "y-title" }, yTitle),
      el("div", { className: "plot-column" }, svg, el("p", { className: "x-title" }, "Time")),
    ),
    readout,
    el(
      "ul",
      { className: "legend" },
      ...curves.map((curve, index) =>
        el(
          "li",
          {},
          el("i", { style: `background:${curveColor(index, curves.length)}` }),
          legendText(curve),
        ),
      ),
    ),
  );
}
