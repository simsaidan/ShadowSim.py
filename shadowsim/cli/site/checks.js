/* Readiness checks and the code preview. This file does not touch document. */

((root, factory) => {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.checks = api;
})(typeof globalThis !== "undefined" ? globalThis : this, () => {
  function blockById(state, laneId, blockId) {
    return state.blocks[laneId].find((block) => block.id === blockId) ?? null;
  }

  function chosenFactory(state) {
    return state.modelFactories.find((item) => item.id === state.preexistingId) ?? null;
  }

  function operatorsReady(state) {
    if (state.selection.model === "preexisting" || !state.modelTerms.length) return false;
    if (state.modelTerms.some((term) => termProblem(state, term))) return false;
    return state.modelTerms.some(
      (term) => term.id === "hamiltonian" || term.id === "local_hamiltonian",
    );
  }

  function usingAddedOperators(state) {
    return state.selection.model !== "preexisting" && state.modelTerms.length > 0;
  }

  function termProblem(state, term) {
    if (term.id === "hamiltonian") return hamiltonianProblem(state, term);
    if (term.id === "local_hamiltonian") return localHamiltonianProblem(state, term);
    if (term.id === "lindblad") return lindbladProblem(state, term);
    return "Unknown operator.";
  }

  function isReference(state, entry) {
    return Boolean(blockById(state, "simulator", entry.id)?.observables);
  }

  function simulatorFields(state, entry) {
    const fields = blockById(state, "simulator", entry.id)?.fields;
    return Array.isArray(fields) ? fields : [];
  }

  function fieldReady(field, text) {
    return simFieldProblem(field, text) == null;
  }

  function simFieldProblem(field, text) {
    const value = String(text ?? "");
    if (field.kind === "choice") {
      if ((field.choices ?? []).includes(value)) return null;
      return `Choose a value for ${field.label}`;
    }
    if (Number.isInteger(field.maximum)) {
      const minimum = Number.isInteger(field.minimum) ? field.minimum : 1;
      if (positiveIntAtMost(value, field.maximum) && BigInt(value) >= BigInt(minimum)) return null;
      const oversize = oversizePositiveInt(value, field.label, field.maximum, false);
      if (oversize) return oversize.replace(/\.$/, "");
      return `Enter an integer from ${minimum} to ${field.maximum} for ${field.label}`;
    }
    if (/^-?\d+$/.test(value)) return null;
    return `Enter an integer for ${field.label}`;
  }

  function needsBackend(state) {
    return state.placedSims.some((entry) => !isReference(state, entry));
  }

  function backendFits(state, entry, backendId) {
    if (!entry || isReference(state, entry) || !backendId) return false;
    const backend = blockById(state, "backend", backendId);
    if (!backend) return false;
    const simulator = blockById(state, "simulator", entry.id);
    if (simulator?.samples && !backend.shots) return false;
    return true;
  }

  function socketsReady(state) {
    return state.placedSims.every(
      (entry) => isReference(state, entry) || backendFits(state, entry, entry.backend),
    );
  }

  function socketStatus(state, preview) {
    if (!otherSlotsPlaced(state)) return null;
    const open = state.placedSims.find(
      (entry) => !isReference(state, entry) && !backendFits(state, entry, entry.backend),
    );
    if (!open) return null;
    const tail = preview ? " to preview the script." : ".";
    return `Snap a backend onto each simulator${tail}`;
  }

  function otherSlotsPlaced(state) {
    return state.lanes.every((lane) => {
      if (lane.id === "model") return true;
      if (lane.id === "backend" && !needsBackend(state)) return true;
      return Boolean(blockById(state, lane.id, state.selection[lane.id]));
    });
  }

  function operatorStatus(state, preview) {
    if (!otherSlotsPlaced(state) || !usingAddedOperators(state) || operatorsReady(state))
      return null;
    const tail = preview ? " to preview the script." : ".";
    const hasHamiltonian = state.modelTerms.some(
      (term) => term.id === "hamiltonian" || term.id === "local_hamiltonian",
    );
    return hasHamiltonian ? `Enter a valid operator${tail}` : `Enter a Hamiltonian${tail}`;
  }

  function isComplete(state) {
    const lanesReady = state.lanes.every((lane) => {
      if (lane.id === "backend" && !needsBackend(state)) return true;
      if (lane.id === "model" && state.selection.model === "preexisting")
        return Boolean(chosenFactory(state));
      if (lane.id === "model") return operatorsReady(state);
      return Boolean(blockById(state, lane.id, state.selection[lane.id]));
    });
    return lanesReady && socketsReady(state);
  }

  function settingNumber(state, key) {
    if (state.settings[key] === "") return null;
    const value = Number(state.settings[key]);
    return Number.isFinite(value) ? value : null;
  }

  function formatSetting(state, key) {
    const value = settingNumber(state, key);
    if (value == null) return null;
    return Object.is(value, -0) ? "0" : String(value);
  }

  function qubitPhrase(state) {
    const label = formatSetting(state, "qubits");
    if (label == null) return null;
    return Number(label) === 1 ? "1 qubit" : `${label} qubits`;
  }

  function pyFloat(value) {
    return Number.isInteger(value) ? `${value}.0` : String(value);
  }

  function stateOwnsQubits(state) {
    return Object.hasOwn(state.stateLimits, state.selection.state);
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

  function selectedState(state) {
    return blockById(state, "state", state.selection.state);
  }

  function stateField(state) {
    return selectedState(state)?.field ?? null;
  }

  function actionTextValue(state, id) {
    const stored = state.actionText?.[id];
    if (typeof stored === "string") return stored;
    const field = blockById(state, "then", id)?.field;
    return typeof field?.default === "string" ? field.default : "";
  }

  function expressionTextValue(state) {
    const stored = state.expressionText?.[state.selection.measure];
    return typeof stored === "string" ? stored : "";
  }

  function measureRecord(state) {
    return blockById(state, "measure", state.selection.measure);
  }

  function modelMeasureSelected(state) {
    return state.selection.measure === "model";
  }

  function positiveIntText(value) {
    return /^[1-9]\d*$/.test(value);
  }

  function positiveIntAtMost(value, maximum) {
    if (!positiveIntText(value)) return false;
    return BigInt(value) <= BigInt(maximum);
  }

  function oversizePositiveInt(text, label, maximum, preview) {
    if (!positiveIntText(text) || positiveIntAtMost(text, maximum)) return null;
    const tail = preview ? " to preview the script." : ".";
    return `${label} must be from 1 to ${maximum}${tail}`;
  }

  function integerMinimum(param) {
    const minimum = param.minimum;
    return Number.isInteger(minimum) && minimum >= 1 ? minimum : 1;
  }

  function integerAlert(state, param) {
    const text = factoryFieldText(state, param).trim();
    const minimum = integerMinimum(param);
    if (!positiveIntText(text) || BigInt(text) < BigInt(minimum)) {
      return `Enter an integer of at least ${minimum} for ${param.label}`;
    }
    return null;
  }

  function factoryAlert(state) {
    if (state.selection.model !== "preexisting") return null;
    return paramAlert(state);
  }

  function factoryParams(state) {
    const params = chosenFactory(state)?.params;
    return Array.isArray(params) ? params : [];
  }

  function factoryFieldText(state, param) {
    const stored = state.factoryText?.[param.name];
    return typeof stored === "string" ? stored : String(param.default ?? "");
  }

  function realText(text) {
    const trimmed = String(text ?? "").trim();
    if (!/^-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
    const value = Number(trimmed);
    return Number.isFinite(value) ? value : null;
  }

  function numberValues(text) {
    const trimmed = String(text ?? "").trim();
    if (!trimmed) return null;
    const parts = trimmed.includes(",") ? trimmed.split(",").map((part) => part.trim()) : [trimmed];
    if (!parts.length || parts.some((part) => part === "")) return null;
    const values = [];
    for (const part of parts) {
      const value = realText(part);
      if (value == null) return null;
      values.push(value);
    }
    return values;
  }

  function parseEdges(text) {
    const trimmed = String(text ?? "").trim();
    if (!trimmed) return [];
    if (trimmed.includes("(") || trimmed.includes(")")) {
      const pairs = [];
      const matcher = /\(\s*(\d+)\s*,\s*(\d+)\s*\)/g;
      let match = matcher.exec(trimmed);
      while (match) {
        pairs.push([Number(match[1]), Number(match[2])]);
        match = matcher.exec(trimmed);
      }
      const rest = trimmed.replace(/\(\s*\d+\s*,\s*\d+\s*\)/g, "").replace(/[,\s]/g, "");
      return rest || !pairs.length ? null : pairs;
    }
    const tokens = trimmed.split(/[\s,]+/).filter(Boolean);
    if (!tokens.length) return null;
    const pairs = [];
    for (const token of tokens) {
      const match = /^(\d+)-(\d+)$/.exec(token);
      if (!match) return null;
      pairs.push([Number(match[1]), Number(match[2])]);
    }
    return pairs;
  }

  function paramAlertDetail(state) {
    for (const param of factoryParams(state)) {
      const text = factoryFieldText(state, param).trim();
      let message = null;
      if (param.kind === "integer") {
        message = integerAlert(state, param);
      } else if (param.kind === "number") {
        if (realText(text) == null) message = `Enter a real number for ${param.label}`;
      } else if (param.kind === "number_or_list") {
        const values = numberValues(text);
        if (values == null) {
          message = text.includes(",")
            ? `Enter real numbers for ${param.label}`
            : `Enter a real number for ${param.label}`;
        }
      } else if (param.kind === "choice") {
        const choices = Array.isArray(param.choices) ? param.choices : [];
        if (!choices.includes(text)) message = `Choose ${choices.join(" or ")} for ${param.label}`;
      } else if (param.kind === "edges") {
        if (parseEdges(text) == null) message = "Enter edges as pairs such as 0-1, 1-2";
      }
      if (message) return { name: param.name, message };
    }
    return null;
  }

  function paramAlert(state) {
    return paramAlertDetail(state)?.message ?? null;
  }

  function factorySetsQubits(state) {
    const factory = chosenFactory(state);
    return state.selection.model === "preexisting" && factory != null && factory.qubits === false;
  }

  function fixedFactoryQubits(state) {
    if (!factorySetsQubits(state)) return null;
    const stored = state.checkedQubits;
    return Number.isInteger(stored) ? stored : null;
  }

  function emitterProblem(state) {
    return factoryAlert(state) != null;
  }

  function readState(state, stateId = state.selection.state) {
    const field = blockById(state, "state", stateId)?.field ?? null;
    if (!field) return null;
    const stored = state.stateText?.[stateId];
    const text = typeof stored === "string" ? stored : "";
    if (field.kind === "bits") {
      const filled = text !== "";
      return { field, text, values: null, filled, count: filled ? text.length : null };
    }
    const values = numberList(text, field.cap);
    const filled = values != null && (!field.nonzero || values.some((value) => value !== 0));
    let count = null;
    if (values && (field.match !== "padded" || filled)) {
      count = field.match === "padded" ? amplitudeQubits(values.length) : values.length;
    }
    return { field, text, values, filled, count };
  }

  function stateImpliedQubits(state) {
    return readState(state)?.count ?? null;
  }

  function stateSizeProblem(state) {
    const expected = fixedFactoryQubits(state);
    if (expected == null) return null;
    const actual = stateImpliedQubits(state);
    if (actual == null || actual === expected) return null;
    return expected;
  }

  function stateSizeStatus(state, preview) {
    const expected = stateSizeProblem(state);
    const field = stateField(state);
    const tail = preview ? " to preview the script." : ".";
    if (expected == null || !field) return "";
    return `${String(field.size).replaceAll("{n}", String(expected))}${tail}`;
  }

  function stateInputProblem(state) {
    const read = readState(state);
    if (!read) return null;
    if (stateSizeProblem(state) != null) return "size";
    return read.filled ? null : "empty";
  }

  function entryParamsReady(state, entry) {
    return simulatorFields(state, entry).every((field) =>
      fieldReady(field, entry.params?.[field.name]),
    );
  }

  function simParamProblem(state, preview) {
    for (const entry of state.placedSims) {
      for (const field of simulatorFields(state, entry)) {
        if (!Number.isInteger(field.maximum)) continue;
        const problem = oversizePositiveInt(
          String(entry.params?.[field.name] ?? ""),
          field.label,
          field.maximum,
          preview,
        );
        if (problem) return problem;
      }
    }
    return null;
  }

  function simParamsReady(state) {
    return state.placedSims.every((entry) => entryParamsReady(state, entry));
  }

  function sameTimeGrid(state) {
    if (state.placedSims.length < 2) return true;
    const steps = state.placedSims[0].params?.time_steps;
    return state.placedSims.every((entry) => entry.params?.time_steps === steps);
  }

  function timeStepMismatch(state) {
    const values = [];
    for (const entry of state.placedSims) {
      const value = String(entry.params?.time_steps ?? "");
      if (value !== "") values.push(value);
    }
    if (values.length < 2 || values.every((value) => value === values[0])) return null;
    return "Use the same number of time steps for every simulator.";
  }

  function hasThen(state, id) {
    return state.placedThens.includes(id);
  }

  function missingPaths(state) {
    const missing = [];
    for (const block of state.blocks.then ?? []) {
      if (!hasThen(state, block.id) || block.field?.kind !== "path") continue;
      if (actionTextValue(state, block.id).trim() === "") missing.push(block.id);
    }
    return missing;
  }

  function savePathReady(state) {
    return missingPaths(state).length === 0;
  }

  function qubitCount(state) {
    const value = settingNumber(state, "qubits");
    if (value == null || !Number.isInteger(value) || value < 1) return null;
    return value;
  }

  function selectedSites(state, count) {
    if (count == null) return [];
    if (state.measureSites == null) return Array.from({ length: count }, (_, index) => index);
    return state.measureSites.filter((site) => Number.isInteger(site) && site >= 0 && site < count);
  }

  function shotsReady(state) {
    return state.placedSims.every((entry) => {
      const backend = blockById(state, "backend", entry.backend);
      if (!backend?.shots) return true;
      return positiveIntAtMost(String(entry.shots ?? "").trim(), state.maxShots);
    });
  }

  function shotsProblem(state, preview) {
    for (const entry of state.placedSims) {
      const backend = blockById(state, "backend", entry.backend);
      if (!backend?.shots) continue;
      const problem = oversizePositiveInt(
        String(entry.shots ?? "").trim(),
        "Shots",
        state.maxShots,
        preview,
      );
      if (problem) return problem;
    }
    return null;
  }

  function shotsFieldProblem(text, maxShots) {
    const raw = String(text ?? "").trim();
    if (maxShots == null) {
      if (positiveIntText(raw)) return null;
      return "Enter a shot count";
    }
    if (positiveIntAtMost(raw, maxShots)) return null;
    const oversize = oversizePositiveInt(raw, "Shots", maxShots, false);
    if (oversize) return oversize.replace(/\.$/, "");
    return "Enter a shot count";
  }

  function backendFieldNumber(field, text) {
    const raw = String(text ?? "").trim();
    if (field?.allow_inf && /^inf(?:inity)?$/i.test(raw)) return Infinity;
    if (!/^(?:\d+(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw)) return null;
    const number = Number(raw);
    if (!Number.isFinite(number) || number < 0) return null;
    return number;
  }

  function backendNumberProblem(field, text) {
    if (backendFieldNumber(field, text) != null) return null;
    if (field?.allow_inf) return `Enter a non-negative number or inf for ${field.label}`;
    return `Enter a non-negative number for ${field.label}`;
  }

  function gateNames(text) {
    const names = [];
    for (const token of String(text ?? "")
      .trim()
      .toLowerCase()
      .split(/[\s,]+/)) {
      if (token && !names.includes(token)) names.push(token);
    }
    return names;
  }

  function gateFieldProblem(field, text) {
    const raw = String(text ?? "").trim();
    if (!raw) return null;
    const names = gateNames(raw);
    if (!names.length) return "Enter gate names separated by commas.";
    const choices = Array.isArray(field?.choices) ? field.choices : null;
    for (const name of names) {
      const known = choices ? choices.includes(name) : /^[a-z][a-z0-9_]*$/.test(name);
      if (!known) return `Unknown gate ${name}.`;
    }
    return null;
  }

  function backendFieldIssue(state) {
    for (const entry of state.placedSims) {
      const fields = blockById(state, "backend", entry.backend)?.fields ?? [];
      for (const field of fields) {
        const text = entry.backendFields?.[field.name];
        if (field.kind === "gates") {
          const problem = gateFieldProblem(field, text);
          if (problem) return problem;
          continue;
        }
        const problem = backendNumberProblem(field, text);
        if (!problem) continue;
        if (!String(text ?? "").trim()) return "";
        return `${problem}.`;
      }
    }
    return null;
  }

  function backendFieldsReady(state) {
    return backendFieldIssue(state) == null;
  }

  function backendFieldStatus(state, preview) {
    const issue = backendFieldIssue(state);
    if (issue) {
      const sentence = issue.replace(/\.$/, "");
      return preview ? `${sentence} to preview the script.` : issue;
    }
    const tail = preview ? " to preview the script." : ".";
    return `Enter a max weight and a minimum coefficient${tail}`;
  }

  function pyBackendNumber(field, text) {
    const number = backendFieldNumber(field, text);
    if (number == null) return "";
    if (number === Infinity) return 'float("inf")';
    return pyFloat(number);
  }

  function pyBackendValue(field, text) {
    if (field.kind !== "gates") return pyBackendNumber(field, text);
    if (gateFieldProblem(field, text)) return "";
    const names = gateNames(text);
    if (!names.length) return "None";
    return `[${names.map(pyString).join(", ")}]`;
  }

  function measureSitesReady(state) {
    if (modelMeasureSelected(state)) return true;
    const count = qubitCount(state);
    if (!state.selection.measure || count == null) return true;
    return selectedSites(state, count).length > 0;
  }

  function pyString(value) {
    return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }

  function pyQuoted(value) {
    if (value.includes("'")) return pyString(value);
    return `'${value.replace(/\\/g, "\\\\")}'`;
  }

  function expressionTokens(source) {
    const tokens = [];
    const pattern =
      /\s+|(\d+(?:\.\d*)?(?:e[+-]?\d+)?|\.\d+(?:e[+-]?\d+)?)|([A-Za-z_]\w*)|("[^"\\]*"|'[^'\\]*')|(\*\*|[-+*/()[\]])/iy;
    let index = 0;
    while (index < source.length) {
      pattern.lastIndex = index;
      const match = pattern.exec(source);
      if (!match) return null;
      index = pattern.lastIndex;
      if (match[1]) tokens.push({ kind: "number" });
      else if (match[2]) tokens.push({ kind: "name", text: match[2] });
      else if (match[3]) tokens.push({ kind: "string", text: match[3].slice(1, -1) });
      else if (match[4]) tokens.push({ kind: match[4] });
    }
    return tokens;
  }

  function expressionProblem(text, width) {
    const source = String(text ?? "").trim();
    if (!source) return "Enter a counts expression.";
    if (source.length > 1000) return "Expression must be at most 1000 characters.";
    const allowed = 'Use numbers, shots, counts["01"], parentheses, and + - * / **.';
    const tokens = expressionTokens(source);
    if (!tokens) return allowed;
    let index = 0;
    let keyProblem = null;
    const peek = () => tokens[index]?.kind;
    const take = (kind) => {
      if (peek() !== kind) return false;
      index += 1;
      return true;
    };
    function atom() {
      const token = tokens[index];
      if (!token) return false;
      index += 1;
      if (token.kind === "number") return true;
      if (token.kind === "name" && token.text === "shots") return true;
      if (token.kind === "name" && token.text === "counts") {
        if (!take("[") || peek() !== "string") return false;
        const key = tokens[index].text;
        index += 1;
        if (key.length !== width || /[^01]/.test(key)) {
          keyProblem ??= `Counts keys must be ${width} characters of 0 and 1.`;
        }
        return take("]");
      }
      if (token.kind === "(") return sum() && take(")");
      return false;
    }
    function power() {
      if (!atom()) return false;
      return take("**") ? unary() : true;
    }
    function unary() {
      if (take("+") || take("-")) return unary();
      return power();
    }
    function product() {
      if (!unary()) return false;
      while (take("*") || take("/")) if (!unary()) return false;
      return true;
    }
    function sum() {
      if (!product()) return false;
      while (take("+") || take("-")) if (!product()) return false;
      return true;
    }
    if (!sum() || index !== tokens.length) return allowed;
    return keyProblem;
  }

  function countsProblem(state) {
    if (measureRecord(state)?.field?.kind !== "expression") return null;
    const sampled = state.placedSims.every(
      (entry) =>
        !isReference(state, entry) &&
        (!entry.backend || blockById(state, "backend", entry.backend)?.shots),
    );
    if (!sampled) return "Counts needs a backend with a shot budget.";
    const count = qubitCount(state);
    if (count == null) return null;
    const sites = selectedSites(state, count);
    if (!sites.length) return null;
    return expressionProblem(expressionTextValue(state), sites.length);
  }

  function countsStatus(state, preview) {
    const problem = countsProblem(state);
    if (!problem || !preview) return problem;
    return `${problem.replace(/\.$/, "")} to preview the script.`;
  }

  function qubitBounds(state) {
    if (usingAddedOperators(state)) return { min: 1, max: state.maxOperatorQubits };
    // The factory that takes n_qubits is Ising: at least 2. The upper cap is the server's.
    if (state.selection.model === "preexisting" && chosenFactory(state)?.qubits)
      return { min: 2, max: null };
    return { min: 1, max: null };
  }

  function qubitProblem(state, preview) {
    const value = settingNumber(state, "qubits");
    if (value == null) return null;
    const { min, max } = qubitBounds(state);
    const tail = preview ? " to preview the script." : ".";
    if (!Number.isInteger(value) || value < min)
      return `Qubits must be an integer of at least ${min}${tail}`;
    if (max != null && value > max) return `Qubits must be from ${min} to ${max}${tail}`;
    return null;
  }

  function totalProblem(state, preview) {
    const value = settingNumber(state, "total");
    if (value == null || value > 0) return null;
    const tail = preview ? " to preview the script." : ".";
    return `Total time must be a positive number${tail}`;
  }

  function numberProblem(state, preview) {
    const qubits = settingNumber(state, "qubits");
    const total = settingNumber(state, "total");
    const needsQubits = !factorySetsQubits(state);
    const tail = preview ? " to preview the script." : ".";
    const missingQubits = needsQubits && qubits == null;
    if (missingQubits && total == null) return `Enter qubits and total time${tail}`;
    if (missingQubits) return `Enter qubits${tail}`;
    if (total == null) {
      const qubitsMessage = needsQubits ? qubitProblem(state, preview) : null;
      return qubitsMessage ?? `Enter a total time${tail}`;
    }
    if (qubits == null) return totalProblem(state, preview);
    return qubitProblem(state, preview) ?? totalProblem(state, preview);
  }

  function stateEntryMessage(state, preview) {
    const field = stateField(state);
    const ending = preview ? " and total time to preview the script." : " and total time.";
    return `${field?.empty || "Enter an initial state"}${ending}`;
  }

  function pathMessage(state, preview) {
    const tail = preview ? " to preview the script." : ".";
    const names = missingPaths(state).map((id) =>
      String(blockById(state, "then", id)?.field?.aria || "path").toLowerCase(),
    );
    const article = (name) => (/^[aeiou]/i.test(name) ? "an" : "a");
    if (!names.length) return `Enter a path${tail}`;
    return `Enter ${names.map((name) => `${article(name)} ${name}`).join(" and ")}${tail}`;
  }

  function voiced(render) {
    const message = render(false);
    if (!message) return null;
    return { message, previewMessage: render(true) };
  }

  function slotFilled(state, lane) {
    if (lane.id === "model") {
      if (state.modelTerms.length > 0) return true;
      return state.selection.model === "preexisting" && Boolean(chosenFactory(state));
    }
    return Boolean(blockById(state, lane.id, state.selection[lane.id]));
  }

  function emptySlotMessage(state, preview) {
    const lane = state.lanes.find((item) => !slotFilled(state, item));
    const tail = preview ? " to preview the script." : ".";
    if (!lane?.title) return `Place a block in each slot${tail}`;
    return `Place a block in the ${lane.title} slot${tail}`;
  }

  function boardProblem(state) {
    if (isComplete(state)) return null;
    return voiced(
      (preview) =>
        operatorStatus(state, preview) ??
        socketStatus(state, preview) ??
        emptySlotMessage(state, preview),
    );
  }

  function setupProblem(state) {
    const factory = factoryAlert(state);
    if (factory)
      return { message: `${factory}.`, previewMessage: `${factory} to preview the script.` };
    if (stateInputProblem(state) === "size")
      return voiced((preview) => stateSizeStatus(state, preview));
    if (stateInputProblem(state) === "empty")
      return voiced((preview) => stateEntryMessage(state, preview));
    const numbers = voiced((preview) => numberProblem(state, preview));
    if (numbers) return numbers;
    const parameters = voiced((preview) => simParamProblem(state, preview));
    if (parameters) return parameters;
    if (!simParamsReady(state))
      return {
        message: "Enter simulator parameters.",
        previewMessage: "Enter simulator parameters to preview the script.",
      };
    if (!sameTimeGrid(state))
      return {
        message: "Use the same number of time steps for every simulator.",
        previewMessage: "Use the same number of time steps to preview the script.",
      };
    if (!measureSitesReady(state))
      return {
        message: "Pick at least one qubit.",
        previewMessage: "Pick at least one qubit to preview the script.",
      };
    const counts = voiced((preview) => countsStatus(state, preview));
    if (counts) return counts;
    const shots = voiced((preview) => shotsProblem(state, preview));
    if (shots) return shots;
    if (!shotsReady(state))
      return {
        message: "Enter a shot count.",
        previewMessage: "Enter a shot count to preview the script.",
      };
    if (!backendFieldsReady(state)) return voiced((preview) => backendFieldStatus(state, preview));
    if (!savePathReady(state)) return voiced((preview) => pathMessage(state, preview));
    return null;
  }

  function firstProblem(state) {
    return boardProblem(state) ?? setupProblem(state);
  }

  function settingsReady(state) {
    return setupProblem(state) == null && (!usingAddedOperators(state) || operatorsReady(state));
  }

  function runAllowed(state) {
    return firstProblem(state) == null;
  }

  function stateLine(state) {
    const read = readState(state);
    if (!read?.field.encode) return "";
    if (read.field.kind === "bits") {
      if (!read.text) return "";
      return `state = ${read.field.encode}(${read.text.length}).encode([${[...read.text].join(", ")}])`;
    }
    if (!read.values) return "";
    return `state = ${read.field.encode}().encode([${read.values.map(pyFloat).join(", ")}])`;
  }

  function fillSetup(state, block, name, shots = "", fields = {}) {
    const qubits = settingNumber(state, "qubits");
    const total = settingNumber(state, "total");
    let setup = block.setup
      .replaceAll("{name}", name)
      .replaceAll("{qubits}", qubits == null ? "" : String(Math.round(qubits)))
      .replaceAll("{total}", total == null ? "" : pyFloat(total))
      .replaceAll("{shots}", String(shots ?? "").trim());
    for (const field of block.fields ?? []) {
      setup = setup.replaceAll(`{${field.name}}`, pyBackendValue(field, fields[field.name]));
    }
    return setup;
  }

  function factoryArgument(state, param) {
    const text = factoryFieldText(state, param).trim();
    if (param.kind === "integer") {
      if (integerAlert(state, param)) return null;
      return `${param.name}=${factoryFieldText(state, param).trim()}`;
    }
    if (param.kind === "edges") {
      const pairs = parseEdges(text);
      if (!pairs?.length) return null;
      return `edges=[${pairs.map(([left, right]) => `(${left}, ${right})`).join(", ")}]`;
    }
    if (param.kind === "choice") return `${param.name}=${pyString(text)}`;
    if (param.kind === "number_or_list" && text.includes(",")) {
      const values = numberValues(text);
      if (!values) return null;
      return `${param.name}=[${values.map(pyFloat).join(", ")}]`;
    }
    const value = realText(text);
    if (value == null) return null;
    return `${param.name}=${pyFloat(value)}`;
  }

  function factoryArguments(state, factory) {
    const args = [];
    if (factory.qubits) {
      const qubits = settingNumber(state, "qubits");
      args.push(`n_qubits=${qubits == null ? "" : String(Math.round(qubits))}`);
    }
    for (const param of factoryParams(state)) {
      const rendered = factoryArgument(state, param);
      if (rendered) args.push(rendered);
    }
    return args;
  }

  function modelLine(state) {
    const factory = chosenFactory(state);
    if (state.selection.model === "preexisting" && factory) {
      if (factoryAlert(state) != null) return "";
      return `model = ${factory.id}(${factoryArguments(state, factory).join(", ")})`;
    }
    return usingAddedOperators(state) ? addedOperatorLines(state) : "";
  }

  function matrixLiteral(state, term) {
    const parsed =
      term.id === "lindblad"
        ? squareMatrix(state, term.matrix ?? "")
        : inspectMatrix(state, term.matrix ?? "");
    const rows = parsed.matrix.map((row) => `[${row.map(pyComplex).join(", ")}]`).join(", ");
    return `np.array([${rows}], dtype=complex)`;
  }

  function addedOperatorLines(state) {
    const count = qubitCount(state);
    const seen = {};
    const lines = [];
    const full = [];
    const circuit = [];
    const lindblads = [];
    state.modelTerms.forEach((term) => {
      const block = blockById(state, "model", term.id);
      if (!block || termProblem(state, term)) return;
      seen[term.id] = (seen[term.id] || 0) + 1;
      const suffix = seen[term.id] === 1 ? "" : `_${seen[term.id]}`;
      const name = `${block.stem}${suffix}`;
      const matrix = matrixLiteral(state, term);
      if (term.id === "hamiltonian") {
        lines.push(`${name} = Hamiltonian(${matrix})`);
        full.push(name);
        circuit.push(`${name}.to_local_hamiltonian()`);
      } else if (term.id === "local_hamiltonian") {
        const sites = localSites(term, count).join(", ");
        lines.push(`${name} = LocalHamiltonian(${matrix}, [${sites}])`);
        full.push(name);
        circuit.push(name);
      } else if (term.id === "lindblad") {
        const sites = localSites(term, count).join(", ");
        lines.push(`${name} = LocalOperator(${matrix}, [${sites}])`);
        lindblads.push(name);
      }
    });
    lines.push(`full_hamiltonians = [${full.join(", ")}]`);
    lines.push(`circuit_hamiltonians = [${circuit.join(", ")}]`);
    lines.push(`lindblads = [${lindblads.join(", ")}]`);
    lines.push(`lindblads_full = [op.to_full_operator(${count}) for op in lindblads]`);
    return lines.join("\n");
  }

  function postedTerms(state) {
    if (!operatorsReady(state)) return undefined;
    return state.modelTerms.map((term) => {
      const parsed =
        term.id === "lindblad"
          ? squareMatrix(state, term.matrix ?? "")
          : inspectMatrix(state, term.matrix ?? "");
      const body = {
        id: term.id,
        matrix: parsed.matrix.map((row) => row.map((value) => [value.re, value.im])),
      };
      if (term.id !== "hamiltonian") body.sites = localSites(term, qubitCount(state));
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

  function termLines(state) {
    if (usingAddedOperators(state)) return [];
    const seen = {};
    return state.modelTerms.flatMap((term) => {
      const block = blockById(state, "model", term.id);
      if (!block) return [];
      seen[term.id] = (seen[term.id] || 0) + 1;
      const suffix = seen[term.id] === 1 ? "" : `_${seen[term.id]}`;
      const name = `${block.stem}${suffix}`;
      if (term.id === "lindblad") {
        if (lindbladProblem(state, term)) return [fillSetup(state, block, name)];
        const parsed = squareMatrix(state, term.matrix ?? "");
        const rows = parsed.matrix.map((row) => `[${row.map(pyComplex).join(", ")}]`).join(", ");
        const sites = localSites(term, qubitCount(state)).join(", ");
        return [`${name} = LocalOperator(np.array([${rows}], dtype=complex), [${sites}])`];
      }
      if (term.id !== "hamiltonian" && term.id !== "local_hamiltonian")
        return [fillSetup(state, block, name)];
      const inspected = inspectMatrix(state, term.matrix ?? "");
      const localProblem = term.id === "local_hamiltonian" && localHamiltonianProblem(state, term);
      if (inspected.problem || localProblem) return [fillSetup(state, block, name)];
      const rows = inspected.matrix.map((row) => `[${row.map(pyComplex).join(", ")}]`).join(", ");
      const matrix = `np.array([${rows}], dtype=complex)`;
      if (term.id === "hamiltonian") return [`${name} = Hamiltonian(${matrix})`];
      const sites = localSites(term, qubitCount(state)).join(", ");
      return [`${name} = LocalHamiltonian(${matrix}, [${sites}])`];
    });
  }

  function measurementSetup(state) {
    if (modelMeasureSelected(state)) return "measurements = model.measurements";
    const count = qubitCount(state);
    const sites = selectedSites(state, count);
    if (measureRecord(state)?.field?.kind === "expression") {
      const qubits = sites.length === 1 ? `(${sites[0]},)` : `(${sites.join(", ")})`;
      return `measurements = [Measurement(${qubits}, ${pyQuoted(expressionTextValue(state).trim())})]`;
    }
    const expectation = (site) =>
      `Measurement((${site},), '(counts["0"] - counts["1"]) / shots', "expectation on ${site}")`;
    if (count == null || sites.length === count) {
      return `measurements = [Measurement((i,), '(counts["0"] - counts["1"]) / shots', f"expectation on {i}") for i in range(${systemQubits(state)})]`;
    }
    return `measurements = [${sites.map((site) => expectation(site)).join(", ")}]`;
  }

  function observableSetup(state) {
    if (modelMeasureSelected(state)) return "e_ops = model.e_ops";
    const letter = measureRecord(state)?.letter ?? "";
    const count = qubitCount(state);
    const sites = selectedSites(state, count);
    if (count == null || sites.length === count) {
      const countName = systemQubits(state);
      return `e_ops = [Operator("I" * i + "${letter}" + "I" * (${countName} - i - 1))
         for i in range(${countName})]`;
    }
    const operators = sites.map((site) => {
      const label = `${"I".repeat(site)}${letter}${"I".repeat(count - site - 1)}`;
      return `Operator(${pyString(label)})`;
    });
    return `e_ops = [${operators.join(", ")}]`;
  }

  function systemQubits(state) {
    return usingAddedOperators(state) ? String(qubitCount(state)) : "model.num_qubits";
  }

  function postedBackend(state, entry) {
    if (isReference(state, entry) || !entry.backend) return null;
    const block = blockById(state, "backend", entry.backend);
    const fields = {};
    if (block?.shots) fields.shots = String(entry.shots ?? "").trim();
    for (const field of block?.fields ?? []) {
      fields[field.name] = String(entry.backendFields?.[field.name] ?? "").trim();
    }
    return { id: entry.backend, arguments: fields };
  }

  function entryBody(state, entry) {
    const params = entry.params ?? {};
    const fields = {};
    for (const field of simulatorFields(state, entry)) {
      fields[field.name] = String(params[field.name] ?? "");
    }
    return { id: entry.id, arguments: fields, backend: postedBackend(state, entry) };
  }

  function pauliBasis(state, sites) {
    const letter = measureRecord(state)?.letter ?? "Z";
    const count = qubitCount(state);
    if (count == null || sites.length === count) return `"${letter}" * ${systemQubits(state)}`;
    const letters = Array.from({ length: count }, (_, qubit) =>
      sites.includes(qubit) ? letter : "Z",
    );
    return pyString(letters.join(""));
  }

  function simulatorCall(state, entry, name, backendName) {
    const params = entry.params;
    const block = blockById(state, "simulator", entry.id);
    if (!params || !block?.setup) return "";
    const total = settingNumber(state, "total");
    const added = usingAddedOperators(state);
    let hamiltonians = "model.local_hamiltonians";
    let lindblads = "model.c_ops_local";
    if (block.observables) {
      hamiltonians = added ? "full_hamiltonians" : "model.full_hamiltonians";
      lindblads = added ? "lindblads_full" : "model.c_ops_full";
    } else if (added) {
      hamiltonians = "circuit_hamiltonians";
      lindblads = "lindblads";
    }
    const sites = selectedSites(state, qubitCount(state));
    const basis =
      !modelMeasureSelected(state) && measureRecord(state)?.rotate
        ? `,\n    basis=${pauliBasis(state, sites)}`
        : "";
    let setup = block.setup
      .replaceAll("{name}", name)
      .replaceAll("{hamiltonians}", hamiltonians)
      .replaceAll("{lindblads}", lindblads)
      .replaceAll("{qubits}", systemQubits(state))
      .replaceAll("{total}", total == null ? "" : pyFloat(total))
      .replaceAll("{basis}", basis)
      .replaceAll("{backend}", backendName);
    for (const field of block.fields ?? []) {
      setup = setup.replaceAll(
        `{${field.name}}`,
        String(params[field.name] ?? field.default ?? ""),
      );
    }
    return setup;
  }

  function backendClass(state, backendId) {
    const setup = blockById(state, "backend", backendId)?.setup ?? "";
    return setup.match(/circuit_backend = ([A-Za-z0-9_]+)/)?.[1] ?? "";
  }

  function backendSetup(state, backendId, variable, shots, fields) {
    const block = blockById(state, "backend", backendId);
    if (!block) return "";
    return fillSetup(state, block, "", shots, fields).replace(
      /^circuit_backend =/,
      `${variable} =`,
    );
  }

  function metricsTarget(state) {
    const directory = actionTextValue(state, "export").trim();
    return directory.endsWith(".json")
      ? `path=${pyString(directory)}`
      : `output_dir=${pyString(directory)}`;
  }

  function exportCall(state) {
    return `benchmark.save_error_metrics(${metricsTarget(state)})`;
  }

  function resourceMetricsCall(state) {
    return `save_resource_metrics(sim, result.runtime, ${metricsTarget(state)})`;
  }

  function benchmarkThenLines(state, names) {
    const lines = [`benchmark = Benchmark(${names.join(", ")})`, "benchmark.run()"];
    state.placedSims.forEach((entry, index) => {
      if (!isReference(state, entry)) lines.push(`${names[index]}.measure(measurements)`);
    });
    if (hasThen(state, "plot")) lines.push("benchmark.save_result_plot()");
    if (hasThen(state, "save")) {
      names.forEach((name) => {
        lines.push(
          `${name}.last_result.save(${pyString(`${actionTextValue(state, "save").trim()}/${name}`)})`,
        );
      });
    }
    if (hasThen(state, "export")) lines.push(exportCall(state));
    return lines;
  }

  function singleThenLines(state) {
    const exporting = hasThen(state, "export");
    const metrics = resourceMetricsCall(state);
    const saveLine = `result.save(${pyString(actionTextValue(state, "save").trim())})`;
    if (!isReference(state, state.placedSims[0])) {
      const lines = ["sim.simulate()", "result = sim.measure(measurements)"];
      if (hasThen(state, "save")) lines.push(saveLine);
      if (hasThen(state, "plot")) lines.push("sim.plot_results()");
      if (exporting) lines.push(metrics);
      return lines;
    }
    if (hasThen(state, "save") && hasThen(state, "plot")) {
      const lines = ["result = sim.simulate()", saveLine, "sim.plot_results()"];
      if (exporting) lines.push(metrics);
      return lines;
    }
    if (hasThen(state, "save")) {
      if (!exporting)
        return [`sim.simulate().save(${pyString(actionTextValue(state, "save").trim())})`];
      return ["result = sim.simulate()", saveLine, metrics];
    }
    if (hasThen(state, "plot")) {
      if (!exporting) return ["sim.simulate()", "sim.plot_results()"];
      return ["result = sim.simulate()", "sim.plot_results()", metrics];
    }
    if (exporting) return ["result = sim.simulate()", metrics];
    return ["result = sim.simulate()"];
  }

  function encodingImport(state) {
    const name = stateField(state)?.encode;
    return name ? `from shadowsim.encoding import ${name}` : "";
  }

  function simulatorClass(state, entry) {
    const setup = blockById(state, "simulator", entry.id)?.setup ?? "";
    return setup.match(/=\s*([A-Za-z0-9_]+)/)?.[1] ?? "";
  }

  function simulatorImport(state) {
    const names = [];
    let circuit = false;
    state.placedSims.forEach((entry) => {
      const className = simulatorClass(state, entry);
      if (!className) return;
      if (!names.includes(className)) names.push(className);
      if (!blockById(state, "simulator", entry.id)?.observables) circuit = true;
    });
    if (circuit && !modelMeasureSelected(state)) names.push("Measurement");
    names.sort();
    return names.length ? `from shadowsim.simulators import ${names.join(", ")}` : "";
  }

  function previewText(state) {
    if (!runAllowed(state)) return "";
    const lines = ["import numpy as np"];
    const encoding = encodingImport(state);
    if (encoding) lines.push(encoding);
    if (state.selection.model === "preexisting")
      lines.push(`from shadowsim.models import ${state.preexistingId}`);
    else if (state.selection.model)
      lines.push(`from shadowsim.models import ${state.selection.model}`);
    const simulators = simulatorImport(state);
    if (simulators) lines.push(simulators);
    const benchmark = state.placedSims.length >= 2;
    if (!benchmark && hasThen(state, "export"))
      lines.push("from shadowsim.simulators.result import save_resource_metrics");
    const backendClasses = [];
    state.placedSims.forEach((entry) => {
      if (isReference(state, entry)) return;
      const className = backendClass(state, entry.backend);
      if (className && !backendClasses.includes(className)) backendClasses.push(className);
    });
    if (backendClasses.length)
      lines.push(`from shadowsim.backends import ${backendClasses.join(", ")}`);
    const symbols = [
      ...new Set(
        state.modelTerms.map((term) => blockById(state, "model", term.id)?.symbol).filter(Boolean),
      ),
    ];
    if (
      state.placedSims.some((entry) => blockById(state, "simulator", entry.id)?.observables) &&
      !modelMeasureSelected(state)
    ) {
      symbols.push("Operator");
    }
    if (state.modelTerms.some((term) => term.id === "lindblad" && !lindbladProblem(state, term)))
      symbols.push("LocalOperator");
    if (symbols.length) lines.push(`from shadowsim.core import ${symbols.join(", ")}`);
    if (benchmark) lines.push("from shadowsim.benchmarking import Benchmark");
    const beforeSimulator = ["", stateLine(state), "", modelLine(state), ...termLines(state), ""];
    state.placedSims.forEach((entry, index) => {
      if (isReference(state, entry)) return;
      const setup = backendSetup(
        state,
        entry.backend,
        `circuit_backend_${index + 1}`,
        entry.shots,
        entry.backendFields,
      );
      if (setup) beforeSimulator.push(setup, "");
    });
    if (state.placedSims.some((entry) => blockById(state, "simulator", entry.id)?.observables)) {
      beforeSimulator.push(observableSetup(state), "");
    }
    if (state.placedSims.some((entry) => !isReference(state, entry)))
      beforeSimulator.push(measurementSetup(state), "");
    const names = state.placedSims.map((_, index) => (benchmark ? `sim_${index + 1}` : "sim"));
    lines.push(
      ...beforeSimulator,
      ...state.placedSims.map((entry, index) =>
        simulatorCall(state, entry, names[index], `circuit_backend_${index + 1}`),
      ),
      "",
    );
    lines.push(...(benchmark ? benchmarkThenLines(state, names) : singleThenLines(state)));
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
    if ((source[cursor] ?? "").toLowerCase() === "j")
      return { re: 0, im: number.value, next: cursor + 1 };
    const imag = source.slice(cursor).match(/^([+-])\s*(?:(\d+(?:\.\d*)?|\.\d+)\s*)?j/i);
    if (!imag) return { re: number.value, im: 0, next: number.next };
    const magnitude = imag[2] == null ? 1 : Number(imag[2]);
    return {
      re: number.value,
      im: imag[1] === "-" ? -magnitude : magnitude,
      next: cursor + imag[0].length,
    };
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
    if (!value || index !== source.length || value.some((row) => !Array.isArray(row)))
      return { error: "shape" };
    const width = value.length;
    if (
      !width ||
      value.some((row) => row.length !== width || row.some((cell) => Array.isArray(cell)))
    ) {
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

  function squareMatrix(state, text) {
    const parsed = parseMatrix(text ?? "");
    if (parsed.error === "empty") return { problem: "Enter a matrix." };
    if (parsed.error) return { problem: "Enter a square matrix." };
    const { matrix } = parsed;
    const size = matrix.length;
    const maxQubits = state.maxOperatorQubits;
    const noun = maxQubits === 1 ? "qubit" : "qubits";
    if (size > 2 ** maxQubits) return { problem: `At most ${maxQubits} ${noun}.` };
    if (size < 2 || (size & (size - 1)) !== 0) return { problem: "Size must be a power of two." };
    return { matrix, qubits: Math.log2(size) };
  }

  function inspectMatrix(state, text) {
    const parsed = squareMatrix(state, text);
    if (parsed.problem) return parsed;
    if (!isHermitian(parsed.matrix)) return { problem: "Matrix must be Hermitian." };
    return parsed;
  }

  function fixedQubitCount(state) {
    if (stateOwnsQubits(state) || state.qubitsSource === "user") return qubitCount(state);
    return null;
  }

  function hamiltonianProblem(state, term) {
    const inspected = inspectMatrix(state, term.matrix);
    if (inspected.problem) return inspected.problem;
    const fixed = fixedQubitCount(state);
    if (fixed != null && inspected.qubits !== fixed) {
      const side = 2 ** fixed;
      const label = fixed === 1 ? "qubit" : "qubits";
      return `Must be ${side}×${side} for ${fixed} ${label}.`;
    }
    if (fixed == null && new Set(validHamiltonianQubits(state)).size > 1)
      return "Matrices must be the same size.";
    return null;
  }

  function validHamiltonianQubits(state) {
    return state.modelTerms.flatMap((term) => {
      if (term.id !== "hamiltonian") return [];
      const inspected = inspectMatrix(state, term.matrix);
      return inspected.problem ? [] : [inspected.qubits];
    });
  }

  function localSites(term, count) {
    return (term.sites ?? [])
      .filter((site) => Number.isInteger(site) && site >= 0 && site < count)
      .sort((left, right) => left - right);
  }

  function actedQubitProblem(state, term, parse) {
    const count = qubitCount(state);
    if (count == null) return "Set qubits first.";
    const sites = localSites(term, count);
    if (!sites.length) return "Pick at least one qubit.";
    if (sites[sites.length - 1] - sites[0] + 1 !== sites.length)
      return "Qubits must be contiguous.";
    const inspected = parse(term.matrix);
    if (inspected.problem) return inspected.problem;
    if (inspected.qubits !== sites.length) {
      const side = 2 ** sites.length;
      const label = sites.length === 1 ? "qubit" : "qubits";
      return `Must be ${side}×${side} for ${sites.length} ${label}.`;
    }
    return null;
  }

  function localHamiltonianProblem(state, term) {
    return actedQubitProblem(state, term, (text) => inspectMatrix(state, text));
  }

  function lindbladProblem(state, term) {
    return actedQubitProblem(state, term, (text) => squareMatrix(state, text));
  }

  return {
    amplitudeQubits: (_state, count) => amplitudeQubits(count),
    blockById,
    factorySetsQubits,
    chosenFactory,
    factoryAlert,
    paramAlertDetail,
    emitterProblem,
    entryBody,
    firstProblem,
    fixedFactoryQubits,
    formatSetting,
    hamiltonianProblem,
    backendFieldNumber: (_state, field, text) => backendFieldNumber(field, text),
    backendFieldStatus,
    backendFieldsReady,
    backendNumberProblem: (_state, field, text) => backendNumberProblem(field, text),
    gateFieldProblem: (_state, field, text) => gateFieldProblem(field, text),
    gateNames: (_state, text) => gateNames(text),
    backendFits,
    inspectMatrix,
    isComplete,
    isReference,
    lindbladProblem,
    localHamiltonianProblem,
    localSites: (_state, term, count) => localSites(term, count),
    measureSitesReady,
    countsProblem,
    countsStatus,
    expressionProblem: (_state, text, width) => expressionProblem(text, width),
    missingPaths,
    numberList: (_state, raw, maxCount) => numberList(raw, maxCount),
    numberProblem,
    operatorStatus,
    otherSlotsPlaced,
    positiveIntText: (_state, value) => positiveIntText(value),
    postedTerms,
    previewText,
    qubitCount,
    qubitPhrase,
    qubitProblem,
    readState,
    runAllowed,
    sameTimeGrid,
    timeStepMismatch,
    savePathReady,
    selectedSites,
    settingNumber,
    settingsReady,
    shotsFieldProblem: (_state, text, maxShots) => shotsFieldProblem(text, maxShots),
    shotsProblem,
    shotsReady,
    simFieldProblem: (_state, field, text) => simFieldProblem(field, text),
    simParamProblem,
    simParamsReady,
    socketStatus,
    squareMatrix,
    stateImpliedQubits,
    stateInputProblem,
    stateOwnsQubits,
    stateSizeProblem,
    stateSizeStatus,
    termProblem,
    totalProblem,
    usingAddedOperators,
    validHamiltonianQubits,
  };
});
