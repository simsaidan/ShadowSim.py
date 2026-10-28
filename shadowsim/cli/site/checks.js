/* Readiness checks and the code preview. This file does not touch document. */

(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.checks = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  let page = null;

  function using(state, fn) {
    const previous = page;
    page = state;
    try {
      return fn();
    } finally {
      page = previous;
    }
  }

  function bind(fn) {
    return (state, ...args) => using(state, () => fn(...args));
  }

  function blockById(laneId, blockId) {
    return page.blocks[laneId].find((block) => block.id === blockId) ?? null;
  }

  function chosenFactory() {
    return page.modelFactories.find((item) => item.id === page.preexistingId) ?? null;
  }

  function operatorsReady() {
    if (page.selection.model === "preexisting" || !page.modelTerms.length) return false;
    if (page.modelTerms.some((term) => termProblem(term))) return false;
    return page.modelTerms.some((term) => term.id === "hamiltonian" || term.id === "local_hamiltonian");
  }

  function usingAddedOperators() {
    return page.selection.model !== "preexisting" && page.modelTerms.length > 0;
  }

  function termProblem(term) {
    if (term.id === "hamiltonian") return hamiltonianProblem(term);
    if (term.id === "local_hamiltonian") return localHamiltonianProblem(term);
    if (term.id === "lindblad") return lindbladProblem(term);
    return "Unknown operator.";
  }

  function isReference(entry) {
    const block = blockById("simulator", entry.id);
    if (!block) return entry.id === "qutip";
    return Boolean(block.observables);
  }

  function needsBackend() {
    return page.placedSims.some((entry) => !isReference(entry));
  }

  function backendFits(entry, backendId) {
    if (!entry || isReference(entry) || !backendId) return false;
    const backend = blockById("backend", backendId);
    if (!backend) return false;
    const simulator = blockById("simulator", entry.id);
    if (simulator?.samples && !backend.shots) return false;
    return true;
  }

  function socketsReady() {
    return page.placedSims.every((entry) => isReference(entry) || backendFits(entry, entry.backend));
  }

  function socketStatus(preview) {
    if (!otherSlotsPlaced()) return null;
    const open = page.placedSims.find((entry) => !isReference(entry) && !backendFits(entry, entry.backend));
    if (!open) return null;
    const tail = preview ? " to preview the script." : ".";
    return `Snap a backend onto each simulator${tail}`;
  }

  function otherSlotsPlaced() {
    return page.lanes.every((lane) => {
      if (lane.id === "model") return true;
      if (lane.id === "backend" && !needsBackend()) return true;
      return Boolean(blockById(lane.id, page.selection[lane.id]));
    });
  }

  function operatorStatus(preview) {
    if (!otherSlotsPlaced() || !usingAddedOperators() || operatorsReady()) return null;
    const tail = preview ? " to preview the script." : ".";
    const hasHamiltonian = page.modelTerms.some(
      (term) => term.id === "hamiltonian" || term.id === "local_hamiltonian",
    );
    return hasHamiltonian ? `Enter a valid operator${tail}` : `Enter a Hamiltonian${tail}`;
  }

  function isComplete() {
    const lanesReady = page.lanes.every((lane) => {
      if (lane.id === "backend" && !needsBackend()) return true;
      if (lane.id === "model" && page.selection.model === "preexisting") return Boolean(chosenFactory());
      if (lane.id === "model") return operatorsReady();
      return Boolean(blockById(lane.id, page.selection[lane.id]));
    });
    return lanesReady && socketsReady();
  }

  function settingNumber(key) {
    if (page.settings[key] === "") return null;
    const value = Number(page.settings[key]);
    return Number.isFinite(value) ? value : null;
  }

  function formatSetting(key) {
    const value = settingNumber(key);
    if (value == null) return null;
    return Object.is(value, -0) ? "0" : String(value);
  }

  function qubitPhrase() {
    const label = formatSetting("qubits");
    if (label == null) return null;
    return Number(label) === 1 ? "1 qubit" : `${label} qubits`;
  }

  function pyFloat(value) {
    return Number.isInteger(value) ? `${value}.0` : String(value);
  }

  function stateOwnsQubits() {
    return Object.hasOwn(page.stateLimits, page.selection.state);
  }

  function numberList(raw, maxCount) {
    const text = raw.trim();
    if (!text || text.endsWith(",")) return null;
    const parts = text.split(",").map((part) => part.trim());
    if (!parts.length || parts.length > maxCount) return null;
    const values = [];
    for (const part of parts) {
      if (!/^-?(?:\d+(?:\.\d+)?|\.\d+)$/.test(part)) return null;
      values.push(Number(part));
    }
    return values;
  }

  function amplitudeQubits(count) {
    let padded = 1;
    while (padded < count) padded *= 2;
    return Math.log2(Math.max(2, padded));
  }

  function stateValues() {
    if (page.selection.state === "angle") return numberList(page.angleText, page.stateLimits.angle);
    if (page.selection.state === "amplitude") return numberList(page.amplitudeText, page.stateLimits.amplitude);
    return null;
  }

  function positiveIntText(value) {
    return /^[1-9]\d*$/.test(value);
  }

  function emitterCount() {
    const text = page.emitterText.trim();
    if (!positiveIntText(text)) return null;
    const count = Number(text);
    return count <= page.maxEmitters ? count : null;
  }

  function cavityModelSelected() {
    return (
      page.selection.model === "preexisting" &&
      (page.preexistingId === "jaynes_cummings" || page.preexistingId === "tavis_cummings")
    );
  }

  function fixedFactoryQubits() {
    if (page.selection.model !== "preexisting") return null;
    if (page.preexistingId === "jaynes_cummings") return 3;
    if (page.preexistingId === "tavis_cummings") {
      const count = emitterCount();
      return count == null ? null : 2 + count;
    }
    return null;
  }

  function emitterProblem() {
    return (
      page.selection.model === "preexisting" && page.preexistingId === "tavis_cummings" && emitterCount() == null
    );
  }

  function stateImpliedQubits() {
    if (page.selection.state === "basis") return page.basisBits ? page.basisBits.length : null;
    if (page.selection.state === "gray") return page.grayBits ? page.grayBits.length : null;
    if (page.selection.state === "angle") return numberList(page.angleText, page.stateLimits.angle)?.length ?? null;
    if (page.selection.state === "amplitude") {
      const values = numberList(page.amplitudeText, page.stateLimits.amplitude);
      if (values && values.some((value) => value !== 0)) return amplitudeQubits(values.length);
    }
    return null;
  }

  function stateSizeProblem() {
    const expected = fixedFactoryQubits();
    if (expected == null) return null;
    const actual = stateImpliedQubits();
    if (actual == null || actual === expected) return null;
    return expected;
  }

  function stateSizeStatus(preview) {
    const expected = stateSizeProblem();
    const tail = preview ? " to preview the script." : ".";
    if (page.selection.state === "basis") return `Enter a ${expected}-bit basis string${tail}`;
    if (page.selection.state === "gray") return `Enter a ${expected}-bit Gray code string${tail}`;
    if (page.selection.state === "angle") return `Enter ${expected} angles${tail}`;
    return `Enter amplitudes for ${expected} qubits${tail}`;
  }

  function stateInputProblem() {
    if (stateSizeProblem() != null) return "size";
    if (page.selection.state === "basis") return page.basisBits === "" ? "basis" : null;
    if (page.selection.state === "gray") return page.grayBits === "" ? "gray" : null;
    if (page.selection.state === "angle") return numberList(page.angleText, page.stateLimits.angle) ? null : "angle";
    if (page.selection.state === "amplitude") {
      const values = numberList(page.amplitudeText, page.stateLimits.amplitude);
      if (!values || values.every((value) => value === 0)) return "amplitude";
    }
    return null;
  }

  function entryParamsReady(entry) {
    const params = entry.params;
    if (!positiveIntText(params.timeSteps)) return false;
    if (entry.id === "qutip") return true;
    if (!positiveIntText(params.numSteps) || !positiveIntText(params.trotterDepth)) return false;
    if (!/^-?\d+$/.test(params.seed)) return false;
    return params.order === "1" || params.order === "2";
  }

  function simParamsReady() {
    return page.placedSims.every(entryParamsReady);
  }

  function sameTimeGrid() {
    if (page.placedSims.length < 2) return true;
    const steps = page.placedSims[0].params.timeSteps;
    return page.placedSims.every((entry) => entry.params.timeSteps === steps);
  }

  function hasThen(id) {
    return page.placedThens.includes(id);
  }

  function missingPaths() {
    const missing = [];
    if (hasThen("save") && page.savePath.trim() === "") missing.push("save");
    if (hasThen("export") && page.exportPath.trim() === "") missing.push("export");
    return missing;
  }

  function savePathReady() {
    return missingPaths().length === 0;
  }

  function qubitCount() {
    const value = settingNumber("qubits");
    if (value == null || !Number.isInteger(value) || value < 1) return null;
    return value;
  }

  function selectedSites(count) {
    if (count == null) return [];
    if (page.measureSites == null) return Array.from({ length: count }, (_, index) => index);
    return page.measureSites.filter((site) => Number.isInteger(site) && site >= 0 && site < count);
  }

  function shotsReady() {
    return page.placedSims.every((entry) => {
      const backend = blockById("backend", entry.backend);
      if (!backend?.shots) return true;
      return positiveIntText(String(entry.shots ?? "").trim());
    });
  }

  function measureSitesReady() {
    const count = qubitCount();
    if (!page.selection.measure || count == null) return true;
    return selectedSites(count).length > 0;
  }

  function pyString(value) {
    return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }

  function qubitBounds() {
    if (usingAddedOperators()) return { min: 1, max: page.maxOperatorQubits };
    // The factory that takes n_qubits is Ising, which requires at least 2.
    if (page.selection.model === "preexisting" && chosenFactory()?.qubits) return { min: 2, max: null };
    return { min: 1, max: null };
  }

  function qubitProblem(preview) {
    const value = settingNumber("qubits");
    if (value == null) return null;
    const { min, max } = qubitBounds();
    const tail = preview ? " to preview the script." : ".";
    if (!Number.isInteger(value) || value < min) return `Qubits must be an integer of at least ${min}${tail}`;
    if (max != null && value > max) return `Qubits must be from 1 to ${max}${tail}`;
    return null;
  }

  function totalProblem(preview) {
    const value = settingNumber("total");
    if (value == null || value > 0) return null;
    const tail = preview ? " to preview the script." : ".";
    return `Total time must be a positive number${tail}`;
  }

  function numberProblem(preview) {
    if (settingNumber("qubits") == null || settingNumber("total") == null) {
      return preview ? "Enter qubits and total time to preview the script." : "Enter qubits and total time.";
    }
    return qubitProblem(preview) ?? totalProblem(preview);
  }

  function settingsReady() {
    return (
      numberProblem(false) == null &&
      stateInputProblem() == null &&
      simParamsReady() &&
      sameTimeGrid() &&
      savePathReady() &&
      measureSitesReady() &&
      shotsReady() &&
      !emitterProblem() &&
      (!usingAddedOperators() || operatorsReady())
    );
  }

  function runAllowed() {
    return isComplete() && settingsReady();
  }

  function stateLine() {
    if (page.selection.state === "basis" || page.selection.state === "gray") {
      const bits = page.selection.state === "basis" ? page.basisBits : page.grayBits;
      const name = page.selection.state === "basis" ? "ComputationalBasisEncoding" : "GrayEncoding";
      return `state = ${name}(${bits.length}).encode([${[...bits].join(", ")}])`;
    }
    const values = stateValues();
    if (!values) return "";
    const rendered = values.map(pyFloat).join(", ");
    if (page.selection.state === "angle") return `state = AngleEncoding().encode([${rendered}])`;
    if (page.selection.state === "amplitude") return `state = AmplitudeEncoding().encode([${rendered}])`;
    return "";
  }

  function fillSetup(block, name, shots = "") {
    const qubits = settingNumber("qubits");
    const total = settingNumber("total");
    return block.setup
      .replaceAll("{name}", name)
      .replaceAll("{qubits}", qubits == null ? "" : String(Math.round(qubits)))
      .replaceAll("{total}", total == null ? "" : pyFloat(total))
      .replaceAll("{shots}", String(shots ?? "").trim());
  }

  function modelLine() {
    const factory = chosenFactory();
    if (page.selection.model === "preexisting" && page.preexistingId === "tavis_cummings" && emitterCount() != null) {
      return `model = tavis_cummings(n_emitters=${emitterCount()})`;
    }
    if (page.selection.model === "preexisting" && factory) return fillSetup(factory, "");
    return usingAddedOperators() ? addedOperatorLines() : "";
  }

  function matrixLiteral(term) {
    const parsed = term.id === "lindblad" ? squareMatrix(term.matrix ?? "") : inspectMatrix(term.matrix ?? "");
    const rows = parsed.matrix.map((row) => `[${row.map(pyComplex).join(", ")}]`).join(", ");
    return `np.array([${rows}], dtype=complex)`;
  }

  function addedOperatorLines() {
    const count = qubitCount();
    const seen = {};
    const lines = [];
    const qutip = [];
    const circuit = [];
    const lindblads = [];
    page.modelTerms.forEach((term) => {
      const block = blockById("model", term.id);
      if (!block || termProblem(term)) return;
      seen[term.id] = (seen[term.id] || 0) + 1;
      const suffix = seen[term.id] === 1 ? "" : `_${seen[term.id]}`;
      const name = `${block.stem}${suffix}`;
      const matrix = matrixLiteral(term);
      if (term.id === "hamiltonian") {
        lines.push(`${name} = Hamiltonian(${matrix})`);
        qutip.push(name);
        circuit.push(`${name}.to_local_hamiltonian()`);
      } else if (term.id === "local_hamiltonian") {
        const sites = localSites(term, count).join(", ");
        lines.push(`${name} = LocalHamiltonian(${matrix}, [${sites}])`);
        qutip.push(name);
        circuit.push(name);
      } else if (term.id === "lindblad") {
        const sites = localSites(term, count).join(", ");
        lines.push(`${name} = LocalOperator(${matrix}, [${sites}])`);
        lindblads.push(name);
      }
    });
    lines.push(`qutip_hamiltonians = [${qutip.join(", ")}]`);
    lines.push(`circuit_hamiltonians = [${circuit.join(", ")}]`);
    lines.push(`lindblads = [${lindblads.join(", ")}]`);
    lines.push(`lindblads_full = [op.to_full_operator(${count}) for op in lindblads]`);
    return lines.join("\n");
  }

  function postedTerms() {
    if (!operatorsReady()) return undefined;
    return page.modelTerms.map((term) => {
      const parsed = term.id === "lindblad" ? squareMatrix(term.matrix ?? "") : inspectMatrix(term.matrix ?? "");
      const body = {
        id: term.id,
        matrix: parsed.matrix.map((row) => row.map((value) => [value.re, value.im])),
      };
      if (term.id !== "hamiltonian") body.sites = localSites(term, qubitCount());
      return body;
    });
  }

  function pyComplex(value) {
    if (value.im === 0) return pyFloat(value.re);
    const imag = `${pyFloat(Math.abs(value.im))}j`;
    const signed = value.im < 0 ? `-${imag}` : imag;
    if (value.re === 0) return signed;
    return `(${pyFloat(value.re)}${value.im < 0 ? "" : "+"}${signed})`;
  }

  function termLines() {
    if (usingAddedOperators()) return [];
    const seen = {};
    return page.modelTerms.flatMap((term) => {
      const block = blockById("model", term.id);
      if (!block) return [];
      seen[term.id] = (seen[term.id] || 0) + 1;
      const suffix = seen[term.id] === 1 ? "" : `_${seen[term.id]}`;
      const name = `${block.stem}${suffix}`;
      if (term.id === "lindblad") {
        if (lindbladProblem(term)) return [fillSetup(block, name)];
        const parsed = squareMatrix(term.matrix ?? "");
        const rows = parsed.matrix.map((row) => `[${row.map(pyComplex).join(", ")}]`).join(", ");
        const sites = localSites(term, qubitCount()).join(", ");
        return [`${name} = LocalOperator(np.array([${rows}], dtype=complex), [${sites}])`];
      }
      if (term.id !== "hamiltonian" && term.id !== "local_hamiltonian") return [fillSetup(block, name)];
      const inspected = inspectMatrix(term.matrix ?? "");
      const localProblem = term.id === "local_hamiltonian" && localHamiltonianProblem(term);
      if (inspected.problem || localProblem) return [fillSetup(block, name)];
      const rows = inspected.matrix.map((row) => `[${row.map(pyComplex).join(", ")}]`).join(", ");
      const matrix = `np.array([${rows}], dtype=complex)`;
      if (term.id === "hamiltonian") return [`${name} = Hamiltonian(${matrix})`];
      const sites = localSites(term, qubitCount()).join(", ");
      return [`${name} = LocalHamiltonian(${matrix}, [${sites}])`];
    });
  }

  function observableSetup() {
    const letter = page.selection.measure.toUpperCase();
    const count = qubitCount();
    const sites = selectedSites(count);
    if (count == null || sites.length === count) {
      const countName = systemQubits();
      return `e_ops = [Operator("I" * i + "${letter}" + "I" * (${countName} - i - 1))
         for i in range(${countName})]`;
    }
    const operators = sites.map((site) => {
      const label = `${"I".repeat(site)}${letter}${"I".repeat(count - site - 1)}`;
      return `Operator(${pyString(label)})`;
    });
    return `e_ops = [${operators.join(", ")}]`;
  }

  function systemQubits() {
    return usingAddedOperators() ? String(qubitCount()) : "model.num_qubits";
  }

  function qutipCall(name, params) {
    const hamiltonians = usingAddedOperators() ? "qutip_hamiltonians" : "model.full_hamiltonians";
    const lindblads = usingAddedOperators() ? "lindblads_full" : "model.c_ops_full";
    return `${name} = QutipSimulator(${hamiltonians}, ${lindblads}, state,
                    e_ops, num_qubits=${systemQubits()},
                    total_time=${pyFloat(settingNumber("total"))}, time_steps=${params.timeSteps})`;
  }

  function entryBody(entry) {
    const params = entry.params;
    const body = { simulator: entry.id, time_steps: params.timeSteps };
    if (isReference(entry)) return body;
    body.num_steps = params.numSteps;
    body.trotter_depth = params.trotterDepth;
    body.seed = params.seed;
    body.order = params.order;
    if (entry.backend) body.backend = entry.backend;
    const backend = blockById("backend", entry.backend);
    if (backend?.shots) body.shots = String(entry.shots ?? "").trim();
    return body;
  }

  function simulatorCall(entry, name, backendName) {
    const params = entry.params;
    const block = blockById("simulator", entry.id);
    if (!params || !block) return "";
    if (block.observables) return qutipCall(name, params);
    const className = entry.id === "trotterization" ? "TrotterizationSimulator" : "SplitJMatrixSimulator";
    const offset = entry.id === "splitjmatrix" ? 1 : 0;
    const groups = selectedSites(qubitCount()).map((site) => `[${site + offset}]`);
    const orderLine = `,\n    order=${params.order}`;
    const expectation = page.selection.measure === "x" ? "expectation_x" : "expectation_z";
    const sites = selectedSites(qubitCount());
    const xLine = page.selection.measure === "x" ? `,\n    x_qubits=[${sites.join(", ")}]` : "";
    const hamiltonians = usingAddedOperators() ? "circuit_hamiltonians" : "model.local_hamiltonians";
    const lindblads = usingAddedOperators() ? "lindblads" : "model.c_ops_local";
    return `${name} = ${className}(
    ${hamiltonians},
    ${lindblads},
    state,
    num_qubits=${systemQubits()},
    total_time=${pyFloat(settingNumber("total"))},
    time_steps=${params.timeSteps},
    num_steps=${params.numSteps},
    trotter_depth=${params.trotterDepth}${orderLine},
    seed=${params.seed},
    measurement_groups=[${groups.join(", ")}],
    reducers=[${expectation}] * ${groups.length}${xLine},
    circuit_backend=${backendName},
)`;
  }

  function backendClass(backendId) {
    const setup = blockById("backend", backendId)?.setup ?? "";
    return setup.match(/circuit_backend = ([A-Za-z0-9_]+)/)?.[1] ?? "";
  }

  function backendSetup(backendId, variable, shots) {
    const block = blockById("backend", backendId);
    if (!block) return "";
    return fillSetup(block, "", shots).replace(/^circuit_backend =/, `${variable} =`);
  }

  function metricsTarget() {
    const directory = page.exportPath.trim();
    return directory.endsWith(".json") ? `path=${pyString(directory)}` : `output_dir=${pyString(directory)}`;
  }

  function exportCall() {
    return `benchmark.save_error_metrics(${metricsTarget()})`;
  }

  function resourceMetricsCall() {
    return `save_resource_metrics(sim, result.runtime, ${metricsTarget()})`;
  }

  function benchmarkThenLines(names) {
    const lines = [`benchmark = Benchmark(${names.join(", ")})`, "benchmark.run()"];
    if (hasThen("plot")) lines.push("benchmark.save_result_plot()");
    if (hasThen("save")) {
      names.forEach((name) => {
        lines.push(`${name}.last_result.save(${pyString(`${page.savePath.trim()}/${name}`)})`);
      });
    }
    if (hasThen("export")) lines.push(exportCall());
    return lines;
  }

  function singleThenLines() {
    const exporting = hasThen("export");
    const metrics = resourceMetricsCall();
    const saveLine = `result.save(${pyString(page.savePath.trim())})`;
    if (hasThen("save") && hasThen("plot")) {
      const lines = ["result = sim.simulate()", saveLine, "sim.plot_results()"];
      if (exporting) lines.push(metrics);
      return lines;
    }
    if (hasThen("save")) {
      if (!exporting) return [`sim.simulate().save(${pyString(page.savePath.trim())})`];
      return ["result = sim.simulate()", saveLine, metrics];
    }
    if (hasThen("plot")) {
      if (!exporting) return ["sim.simulate()", "sim.plot_results()"];
      return ["result = sim.simulate()", "sim.plot_results()", metrics];
    }
    if (exporting) return ["result = sim.simulate()", metrics];
    return ["result = sim.simulate()"];
  }

  function previewText() {
    if (!runAllowed()) return "";
    const lines = ["import numpy as np", "from shadowsim.encoding import *"];
    if (page.selection.model === "preexisting") lines.push(`from shadowsim.models import ${page.preexistingId}`);
    else if (page.selection.model) lines.push(`from shadowsim.models import ${page.selection.model}`);
    lines.push("from shadowsim.simulators import *");
    const benchmark = page.placedSims.length >= 2;
    if (!benchmark && hasThen("export")) lines.push("from shadowsim.simulators.result import save_resource_metrics");
    const backendClasses = [];
    page.placedSims.forEach((entry) => {
      if (isReference(entry)) return;
      const className = backendClass(entry.backend);
      if (className && !backendClasses.includes(className)) backendClasses.push(className);
    });
    if (backendClasses.length) lines.push(`from shadowsim.backends import ${backendClasses.join(", ")}`);
    const symbols = [
      ...new Set(page.modelTerms.map((term) => blockById("model", term.id)?.symbol).filter(Boolean)),
    ];
    if (page.placedSims.some((entry) => blockById("simulator", entry.id)?.observables)) symbols.push("Operator");
    if (page.modelTerms.some((term) => term.id === "lindblad" && !lindbladProblem(term))) symbols.push("LocalOperator");
    if (symbols.length) lines.push(`from shadowsim.core import ${symbols.join(", ")}`);
    if (benchmark) lines.push("from shadowsim.benchmarking import Benchmark");
    const beforeSimulator = ["", stateLine(), "", modelLine(), ...termLines(), ""];
    page.placedSims.forEach((entry, index) => {
      if (isReference(entry)) return;
      const setup = backendSetup(entry.backend, `circuit_backend_${index + 1}`, entry.shots);
      if (setup) beforeSimulator.push(setup, "");
    });
    if (page.placedSims.some((entry) => blockById("simulator", entry.id)?.observables)) {
      beforeSimulator.push(observableSetup(), "");
    }
    const names = page.placedSims.map((_, index) => (benchmark ? `sim_${index + 1}` : "sim"));
    lines.push(
      ...beforeSimulator,
      ...page.placedSims.map((entry, index) =>
        simulatorCall(entry, names[index], `circuit_backend_${index + 1}`),
      ),
      "",
    );
    lines.push(...(benchmark ? benchmarkThenLines(names) : singleThenLines()));
    return lines.join("\n");
  }

  function readNumber(source, index) {
    const match = source.slice(index).match(/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)/);
    if (!match) return null;
    return { value: Number(match[0]), next: index + match[0].length };
  }

  function skipSpaces(source, index) {
    while (/\s/.test(source[index] ?? "")) index += 1;
    return index;
  }

  function parseComplex(source, index) {
    const lone = source.slice(index).match(/^[+-]?j/i);
    const number = readNumber(source, index);
    if (lone && (!number || lone[0].length < number.next - index)) {
      return { re: 0, im: lone[0].startsWith("-") ? -1 : 1, next: index + lone[0].length };
    }
    if (!number) return null;
    const cursor = skipSpaces(source, number.next);
    if ((source[cursor] ?? "").toLowerCase() === "j") return { re: 0, im: number.value, next: cursor + 1 };
    const imag = source.slice(cursor).match(/^([+-])\s*(?:(\d+(?:\.\d*)?|\.\d+)\s*)?j/i);
    if (!imag) return { re: number.value, im: 0, next: number.next };
    const magnitude = imag[2] == null ? 1 : Number(imag[2]);
    return { re: number.value, im: imag[1] === "-" ? -magnitude : magnitude, next: cursor + imag[0].length };
  }

  function parseMatrix(text) {
    const source = text.trim();
    if (!source) return { error: "empty" };
    let index = 0;
    function skip() {
      while (/\s/.test(source[index] ?? "")) index += 1;
    }
    function parseList() {
      skip();
      if (source[index] !== "[") return null;
      index += 1;
      skip();
      const items = [];
      if (source[index] === "]") {
        index += 1;
        return items;
      }
      while (index < source.length) {
        skip();
        const item = source[index] === "[" ? parseList() : parseComplex(source, index);
        if (!item) return null;
        if (item.next) index = item.next;
        items.push(item.next ? { re: item.re, im: item.im } : item);
        skip();
        if (source[index] === ",") {
          index += 1;
          continue;
        }
        if (source[index] === "]") {
          index += 1;
          return items;
        }
        return null;
      }
      return null;
    }
    const value = parseList();
    skip();
    if (!value || index !== source.length || value.some((row) => !Array.isArray(row))) return { error: "shape" };
    const width = value.length;
    if (!width || value.some((row) => row.length !== width || row.some((cell) => Array.isArray(cell)))) {
      return { error: "shape" };
    }
    return { matrix: value };
  }

  function nearly(left, right) {
    return Math.abs(left - right) <= 1e-8 + 1e-5 * Math.max(Math.abs(left), Math.abs(right));
  }

  function isHermitian(matrix) {
    return matrix.every((row, rowIndex) =>
      row.every((value, columnIndex) => {
        const mirror = matrix[columnIndex][rowIndex];
        return nearly(value.re, mirror.re) && nearly(value.im, -mirror.im);
      }),
    );
  }

  function squareMatrix(text) {
    const parsed = parseMatrix(text ?? "");
    if (parsed.error === "empty") return { problem: "Enter a matrix." };
    if (parsed.error) return { problem: "Enter a square matrix." };
    const { matrix } = parsed;
    const size = matrix.length;
    if (size > 256) return { problem: "At most 8 qubits." };
    if (size < 2 || (size & (size - 1)) !== 0) return { problem: "Size must be a power of two." };
    return { matrix, qubits: Math.log2(size) };
  }

  function inspectMatrix(text) {
    const parsed = squareMatrix(text);
    if (parsed.problem) return parsed;
    if (!isHermitian(parsed.matrix)) return { problem: "Matrix must be Hermitian." };
    return parsed;
  }

  function fixedQubitCount() {
    if (stateOwnsQubits() || page.qubitsSource === "user") return qubitCount();
    return null;
  }

  function hamiltonianProblem(term) {
    const inspected = inspectMatrix(term.matrix);
    if (inspected.problem) return inspected.problem;
    const fixed = fixedQubitCount();
    if (fixed != null && inspected.qubits !== fixed) {
      const side = 2 ** fixed;
      const label = fixed === 1 ? "qubit" : "qubits";
      return `Must be ${side}×${side} for ${fixed} ${label}.`;
    }
    if (fixed == null && new Set(validHamiltonianQubits()).size > 1) return "Matrices must be the same size.";
    return null;
  }

  function validHamiltonianQubits() {
    return page.modelTerms.flatMap((term) => {
      if (term.id !== "hamiltonian") return [];
      const inspected = inspectMatrix(term.matrix);
      return inspected.problem ? [] : [inspected.qubits];
    });
  }

  function localSites(term, count) {
    return (term.sites ?? [])
      .filter((site) => Number.isInteger(site) && site >= 0 && site < count)
      .sort((left, right) => left - right);
  }

  function actedQubitProblem(term, parse) {
    const count = qubitCount();
    if (count == null) return "Set qubits first.";
    const sites = localSites(term, count);
    if (!sites.length) return "Pick at least one qubit.";
    if (sites[sites.length - 1] - sites[0] + 1 !== sites.length) return "Qubits must be contiguous.";
    const inspected = parse(term.matrix);
    if (inspected.problem) return inspected.problem;
    if (inspected.qubits !== sites.length) {
      const side = 2 ** sites.length;
      const label = sites.length === 1 ? "qubit" : "qubits";
      return `Must be ${side}×${side} for ${sites.length} ${label}.`;
    }
    return null;
  }

  function localHamiltonianProblem(term) {
    return actedQubitProblem(term, inspectMatrix);
  }

  function lindbladProblem(term) {
    return actedQubitProblem(term, squareMatrix);
  }

  return {
    amplitudeQubits: bind(amplitudeQubits),
    blockById: bind(blockById),
    cavityModelSelected: bind(cavityModelSelected),
    chosenFactory: bind(chosenFactory),
    emitterCount: bind(emitterCount),
    emitterProblem: bind(emitterProblem),
    entryBody: bind(entryBody),
    fixedFactoryQubits: bind(fixedFactoryQubits),
    formatSetting: bind(formatSetting),
    hamiltonianProblem: bind(hamiltonianProblem),
    backendFits: bind(backendFits),
    inspectMatrix: bind(inspectMatrix),
    isComplete: bind(isComplete),
    isReference: bind(isReference),
    lindbladProblem: bind(lindbladProblem),
    localHamiltonianProblem: bind(localHamiltonianProblem),
    localSites: bind(localSites),
    measureSitesReady: bind(measureSitesReady),
    missingPaths: bind(missingPaths),
    numberList: bind(numberList),
    numberProblem: bind(numberProblem),
    operatorStatus: bind(operatorStatus),
    otherSlotsPlaced: bind(otherSlotsPlaced),
    positiveIntText: bind(positiveIntText),
    postedTerms: bind(postedTerms),
    previewText: bind(previewText),
    qubitCount: bind(qubitCount),
    qubitPhrase: bind(qubitPhrase),
    qubitProblem: bind(qubitProblem),
    runAllowed: bind(runAllowed),
    sameTimeGrid: bind(sameTimeGrid),
    savePathReady: bind(savePathReady),
    selectedSites: bind(selectedSites),
    settingNumber: bind(settingNumber),
    settingsReady: bind(settingsReady),
    shotsReady: bind(shotsReady),
    simParamsReady: bind(simParamsReady),
    socketStatus: bind(socketStatus),
    squareMatrix: bind(squareMatrix),
    stateImpliedQubits: bind(stateImpliedQubits),
    stateInputProblem: bind(stateInputProblem),
    stateOwnsQubits: bind(stateOwnsQubits),
    stateSizeProblem: bind(stateSizeProblem),
    stateSizeStatus: bind(stateSizeStatus),
    termProblem: bind(termProblem),
    totalProblem: bind(totalProblem),
    usingAddedOperators: bind(usingAddedOperators),
    validHamiltonianQubits: bind(validHamiltonianQubits),
  };
});
