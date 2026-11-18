/* Chart for a finished run. */

import { el } from "./dom.js";

const CURVE_COLORS = ["#4c4cb8", "#1f7a6c", "#a67c1a", "#b66880", "#6a4ca8"];

function formatAxis(value) {
  if (!Number.isFinite(value)) return "";
  if (Number.isInteger(value)) return String(value);
  return String(Math.round(value * 1000) / 1000);
}

function niceNum(range, round) {
  if (!Number.isFinite(range) || range <= 0) return 1;
  const exponent = Math.floor(Math.log10(range));
  const fraction = range / 10 ** exponent;
  let nice;
  if (round) {
    if (fraction < 1.5) nice = 1;
    else if (fraction < 3) nice = 2;
    else if (fraction < 7) nice = 5;
    else nice = 10;
  } else if (fraction <= 1) nice = 1;
  else if (fraction <= 2) nice = 2;
  else if (fraction <= 5) nice = 5;
  else nice = 10;
  return nice * 10 ** exponent;
}

function niceTicks(min, max, targetCount = 5) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  let lo = Number(min);
  let hi = Number(max);
  if (lo === hi) {
    lo -= 1;
    hi += 1;
  } else if (lo > hi) {
    [lo, hi] = [hi, lo];
  }
  const target = Math.max(2, Math.round(Number(targetCount)) || 5);
  const range = niceNum(hi - lo, false);
  const step = niceNum(range / (target - 1), true);
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const count = Math.round((end - start) / step);
  const ticks = [];
  for (let index = 0; index <= count; index++) {
    ticks.push(Number((start + index * step).toPrecision(12)));
  }
  return ticks;
}

function ticksInDomain(min, max, targetCount = 5) {
  const ticks = niceTicks(min, max, targetCount).filter((tick) => tick >= min && tick <= max);
  if (!ticks.length) return [min, max];
  if (ticks[0] !== min) ticks.unshift(min);
  if (ticks[ticks.length - 1] !== max) ticks.push(max);
  return ticks;
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

function hoverReadout(payload, index, view, observable, curves) {
  const times = Array.isArray(payload.times) ? payload.times : [];
  if (!Number.isInteger(index) || index < 0 || index >= times.length) return "";
  const time = Number(times[index]);
  if (!Number.isFinite(time)) return "";
  const listed = Array.isArray(curves) ? curves : shownCurves(payload, view, observable);
  const parts = [];
  for (const curve of listed) {
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

function comparisonLines(payload) {
  const series = Array.isArray(payload.series) ? payload.series : [];
  if (series.length < 2) return [];
  const errors = Array.isArray(payload.errors) ? payload.errors : [];
  if (!errors.length) return [];
  const reference = series[0]?.name ? String(series[0].name) : "reference";
  const labels = Array.isArray(payload.labels) ? payload.labels : [];
  const lines = [];
  series.slice(1).forEach((challenger, challengerIndex) => {
    const row = errors[challengerIndex];
    const metrics = row && Array.isArray(row.observables) ? row.observables : [];
    if (!metrics.length) return;
    const name = challenger?.name ? String(challenger.name) : `challenger ${challengerIndex + 1}`;
    const several = metrics.length > 1;
    for (const metric of metrics) {
      const max = formatMetric(metric.linf);
      const rmse = formatMetric(metric.rmse);
      if (!max || !rmse) continue;
      const index = metric.index;
      const observable =
        typeof labels[index] === "string" && labels[index]
          ? labels[index]
          : Number.isInteger(index)
            ? `Observable ${index}`
            : "";
      const head =
        several && observable
          ? `${name} vs ${reference} · ${observable}`
          : `${name} vs ${reference}`;
      lines.push(`${head}: max ${max}, RMSE ${rmse}`);
    }
  });
  return lines;
}

function comparisonSummary(payload) {
  const lines = comparisonLines(payload);
  if (!lines.length) return null;
  return el("p", { className: "comparison" }, lines.join(" · "));
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
  return fields
    .map(([key, label]) => {
      const value = formatCircuitMetric(record[key]);
      return value ? `${label} ${value}` : "";
    })
    .filter(Boolean)
    .join(", ");
}

function formatCircuitMetric(value) {
  if (typeof value === "number" && Number.isInteger(value)) return String(value);
  return "";
}

export function savedNote(payload) {
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

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  const text = value == null ? "" : String(value);
  if (/[",\n\r]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

function seriesDownload(payload, view, observable) {
  const times = Array.isArray(payload.times) ? payload.times : [];
  const curves = shownCurves(payload, view, observable).map((curve) => ({
    label: curve.label,
    values: Array.isArray(curve.values) ? [...curve.values] : [],
  }));
  return {
    times: [...times],
    view,
    observable: Number.isInteger(observable) ? observable : null,
    curves,
  };
}

function seriesCsv(payload, view, observable) {
  const data = seriesDownload(payload, view, observable);
  const header = ["t", ...data.curves.map((curve) => curve.label)].map(csvCell).join(",");
  const rows = data.times.map((time, index) => {
    const cells = [
      time,
      ...data.curves.map((curve) => {
        const raw = curve.values[index];
        if (raw == null) return "";
        const value = Number(raw);
        return Number.isFinite(value) ? value : "";
      }),
    ];
    return cells.map(csvCell).join(",");
  });
  return [header, ...rows].join("\n");
}

function downloadSeries(payload, view, observable) {
  const body = seriesCsv(payload, view, observable);
  downloadBlob("shadowsim-series.csv", new Blob([body], { type: "text/csv" }));
}

function plotSize(svg) {
  const box = svg.viewBox?.baseVal;
  const width = box?.width ? box.width : Number(svg.getAttribute("width")) || 640;
  const height = box?.height ? box.height : Number(svg.getAttribute("height")) || 220;
  return { width, height };
}

function renderSvgPng(svg, done) {
  if (!svg || typeof done !== "function") return;
  const markup = new XMLSerializer().serializeToString(svg);
  const url = URL.createObjectURL(new Blob([markup], { type: "image/svg+xml;charset=utf-8" }));
  const image = new Image();
  image.onload = () => {
    const { width, height } = plotSize(svg);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    URL.revokeObjectURL(url);
    if (!ctx || typeof canvas.toBlob !== "function") {
      done(null);
      return;
    }
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(image, 0, 0);
    canvas.toBlob((blob) => done(blob || null), "image/png");
  };
  image.onerror = () => {
    URL.revokeObjectURL(url);
    done(null);
  };
  image.src = url;
}

function downloadFigure(host) {
  const svg = host.querySelector("svg.plot");
  if (!svg) return;
  renderSvgPng(svg, (blob) => {
    if (blob) downloadBlob("shadowsim-figure.png", blob);
  });
}

export function resultsComponent(payload) {
  const note = savedNote(payload);
  const comparison = comparisonSummary(payload);
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
        { className: "chart-switch", role: "group", "aria-label": "Observable" },
        ...observableButtons,
      )
    : null;
  const viewSwitcher = viewButtons.length
    ? el("div", { className: "chart-switch", role: "group", "aria-label": "Chart" }, ...viewButtons)
    : null;
  const actions = el(
    "div",
    { className: "panel-actions" },
    el(
      "button",
      {
        type: "button",
        className: "copy",
        onclick: () => downloadFigure(host),
      },
      "Download PNG",
    ),
    el(
      "button",
      {
        type: "button",
        className: "copy",
        onclick: () => downloadSeries(payload, view, observable),
      },
      "Download CSV",
    ),
  );
  return el(
    "div",
    { className: "results" },
    note,
    comparison,
    observableSwitcher,
    viewSwitcher,
    actions,
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
  const hidden = new Set();
  let showTable = false;
  const root = el("div", { className: "chart" });
  const width = 640;
  const height = 220;
  const pad = 28;
  const padLeft = 56;
  const first = Number(times[0]);
  const last = Number(times[times.length - 1]);

  function legendList() {
    return el(
      "ul",
      { className: "legend" },
      ...curves.map((curve, index) => {
        const on = !hidden.has(index);
        return el(
          "li",
          {},
          el(
            "button",
            {
              type: "button",
              "aria-pressed": on ? "true" : "false",
              className: on ? null : "off",
              onclick: () => {
                if (hidden.has(index)) hidden.delete(index);
                else hidden.add(index);
                render();
              },
            },
            el("i", { style: `background:${curveColor(index, curves.length)}` }),
            curve.label,
          ),
        );
      }),
    );
  }

  function tableToggle() {
    return el(
      "button",
      {
        type: "button",
        className: "chart-table-toggle",
        "aria-expanded": showTable ? "true" : "false",
        onclick: () => {
          showTable = !showTable;
          render();
        },
      },
      showTable ? "Hide data table" : "Show data table",
    );
  }

  function dataTable(visible) {
    if (!showTable) return null;
    const listed = visible.map((entry) => entry.curve);
    return el(
      "table",
      { className: "chart-table" },
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          el("th", { scope: "col" }, "Time"),
          ...listed.map((curve) => el("th", { scope: "col" }, curve.label)),
        ),
      ),
      el(
        "tbody",
        {},
        ...times.map((time, index) =>
          el(
            "tr",
            {},
            el("th", { scope: "row" }, formatAxis(Number(time))),
            ...listed.map((curve) => {
              const values = Array.isArray(curve.values) ? curve.values : [];
              const raw = values[index];
              if (raw == null) return el("td", {}, "");
              const value = Number(raw);
              return el("td", {}, Number.isFinite(value) ? formatAxis(value) : "");
            }),
          ),
        ),
      ),
    );
  }

  function chartChrome(visible) {
    return [legendList(), tableToggle(), dataTable(visible)].filter(Boolean);
  }

  function render() {
    const visible = curves
      .map((curve, index) => ({ curve, index }))
      .filter((entry) => !hidden.has(entry.index));
    if (!visible.length) {
      root.replaceChildren(
        el("p", { className: "placeholder" }, "The run returned no curves."),
        ...chartChrome(visible),
      );
      return;
    }
    const plotted = visible.map((entry) => ({
      ...entry,
      pairs: finitePairs(times, entry.curve.values),
    }));
    let yMin = Infinity;
    let yMax = -Infinity;
    for (const entry of plotted) {
      for (const [, value] of entry.pairs) {
        yMin = Math.min(yMin, value);
        yMax = Math.max(yMax, value);
      }
    }
    if (!Number.isFinite(yMin) || !Number.isFinite(yMax)) {
      root.replaceChildren(
        el("p", { className: "placeholder" }, "The run returned no curves."),
        ...chartChrome(visible),
      );
      return;
    }
    if (yMin === yMax) {
      yMin -= 1;
      yMax += 1;
    }
    const yTicks = niceTicks(yMin, yMax);
    yMin = yTicks[0];
    yMax = yTicks[yTicks.length - 1];
    const xTicks = ticksInDomain(first, last);
    const xSpan = last - first || 1;
    const ySpan = yMax - yMin || 1;
    const plotLeft = padLeft;
    const plotRight = width - pad;
    const plotTop = pad;
    const plotBottom = height - pad;
    const sx = (time) => plotLeft + ((Number(time) - first) / xSpan) * (plotRight - plotLeft);
    const sy = (value) => plotBottom - ((Number(value) - yMin) / ySpan) * (plotBottom - plotTop);
    const listed = visible.map((entry) => entry.curve);
    const yTitle = error ? errorAxisTitle(payload) : yAxisTitle(listed);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "plot");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", `${yTitle} versus time`);
    for (const tick of yTicks) {
      if (tick === yMin || tick === yMax) continue;
      const grid = document.createElementNS("http://www.w3.org/2000/svg", "line");
      grid.setAttribute("class", "grid");
      grid.setAttribute("x1", String(plotLeft));
      grid.setAttribute("x2", String(plotRight));
      grid.setAttribute("y1", String(sy(tick)));
      grid.setAttribute("y2", String(sy(tick)));
      svg.append(grid);
    }
    for (const tick of xTicks) {
      if (tick === first || tick === last) continue;
      const grid = document.createElementNS("http://www.w3.org/2000/svg", "line");
      grid.setAttribute("class", "grid");
      grid.setAttribute("x1", String(sx(tick)));
      grid.setAttribute("x2", String(sx(tick)));
      grid.setAttribute("y1", String(plotTop));
      grid.setAttribute("y2", String(plotBottom));
      svg.append(grid);
    }
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
    for (const entry of plotted) {
      if (!entry.pairs.length) continue;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", curveColor(entry.index, curves.length));
      line.setAttribute("stroke-width", "2");
      line.setAttribute(
        "points",
        entry.pairs.map(([time, value]) => `${sx(time)},${sy(value)}`).join(" "),
      );
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = entry.curve.label;
      line.append(title);
      svg.append(line);
    }
    for (const tick of yTicks) {
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("data-axis", "y");
      label.setAttribute("x", String(padLeft - 6));
      label.setAttribute("y", String(sy(tick)));
      label.setAttribute("text-anchor", "end");
      label.setAttribute("dominant-baseline", "middle");
      label.textContent = formatAxis(tick);
      svg.append(label);
    }
    for (const [index, tick] of xTicks.entries()) {
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("data-axis", "x");
      label.setAttribute("x", String(sx(tick)));
      label.setAttribute("y", String(height - 8));
      if (index === xTicks.length - 1) label.setAttribute("text-anchor", "end");
      else if (index > 0) label.setAttribute("text-anchor", "middle");
      label.textContent = formatAxis(tick);
      svg.append(label);
    }
    const hover = document.createElementNS("http://www.w3.org/2000/svg", "g");
    hover.setAttribute("class", "hover");
    svg.append(hover);
    const readout = el("p", { className: "readout" });
    function clearHover() {
      hover.replaceChildren();
      readout.textContent = "";
    }
    function showHover(index) {
      hover.replaceChildren();
      if (!Number.isInteger(index) || index < 0 || index >= times.length) {
        readout.textContent = "";
        return;
      }
      const time = Number(times[index]);
      if (!Number.isFinite(time)) {
        readout.textContent = "";
        return;
      }
      const x = sx(time);
      const crosshair = document.createElementNS("http://www.w3.org/2000/svg", "line");
      crosshair.setAttribute("class", "crosshair");
      crosshair.setAttribute("x1", String(x));
      crosshair.setAttribute("x2", String(x));
      crosshair.setAttribute("y1", String(plotTop));
      crosshair.setAttribute("y2", String(plotBottom));
      hover.append(crosshair);
      for (const entry of visible) {
        const values = Array.isArray(entry.curve.values) ? entry.curve.values : [];
        const raw = values[index];
        if (raw == null) continue;
        const value = Number(raw);
        if (!Number.isFinite(value)) continue;
        const marker = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        marker.setAttribute("class", "marker");
        marker.setAttribute("cx", String(x));
        marker.setAttribute("cy", String(sy(value)));
        marker.setAttribute("r", "4");
        marker.setAttribute("fill", curveColor(entry.index, curves.length));
        hover.append(marker);
      }
      readout.textContent = hoverReadout(payload, index, view, observable, listed);
    }
    svg.addEventListener("pointermove", (event) => {
      const rect = svg.getBoundingClientRect();
      if (!rect.width) return;
      const x = ((event.clientX - rect.left) / rect.width) * width;
      const fraction = plotFraction(x, plotLeft, plotRight);
      if (fraction == null) {
        clearHover();
        return;
      }
      showHover(nearestTimeIndex(payload, fraction));
    });
    svg.addEventListener("pointerleave", clearHover);
    root.replaceChildren(
      el(
        "div",
        { className: "plot-frame" },
        el("span", { className: "y-title" }, yTitle),
        el("div", { className: "plot-column" }, svg, el("p", { className: "x-title" }, "Time")),
      ),
      readout,
      ...chartChrome(visible),
    );
  }

  render();
  return root;
}
