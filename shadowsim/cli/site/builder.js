/* Builder page. Model, method, and backend cards come from the package. */

import { resultsComponent, savedNote } from "./chart.js";
import { el } from "./dom.js";

// checks.js is a classic script and sets this before the module runs.
const checks = globalThis.checks;

const LANES = [
  {
    id: "state",
    title: "Initial state",
    hint: "How the system starts",
    pick: "Pick an initial state",
    tone: "gold",
  },
  {
    id: "model",
    title: "Model",
    hint: "A preexisting model, or operators you add",
    pick: "Pick a model",
    tone: "teal",
  },
  {
    id: "simulator",
    title: "Method",
    hint: "The first row is the reference",
    pick: "Build a method",
    tone: "blue",
  },
  {
    id: "measure",
    title: "Measure",
    hint: "What to record",
    pick: "Pick a measurement",
    tone: "green",
  },
  {
    id: "then",
    title: "Then",
    hint: "What to do with the results",
    pick: "Add an action",
    tone: "rose",
  },
];

const DEFAULT_SHOTS = "256";
const BOARD_KEY = "shadowsim.builder.board";
const DOCUMENT_KEYS = new Set([
  "version",
  "total",
  "state",
  "model",
  "simulators",
  "measure",
  "actions",
]);
const CHECK_DELAY = 200;
const CLEAR_UNDO_MS = 8000;

const state = {
  blocks: {
    state: [],
    model: [],
    simulator: [],
    backend: [],
    measure: [],
    then: [],
  },
  limits: null,
  selection: {
    state: null,
    model: null,
    simulator: null,
    backend: null,
    measure: null,
    then: null,
  },
  modelTerms: [],
  modelTermKey: 0,
  modelFactories: [],
  preexistingId: null,
  preexistingOpen: false,
  factoryText: {},
  settings: { qubits: "", total: "" },
  stateText: {},
  qubitsSource: null,
  placedSims: [],
  simKey: 0,
  placedThens: [],
  actionText: {},
  pathOpen: {},
  stateOpen: false,
  measureOpen: false,
  measureSites: null,
  catalogMeasures: [],
  modelMeasurements: [],
  expressionText: {},
  dragging: null,
  running: false,
  boardReady: false,
  copyTimer: 0,
  copiedButton: null,
  copiedLabel: "Copy",
  clearUndo: null,
  clearUndoTimer: 0,
  statusHold: null,
  runStartedAt: 0,
  runTimer: null,
  shownRun: null,
  shownPayload: null,
  writtenActions: null,
  pendingWrite: null,
  writeInFlight: false,
  writeSerial: 0,
  acceptedBody: null,
  acceptedQubits: null,
  rejectedBody: null,
  checkError: null,
  checkTimer: null,
  checkSerial: 0,
  pendingBody: null,
  checkInFlight: false,
  laneNotes: { state: "", model: "", simulator: "", backend: "", measure: "", then: "" },
  laneStatus: {
    state: "ready",
    model: "ready",
    simulator: "ready",
    backend: "ready",
    measure: "ready",
    then: "ready",
  },
};

const LANE_CATALOG = {
  state: { path: "/states", key: "states" },
  model: { path: "/models", key: "models" },
  simulator: { path: "/simulators", key: "simulators" },
  backend: { path: "/backends", key: "backends" },
  measure: { path: "/measurements", key: "measurements" },
  then: { path: "/actions", key: "actions" },
};

function currentPage() {
  return {
    lanes: LANES,
    blocks: state.blocks,
    selection: state.selection,
    settings: state.settings,
    modelTerms: state.modelTerms,
    modelFactories: state.modelFactories,
    preexistingId: state.preexistingId,
    factoryText: state.factoryText,
    stateText: state.stateText,
    placedSims: state.placedSims,
    placedThens: state.placedThens,
    actionText: state.actionText,
    measureSites: state.measureSites,
    expressionText: state.expressionText,
    qubitsSource: state.qubitsSource,
    stateLimits: state.limits?.states ?? {},
    maxOperatorQubits: state.limits?.operatorQubits ?? 0,
    maxTimeSteps: state.limits?.timeSteps ?? 0,
    maxNumSteps: state.limits?.numSteps ?? 0,
    maxTrotterDepth: state.limits?.trotterDepth ?? 0,
    maxShots: state.limits?.shots ?? 0,
    checkedQubits:
      state.checkError == null && state.acceptedBody != null ? state.acceptedQubits : null,
  };
}

function loadingNote(key) {
  return el("p", { className: "placeholder" }, `Loading ${key}…`);
}

function errorNote(message) {
  return el("p", { className: "hint" }, message);
}

function laneNote(laneId) {
  if (state.laneStatus[laneId] === "loading") {
    return loadingNote(LANE_CATALOG[laneId].key);
  }
  if (state.laneNotes[laneId]) return errorNote(state.laneNotes[laneId]);
  return null;
}

function freshParams(block) {
  const params = {};
  for (const field of block?.fields ?? []) params[field.name] = String(field.default ?? "");
  return params;
}

function accepted() {
  return (
    state.acceptedBody != null && state.acceptedBody === documentBody() && state.checkError == null
  );
}

function runAllowed() {
  return checks.runAllowed(currentPage()) && accepted();
}

function previewText() {
  if (!accepted()) return "";
  return checks.previewText(currentPage());
}

function fieldError(id, message) {
  return el(
    "p",
    {
      className: "field-error",
      id,
      hidden: !message || null,
    },
    message || "",
  );
}

function chipAlert({ className = "chip-alert", id = null, hidden = false } = {}) {
  return el(
    "span",
    {
      className,
      id,
      hidden: hidden || null,
      "aria-hidden": "true",
    },
    "!",
  );
}

function setChipAlert(alert, shown) {
  if (!alert) return;
  alert.hidden = !shown;
  alert.setAttribute("aria-hidden", "true");
  alert.removeAttribute("aria-label");
  alert.removeAttribute("role");
  alert.removeAttribute("title");
  alert.removeAttribute("id");
}

function setFieldValidity(field, errorId, message) {
  if (!field) return;
  if (message) {
    field.setAttribute("aria-invalid", "true");
    field.setAttribute("aria-describedby", errorId);
    return;
  }
  field.removeAttribute("aria-invalid");
  field.removeAttribute("aria-describedby");
}

function syncFieldError(host, id, message) {
  if (!host) return null;
  let error = host.querySelector(":scope > .field-error");
  if (!message) {
    if (error) {
      error.hidden = true;
      error.textContent = "";
      error.removeAttribute("id");
    }
    return null;
  }
  if (!error) {
    error = fieldError(id, message);
    host.append(error);
  } else {
    error.id = id;
    error.hidden = false;
    error.textContent = message;
  }
  return error;
}

function modelChoiceBlocked(block) {
  return blockedReason(block) != null;
}

function blockedReason(block) {
  if (!block) return null;
  if (block.id === "preexisting" && state.modelTerms.length > 0) {
    return "Remove added operators to use a preexisting model.";
  }
  if (block.adds && state.selection.model === "preexisting") {
    return "Remove the preexisting model to add operators.";
  }
  return null;
}

function blockCard(lane, block, { inSlot, onPlace, onRemove, blocked }) {
  if (inSlot) {
    return el(
      "div",
      {
        className: `chip tone-${lane.tone}`,
        "data-block": block.id,
        tabindex: "-1",
      },
      el("div", {}, el("strong", {}, block.title), el("span", {}, block.detail)),
      el(
        "button",
        {
          className: "remove",
          type: "button",
          "aria-label": `Remove ${block.title}`,
          onclick: (event) => {
            event.stopPropagation();
            onRemove();
          },
        },
        "×",
      ),
    );
  }

  const reason = blocked ? blockedReason(block) : null;
  const reasonId = reason ? `block-reason-${lane.id}-${block.id}` : null;
  const card = el(
    "button",
    {
      className: `block tone-${lane.tone}`,
      type: "button",
      draggable: blocked ? "false" : "true",
      disabled: Boolean(blocked),
      "aria-describedby": reasonId,
      "data-lane": lane.id,
      "data-block": block.id,
      ondragstart: (event) => {
        if (blocked) {
          event.preventDefault();
          return;
        }
        state.dragging = { lane: lane.id, id: block.id };
        event.dataTransfer.setData("text/plain", `${lane.id}:${block.id}`);
        event.dataTransfer.effectAllowed = "copy";
      },
      ondragend: () => {
        state.dragging = null;
      },
      onclick: () => {
        if (!blocked) onPlace();
      },
    },
    el(
      "div",
      {},
      el("strong", {}, block.title),
      el("span", {}, block.detail),
      reason ? el("span", { className: "block-reason", id: reasonId }, reason) : null,
    ),
  );
  return card;
}

function acceptedLayoutQubits() {
  if (
    state.acceptedBody == null ||
    state.acceptedBody !== documentBody() ||
    state.checkError != null
  )
    return null;
  return state.acceptedQubits;
}

function qubitDetail(count) {
  return count === 1 ? "1 qubit" : `${count} qubits`;
}

function preexistingDetail() {
  const factory = checks.chosenFactory(currentPage());
  if (!factory) return "";
  const qubits = acceptedLayoutQubits();
  if (factory.qubits) return qubits == null ? "at least 2 qubits" : qubitDetail(qubits);
  if (qubits == null) return checks.factoryAlert(currentPage()) || "Set the model arguments";
  return qubitDetail(qubits);
}

function factoryParams() {
  const params = checks.chosenFactory(currentPage())?.params;
  return Array.isArray(params) ? params : [];
}

function paramText(param) {
  const stored = state.factoryText[param.name];
  return typeof stored === "string" ? stored : String(param.default ?? "");
}

function movedFromDefault(name) {
  const param = factoryParams().find((item) => item.name === name);
  return Boolean(param) && paramText(param) !== String(param.default ?? "");
}

function fieldLocked(param) {
  return factoryParams().some(
    (other) =>
      Array.isArray(other.disables) &&
      other.disables.includes(param.name) &&
      movedFromDefault(other.name),
  );
}

function paintFactoryLocks() {
  for (const param of factoryParams()) {
    const control = document.querySelector(`[data-param="${param.name}"]`);
    if (control) control.disabled = fieldLocked(param);
  }
}

function rememberFactoryText(name, value) {
  state.factoryText[name] = value;
}

function factoryField(param, errorMessage = null) {
  const value = paramText(param);
  const locked = fieldLocked(param);
  const errorId = `factory-error-${param.name}`;
  if (param.kind === "choice") {
    return el(
      "label",
      { className: "chip-field" },
      param.label,
      el(
        "select",
        {
          "aria-label": param.label,
          "data-param": param.name,
          "aria-invalid": errorMessage ? "true" : null,
          "aria-describedby": errorMessage ? errorId : null,
          disabled: locked || null,
          onchange: (event) => {
            update(() => {
              rememberFactoryText(param.name, event.target.value);
              deriveModelQubits();
              if (state.selection.state) deriveStateQubits();
            });
          },
        },
        ...(Array.isArray(param.choices) ? param.choices : []).map((choice) =>
          el("option", { value: choice, selected: choice === value }, choice),
        ),
      ),
      fieldError(errorId, errorMessage),
    );
  }
  const integer = param.kind === "integer";
  const numeric = integer || param.kind === "number" || param.kind === "number_or_list";
  return el(
    "label",
    { className: "chip-field" },
    param.label,
    el("input", {
      type: "text",
      inputmode: integer ? "numeric" : numeric ? "decimal" : "text",
      "aria-label": param.label,
      "data-param": param.name,
      "aria-invalid": errorMessage ? "true" : null,
      "aria-describedby": errorMessage ? errorId : null,
      value,
      disabled: locked || null,
      spellcheck: "false",
      autocomplete: "off",
      oninput: (event) => {
        const next = event.target.value;
        update(() => {
          rememberFactoryText(param.name, next);
          deriveModelQubits();
          if (state.selection.state) deriveStateQubits();
        });
      },
    }),
    fieldError(errorId, errorMessage),
  );
}

function postedFactory() {
  if (state.selection.model !== "preexisting") return null;
  const params = factoryParams();
  if (!params.length) return null;
  const body = {};
  for (const param of params) body[param.name] = paramText(param);
  return body;
}

function modelAlert() {
  if (state.checkError) return state.checkError;
  return checks.factoryAlert(currentPage());
}

function paintFactoryDetail() {
  const detail = document.querySelector(".preexisting-detail");
  if (detail) detail.textContent = preexistingDetail();
}

function paintModelAlert() {
  const chip = document.querySelector(".chip.preexisting");
  const text = modelAlert();
  setChipAlert(chip?.querySelector(".preexisting-alert"), Boolean(text));
  if (!chip) return;
  for (const control of chip.querySelectorAll("[data-param], select[aria-label='Model']")) {
    setFieldValidity(control, null, null);
  }
  for (const error of chip.querySelectorAll(".field-error")) {
    error.hidden = true;
    error.textContent = "";
    error.removeAttribute("id");
  }
  if (!text || !state.preexistingOpen) return;
  const detail = state.checkError ? null : checks.paramAlertDetail(currentPage());
  const name = detail?.name ?? null;
  const errorId = name ? `factory-error-${name}` : "factory-error-model";
  const control = name
    ? chip.querySelector(`[data-param="${name}"]`)
    : chip.querySelector('select[aria-label="Model"]');
  const host = control?.closest("label");
  syncFieldError(host, errorId, text);
  setFieldValidity(control, errorId, text);
}

function preexistingChip() {
  const factory = checks.chosenFactory(currentPage());
  const alertText = modelAlert();
  const detail = state.checkError ? null : checks.paramAlertDetail(currentPage());
  const modelError = state.checkError ? alertText : null;
  const modelErrorId = "factory-error-model";
  const select = el(
    "select",
    {
      "aria-label": "Model",
      "aria-invalid": modelError ? "true" : null,
      "aria-describedby": modelError ? modelErrorId : null,
      onchange: (event) => {
        update(
          () => {
            state.preexistingId = event.target.value;
            deriveModelQubits();
            releaseStatusHold();
          },
          { lanes: ["model"], palettes: ["model"], clearResults: true },
        );
      },
    },
    ...state.modelFactories.map((item) =>
      el("option", { value: item.id, selected: item.id === factory?.id }, item.title),
    ),
  );
  return el(
    "div",
    {
      className: `chip tone-teal preexisting${state.preexistingOpen ? " is-editing" : ""}`,
      tabindex: "-1",
    },
    el(
      "div",
      { className: "chip-head" },
      el(
        "button",
        {
          type: "button",
          onclick: () => {
            if (state.preexistingOpen) return;
            update(
              () => {
                state.preexistingOpen = true;
              },
              {
                lanes: ["model"],
                chrome: false,
                focus: { kind: "first-field", chip: ".chip.preexisting" },
              },
            );
          },
        },
        el("strong", {}, "Preexisting model"),
        el("span", { className: "preexisting-detail" }, preexistingDetail()),
      ),
      el(
        "div",
        { className: "chip-actions" },
        chipAlert({
          className: "chip-alert preexisting-alert",
          hidden: !alertText,
        }),
        state.preexistingOpen
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: () => {
                  update(
                    () => {
                      state.preexistingOpen = false;
                    },
                    {
                      lanes: ["model"],
                      chrome: false,
                      focus: { kind: "header", chip: ".chip.preexisting" },
                    },
                  );
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": "Remove Preexisting model",
            onclick: (event) => {
              event.stopPropagation();
              clearLane("model");
            },
          },
          "×",
        ),
      ),
    ),
    state.preexistingOpen
      ? el(
          "label",
          { className: "chip-field" },
          "Model",
          select,
          fieldError(modelErrorId, modelError),
        )
      : null,
    ...(state.preexistingOpen
      ? factoryParams().map((param) =>
          factoryField(param, detail?.name === param.name ? detail.message : null),
        )
      : []),
  );
}

function grayPrepared(bits) {
  let index = 0;
  for (const bit of bits) index = (index << 1) | (bit === "1" ? 1 : 0);
  return (index ^ (index >>> 1)).toString(2).padStart(bits.length, "0");
}

function stateField(id) {
  return checks.blockById(currentPage(), "state", id)?.field ?? null;
}

function stateTextOf(id) {
  return state.stateText[id] ?? "";
}

function blankDetail(field) {
  return String(field.blank ?? "").replaceAll("{cap}", String(field.cap ?? ""));
}

function stateDetail(id) {
  const read = checks.readState(currentPage(), id);
  if (!read?.filled) return read ? blankDetail(read.field) : "";
  if (read.field.kind === "bits") {
    const shown = read.field.display === "gray" ? grayPrepared(read.text) : read.text;
    return `Start in |${shown}>`;
  }
  const unit = read.field.unit || "value";
  return read.count === 1 ? `1 ${unit}` : `${read.count} ${unit}s`;
}

function stateReady(id) {
  return checks.readState(currentPage(), id)?.filled === true;
}

function deriveStateQubits() {
  if (!checks.stateOwnsQubits(currentPage()) || checks.factorySetsQubits(currentPage())) return;
  const count = checks.stateImpliedQubits(currentPage());
  state.settings.qubits = count == null ? "" : String(count);
  state.qubitsSource = count == null ? null : "state";
  if (count == null) state.measureOpen = false;
}

function deriveModelQubits() {
  if (!checks.factorySetsQubits(currentPage())) {
    if (state.qubitsSource !== "model") return;
    if (checks.stateOwnsQubits(currentPage())) {
      state.qubitsSource = null;
      deriveStateQubits();
    } else state.qubitsSource = state.settings.qubits === "" ? null : "user";
    return;
  }
  const fixed = acceptedLayoutQubits();
  state.settings.qubits = fixed == null ? "" : String(fixed);
  state.qubitsSource = "model";
  if (fixed == null) state.measureOpen = false;
}

function stateAlertLabel(id) {
  const field = stateField(id);
  if (!field) return "";
  const expected = checks.stateSizeProblem(currentPage());
  if (expected != null) return String(field.mismatch ?? "").replaceAll("{n}", String(expected));
  return field.empty ?? "";
}

function paintStateChip() {
  const detail = document.querySelector(".basis-detail");
  if (detail && state.selection.state) detail.textContent = stateDetail(state.selection.state);
  const chip = document.querySelector(".chip.tone-gold");
  if (!chip || !state.selection.state) return;
  const id = state.selection.state;
  const invalid = !(stateReady(id) && checks.stateSizeProblem(currentPage()) == null);
  const label = invalid ? stateAlertLabel(id) : null;
  const errorId = `state-error-${id}`;
  setChipAlert(chip.querySelector(".chip-alert"), invalid);
  const field = chip.querySelector(".chip-field input");
  const host = field?.closest("label");
  syncFieldError(host, errorId, label);
  setFieldValidity(field, errorId, label);
}

function stateChip(options) {
  const open = state.stateOpen;
  const invalid = !(stateReady(options.id) && checks.stateSizeProblem(currentPage()) == null);
  const message = invalid ? stateAlertLabel(options.id) : null;
  const errorId = `state-error-${options.id}`;
  const input = el("input", {
    type: "text",
    inputmode: options.bits ? "numeric" : "decimal",
    ...(options.bits ? { maxlength: String(options.cap) } : {}),
    "aria-label": options.aria,
    "aria-invalid": message ? "true" : null,
    "aria-describedby": message ? errorId : null,
    value: options.value,
    spellcheck: "false",
    autocomplete: "off",
    oninput: options.oninput,
  });
  const chipSelector = `.chip.state.${options.id}`;
  return el(
    "div",
    {
      className: `chip tone-gold state ${options.id}${open ? " is-editing" : ""}`,
      tabindex: "-1",
    },
    el(
      "div",
      { className: "chip-head" },
      el(
        "button",
        {
          type: "button",
          onclick: () => {
            if (state.stateOpen) return;
            update(
              () => {
                state.stateOpen = true;
              },
              {
                lanes: ["state"],
                chrome: false,
                focus: { kind: "first-field", chip: chipSelector },
              },
            );
          },
        },
        el("strong", {}, options.title),
        el("span", { className: "basis-detail" }, stateDetail(options.id)),
      ),
      el(
        "div",
        { className: "chip-actions" },
        chipAlert({ hidden: !invalid }),
        open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: () => {
                  update(
                    () => {
                      state.stateOpen = false;
                    },
                    {
                      lanes: ["state"],
                      chrome: false,
                      focus: { kind: "header", chip: chipSelector },
                    },
                  );
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${options.title}`,
            onclick: (event) => {
              event.stopPropagation();
              clearLane("state");
            },
          },
          "×",
        ),
      ),
    ),
    open
      ? el("label", { className: "chip-field" }, options.field, input, fieldError(errorId, message))
      : null,
  );
}

function stateFieldChip(block) {
  const field = block.field ?? {};
  const bits = field.kind === "bits";
  return stateChip({
    id: block.id,
    title: block.title,
    field: field.label,
    aria: field.aria,
    bits,
    cap: field.cap,
    value: stateTextOf(block.id),
    oninput: (event) => {
      const next = event.target.value;
      update(() => {
        state.stateText[block.id] = next;
        deriveStateQubits();
      });
    },
  });
}

function timeStepMessage(entry) {
  const message = checks.timeStepMismatch(currentPage());
  if (!message || String(entry.params?.time_steps ?? "") === "") return null;
  return message;
}

function simulatorFieldMessage(entry, field) {
  if (field.name === "time_steps") {
    const mismatch = timeStepMessage(entry);
    if (mismatch) return mismatch;
  }
  return checks.simFieldProblem(currentPage(), field, entry.params?.[field.name]);
}

function simField(params, key, label, seed, errorId, message) {
  return el(
    "label",
    {},
    label,
    el("input", {
      type: "text",
      inputmode: seed ? "text" : "numeric",
      "aria-label": label,
      "aria-invalid": message ? "true" : null,
      "aria-describedby": message ? errorId : null,
      value: params[key],
      spellcheck: "false",
      oninput: (event) => {
        const next = event.target.value;
        update(() => {
          params[key] = next;
        });
      },
    }),
    fieldError(errorId, message),
  );
}

function simulatorControl(entry, field) {
  const params = entry.params;
  const value = String(params[field.name] ?? field.default ?? "");
  const errorId = `sim-error-${entry.key}-${field.name}`;
  const message = simulatorFieldMessage(entry, field);
  if (field.kind === "choice") {
    const choices = Array.isArray(field.choices) ? field.choices : [];
    return el(
      "label",
      {},
      field.label,
      el(
        "select",
        {
          "aria-label": field.label,
          "aria-invalid": message ? "true" : null,
          "aria-describedby": message ? errorId : null,
          onchange: (event) => {
            update(() => {
              params[field.name] = event.target.value;
            });
          },
        },
        ...choices.map((choice) =>
          el("option", { value: choice, selected: choice === value }, choice),
        ),
      ),
      fieldError(errorId, message),
    );
  }
  return simField(
    params,
    field.name,
    field.label,
    !Number.isInteger(field.minimum),
    errorId,
    message,
  );
}

function simulatorChip(entry) {
  const block = checks.blockById(currentPage(), "simulator", entry.id);
  if (!block) return null;
  const fields = block.fields ?? [];
  const invalid = fields.some((field) => simulatorFieldMessage(entry, field));
  const controls = fields.map((field) => simulatorControl(entry, field));
  return el(
    "div",
    {
      className: `chip tone-blue simulator${entry.open ? " is-editing" : ""}`,
      "data-key": String(entry.key),
      tabindex: "-1",
    },
    el(
      "div",
      { className: "chip-head" },
      el(
        "button",
        {
          type: "button",
          onclick: () => {
            if (entry.open) return;
            update(
              () => {
                entry.open = true;
              },
              {
                lanes: ["simulator"],
                chrome: false,
                focus: { kind: "first-field", chip: ".chip.simulator", key: entry.key },
              },
            );
          },
        },
        el("strong", {}, block.title),
        el("span", {}, block.detail),
      ),
      el(
        "div",
        { className: "chip-actions" },
        chipAlert({ hidden: !invalid }),
        entry.open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: () => {
                  update(
                    () => {
                      entry.open = false;
                    },
                    {
                      lanes: ["simulator"],
                      chrome: false,
                      focus: { kind: "header", chip: ".chip.simulator", key: entry.key },
                    },
                  );
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${block.title}`,
            onclick: (event) => {
              event.stopPropagation();
              removeSimulator(entry.key);
            },
          },
          "×",
        ),
      ),
    ),
    entry.open ? el("div", { className: "sim-fields" }, ...controls) : null,
  );
}

function pathValue(id) {
  if (Object.hasOwn(state.actionText, id)) return state.actionText[id];
  return checks.blockById(currentPage(), "then", id)?.field?.default ?? "";
}

function pathChip(block) {
  const field = block.field ?? {};
  const open = Boolean(state.pathOpen[block.id]);
  const path = pathValue(block.id);
  const shown = path.trim();
  const chipSelector = `.chip.path.${block.id}`;
  return el(
    "div",
    {
      className: `chip tone-rose path ${block.id}${open ? " is-editing" : ""}`,
      tabindex: "-1",
    },
    el(
      "div",
      { className: "chip-head" },
      el(
        "button",
        {
          type: "button",
          onclick: () => {
            if (open) return;
            update(
              () => {
                state.pathOpen[block.id] = true;
              },
              {
                lanes: ["then"],
                chrome: false,
                focus: { kind: "first-field", chip: chipSelector },
              },
            );
          },
        },
        el("strong", {}, block.title),
        el("span", {}, shown || block.detail),
      ),
      el(
        "div",
        { className: "chip-actions" },
        open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: () => {
                  update(
                    () => {
                      state.pathOpen[block.id] = false;
                    },
                    {
                      lanes: ["then"],
                      chrome: false,
                      focus: { kind: "header", chip: chipSelector },
                    },
                  );
                  if (block.id === "save" || block.id === "export") queueWrite();
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${block.title}`,
            onclick: (event) => {
              event.stopPropagation();
              removeThen(block.id);
            },
          },
          "×",
        ),
      ),
    ),
    open
      ? el(
          "label",
          { className: "chip-field" },
          field.label || "Path",
          el("input", {
            type: "text",
            "aria-label": field.aria || "Path",
            value: path,
            spellcheck: "false",
            oninput: (event) => {
              update(() => {
                state.actionText[block.id] = event.target.value;
              });
            },
          }),
        )
      : null,
  );
}

function gateSummary(field, text) {
  if (checks.gateFieldProblem(currentPage(), field, text)) return "";
  const names = checks.gateNames(currentPage(), text);
  return names.length ? names.join(", ") : "";
}

function backendSummary(block, entry) {
  const parts = [];
  if (block.shots) {
    const shotText = String(entry.shots ?? "").trim();
    if (!checks.positiveIntText(currentPage(), shotText)) return block.detail;
    parts.push(`${shotText} shots`);
  }
  for (const field of block.fields ?? []) {
    const text = String(entry.backendFields?.[field.name] ?? "").trim();
    if (field.kind === "gates") {
      const gates = gateSummary(field, text);
      if (gates) parts.push(gates);
      continue;
    }
    if (checks.backendFieldNumber(currentPage(), field, text) == null) return block.detail;
    parts.push(`${field.label} ${text}`);
  }
  return parts.length ? parts.join(", ") : block.detail;
}

function backendChip(entry) {
  const block = checks.blockById(currentPage(), "backend", entry.backend);
  if (!block) return null;
  const fields = block.fields ?? [];
  const samples = Boolean(block.shots);
  const configurable = samples || fields.length > 0;
  const editing = samples
    ? Boolean(entry.shotsOpen)
    : Boolean(entry.backendOpen) && fields.length > 0;
  const shown = backendSummary(block, entry);
  return el(
    "div",
    {
      className: `chip tone-violet backend${editing ? " is-editing" : ""}`,
      "data-key": String(entry.key),
      tabindex: "-1",
    },
    el(
      "div",
      { className: "chip-head" },
      el(
        "button",
        {
          type: "button",
          onclick: () => {
            if (!configurable || editing) return;
            update(
              () => {
                if (samples) entry.shotsOpen = true;
                else entry.backendOpen = true;
              },
              {
                lanes: ["simulator"],
                chrome: false,
                focus: { kind: "first-field", chip: ".chip.backend", key: entry.key },
              },
            );
          },
        },
        el("strong", {}, block.title),
        el("span", { className: "backend-detail" }, shown),
      ),
      el(
        "div",
        { className: "chip-actions" },
        editing
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: () => {
                  update(
                    () => {
                      entry.shotsOpen = false;
                      entry.backendOpen = false;
                    },
                    {
                      lanes: ["simulator"],
                      chrome: false,
                      focus: { kind: "header", chip: ".chip.backend", key: entry.key },
                    },
                  );
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${block.title}`,
            onclick: (event) => {
              event.stopPropagation();
              removeBackend(entry.key);
            },
          },
          "×",
        ),
      ),
    ),
    editing && samples
      ? (() => {
          const errorId = `shots-error-${entry.key}`;
          const message = checks.shotsFieldProblem(currentPage(), entry.shots, state.maxShots);
          return el(
            "label",
            { className: "chip-field" },
            "Shots",
            el("input", {
              type: "text",
              inputmode: "numeric",
              "aria-label": "Shots",
              "aria-invalid": message ? "true" : null,
              "aria-describedby": message ? errorId : null,
              value: String(entry.shots ?? ""),
              spellcheck: "false",
              oninput: (event) => {
                const next = event.target.value;
                update(() => {
                  entry.shots = next;
                });
              },
            }),
            fieldError(errorId, message),
          );
        })()
      : null,
    editing && fields.length
      ? el(
          "div",
          { className: "backend-fields" },
          ...fields.map((field) => {
            const text = entry.backendFields?.[field.name];
            const errorId = `backend-error-${entry.key}-${field.name}`;
            const message =
              field.kind === "gates"
                ? checks.gateFieldProblem(currentPage(), field, text)
                : checks.backendNumberProblem(currentPage(), field, text);
            return el(
              "label",
              {},
              field.label,
              el("input", {
                type: "text",
                inputmode: field.kind === "gates" ? "text" : "decimal",
                "aria-label": field.label,
                "aria-invalid": message ? "true" : null,
                "aria-describedby": message ? errorId : null,
                value: String(text ?? ""),
                spellcheck: "false",
                autocomplete: "off",
                oninput: (event) => {
                  const next = event.target.value;
                  update(() => {
                    entry.backendFields = entry.backendFields ?? {};
                    entry.backendFields[field.name] = next;
                  });
                },
              }),
              fieldError(errorId, message),
            );
          }),
        )
      : null,
  );
}

function backendSocket(entry) {
  return el(
    "div",
    {
      className: "socket",
      "data-socket": String(entry.key),
      ondragover: (event) => {
        if (state.dragging?.lane !== "backend") return;
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.classList.add("is-over");
      },
      ondragleave: (event) => event.currentTarget.classList.remove("is-over"),
      ondrop: (event) => {
        if (state.dragging?.lane !== "backend") return;
        event.preventDefault();
        event.stopPropagation();
        attachBackend(state.dragging.id, entry.key);
      },
    },
    "Add a backend",
  );
}

function methodRow(entry) {
  const simulator = simulatorChip(entry);
  if (!simulator) return null;
  if (checks.isReference(currentPage(), entry))
    return el("div", { className: "method-row reference" }, simulator);
  const backend = entry.backend ? backendChip(entry) : backendSocket(entry);
  return el("div", { className: "method-row" }, simulator, backend);
}

function hamiltonianDetail(term) {
  const problem = checks.hamiltonianProblem(currentPage(), term);
  if (!term.matrix.trim()) return "Square Hermitian matrix";
  if (problem) return problem.replace(/\.$/, "");
  const size = checks.inspectMatrix(currentPage(), term.matrix).matrix.length;
  return `${size}×${size}`;
}

function deriveHamiltonianQubits() {
  if (checks.stateOwnsQubits(currentPage()) || state.qubitsSource === "user") return;
  const counts = [...new Set(checks.validHamiltonianQubits(currentPage()))];
  if (counts.length === 1) {
    state.settings.qubits = String(counts[0]);
    state.qubitsSource = "hamiltonian";
  } else if (state.qubitsSource === "hamiltonian") {
    state.settings.qubits = "";
    state.qubitsSource = null;
  }
  if (checks.qubitCount(currentPage()) == null) state.measureOpen = false;
}

function paintHamiltonianChips() {
  document.querySelectorAll(".chip.hamiltonian").forEach((chip) => {
    const term = state.modelTerms.find((item) => item.key === Number(chip.dataset.key));
    if (!term) return;
    const detail = chip.querySelector(".hamiltonian-detail");
    if (detail) detail.textContent = hamiltonianDetail(term);
    paintOperatorAlert(chip, term);
  });
}

function hamiltonianChip(term) {
  const errorId = `operator-error-${term.key}`;
  const input = el("textarea", {
    "aria-label": "Hamiltonian matrix",
    spellcheck: "false",
    rows: "4",
    oninput: (event) => {
      update(() => {
        term.matrix = event.target.value;
        deriveHamiltonianQubits();
      });
    },
  });
  input.value = term.matrix;
  const chip = el(
    "div",
    {
      className: "chip tone-teal hamiltonian is-editing",
      "data-key": String(term.key),
      tabindex: "-1",
    },
    el(
      "div",
      { className: "chip-head" },
      el(
        "div",
        {},
        el("strong", {}, "Add a Hamiltonian"),
        el("span", { className: "hamiltonian-detail" }, hamiltonianDetail(term)),
      ),
      el(
        "div",
        { className: "chip-actions" },
        chipAlert(),
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": "Remove Hamiltonian",
            onclick: (event) => {
              event.stopPropagation();
              removeTerm(term.key);
            },
          },
          "×",
        ),
      ),
    ),
    el("label", { className: "chip-field" }, "Matrix", input, fieldError(errorId, null)),
  );
  paintOperatorAlert(chip, term);
  return chip;
}

function actedQubitDetail(term) {
  if (checks.qubitCount(currentPage()) == null) return "Set qubits first";
  const problem =
    term.id === "lindblad"
      ? checks.lindbladProblem(currentPage(), term)
      : checks.localHamiltonianProblem(currentPage(), term);
  if (problem) return problem.replace(/\.$/, "");
  const sites = checks.localSites(currentPage(), term, checks.qubitCount(currentPage()));
  const parsed =
    term.id === "lindblad"
      ? checks.squareMatrix(currentPage(), term.matrix)
      : checks.inspectMatrix(currentPage(), term.matrix);
  const label = sites.length === 1 ? `qubit ${sites[0]}` : `qubits ${sites.join(", ")}`;
  return `${parsed.matrix.length}×${parsed.matrix.length} on ${label}`;
}

function toggleLocalSite(term, site, checked) {
  const next = checks
    .localSites(currentPage(), term, checks.qubitCount(currentPage()))
    .filter((index) => index !== site);
  if (checked) next.push(site);
  next.sort((left, right) => left - right);
  term.sites = next;
}

function localSiteFields(term) {
  const count = checks.qubitCount(currentPage());
  const chosen = new Set(checks.localSites(currentPage(), term, count));
  const boxes = [];
  for (let site = 0; site < count; site += 1) {
    boxes.push(
      el(
        "label",
        { className: "qubit" },
        el("input", {
          type: "checkbox",
          "aria-label": `${term.id === "lindblad" ? "Lindblad" : "Local"} qubit ${site}`,
          checked: chosen.has(site),
          onchange: (event) => {
            update(() => {
              toggleLocalSite(term, site, event.target.checked);
            });
          },
        }),
        String(site),
      ),
    );
  }
  return el("div", { className: "qubit-picker" }, ...boxes);
}

function localFields(term) {
  const errorId = `operator-error-${term.key}`;
  const input = el("textarea", {
    "aria-label": term.id === "lindblad" ? "Lindblad matrix" : "Local Hamiltonian matrix",
    spellcheck: "false",
    rows: "4",
    oninput: (event) => {
      update(() => {
        term.matrix = event.target.value;
      });
    },
  });
  input.value = term.matrix;
  return el(
    "div",
    { className: "local-fields" },
    el("label", { className: "chip-field" }, "Matrix", input, fieldError(errorId, null)),
    localSiteFields(term),
  );
}

function operatorProblem(term) {
  if (term.id === "lindblad") return checks.lindbladProblem(currentPage(), term);
  if (term.id === "local_hamiltonian") return checks.localHamiltonianProblem(currentPage(), term);
  return checks.hamiltonianProblem(currentPage(), term);
}

function paintOperatorAlert(chip, term) {
  const problem = operatorProblem(term);
  const shown =
    Boolean(problem) && (term.id === "hamiltonian" || checks.qubitCount(currentPage()) != null);
  const message = shown ? problem : null;
  const errorId = `operator-error-${term.key}`;
  setChipAlert(chip.querySelector(".chip-alert"), shown);
  const field = chip.querySelector("textarea");
  const host = field?.closest("label");
  syncFieldError(host, errorId, message);
  setFieldValidity(field, errorId, message);
}

function paintLocalHamiltonianChips() {
  document.querySelectorAll(".chip.local-hamiltonian, .chip.lindblad").forEach((chip) => {
    const term = state.modelTerms.find((item) => item.key === Number(chip.dataset.key));
    if (!term) return;
    const count = checks.qubitCount(currentPage());
    if (count != null) term.sites = checks.localSites(currentPage(), term, count);
    const open = count != null;
    chip.classList.toggle("is-editing", open);
    const detail = chip.querySelector(".hamiltonian-detail");
    if (detail) detail.textContent = actedQubitDetail(term);
    const fields = chip.querySelector(".local-fields");
    if (!open) fields?.remove();
    else if (!fields) chip.append(localFields(term));
    else fields.querySelector(".qubit-picker")?.replaceWith(localSiteFields(term));
    paintOperatorAlert(chip, term);
  });
}

function actedQubitChip(term) {
  const open = checks.qubitCount(currentPage()) != null;
  const lindblad = term.id === "lindblad";
  const title = lindblad ? "Add a Lindblad operator" : "Add a Local Hamiltonian";
  const chip = el(
    "div",
    {
      className: `chip tone-teal ${lindblad ? "lindblad" : "local-hamiltonian"}${open ? " is-editing" : ""}`,
      "data-key": String(term.key),
      tabindex: "-1",
    },
    el(
      "div",
      { className: "chip-head" },
      el(
        "div",
        {},
        el("strong", {}, title),
        el("span", { className: "hamiltonian-detail" }, actedQubitDetail(term)),
      ),
      el(
        "div",
        { className: "chip-actions" },
        chipAlert(),
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": lindblad ? "Remove Lindblad operator" : "Remove local Hamiltonian",
            onclick: (event) => {
              event.stopPropagation();
              removeTerm(term.key);
            },
          },
          "×",
        ),
      ),
    ),
    open ? localFields(term) : null,
  );
  paintOperatorAlert(chip, term);
  return chip;
}

function slotChips(lane) {
  const chips = [];
  const chosen = checks.blockById(currentPage(), lane.id, state.selection[lane.id]);
  if (chosen && !chosen.adds && lane.id !== "then") {
    if (chosen.id === "preexisting") chips.push(preexistingChip());
    else if (lane.id === "state") chips.push(stateFieldChip(chosen));
    else if (lane.id === "measure") chips.push(measureChip(chosen));
    else if (lane.id !== "simulator") {
      chips.push(blockCard(lane, chosen, { inSlot: true, onRemove: () => clearLane(lane.id) }));
    }
  }
  if (lane.id === "then") {
    for (const id of state.placedThens) {
      const block = checks.blockById(currentPage(), "then", id);
      if (!block) continue;
      if (block.field?.kind === "path") chips.push(pathChip(block));
      else chips.push(blockCard(lane, block, { inSlot: true, onRemove: () => removeThen(id) }));
    }
    return chips;
  }
  if (lane.id === "simulator") {
    for (const entry of state.placedSims) {
      const row = methodRow(entry);
      if (row) chips.push(row);
    }
    return chips;
  }
  if (lane.id !== "model") return chips;
  for (const term of state.modelTerms) {
    const block = checks.blockById(currentPage(), "model", term.id);
    if (!block) continue;
    if (term.id === "hamiltonian") chips.push(hamiltonianChip(term));
    else if (term.id === "local_hamiltonian" || term.id === "lindblad")
      chips.push(actedQubitChip(term));
    else chips.push(blockCard(lane, block, { inSlot: true, onRemove: () => removeTerm(term.key) }));
  }
  return chips;
}

function laneColumn(lane) {
  return String(1 + LANES.indexOf(lane) * 2);
}

function placeOnGrid(node, lane, row) {
  node.style.gridColumn = laneColumn(lane);
  node.style.gridRow = row;
  return node;
}

function slotAcceptsDrag(laneId) {
  if (!state.dragging) return false;
  if (state.dragging.lane === laneId) return true;
  return laneId === "simulator" && state.dragging.lane === "backend";
}

function laneIsLoading(laneId) {
  if (laneId === "simulator") {
    return state.laneStatus.simulator === "loading" || state.laneStatus.backend === "loading";
  }
  return state.laneStatus[laneId] === "loading";
}

function slotComponent(lane) {
  const loading = laneIsLoading(lane.id);
  const slot = el(
    "section",
    {
      className: `slot tone-${lane.tone}`,
      "data-slot": lane.id,
      ondragover: (event) => {
        if (loading || !slotAcceptsDrag(lane.id)) return;
        event.preventDefault();
        slot.classList.add("is-over");
      },
      ondragleave: () => slot.classList.remove("is-over"),
      ondrop: (event) => {
        if (loading || !slotAcceptsDrag(lane.id)) return;
        event.preventDefault();
        if (state.dragging.lane === "backend") attachBackend(state.dragging.id);
        else place(lane.id, state.dragging.id);
      },
    },
    el("h2", { tabindex: "-1" }, lane.title),
    loading ? null : el("p", { className: "hint" }, lane.hint),
    ...(loading ? [] : slotChips(lane)),
  );
  return placeOnGrid(slot, lane, "1");
}

function methodPalette(lane, onPlace) {
  const notes = [laneNote("simulator"), laneNote("backend")].filter(Boolean);
  const simulatorReady = state.laneStatus.simulator === "ready";
  const backendReady = state.laneStatus.backend === "ready";
  const groups = [];
  if (simulatorReady) {
    groups.push(
      ["Classical references", state.blocks.simulator.filter((block) => block.observables), lane],
      ["Simulators", state.blocks.simulator.filter((block) => !block.observables), lane],
    );
  }
  if (backendReady) {
    groups.push(["Backends", state.blocks.backend, { id: "backend", tone: "violet" }]);
  }
  return placeOnGrid(
    el(
      "section",
      { className: "lane", "data-palette": lane.id },
      el("h2", {}, lane.pick),
      ...notes,
      ...groups
        .filter(([, blocks]) => blocks.length)
        .map(([title, blocks, cardLane]) =>
          el(
            "div",
            { className: "palette-group" },
            el("h3", {}, title),
            el(
              "div",
              { className: "cards" },
              ...blocks.map((block) =>
                blockCard(cardLane, block, {
                  inSlot: false,
                  blocked: false,
                  onPlace: () =>
                    cardLane.id === "backend" ? attachBackend(block.id) : onPlace(block.id),
                }),
              ),
            ),
          ),
        ),
    ),
    lane,
    "2",
  );
}

function paletteComponent(lane, onPlace) {
  if (lane.id === "simulator") return methodPalette(lane, onPlace);
  const note = laneNote(lane.id);
  const cards =
    state.laneStatus[lane.id] === "loading"
      ? null
      : el(
          "div",
          { className: "cards" },
          ...state.blocks[lane.id].map((block) =>
            blockCard(lane, block, {
              inSlot: false,
              blocked: lane.id === "model" && modelChoiceBlocked(block),
              onPlace: () => onPlace(block.id),
            }),
          ),
        );
  return placeOnGrid(
    el(
      "section",
      { className: "lane", "data-palette": lane.id },
      el("h2", {}, lane.pick),
      note,
      cards,
    ),
    lane,
    "2",
  );
}

function summaryComponent() {
  if (!checks.isComplete(currentPage())) {
    return el("p", { className: "summary" }, "Place a block in each slot, then run.");
  }
  const initial = checks.blockById(currentPage(), "state", state.selection.state);
  const model =
    state.selection.model === "preexisting" ? checks.chosenFactory(currentPage()) : null;
  const actions = thenSummary();
  const qubits = checks.qubitPhrase(currentPage());
  const total = checks.formatSetting(currentPage(), "total");
  const modelPhrase = model
    ? [el("strong", {}, model.title), " model", ...termSummary()]
    : [el("strong", {}, "added operators")];
  return el(
    "p",
    { className: "summary" },
    "Start from ",
    el("strong", {}, initial.title),
    ", evolve the ",
    ...modelPhrase,
    " with ",
    ...simulatorSummary(),
    ", measure ",
    el("strong", {}, measurePhrase()),
    ", then ",
    ...actions,
    qubits ? ", on " : "",
    qubits ? el("strong", {}, qubits) : "",
    total ? " for a total time of " : "",
    total ? el("strong", {}, total) : "",
    ".",
  );
}

function downloadBoard() {
  if (state.running || !accepted()) return;
  const blob = new Blob([state.acceptedBody], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: "shadowsim-board.json" });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function importBoardFile(file) {
  if (state.running || !file || typeof file.text !== "function") return;
  let raw = "";
  try {
    raw = await file.text();
  } catch {
    holdImportStatus("The selection was rejected.");
    return;
  }
  await importBoardText(raw);
}

function importBoardButton() {
  const file = el("input", {
    className: "board-file-input",
    type: "file",
    accept: "application/json,.json",
    hidden: true,
    "aria-label": "Board file",
    onchange: (event) => {
      const input = event.target;
      const chosen = input.files?.[0];
      input.value = "";
      if (chosen) void importBoardFile(chosen);
    },
  });
  return el(
    "span",
    { className: "board-import" },
    file,
    el(
      "button",
      {
        className: "board-file import-board",
        type: "button",
        disabled: state.running,
        onclick: () => file.click(),
      },
      "Import board",
    ),
  );
}

function settingsComponent() {
  const field = (key, label, inputMode) =>
    el(
      "label",
      { className: "setting" },
      label,
      el("input", {
        type: "text",
        inputmode: inputMode,
        value: state.settings[key],
        "aria-label": label,
        readonly:
          key === "qubits" &&
          (checks.stateOwnsQubits(currentPage()) || checks.factorySetsQubits(currentPage())),
        oninput: (event) => {
          if (
            key === "qubits" &&
            (checks.stateOwnsQubits(currentPage()) || checks.factorySetsQubits(currentPage()))
          )
            return;
          update(() => {
            state.settings[key] = event.target.value.trim();
            if (key !== "qubits") return;
            state.qubitsSource = state.settings.qubits === "" ? null : "user";
            if (checks.qubitCount(currentPage()) == null) state.measureOpen = false;
            deriveHamiltonianQubits();
          });
        },
      }),
    );
  return el(
    "div",
    { className: "settings" },
    el(
      "div",
      { className: "settings-fields" },
      el("h2", {}, "Settings"),
      field("qubits", "Qubits", "numeric"),
      field("total", "Total time", "decimal"),
    ),
    el(
      "div",
      { className: "settings-actions" },
      el(
        "button",
        {
          className: "board-file export-board",
          type: "button",
          disabled: state.running || !accepted(),
          onclick: () => downloadBoard(),
        },
        "Export board",
      ),
      importBoardButton(),
      el(
        "button",
        {
          className: "clear",
          type: "button",
          disabled: state.running,
          onclick: () => emptyBoard(),
        },
        "Clear",
      ),
      el(
        "button",
        {
          className: "run",
          type: "button",
          disabled: !state.running && !runAllowed(),
          onclick: () => void (state.running ? cancelRun() : startRun()),
        },
        state.running ? "Cancel" : "Run simulation",
      ),
    ),
  );
}

function releaseStatusHold() {
  state.statusHold = null;
}

function documentBody() {
  return JSON.stringify(runRequest());
}

function cancelScheduledCheck() {
  if (state.checkTimer != null) clearTimeout(state.checkTimer);
  state.checkTimer = null;
}

function dropAcceptance() {
  state.acceptedBody = null;
  state.acceptedQubits = null;
  state.rejectedBody = null;
  state.checkError = null;
  state.checkInFlight = false;
  state.pendingBody = null;
}

function scheduleCheck() {
  if (state.limits == null) return;
  if (state.pendingWrite != null && state.pendingWrite !== documentBody()) {
    state.pendingWrite = null;
  }
  if (!checks.runAllowed(currentPage())) {
    cancelScheduledCheck();
    state.checkSerial += 1;
    dropAcceptance();
    return;
  }
  const requested = documentBody();
  if (state.acceptedBody === requested && state.checkError == null) {
    cancelScheduledCheck();
    state.pendingBody = null;
    maybeStartWrite();
    return;
  }
  if (state.checkError != null && state.rejectedBody === requested) {
    cancelScheduledCheck();
    state.pendingBody = null;
    return;
  }
  if (state.pendingBody === requested) return;
  cancelScheduledCheck();
  state.checkSerial += 1;
  const serial = state.checkSerial;
  state.pendingBody = requested;
  state.acceptedBody = null;
  state.acceptedQubits = null;
  state.rejectedBody = null;
  state.checkError = null;
  state.checkInFlight = false;
  if (typeof fetch !== "function" || typeof setTimeout !== "function") {
    state.pendingBody = null;
    return;
  }
  state.checkTimer = setTimeout(() => {
    state.checkTimer = null;
    void postCheck(requested, serial);
  }, CHECK_DELAY);
}

function applyAcceptedQubits() {
  if (!checks.factorySetsQubits(currentPage()) || state.acceptedQubits == null) return;
  state.settings.qubits = String(state.acceptedQubits);
  state.qubitsSource = "model";
}

async function requestCheck(body) {
  const response = await fetch("/runs/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok || !Number.isInteger(payload.qubits) || payload.qubits < 1) {
    const error =
      typeof payload.error === "string" && payload.error
        ? payload.error
        : "The selection was rejected.";
    return { ok: false, error };
  }
  return { ok: true, qubits: payload.qubits, measurements: readModelMeasurements(payload) };
}

async function postCheck(requested, serial) {
  if (serial !== state.checkSerial || requested !== documentBody()) return;
  let refreshMeasure = false;
  update(
    () => {
      state.checkInFlight = true;
    },
    { checking: true },
  );
  try {
    const result = await requestCheck(requested);
    if (serial !== state.checkSerial || requested !== documentBody()) return;
    if (!result.ok) {
      state.checkError = result.error;
      state.rejectedBody = requested;
      state.acceptedBody = null;
      state.acceptedQubits = null;
      return;
    }
    state.acceptedQubits = result.qubits;
    applyAcceptedQubits();
    if (state.selection.model === "preexisting") {
      state.modelMeasurements = result.measurements ?? [];
      installFactoryMeasure();
      refreshMeasure = true;
    }
    if (documentBody() !== requested) {
      state.acceptedQubits = null;
      return;
    }
    state.checkError = null;
    state.rejectedBody = null;
    state.acceptedBody = requested;
  } catch {
    if (serial !== state.checkSerial || requested !== documentBody()) return;
    state.checkError = "The selection could not be checked.";
    state.rejectedBody = requested;
    state.acceptedBody = null;
    state.acceptedQubits = null;
  } finally {
    if (serial === state.checkSerial) {
      update(
        () => {
          state.checkInFlight = false;
          state.pendingBody = null;
        },
        refreshMeasure ? { lanes: ["measure"], palettes: ["measure"] } : {},
      );
      maybeStartWrite();
    }
  }
}

// biome-ignore lint/correctness/noUnusedVariables: the page tests call this
function applyCheck(qubits) {
  if (!checks.runAllowed(currentPage())) return false;
  update(() => {
    cancelScheduledCheck();
    state.checkSerial += 1;
    state.checkError = null;
    state.rejectedBody = null;
    state.checkInFlight = false;
    state.pendingBody = null;
    state.acceptedQubits = qubits == null ? null : Number(qubits);
    applyAcceptedQubits();
    state.acceptedBody = documentBody();
  });
  maybeStartWrite();
  return true;
}

function findChip({ chip, key, block } = {}) {
  if (!chip) return null;
  const nodes = [...document.querySelectorAll(chip)];
  if (key != null) {
    return nodes.find((node) => node.dataset.key === String(key)) ?? null;
  }
  if (block != null) {
    return nodes.find((node) => node.dataset.block === String(block)) ?? null;
  }
  return nodes[0] ?? null;
}

function firstField(chip) {
  return chip?.querySelector("input, select, textarea") ?? null;
}

function headerButton(chip) {
  return chip?.querySelector(".chip-head > button") ?? null;
}

function slotHeading(laneId) {
  return document.querySelector(`.slot[data-slot="${laneId}"] > h2`);
}

function slotItems(laneId) {
  const slot = document.querySelector(`.slot[data-slot="${laneId}"]`);
  if (!slot) return [];
  if (laneId === "simulator") {
    return [...slot.querySelectorAll(":scope > .method-row > .chip.simulator")];
  }
  return [...slot.querySelectorAll(":scope > .chip")];
}

function applyFocusHint(hint) {
  if (!hint) return;
  let target = null;
  if (hint.kind === "first-field") target = firstField(findChip(hint));
  else if (hint.kind === "header") target = headerButton(findChip(hint));
  else if (hint.kind === "chip") target = findChip(hint);
  else if (hint.kind === "after-remove") {
    const items = slotItems(hint.slot);
    target = items[hint.index] ?? slotHeading(hint.slot);
  }
  target?.focus?.();
}

function update(mutate, scope = {}) {
  if (typeof mutate === "function") mutate(state);
  if (scope.deriveState) deriveStateQubits();
  render(scope);
}

function render(scope = {}) {
  if (scope.board) {
    const board = scope.root ?? document.querySelector(".board");
    if (board) draw(board);
    applyFocusHint(scope.focus);
    return;
  }
  for (const laneId of scope.lanes ?? []) renderLane(laneId);
  for (const laneId of scope.palettes ?? []) renderPalette(laneId);
  if (scope.chrome !== false) renderChrome(scope);
  applyFocusHint(scope.focus);
}

function renderLane(laneId) {
  const current = document.querySelector(`.slot[data-slot="${laneId}"]`);
  const lane = laneById(laneId);
  if (current && lane) current.replaceWith(slotComponent(lane));
}

function renderPalette(laneId) {
  const current = document.querySelector(`.lane[data-palette="${laneId}"]`);
  const lane = laneById(laneId);
  if (!current || !lane) return;
  current.replaceWith(paletteComponent(lane, (blockId) => place(lane.id, blockId)));
}

function renderChrome(scope) {
  if (scope.statusOnly) {
    setStatus(statusMessage(), !state.statusHold && runAllowed());
    return;
  }
  if (scope.checking) {
    paintChecking();
    return;
  }
  scheduleCheck();
  deriveModelQubits();
  paintDerived();
  const summary = document.querySelector(".summary");
  if (summary) summary.replaceWith(summaryComponent());
  if (!state.running) {
    releaseStatusHold();
    setStatus(statusMessage(), runAllowed());
  }
  paintPreview();
  paintButtons();
  rememberBoard();
  if (scope.clearResults) clearResults();
  else clearStaleResults();
}

function paintChecking() {
  if (state.running) return;
  setStatus(statusMessage(), !state.statusHold && runAllowed());
  paintPreview();
  paintButtons();
}

function paintPreview() {
  const panel = document.querySelector('.panel[aria-label="Code preview"]');
  const body = panel?.querySelector("pre.script, p.placeholder");
  if (body) body.replaceWith(codeBody());
  const json = panel?.querySelector("pre.board-json");
  if (!json) return;
  const text = boardFileText();
  json.textContent = text;
  json.replaceChildren(document.createTextNode(text));
}

function paintButtons() {
  setButtonDisabled(document.querySelector(".export-board"), state.running || !accepted());
  setButtonDisabled(document.querySelector(".import-board"), state.running);
  const copy = document.querySelector('.panel[aria-label="Code preview"] .copy');
  if (copy) {
    const enabled = Boolean(previewText());
    copy.disabled = !enabled;
    if (enabled) copy.removeAttribute("disabled");
    else {
      copy.setAttribute("disabled", "");
      copy.textContent = "Copy";
    }
  }
  const run = document.querySelector(".run");
  if (run && !state.running) run.disabled = !runAllowed();
}

function paintQubitField() {
  const qubitsInput = document.querySelector('input[aria-label="Qubits"]');
  if (!qubitsInput) return;
  qubitsInput.readOnly =
    checks.stateOwnsQubits(currentPage()) || checks.factorySetsQubits(currentPage());
  if (qubitsInput.value !== state.settings.qubits) qubitsInput.value = state.settings.qubits;
}

function paintPathDetails() {
  for (const id of state.placedThens) {
    const block = checks.blockById(currentPage(), "then", id);
    if (block?.field?.kind !== "path") continue;
    const chip = document.querySelector(`.chip.path.${id}`);
    const detail = chip?.querySelector(".chip-head span");
    if (!detail) continue;
    const shown = pathValue(id).trim();
    detail.textContent = shown || block.detail;
  }
}

function paintBackendDetails() {
  const rows = document.querySelectorAll(".method-row");
  state.placedSims.forEach((entry, index) => {
    const detail = rows[index]?.querySelector(".backend-detail");
    if (!detail || !entry.backend) return;
    const block = checks.blockById(currentPage(), "backend", entry.backend);
    if (block) detail.textContent = backendSummary(block, entry);
  });
  paintBackendFields();
}

function paintBackendFields() {
  document.querySelectorAll(".chip.backend").forEach((chip) => {
    const entry = state.placedSims.find((item) => String(item.key) === chip.dataset.key);
    if (!entry?.backend) return;
    const block = checks.blockById(currentPage(), "backend", entry.backend);
    if (!block) return;
    if (block.shots) {
      const field = chip.querySelector('input[aria-label="Shots"]');
      const host = field?.closest("label");
      const errorId = `shots-error-${entry.key}`;
      const message = checks.shotsFieldProblem(currentPage(), entry.shots, state.maxShots);
      syncFieldError(host, errorId, message);
      setFieldValidity(field, errorId, message);
    }
    for (const spec of block.fields ?? []) {
      const field = chip.querySelector(`input[aria-label="${spec.label}"]`);
      const host = field?.closest("label");
      const errorId = `backend-error-${entry.key}-${spec.name}`;
      const text = entry.backendFields?.[spec.name];
      const message =
        spec.kind === "gates"
          ? checks.gateFieldProblem(currentPage(), spec, text)
          : checks.backendNumberProblem(currentPage(), spec, text);
      syncFieldError(host, errorId, message);
      setFieldValidity(field, errorId, message);
    }
  });
}

function paintMeasureChip() {
  const chip = document.querySelector(".chip.measure");
  if (!chip) return;
  const count = checks.qubitCount(currentPage());
  const detail = chip.querySelector(".measure-detail");
  if (detail) detail.textContent = measureDetail(count);
  if (count == null) {
    chip.classList.remove("is-editing");
    chip.querySelector(".done")?.remove();
    chip.querySelector(".qubit-picker")?.remove();
    chip.querySelector(".chip-field")?.remove();
    return;
  }
  if (!state.measureOpen) return;
  const fields = chip.querySelector(".qubit-picker");
  const next = measureFields();
  if (fields) fields.replaceWith(next);
  else chip.append(next);
  if (
    checks.blockById(currentPage(), "measure", state.selection.measure)?.field?.kind !==
    "expression"
  )
    return;
  const hint = chip.querySelector(".counts-hint");
  if (hint) hint.textContent = countsHint();
  else chip.append(countsField());
  const input = chip.querySelector(".chip-field input");
  if (input) input.placeholder = countsPlaceholder();
}

function paintSimFields() {
  document.querySelectorAll(".chip.simulator").forEach((chip) => {
    const entry = state.placedSims.find((item) => String(item.key) === chip.dataset.key);
    if (!entry) return;
    const block = checks.blockById(currentPage(), "simulator", entry.id);
    const fields = block?.fields ?? [];
    let invalid = false;
    for (const spec of fields) {
      const control = chip.querySelector(
        `input[aria-label="${spec.label}"], select[aria-label="${spec.label}"]`,
      );
      const host = control?.closest("label");
      const errorId = `sim-error-${entry.key}-${spec.name}`;
      const message = simulatorFieldMessage(entry, spec);
      if (message) invalid = true;
      syncFieldError(host, errorId, message);
      setFieldValidity(control, errorId, message);
    }
    setChipAlert(chip.querySelector(".chip-alert"), invalid);
  });
}

function paintDerived() {
  paintFactoryLocks();
  paintFactoryDetail();
  paintModelAlert();
  paintStateChip();
  paintHamiltonianChips();
  paintLocalHamiltonianChips();
  paintSimFields();
  paintBackendDetails();
  paintPathDetails();
  paintMeasureChip();
  paintQubitField();
}

function statusMessage() {
  if (state.statusHold) return state.statusHold;
  if (state.limits == null) return "Loading limits…";
  const problem = checks.firstProblem(currentPage());
  if (problem) return problem.message;
  if (state.checkError) return `${state.checkError.replace(/[.!?]$/, "")}.`;
  if (state.checkInFlight || !accepted()) return "Checking the selection.";
  return "Ready to run.";
}

function statusComponent() {
  const ready = !state.statusHold && runAllowed();
  return el(
    "div",
    { className: ready ? "status ready" : "status" },
    el("p", { className: "status-live", role: "status" }, statusMessage()),
    el("span", { className: "status-clock", hidden: true, "aria-hidden": "true" }),
  );
}

function clearUndoToast() {
  if (!state.clearUndo) return null;
  return el(
    "div",
    { className: "clear-undo", role: "status" },
    el("span", {}, "Board cleared."),
    el(
      "button",
      {
        className: "undo-clear",
        type: "button",
        onclick: () => undoClear(),
      },
      "Undo",
    ),
  );
}

function dismissClearUndo() {
  if (state.clearUndoTimer) clearTimeout(state.clearUndoTimer);
  state.clearUndoTimer = 0;
  state.clearUndo = null;
}

function showClearUndo(snapshot) {
  dismissClearUndo();
  state.clearUndo = snapshot;
  state.clearUndoTimer = setTimeout(() => {
    state.clearUndoTimer = 0;
    state.clearUndo = null;
    const board = document.querySelector(".board");
    if (!board) return;
    const toast = board.querySelector(".clear-undo");
    if (toast) toast.remove();
  }, CLEAR_UNDO_MS);
}

function undoClear() {
  if (state.running || !state.clearUndo) return;
  const snapshot = state.clearUndo;
  dismissClearUndo();
  update(
    () => {
      applyBoard(snapshot);
    },
    { board: true },
  );
}

function showCopied(button, label = "Copy") {
  if (state.copiedButton && state.copiedButton !== button && state.copiedButton.isConnected) {
    state.copiedButton.textContent = state.copiedLabel;
  }
  state.copiedButton = button;
  state.copiedLabel = label;
  button.textContent = "Copied";
  if (state.copyTimer) clearTimeout(state.copyTimer);
  state.copyTimer = setTimeout(() => {
    state.copyTimer = 0;
    if (!button.isConnected) return;
    button.textContent = label;
    if (state.copiedButton === button) state.copiedButton = null;
  }, 1500);
}

function copyPreview(event) {
  const code = previewText();
  if (!code) return;
  const pending = navigator.clipboard?.writeText?.(code);
  if (!pending || typeof pending.then !== "function") return;
  const button = event?.currentTarget;
  pending.then(
    () => {
      if (button) showCopied(button);
    },
    () => {},
  );
}

function copyButton() {
  return el(
    "button",
    {
      className: "copy",
      type: "button",
      disabled: !previewText(),
      onclick: (event) => copyPreview(event),
    },
    "Copy",
  );
}

function boardFileText() {
  if (accepted()) return state.acceptedBody;
  const file = runRequest();
  delete file.server;
  return JSON.stringify(file);
}

function copyBoard(event) {
  const pending = navigator.clipboard?.writeText?.(boardFileText());
  if (!pending || typeof pending.then !== "function") return;
  const button = event?.currentTarget;
  pending.then(
    () => {
      if (button) showCopied(button, "Copy board");
    },
    () => {},
  );
}

function copyBoardButton() {
  return el(
    "button",
    {
      className: "copy-board",
      type: "button",
      "aria-label": "Copy board",
      onclick: (event) => copyBoard(event),
    },
    "Copy board",
  );
}

function codeBody() {
  const code = previewText();
  if (code) return el("pre", { className: "script" }, code);
  const problem = checks.firstProblem(currentPage());
  if (problem) return el("p", { className: "placeholder" }, problem.previewMessage);
  const message = state.checkError
    ? `${state.checkError.replace(/[.!?]$/, "")} to preview the script.`
    : "Checking the selection.";
  return el("p", { className: "placeholder" }, message);
}

function setStatus(message, ready) {
  const status = document.querySelector(".status");
  if (!status) return;
  status.className = ready ? "status ready" : "status";
  const live = status.querySelector(".status-live");
  if (live) live.textContent = message;
}

function setResults(node) {
  const panel = document.querySelector('.panel[aria-label="Results"]');
  const body = panel?.querySelector(":scope > .placeholder, :scope > .chart, :scope > .results");
  if (body) body.replaceWith(node);
}

function resultsPlaceholder() {
  return el("p", { className: "placeholder" }, "Run a simulation to see results here.");
}

function clearResults() {
  state.shownRun = null;
  state.shownPayload = null;
  state.writtenActions = null;
  state.pendingWrite = null;
  state.writeSerial += 1;
  setResults(resultsPlaceholder());
}

function resultsBody() {
  const panel = document.querySelector('.panel[aria-label="Results"]');
  return panel?.querySelector(":scope > .placeholder, :scope > .chart, :scope > .results") ?? null;
}

function staleBanner() {
  return el("p", { className: "stale" }, "Out of date. Run again to refresh.");
}

function markResultsStale() {
  const body = resultsBody();
  if (!body || body.classList.contains("placeholder")) return;
  if (!body.classList.contains("results")) {
    const wrap = el("div", { className: "results stale" });
    body.replaceWith(wrap);
    wrap.append(staleBanner(), body);
    return;
  }
  body.classList.add("stale");
  if (!body.querySelector(":scope > .stale")) body.prepend(staleBanner());
}

function markResultsCurrent() {
  const body = resultsBody();
  if (!body?.classList.contains("results")) return;
  body.classList.remove("stale");
  body.querySelector(":scope > .stale")?.remove();
}

function clearStaleResults() {
  if (state.shownRun == null) return;
  if (state.shownRun === shownRunKey()) {
    markResultsCurrent();
    return;
  }
  markResultsStale();
}

function requestedWritePaths(selection = runRequest()) {
  const actions = selection.actions || {};
  const ids = Array.isArray(actions.ids) ? actions.ids : [];
  const paths = {};
  if (ids.includes("save")) paths.save_path = String(actions.save_path ?? "").trim();
  if (ids.includes("export")) paths.export_path = String(actions.export_path ?? "").trim();
  return paths;
}

function rememberWrittenActions(selection) {
  state.writtenActions = requestedWritePaths(selection);
}

function writeAlreadyDone(selection = runRequest()) {
  const paths = requestedWritePaths(selection);
  const keys = Object.keys(paths);
  if (!keys.length) return true;
  const written = state.writtenActions;
  if (!written) return false;
  return keys.every((key) => written[key] === paths[key]);
}

function paintWriteNote(payload) {
  if (!state.shownPayload) state.shownPayload = {};
  if (Object.hasOwn(payload, "saved")) state.shownPayload.saved = payload.saved;
  if (Object.hasOwn(payload, "exported")) state.shownPayload.exported = payload.exported;
  const panel = document.querySelector('.panel[aria-label="Results"]');
  const body = panel?.querySelector(":scope > .placeholder, :scope > .chart, :scope > .results");
  if (!body || body.classList.contains("placeholder")) return;
  const note = savedNote(state.shownPayload);
  if (body.classList.contains("results")) {
    const existing = body.querySelector(":scope > .hint");
    if (note && existing) existing.replaceWith(note);
    else if (note && !existing) body.prepend(note);
    else if (!note && existing) existing.remove();
    return;
  }
  if (!note) return;
  const wrap = el("div", { className: "results" });
  body.replaceWith(wrap);
  wrap.append(note, body);
}

function queueWrite() {
  if (state.running) return;
  if (typeof fetch !== "function") return;
  if (state.shownRun == null || state.shownRun !== shownRunKey()) return;
  const selection = runRequest();
  if (writeAlreadyDone(selection)) return;
  state.pendingWrite = JSON.stringify(selection);
  maybeStartWrite();
}

function maybeStartWrite() {
  if (state.pendingWrite == null || state.writeInFlight || state.running) return;
  if (typeof fetch !== "function") return;
  if (!accepted() || state.acceptedBody !== state.pendingWrite) return;
  if (state.shownRun == null || state.shownRun !== shownRunKey()) {
    state.pendingWrite = null;
    return;
  }
  const requested = state.pendingWrite;
  state.pendingWrite = null;
  void postWrite(requested);
}

async function postWrite(requested) {
  const serial = ++state.writeSerial;
  state.writeInFlight = true;
  try {
    const response = await fetch("/runs/write", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: requested,
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (serial !== state.writeSerial) return;
    if (documentBody() !== requested || state.shownRun !== shownRunKey(JSON.parse(requested))) {
      return;
    }
    if (!response.ok) {
      const message =
        typeof payload.error === "string" && payload.error ? payload.error : "The write failed.";
      state.statusHold = message.endsWith(".") ? message : `${message}.`;
      setStatus(state.statusHold);
      return;
    }
    rememberWrittenActions(JSON.parse(requested));
    paintWriteNote(payload);
    releaseStatusHold();
    setStatus(statusMessage(), runAllowed());
  } catch {
    if (serial !== state.writeSerial || documentBody() !== requested) return;
    state.statusHold = "The write failed.";
    setStatus(state.statusHold);
  } finally {
    if (serial === state.writeSerial) state.writeInFlight = false;
    maybeStartWrite();
  }
}

function clockLabel(elapsedMs) {
  const total = Math.max(0, Math.floor(elapsedMs / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function runningLabel(elapsedMs) {
  return `Running · ${clockLabel(elapsedMs)}`;
}

function finishedLabel(elapsedMs) {
  return `Finished · ${clockLabel(elapsedMs)}. Results below are from this run.`;
}

function showRunningClock() {
  if (!state.running) return;
  const status = document.querySelector(".status");
  if (!status) return;
  status.className = "status running";
  const clock = status.querySelector(".status-clock");
  if (!clock) return;
  clock.hidden = false;
  clock.textContent = runningLabel(Date.now() - state.runStartedAt);
}

function hideRunningClock() {
  const status = document.querySelector(".status");
  if (!status) return;
  status.classList.remove("running");
  const clock = status.querySelector(".status-clock");
  if (!clock) return;
  clock.hidden = true;
  clock.textContent = "";
}

function stopRunClock() {
  if (state.runTimer == null) return;
  clearInterval(state.runTimer);
  state.runTimer = null;
}

function setButtonDisabled(button, disabled) {
  if (!button) return;
  button.disabled = disabled;
  if (disabled) {
    button.setAttribute("disabled", "");
    return;
  }
  button.removeAttribute("disabled");
}

function setRunButton(label) {
  const button = document.querySelector(".run");
  if (!button) return;
  button.textContent = label;
  button.disabled = label !== "Cancel" && !runAllowed();
  const clear = document.querySelector(".clear");
  if (clear) clear.disabled = label === "Cancel";
  paintButtons();
}

async function cancelRun() {
  if (!state.running) return;
  try {
    await fetch("/runs/cancel", { method: "POST" });
  } catch {
    // The run request stays open and reports the outcome.
  }
}

function stateValue() {
  const read = checks.readState(currentPage());
  if (!read) return null;
  return read.field.kind === "bits" ? read.text : read.values;
}

function modelMeasureBlock() {
  const labels = state.modelMeasurements
    .map((item) => item.label)
    .filter((label) => typeof label === "string" && label);
  const detail = labels.length ? labels.join("; ") : "The model's measurements";
  return {
    id: "model",
    title: "Model measurements",
    detail,
    phrase: detail,
    kind: "model",
  };
}

function rememberCatalogMeasures() {
  if (state.blocks.measure.some((block) => block.kind === "model")) return;
  state.catalogMeasures = state.blocks.measure.slice();
}

function installFactoryMeasure() {
  rememberCatalogMeasures();
  state.blocks.measure = [modelMeasureBlock()];
}

function installCatalogMeasure() {
  if (state.catalogMeasures.length) state.blocks.measure = state.catalogMeasures.slice();
  state.modelMeasurements = [];
}

function useFactoryMeasure() {
  state.modelMeasurements = [];
  installFactoryMeasure();
  state.selection.measure = "model";
  state.measureOpen = false;
  state.measureSites = null;
}

function readModelMeasurements(payload) {
  if (!Array.isArray(payload?.measurements)) return [];
  return payload.measurements.filter(
    (item) => item && typeof item.label === "string" && Array.isArray(item.qubits),
  );
}

function postedBoard(saved) {
  if (!plainObject(saved)) return saved;
  const model = saved.model;
  const measure = saved.measure;
  if (!plainObject(model) || !plainObject(measure)) return saved;
  if (Array.isArray(model.terms) && model.terms.length) return saved;
  if (typeof model.id !== "string" || !model.id) return saved;
  if (measure.id === "model") return saved;
  return { ...saved, measure: { id: "model" } };
}

function postedMeasure() {
  if (state.selection.measure === "model") return { id: "model" };
  const measure = { id: state.selection.measure, sites: explicitSites() };
  const field = checks.blockById(currentPage(), "measure", state.selection.measure)?.field;
  if (field?.kind === "expression")
    measure.expression = (state.expressionText[state.selection.measure] ?? "").trim();
  return measure;
}

function postedActions() {
  const actions = { ids: [...state.placedThens] };
  for (const block of state.blocks.then) {
    if (block.field?.kind !== "path") continue;
    actions[block.field.key] = pathValue(block.id).trim();
  }
  return actions;
}

function modelArguments() {
  if (state.selection.model !== "preexisting") return {};
  const body = { ...(postedFactory() ?? {}) };
  if (checks.chosenFactory(currentPage())?.qubits) body.n_qubits = state.settings.qubits;
  return body;
}

function postedModel() {
  const terms = checks.postedTerms(currentPage());
  if (Array.isArray(terms) && terms.length) return { terms, qubits: state.settings.qubits };
  return {
    id: state.selection.model === "preexisting" ? state.preexistingId : state.selection.model,
    arguments: modelArguments(),
  };
}

function runRequest() {
  return {
    version: 1,
    total: state.settings.total,
    state: { id: state.selection.state, value: stateValue() },
    model: postedModel(),
    simulators: state.placedSims.map((entry) => checks.entryBody(currentPage(), entry)),
    measure: postedMeasure(),
    actions: postedActions(),
  };
}

function boardSnapshot() {
  return JSON.parse(JSON.stringify(runRequest()));
}

function shownRunKey(document = runRequest()) {
  const { actions: _actions, ...simulation } = document;
  return JSON.stringify(simulation);
}

function showRunResult(identity, node, payload = null) {
  if (shownRunKey() !== identity) {
    clearResults();
    return false;
  }
  state.shownRun = identity;
  state.shownPayload = payload;
  setResults(node);
  return true;
}

async function startRun() {
  if (state.running || !runAllowed()) return;
  state.running = true;
  releaseStatusHold();
  state.runStartedAt = Date.now();
  setRunButton("Cancel");
  setStatus("Running.");
  showRunningClock();
  state.runTimer = setInterval(showRunningClock, 1000);
  const selection = runRequest();
  const requested = JSON.stringify(selection);
  const identity = shownRunKey(selection);
  state.shownRun = identity;
  state.shownPayload = null;
  state.writtenActions = null;
  state.pendingWrite = null;
  state.writeSerial += 1;
  setResults(el("p", { className: "placeholder" }, "Running."));
  try {
    const response = await fetch("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: requested,
    });
    const payload = await response.json();
    const elapsedMs = Date.now() - state.runStartedAt;
    if (payload.cancelled) {
      if (showRunResult(identity, el("p", { className: "placeholder" }, "Cancelled."))) {
        state.statusHold = "Cancelled.";
      }
      return;
    }
    if (!response.ok) {
      const message = payload.error || "The run failed.";
      if (showRunResult(identity, el("p", { className: "placeholder" }, message)))
        state.statusHold = message;
      return;
    }
    if (showRunResult(identity, resultsComponent(payload), payload)) {
      rememberWrittenActions(selection);
      state.statusHold = finishedLabel(elapsedMs);
    }
  } catch {
    if (showRunResult(identity, el("p", { className: "placeholder" }, "The run failed."))) {
      state.statusHold = "The run failed.";
    }
  } finally {
    stopRunClock();
    hideRunningClock();
    state.running = false;
    setRunButton("Run simulation");
    if (state.statusHold) setStatus(state.statusHold);
    else setStatus(statusMessage(), runAllowed());
  }
}

function panelsComponent() {
  return el(
    "div",
    { className: "panels" },
    el(
      "section",
      { className: "panel", "aria-label": "Code preview" },
      el(
        "div",
        { className: "panel-head" },
        el("h2", {}, "Code preview"),
        el("div", { className: "panel-actions" }, copyButton(), copyBoardButton()),
      ),
      codeBody(),
      el("pre", { className: "board-json" }, boardFileText()),
    ),
    el(
      "section",
      { className: "panel", "aria-label": "Results" },
      el("h2", {}, "Results"),
      resultsPlaceholder(),
    ),
  );
}

function layoutComponent() {
  const layout = el("div", { className: "layout" });
  LANES.forEach((lane, index) => {
    const slot = slotComponent(lane);
    const palette = paletteComponent(lane, (blockId) => place(lane.id, blockId));
    layout.append(slot, palette);
    if (index === LANES.length - 1) return;
    const chevron = el("div", { className: "chevron", "aria-hidden": "true" }, ">");
    chevron.style.gridColumn = String(2 + index * 2);
    chevron.style.gridRow = "1";
    layout.append(chevron);
  });
  return layout;
}

function draw(board) {
  state.shownRun = null;
  state.shownPayload = null;
  state.writtenActions = null;
  state.pendingWrite = null;
  state.writeSerial += 1;
  board.replaceChildren(
    ...[
      layoutComponent(),
      settingsComponent(),
      summaryComponent(),
      statusComponent(),
      clearUndoToast(),
      panelsComponent(),
    ].filter(Boolean),
  );
  rememberBoard();
  scheduleCheck();
}

function termSummary() {
  const nodes = [];
  state.modelTerms.forEach((term, index) => {
    const block = checks.blockById(currentPage(), "model", term.id);
    if (!block) return;
    nodes.push(index === 0 ? ", plus " : ", ");
    nodes.push(el("strong", {}, block.title));
  });
  return nodes;
}

function measureDetail(count) {
  const block = checks.blockById(currentPage(), "measure", state.selection.measure);
  if (block?.kind === "model") return block.detail ?? "";
  if (count == null) return block?.detail ?? "";
  const sites = checks.selectedSites(currentPage(), count);
  if (!sites.length) return "No qubits";
  if (sites.length === count) return block?.detail ?? "";
  return `Qubits ${sites.join(", ")}`;
}

function measurePhrase() {
  const block = checks.blockById(currentPage(), "measure", state.selection.measure);
  if (!block) return "";
  if (block.kind === "model") return block.phrase ?? "";
  const count = checks.qubitCount(currentPage());
  const sites = checks.selectedSites(currentPage(), count);
  if (count == null || sites.length === count) return block.phrase;
  if (!sites.length) return `${block.title} on no qubits`;
  return `${block.title} on qubits ${sites.join(", ")}`;
}

function explicitSites() {
  const count = checks.qubitCount(currentPage());
  if (state.measureSites == null || count == null) return null;
  const sites = checks.selectedSites(currentPage(), count);
  return sites.length === count ? null : sites;
}

function toggleMeasureSite(site, checked) {
  const count = checks.qubitCount(currentPage());
  if (count == null) return;
  const next = checks.selectedSites(currentPage(), count).filter((index) => index !== site);
  if (checked) next.push(site);
  next.sort((left, right) => left - right);
  state.measureSites = next.length === count ? null : next;
}

function measureFields() {
  const count = checks.qubitCount(currentPage());
  const chosen = new Set(checks.selectedSites(currentPage(), count));
  const boxes = [];
  for (let site = 0; site < count; site += 1) {
    boxes.push(
      el(
        "label",
        { className: "qubit" },
        el("input", {
          type: "checkbox",
          "aria-label": `Qubit ${site}`,
          checked: chosen.has(site),
          onchange: (event) => {
            update(() => {
              toggleMeasureSite(site, event.target.checked);
            });
          },
        }),
        String(site),
      ),
    );
  }
  return el("div", { className: "qubit-picker" }, ...boxes);
}

function countsHint() {
  const sites = checks.selectedSites(currentPage(), checks.qubitCount(currentPage()));
  if (!sites.length) return "Pick at least one qubit.";
  const label = sites.length === 1 ? "qubit" : "qubits";
  return `Keys list ${label} ${sites.join(", ")} in that order. shots is the total.`;
}

function countsPlaceholder() {
  const width = Math.max(
    checks.selectedSites(currentPage(), checks.qubitCount(currentPage())).length,
    1,
  );
  return `counts["${"0".repeat(width)}"] / shots`;
}

function countsField() {
  return el(
    "label",
    { className: "chip-field" },
    "Expression",
    el("input", {
      type: "text",
      "aria-label": "Counts expression",
      value: state.expressionText[state.selection.measure] ?? "",
      placeholder: countsPlaceholder(),
      spellcheck: "false",
      oninput: (event) => {
        update(() => {
          state.expressionText[state.selection.measure] = event.target.value;
        });
      },
    }),
    el("span", { className: "counts-hint" }, countsHint()),
  );
}

function measureChip(block) {
  if (block.kind === "model") {
    return el(
      "div",
      { className: "chip tone-green measure", tabindex: "-1" },
      el(
        "div",
        { className: "chip-head" },
        el("strong", {}, block.title),
        el("span", { className: "measure-detail" }, block.detail ?? ""),
        el(
          "div",
          { className: "chip-actions" },
          el(
            "button",
            {
              className: "remove",
              type: "button",
              "aria-label": `Remove ${block.title}`,
              onclick: (event) => {
                event.stopPropagation();
                clearLane("measure");
              },
            },
            "×",
          ),
        ),
      ),
    );
  }
  const count = checks.qubitCount(currentPage());
  const open = state.measureOpen && count != null;
  return el(
    "div",
    {
      className: `chip tone-green measure${open ? " is-editing" : ""}`,
      tabindex: "-1",
    },
    el(
      "div",
      { className: "chip-head" },
      el(
        "button",
        {
          type: "button",
          onclick: () => {
            if (open || checks.qubitCount(currentPage()) == null) return;
            update(
              () => {
                state.measureOpen = true;
              },
              {
                lanes: ["measure"],
                chrome: false,
                focus: { kind: "first-field", chip: ".chip.measure" },
              },
            );
          },
        },
        el("strong", {}, block.title),
        el("span", { className: "measure-detail" }, measureDetail(count)),
      ),
      el(
        "div",
        { className: "chip-actions" },
        open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: () => {
                  update(
                    () => {
                      state.measureOpen = false;
                    },
                    {
                      lanes: ["measure"],
                      chrome: false,
                      focus: { kind: "header", chip: ".chip.measure" },
                    },
                  );
                },
              },
              "Done",
            )
          : null,
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${block.title}`,
            onclick: (event) => {
              event.stopPropagation();
              clearLane("measure");
            },
          },
          "×",
        ),
      ),
    ),
    open ? measureFields() : null,
    open && block.field?.kind === "expression" ? countsField() : null,
  );
}

function thenSummary() {
  const phrases = state.placedThens
    .map((id) => checks.blockById(currentPage(), "then", id)?.phrase)
    .filter(Boolean);
  const nodes = [];
  phrases.forEach((phrase, index) => {
    if (index) nodes.push(index === phrases.length - 1 ? " and " : ", ");
    nodes.push(el("strong", {}, phrase));
  });
  return nodes;
}

function methodPhrase(entry) {
  const title = checks.blockById(currentPage(), "simulator", entry.id)?.title;
  if (!title) return null;
  const backend = checks.blockById(currentPage(), "backend", entry.backend);
  if (!checks.isReference(currentPage(), entry) && backend) return `${title} on ${backend.phrase}`;
  return title;
}

function simulatorSummary() {
  const titles = state.placedSims.map(methodPhrase).filter(Boolean);
  if (!titles.length) return [];
  if (titles.length === 1) return [el("strong", {}, titles[0])];
  const nodes = [el("strong", {}, titles[0]), ", benchmarked against "];
  titles.slice(1).forEach((title, index, list) => {
    if (index) nodes.push(index === list.length - 1 ? " and " : ", ");
    nodes.push(el("strong", {}, title));
  });
  return nodes;
}

function laneById(laneId) {
  return LANES.find((lane) => lane.id === laneId);
}

function placeFocus(laneId, blockId, block) {
  if (laneId === "simulator") {
    const entry = state.placedSims[state.placedSims.length - 1];
    return { kind: "first-field", chip: ".chip.simulator", key: entry.key };
  }
  if (laneId === "model" && block?.adds) {
    const term = state.modelTerms[state.modelTerms.length - 1];
    const chip =
      term.id === "hamiltonian"
        ? ".chip.hamiltonian"
        : term.id === "lindblad"
          ? ".chip.lindblad"
          : ".chip.local-hamiltonian";
    return { kind: "first-field", chip, key: term.key };
  }
  if (laneId === "model" && blockId === "preexisting") {
    return { kind: "first-field", chip: ".chip.preexisting" };
  }
  if (laneId === "state") {
    return { kind: "first-field", chip: `.chip.state.${blockId}` };
  }
  if (laneId === "measure") {
    if (block?.kind === "model") return { kind: "chip", chip: ".chip.measure" };
    if (state.measureOpen) return { kind: "first-field", chip: ".chip.measure" };
    return { kind: "header", chip: ".chip.measure" };
  }
  if (laneId === "then") {
    if (block?.field?.kind === "path") {
      return { kind: "first-field", chip: `.chip.path.${blockId}` };
    }
    return { kind: "chip", chip: ".chip", block: blockId };
  }
  return { kind: "chip", chip: ".chip", block: blockId };
}

function place(laneId, blockId) {
  if (state.running) return;
  const block = checks.blockById(currentPage(), laneId, blockId);
  if (laneId === "model" && modelChoiceBlocked(block)) return;
  if (laneId === "simulator") {
    state.placedSims.push({
      id: blockId,
      key: ++state.simKey,
      params: freshParams(block),
      open: true,
      backend: null,
      shots: DEFAULT_SHOTS,
      shotsOpen: false,
    });
    state.selection.simulator = state.placedSims[0].id;
  } else if (laneId === "model" && block?.adds) {
    state.modelTerms.push({ id: blockId, key: ++state.modelTermKey, matrix: "", sites: [] });
  } else if (laneId === "model" && blockId === "preexisting") {
    state.selection.model = "preexisting";
    if (!state.preexistingId) state.preexistingId = state.modelFactories[0]?.id ?? null;
    state.preexistingOpen = true;
    useFactoryMeasure();
  } else if (laneId === "state") {
    state.selection.state = blockId;
    state.stateOpen = true;
  } else if (laneId === "measure") {
    state.selection.measure = blockId;
    state.measureOpen = block?.kind !== "model" && checks.qubitCount(currentPage()) != null;
    if (block?.kind === "model") state.measureSites = null;
  } else if (laneId === "then") {
    if (!state.placedThens.includes(blockId)) state.placedThens.push(blockId);
    state.selection.then = state.placedThens[0] ?? null;
    if (block?.field?.kind === "path") state.pathOpen[blockId] = true;
  } else state.selection[laneId] = blockId;
  deriveModelQubits();
  deriveStateQubits();
  state.dragging = null;
  releaseStatusHold();
  const lanes = [laneId];
  const palettes = laneId === "model" ? ["model"] : [];
  if (laneId === "model" && blockId === "preexisting") {
    lanes.push("measure");
    palettes.push("measure");
  }
  update(null, {
    lanes,
    palettes,
    clearResults: laneId !== "then",
    focus: placeFocus(laneId, blockId, block),
  });
  if (laneId === "then" && (blockId === "save" || blockId === "export")) queueWrite();
}

function removeThen(id) {
  if (state.running) return;
  const index = state.placedThens.indexOf(id);
  if (index < 0) return;
  update(
    () => {
      state.placedThens.splice(index, 1);
      state.selection.then = state.placedThens[0] ?? null;
      releaseStatusHold();
    },
    { lanes: ["then"], focus: { kind: "after-remove", slot: "then", index } },
  );
}

function attachBackend(backendId, key) {
  if (state.running) return;
  const backend = checks.blockById(currentPage(), "backend", backendId);
  if (!backend) return;
  const target =
    key == null
      ? state.placedSims.find(
          (entry) =>
            !checks.isReference(currentPage(), entry) &&
            !entry.backend &&
            checks.backendFits(currentPage(), entry, backendId),
        )
      : state.placedSims.find((entry) => entry.key === key);
  if (
    !target ||
    checks.isReference(currentPage(), target) ||
    !checks.backendFits(currentPage(), target, backendId)
  ) {
    const open = state.placedSims.filter(
      (entry) =>
        !checks.isReference(currentPage(), entry) &&
        (key == null ? !entry.backend : entry.key === key),
    );
    const blocked = open.find(
      (entry) => checks.blockById(currentPage(), "simulator", entry.id)?.samples && !backend.shots,
    );
    const title = blocked ? checks.blockById(currentPage(), "simulator", blocked.id)?.title : null;
    if (title) state.statusHold = `${title} needs a backend with a shot budget.`;
    else if (!state.placedSims.some((entry) => !checks.isReference(currentPage(), entry)))
      state.statusHold = "Place a simulator before its backend.";
    else state.statusHold = "Snap a backend onto an open simulator.";
    state.dragging = null;
    document.querySelectorAll(".is-over").forEach((node) => {
      node.classList.remove("is-over");
    });
    setStatus(state.statusHold);
    return;
  }
  target.backend = backendId;
  if (backend.fields?.length) {
    target.backendFields = { ...(target.backendFields ?? {}) };
    for (const field of backend.fields) {
      if (!String(target.backendFields[field.name] ?? "").trim())
        target.backendFields[field.name] = field.default;
    }
  }
  if (backend.shots) {
    if (!checks.positiveIntText(currentPage(), String(target.shots ?? "").trim()))
      target.shots = DEFAULT_SHOTS;
    target.shotsOpen = true;
    target.backendOpen = false;
  } else if (backend.fields?.length) {
    target.shotsOpen = false;
    target.backendOpen = true;
  } else {
    target.shotsOpen = false;
    target.backendOpen = false;
  }
  const opens = Boolean(backend.shots || backend.fields?.length);
  update(
    () => {
      state.dragging = null;
      releaseStatusHold();
    },
    {
      lanes: ["simulator"],
      clearResults: true,
      focus: opens
        ? { kind: "first-field", chip: ".chip.backend", key: target.key }
        : { kind: "header", chip: ".chip.backend", key: target.key },
    },
  );
}

function removeBackend(key) {
  if (state.running) return;
  const entry = state.placedSims.find((item) => item.key === key);
  if (!entry) return;
  update(
    () => {
      entry.backend = null;
      entry.shotsOpen = false;
      entry.backendOpen = false;
      releaseStatusHold();
    },
    {
      lanes: ["simulator"],
      clearResults: true,
      focus: { kind: "header", chip: ".chip.simulator", key },
    },
  );
}

function removeSimulator(key) {
  if (state.running) return;
  const index = state.placedSims.findIndex((entry) => entry.key === key);
  if (index < 0) return;
  update(
    () => {
      state.placedSims.splice(index, 1);
      state.selection.simulator = state.placedSims[0]?.id ?? null;
      releaseStatusHold();
    },
    {
      lanes: ["simulator"],
      clearResults: true,
      focus: { kind: "after-remove", slot: "simulator", index },
    },
  );
}

function removeTerm(key) {
  if (state.running) return;
  const index = state.modelTerms.findIndex((term) => term.key === key);
  if (index < 0) return;
  update(
    () => {
      state.modelTerms.splice(index, 1);
      if (
        !state.modelTerms.some((term) => term.id === "hamiltonian") &&
        state.qubitsSource === "hamiltonian"
      ) {
        state.settings.qubits = "";
        state.qubitsSource = null;
        if (checks.qubitCount(currentPage()) == null) state.measureOpen = false;
      } else deriveHamiltonianQubits();
      releaseStatusHold();
    },
    {
      lanes: ["model"],
      palettes: ["model"],
      clearResults: true,
      focus: { kind: "after-remove", slot: "model", index },
    },
  );
}

function clearLane(laneId) {
  if (state.running) return;
  const leavingFactory = laneId === "model" && state.selection.model === "preexisting";
  const lanes = [laneId];
  const palettes = laneId === "model" ? ["model"] : [];
  if (leavingFactory) {
    lanes.push("measure");
    palettes.push("measure");
  }
  update(
    () => {
      if (laneId === "simulator") state.placedSims.splice(0, state.placedSims.length);
      if (laneId === "then") state.placedThens.splice(0, state.placedThens.length);
      if (laneId === "state") state.stateOpen = false;
      if (laneId === "measure") {
        state.measureOpen = false;
        state.measureSites = null;
      }
      if (leavingFactory) {
        installCatalogMeasure();
        if (state.selection.measure === "model") {
          state.selection.measure = null;
          state.measureOpen = false;
          state.measureSites = null;
        }
      }
      if (laneId === "state" && state.qubitsSource === "state" && state.settings.qubits !== "")
        state.qubitsSource = "user";
      if (laneId === "model" && state.qubitsSource === "hamiltonian") {
        state.settings.qubits = "";
        state.qubitsSource = null;
        if (checks.qubitCount(currentPage()) == null) state.measureOpen = false;
      }
      if (laneId === "model" && state.qubitsSource === "model") {
        state.selection.model = null;
        deriveModelQubits();
      }
      state.selection[laneId] = null;
      releaseStatusHold();
    },
    {
      lanes,
      palettes,
      clearResults: true,
      focus: { kind: "after-remove", slot: laneId, index: 0 },
    },
  );
}

function knownBlock(laneId, blockId) {
  return typeof blockId === "string" && Boolean(checks.blockById(currentPage(), laneId, blockId));
}

function plainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function textNumber(value) {
  if (typeof value === "string") return value;
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return Object.is(value, -0) ? "0" : String(value);
}

function numberListText(value) {
  if (!Array.isArray(value)) return "";
  return value.map((item) => textNumber(item)).join(", ");
}

function complexText(entry) {
  const re = Array.isArray(entry) ? Number(entry[0]) : Number(entry);
  const im = Array.isArray(entry) ? Number(entry[1] ?? 0) : 0;
  if (!im) return textNumber(re);
  const magnitude = Math.abs(im) === 1 ? "j" : `${textNumber(Math.abs(im))}j`;
  if (!re) return im < 0 ? `-${magnitude}` : magnitude;
  return `${textNumber(re)}${im < 0 ? "-" : "+"}${magnitude}`;
}

function matrixText(matrix) {
  if (!Array.isArray(matrix)) return "";
  const rows = matrix.map(
    (row) => `[${(Array.isArray(row) ? row : []).map((entry) => complexText(entry)).join(", ")}]`,
  );
  return `[${rows.join(", ")}]`;
}

function resetBoard() {
  state.selection.state = null;
  state.selection.model = null;
  state.selection.simulator = null;
  state.selection.backend = null;
  state.selection.measure = null;
  state.selection.then = null;
  state.settings.qubits = "";
  state.settings.total = "";
  for (const key of Object.keys(state.stateText)) delete state.stateText[key];
  state.qubitsSource = null;
  state.preexistingId = null;
  state.factoryText = {};
  state.modelTerms.splice(0, state.modelTerms.length);
  state.placedSims.splice(0, state.placedSims.length);
  state.placedThens.splice(0, state.placedThens.length);
  for (const key of Object.keys(state.actionText)) delete state.actionText[key];
  for (const key of Object.keys(state.pathOpen)) delete state.pathOpen[key];
  for (const block of state.blocks.then) {
    if (block.field?.kind === "path") state.actionText[block.id] = block.field.default ?? "";
  }
  state.measureSites = null;
  for (const key of Object.keys(state.expressionText)) delete state.expressionText[key];
  state.stateOpen = false;
  state.measureOpen = false;
  state.preexistingOpen = false;
  state.modelMeasurements = [];
  if (state.catalogMeasures.length) state.blocks.measure = state.catalogMeasures.slice();
}

function applyState(saved) {
  if (!plainObject(saved)) return;
  const id = knownBlock("state", saved.id) ? saved.id : null;
  state.selection.state = id;
  if (!id) return;
  const field = stateField(id);
  if (field?.kind === "bits" && typeof saved.value === "string") state.stateText[id] = saved.value;
  else if (field?.kind === "numbers") state.stateText[id] = numberListText(saved.value);
}

function applyModel(model) {
  if (!plainObject(model)) return;
  const terms = Array.isArray(model.terms) ? model.terms : [];
  if (terms.length) {
    installCatalogMeasure();
    state.settings.qubits = textNumber(model.qubits);
    state.qubitsSource = "user";
    const next = [];
    for (const term of terms) {
      if (
        !plainObject(term) ||
        !knownBlock("model", term.id) ||
        !checks.blockById(currentPage(), "model", term.id)?.adds
      )
        continue;
      next.push({
        id: term.id,
        matrix: matrixText(term.matrix),
        sites: Array.isArray(term.sites) ? term.sites.filter((site) => Number.isInteger(site)) : [],
      });
    }
    state.modelTerms.splice(
      0,
      state.modelTerms.length,
      ...next.map((term) => ({ ...term, key: ++state.modelTermKey })),
    );
    return;
  }
  const id =
    typeof model.id === "string" && state.modelFactories.some((item) => item.id === model.id)
      ? model.id
      : null;
  if (!id) return;
  state.selection.model = "preexisting";
  state.preexistingId = id;
  const args = plainObject(model.arguments) ? model.arguments : {};
  if ("n_qubits" in args) {
    state.settings.qubits = textNumber(args.n_qubits);
    state.qubitsSource = "user";
  }
  for (const [key, value] of Object.entries(args)) {
    if (key === "n_qubits") continue;
    if (typeof value === "string" || typeof value === "number")
      state.factoryText[key] = textNumber(value);
  }
  installFactoryMeasure();
  state.selection.measure = "model";
  state.measureOpen = false;
  state.measureSites = null;
}

function simParams(block, args) {
  const params = freshParams(block);
  if (!plainObject(args)) return params;
  for (const field of block?.fields ?? []) {
    if (!(field.name in args)) continue;
    const value = args[field.name];
    if (typeof value === "string" || typeof value === "number")
      params[field.name] = textNumber(value);
  }
  return params;
}

function applySims(entries) {
  const next = [];
  for (const entry of Array.isArray(entries) ? entries : []) {
    if (!plainObject(entry) || !knownBlock("simulator", entry.id)) continue;
    const block = checks.blockById(currentPage(), "simulator", entry.id);
    const row = {
      id: entry.id,
      params: simParams(block, entry.arguments),
      open: false,
      backend: null,
      shots: DEFAULT_SHOTS,
      shotsOpen: false,
      backendOpen: false,
    };
    const backend = entry.backend;
    if (
      plainObject(backend) &&
      typeof backend.id === "string" &&
      checks.backendFits(currentPage(), row, backend.id)
    ) {
      row.backend = backend.id;
      const args = plainObject(backend.arguments) ? backend.arguments : {};
      if ("shots" in args) row.shots = textNumber(args.shots);
      const fields = {};
      for (const [key, value] of Object.entries(args)) {
        if (key === "shots") continue;
        if (typeof value === "string" || typeof value === "number") fields[key] = textNumber(value);
      }
      if (Object.keys(fields).length) row.backendFields = fields;
    }
    next.push(row);
  }
  state.placedSims.splice(
    0,
    state.placedSims.length,
    ...next.map((entry) => ({ ...entry, key: ++state.simKey })),
  );
  state.selection.simulator = state.placedSims[0]?.id ?? null;
}

function applyMeasure(measure) {
  if (!plainObject(measure)) return;
  if (state.selection.model === "preexisting") {
    installFactoryMeasure();
    state.selection.measure = "model";
    state.measureOpen = false;
    state.measureSites = null;
    return;
  }
  state.selection.measure = knownBlock("measure", measure.id) ? measure.id : null;
  state.measureSites = Array.isArray(measure.sites)
    ? measure.sites.filter((site) => Number.isInteger(site))
    : null;
  const field = checks.blockById(currentPage(), "measure", state.selection.measure)?.field;
  if (field?.kind === "expression" && typeof measure.expression === "string") {
    state.expressionText[state.selection.measure] = measure.expression;
  }
}

function applyActions(actions) {
  if (!plainObject(actions)) return;
  const next = [];
  for (const id of Array.isArray(actions.ids) ? actions.ids : []) {
    if (knownBlock("then", id) && !next.includes(id)) next.push(id);
  }
  state.placedThens.splice(0, state.placedThens.length, ...next);
  state.selection.then = next[0] ?? null;
  for (const block of state.blocks.then) {
    const field = block.field;
    if (field?.kind === "path" && typeof actions[field.key] === "string")
      state.actionText[block.id] = actions[field.key];
  }
}

function applyDocument(saved) {
  if (!plainObject(saved)) return;
  resetBoard();
  if (typeof saved.total === "string" || typeof saved.total === "number")
    state.settings.total = textNumber(saved.total);
  applyState(saved.state);
  applyModel(saved.model);
  applySims(saved.simulators);
  applyMeasure(saved.measure);
  applyActions(saved.actions);
}

function applyBoard(saved) {
  applyDocument(saved);
}

function forgetBoard() {
  try {
    localStorage.removeItem(BOARD_KEY);
  } catch {
    // Storage can be unavailable.
  }
}

async function restoreBoard() {
  let raw = null;
  try {
    raw = localStorage.getItem(BOARD_KEY);
  } catch {
    return;
  }
  if (!raw) return;
  let saved = null;
  try {
    saved = JSON.parse(raw);
  } catch {
    forgetBoard();
    return;
  }
  if (!plainObject(saved) || Object.keys(saved).some((key) => !DOCUMENT_KEYS.has(key))) {
    forgetBoard();
    return;
  }
  const body = JSON.stringify(postedBoard(saved));
  let response = null;
  let payload = {};
  try {
    response = await fetch("/runs/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
  } catch {
    state.statusHold = "The selection could not be checked.";
    return;
  }
  if (!response.ok || !Number.isInteger(payload.qubits) || payload.qubits < 1) {
    state.statusHold =
      typeof payload.error === "string" && payload.error
        ? payload.error
        : "The selection was rejected.";
    return;
  }
  applyDocument(JSON.parse(body));
  state.acceptedQubits = payload.qubits;
  applyAcceptedQubits();
  if (state.selection.model === "preexisting") {
    state.modelMeasurements = readModelMeasurements(payload);
    installFactoryMeasure();
  }
  state.checkError = null;
  state.rejectedBody = null;
  state.checkInFlight = false;
  state.pendingBody = null;
  if (documentBody() === body) {
    state.acceptedBody = body;
    releaseStatusHold();
  } else state.acceptedBody = null;
}

function rememberBoard() {
  if (!state.boardReady || !accepted()) return;
  try {
    localStorage.setItem(BOARD_KEY, state.acceptedBody);
  } catch {
    // Storage can be unavailable. The page still runs.
  }
}

function holdImportStatus(message) {
  update(
    () => {
      state.statusHold = message;
    },
    { statusOnly: true },
  );
}

async function importBoardText(raw) {
  if (state.running) return;
  let saved = null;
  try {
    saved = JSON.parse(raw);
  } catch {
    holdImportStatus("The selection was rejected.");
    return;
  }
  if (!plainObject(saved)) {
    holdImportStatus("The selection was rejected.");
    return;
  }
  const body = JSON.stringify(postedBoard(saved));
  let result = null;
  try {
    result = await requestCheck(body);
  } catch {
    if (!state.running) holdImportStatus("The selection could not be checked.");
    return;
  }
  if (state.running || !result.ok) {
    if (!state.running)
      holdImportStatus(result?.error ? result.error : "The selection was rejected.");
    return;
  }
  cancelScheduledCheck();
  state.checkSerial += 1;
  applyDocument(JSON.parse(body));
  state.acceptedQubits = result.qubits;
  applyAcceptedQubits();
  if (state.selection.model === "preexisting") {
    state.modelMeasurements = result.measurements ?? [];
    installFactoryMeasure();
  }
  state.checkError = null;
  state.rejectedBody = null;
  state.checkInFlight = false;
  state.pendingBody = null;
  if (documentBody() === body) {
    state.acceptedBody = body;
    releaseStatusHold();
  } else state.acceptedBody = null;
  update(null, { board: true });
}

function emptyBoard() {
  if (state.running) return;
  const snapshot = boardSnapshot();
  update(
    () => {
      resetBoard();
      forgetBoard();
      releaseStatusHold();
      showClearUndo(snapshot);
    },
    { board: true },
  );
}

function validLimits(payload) {
  const states = payload == null ? null : payload.states;
  if (states == null || typeof states !== "object") return false;
  return [
    states.basis,
    states.gray,
    states.angle,
    states.amplitude,
    payload.operatorQubits,
    payload.timeSteps,
    payload.numSteps,
    payload.trotterDepth,
    payload.shots,
  ].every((value) => Number.isInteger(value) && value > 0);
}

function applyLimits(payload) {
  if (!validLimits(payload)) return false;
  state.limits = payload;
  return true;
}

async function loadLimits() {
  try {
    const response = await fetch("/limits");
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    return response.ok && applyLimits(payload);
  } catch {
    return false;
  }
}

function mount(root) {
  const board = el("section", { className: "board" });
  root.append(board);
  draw(board);
}

function paintLoadedLane(lane) {
  if (!document.querySelector(".board")) return;
  const laneId = lane === "backend" ? "simulator" : lane;
  update(null, { lanes: [laneId], palettes: [laneId], chrome: false });
}

async function loadLane(path, lane, key) {
  state.laneStatus[lane] = "loading";
  try {
    const response = await fetch(path);
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    const items = payload[key];
    if (!response.ok || !Array.isArray(items)) {
      state.laneNotes[lane] = payload.error || `Could not load ${key}.`;
      state.laneStatus[lane] = "error";
      state.blocks[lane] = [];
      if (lane === "measure") state.catalogMeasures = [];
      state.selection[lane] = null;
      return;
    }
    if (lane === "model") {
      state.modelFactories = items.filter((item) => !item.adds);
      state.blocks.model = [
        {
          id: "preexisting",
          title: "Preexisting model",
          detail: "Choose a built-in model",
          phrase: "a preexisting model",
        },
        ...items.filter((item) => item.adds),
      ];
      if (
        state.preexistingId &&
        !state.modelFactories.some((item) => item.id === state.preexistingId)
      )
        state.preexistingId = null;
    } else state.blocks[lane] = items;
    if (lane === "measure") state.catalogMeasures = items.slice();
    if (lane === "then") {
      for (const item of items) {
        if (item.field?.kind === "path" && !Object.hasOwn(state.actionText, item.id)) {
          state.actionText[item.id] = item.field.default ?? "";
        }
      }
    }
    state.laneNotes[lane] = "";
    state.laneStatus[lane] = "ready";
    if (
      state.selection[lane] != null &&
      !checks.blockById(currentPage(), lane, state.selection[lane])
    )
      state.selection[lane] = null;
  } catch {
    state.laneNotes[lane] = `Could not load ${key}.`;
    state.laneStatus[lane] = "error";
    state.blocks[lane] = [];
    if (lane === "measure") state.catalogMeasures = [];
    state.selection[lane] = null;
  }
}

async function bootBuilder() {
  const laneLoads = Object.entries(LANE_CATALOG).map(([lane, { path, key }]) =>
    loadLane(path, lane, key).then(() => paintLoadedLane(lane)),
  );
  const limitsOk = await loadLimits();
  if (!limitsOk) {
    state.statusHold = "Could not load limits.";
    setStatus(state.statusHold);
  } else {
    setStatus(statusMessage(), runAllowed());
  }
  await Promise.all(laneLoads);
  if (!limitsOk) return;
  await restoreBoard();
  state.boardReady = true;
  update(null, { board: true });
}

function startBuilder(root) {
  for (const lane of Object.keys(state.laneStatus)) {
    state.laneStatus[lane] = "loading";
    state.laneNotes[lane] = "";
    state.blocks[lane] = [];
    state.selection[lane] = null;
  }
  state.modelFactories = [];
  state.catalogMeasures = [];
  state.modelTerms.splice(0, state.modelTerms.length);
  state.placedSims.splice(0, state.placedSims.length);
  state.placedThens.splice(0, state.placedThens.length);
  mount(root);
  void bootBuilder();
}

const builder = document.querySelector("#builder");
if (builder) startBuilder(builder);
