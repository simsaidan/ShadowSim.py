/* Builder page. Model, method, and backend cards come from the package. */

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

const BLOCKS = {
  state: [],
  model: [],
  simulator: [],
  backend: [],
  measure: [],
  then: [],
};

let limits = null;

const selection = {
  state: null,
  model: null,
  simulator: null,
  backend: null,
  measure: null,
  then: null,
};

const modelTerms = [];
let modelTermKey = 0;
let modelFactories = [];
let preexistingId = null;
let preexistingOpen = false;
let factoryText = {};

const settings = { qubits: "", total: "" };
const stateText = {};
let qubitsSource = null;
const placedSims = [];
let simKey = 0;
const placedThens = [];
const actionText = {};
const pathOpen = {};
let stateOpen = false;
let measureOpen = false;
let measureSites = null;
const expressionText = {};
const DEFAULT_SHOTS = "256";

let dragging = null;
let running = false;
const BOARD_KEY = "shadowsim.builder.board";
let boardReady = false;
let copyTimer = 0;
let copiedButton = null;
let copiedLabel = "Copy";
let statusHold = null;
let runStartedAt = 0;
let runTimer = null;
let shownRun = null;
let acceptedBody = null;
let acceptedQubits = null;
let rejectedBody = null;
let checkError = null;
let checkTimer = null;
let checkSerial = 0;
let pendingBody = null;
let checkInFlight = false;
const CHECK_DELAY = 200;
const laneNotes = { model: "", simulator: "", backend: "" };

const CURVE_COLORS = ["#4c4cb8", "#1f7a6c", "#a67c1a", "#b66880", "#6a4ca8"];

function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value == null || value === false) continue;
    if (key === "className") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function currentPage() {
  return {
    lanes: LANES,
    blocks: BLOCKS,
    selection,
    settings,
    modelTerms,
    modelFactories,
    preexistingId,
    factoryText,
    stateText,
    placedSims,
    placedThens,
    actionText,
    measureSites,
    expressionText,
    qubitsSource,
    stateLimits: limits.states,
    maxOperatorQubits: limits.operatorQubits,
    maxTimeSteps: limits.timeSteps,
    maxNumSteps: limits.numSteps,
    maxTrotterDepth: limits.trotterDepth,
    maxShots: limits.shots,
    checkedQubits: checkError == null && acceptedBody != null ? acceptedQubits : null,
  };
}

function check(fn, ...args) {
  return fn(currentPage(), ...args);
}

function blockById(laneId, blockId) {
  return check(checks.blockById, laneId, blockId);
}

function chosenFactory() {
  return check(checks.chosenFactory);
}

function operatorStatus(preview) {
  return check(checks.operatorStatus, preview);
}

function isReference(entry) {
  return check(checks.isReference, entry);
}

function backendFits(entry, backendId) {
  return check(checks.backendFits, entry, backendId);
}

function socketStatus(preview) {
  return check(checks.socketStatus, preview);
}

function isComplete() {
  return check(checks.isComplete);
}

function formatSetting(key) {
  return check(checks.formatSetting, key);
}

function qubitPhrase() {
  return check(checks.qubitPhrase);
}

function stateOwnsQubits() {
  return check(checks.stateOwnsQubits);
}

function numberList(raw, maxCount) {
  return check(checks.numberList, raw, maxCount);
}

function amplitudeQubits(count) {
  return check(checks.amplitudeQubits, count);
}

function factoryAlert() {
  return check(checks.factoryAlert);
}

function factorySetsQubits() {
  return check(checks.factorySetsQubits);
}

function stateImpliedQubits() {
  return check(checks.stateImpliedQubits);
}

function stateSizeProblem() {
  return check(checks.stateSizeProblem);
}

function stateSizeStatus(preview) {
  return check(checks.stateSizeStatus, preview);
}

function stateInputProblem() {
  return check(checks.stateInputProblem);
}

function positiveIntText(value) {
  return check(checks.positiveIntText, value);
}

function freshParams(id) {
  if (isReference({ id })) return { timeSteps: "101" };
  return { timeSteps: "11", numSteps: "4", trotterDepth: "1", seed: "0", order: "1" };
}

function simParamProblem(preview) {
  return check(checks.simParamProblem, preview);
}

function simParamsReady() {
  return check(checks.simParamsReady);
}

function sameTimeGrid() {
  return check(checks.sameTimeGrid);
}

function missingPaths() {
  return check(checks.missingPaths);
}

function savePathReady() {
  return check(checks.savePathReady);
}

function qubitCount() {
  return check(checks.qubitCount);
}

function selectedSites(count) {
  return check(checks.selectedSites, count);
}

function shotsProblem(preview) {
  return check(checks.shotsProblem, preview);
}

function shotsReady() {
  return check(checks.shotsReady);
}

function measureSitesReady() {
  return check(checks.measureSitesReady);
}

function countsStatus(preview) {
  return check(checks.countsStatus, preview);
}

function numberProblem(preview) {
  return check(checks.numberProblem, preview);
}

function settingsReady() {
  return check(checks.settingsReady);
}

function locallyReady() {
  return check(checks.runAllowed);
}

function accepted() {
  return acceptedBody != null && acceptedBody === documentBody() && checkError == null;
}

function runAllowed() {
  return locallyReady() && accepted();
}

function postedTerms() {
  return check(checks.postedTerms);
}

function entryBody(entry) {
  return check(checks.entryBody, entry);
}

function previewText() {
  if (!accepted()) return "";
  return check(checks.previewText);
}

function modelChoiceBlocked(block) {
  if (!block) return false;
  if (block.id === "preexisting") return modelTerms.length > 0;
  if (block.adds) return selection.model === "preexisting";
  return false;
}

function blockCard(lane, block, { inSlot, onPlace, onRemove, blocked }) {
  if (inSlot) {
    return el(
      "div",
      { className: `chip tone-${lane.tone}` },
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

  const card = el(
    "button",
    {
      className: `block tone-${lane.tone}`,
      type: "button",
      draggable: blocked ? "false" : "true",
      disabled: Boolean(blocked),
      "data-lane": lane.id,
      "data-block": block.id,
      ondragstart: (event) => {
        if (blocked) {
          event.preventDefault();
          return;
        }
        dragging = { lane: lane.id, id: block.id };
        event.dataTransfer.setData("text/plain", `${lane.id}:${block.id}`);
        event.dataTransfer.effectAllowed = "copy";
      },
      ondragend: () => {
        dragging = null;
      },
      onclick: () => {
        if (!blocked) onPlace();
      },
    },
    el("div", {}, el("strong", {}, block.title), el("span", {}, block.detail)),
  );
  return card;
}

function acceptedLayoutQubits() {
  if (acceptedBody == null || acceptedBody !== documentBody() || checkError != null) return null;
  return acceptedQubits;
}

function qubitDetail(count) {
  return count === 1 ? "1 qubit" : `${count} qubits`;
}

function preexistingDetail() {
  const factory = chosenFactory();
  if (!factory) return "";
  const qubits = acceptedLayoutQubits();
  if (factory.qubits) return qubits == null ? "at least 2 qubits" : qubitDetail(qubits);
  if (qubits == null) return factoryAlert() || "Set the model arguments";
  return qubitDetail(qubits);
}

function factoryParams() {
  const params = chosenFactory()?.params;
  return Array.isArray(params) ? params : [];
}

function paramText(param) {
  const stored = factoryText[param.name];
  return typeof stored === "string" ? stored : String(param.default ?? "");
}

function movedFromDefault(name) {
  const param = factoryParams().find((item) => item.name === name);
  return Boolean(param) && paramText(param) !== String(param.default ?? "");
}

function fieldLocked(param) {
  return factoryParams().some(
    (other) => Array.isArray(other.disables) && other.disables.includes(param.name) && movedFromDefault(other.name),
  );
}

function refreshFactoryLocks(chip) {
  if (!chip) return;
  for (const param of factoryParams()) {
    const control = chip.querySelector(`[data-param="${param.name}"]`);
    if (control) control.disabled = fieldLocked(param);
  }
}

function rememberFactoryText(name, value) {
  factoryText[name] = value;
}

function factoryField(param) {
  const value = paramText(param);
  const locked = fieldLocked(param);
  if (param.kind === "choice") {
    return el(
      "label",
      { className: "preexisting-field" },
      param.label,
      el(
        "select",
        {
          "aria-label": param.label,
          "data-param": param.name,
          disabled: locked || null,
          onchange: (event) => {
            rememberFactoryText(param.name, event.target.value);
            refreshFactoryLocks(event.target.closest(".chip"));
            refreshCavityModel();
          },
        },
        ...(Array.isArray(param.choices) ? param.choices : []).map((choice) =>
          el("option", { value: choice, selected: choice === value }, choice),
        ),
      ),
    );
  }
  const integer = param.kind === "integer";
  const numeric = integer || param.kind === "number" || param.kind === "number_or_list";
  return el(
    "label",
    { className: "preexisting-field" },
    param.label,
    el("input", {
      type: "text",
      inputmode: integer ? "numeric" : numeric ? "decimal" : "text",
      "aria-label": param.label,
      "data-param": param.name,
      value,
      disabled: locked || null,
      spellcheck: "false",
      autocomplete: "off",
      oninput: (event) => {
        const next = integer ? event.target.value.replace(/\D/g, "") : event.target.value.trim();
        if (integer && event.target.value !== next) event.target.value = next;
        rememberFactoryText(param.name, next);
        refreshFactoryLocks(event.target.closest(".chip"));
        refreshCavityModel();
      },
    }),
  );
}

function postedFactory() {
  if (selection.model !== "preexisting") return null;
  const params = factoryParams();
  if (!params.length) return null;
  const body = {};
  for (const param of params) body[param.name] = paramText(param);
  return body;
}

function modelAlert() {
  if (checkError) return checkError;
  return factoryAlert();
}

function syncFactoryDetail() {
  const detail = document.querySelector(".preexisting-detail");
  if (detail) detail.textContent = preexistingDetail();
}

function syncModelAlert() {
  const alert = document.querySelector(".preexisting-alert");
  if (!alert) return;
  const text = modelAlert();
  alert.hidden = !text;
  if (!text) return;
  alert.setAttribute("aria-label", text);
  alert.title = text;
}

function refreshCavityModel() {
  syncModelQubits();
  syncFactoryDetail();
  if (selection.state) refreshStateChip(selection.state);
  else refreshSummaryAndPreview();
  syncModelAlert();
}

function replaceChip(node, next) {
  node.closest(".chip").replaceWith(next);
}

function preexistingChip() {
  const factory = chosenFactory();
  const select = el(
    "select",
    {
      "aria-label": "Model",
      onchange: (event) => {
        preexistingId = event.target.value;
        syncModelQubits();
        releaseStatusHold();
        commitLane("model", true);
      },
    },
    ...modelFactories.map((item) =>
      el("option", { value: item.id, selected: item.id === factory?.id }, item.title),
    ),
  );
  const alertText = modelAlert() ?? "Check the model arguments";
  return el(
    "div",
    { className: `chip tone-teal preexisting${preexistingOpen ? " is-editing" : ""}` },
    el(
      "div",
      { className: "preexisting-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (preexistingOpen) return;
            preexistingOpen = true;
            replaceChip(event.currentTarget, preexistingChip());
          },
        },
        el("strong", {}, "Preexisting model"),
        el("span", { className: "preexisting-detail" }, preexistingDetail()),
      ),
      el(
        "div",
        { className: "preexisting-actions" },
        el(
          "span",
          {
            className: "basis-alert preexisting-alert",
            role: "img",
            "aria-label": alertText,
            title: alertText,
            hidden: !modelAlert(),
          },
          "!",
        ),
        preexistingOpen
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  preexistingOpen = false;
                  replaceChip(event.currentTarget, preexistingChip());
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
    preexistingOpen ? el("label", { className: "preexisting-field" }, "Model", select) : null,
    ...(preexistingOpen ? factoryParams().map(factoryField) : []),
  );
}

function grayPrepared(bits) {
  let index = 0;
  for (const bit of bits) index = (index << 1) | (bit === "1" ? 1 : 0);
  return (index ^ (index >>> 1)).toString(2).padStart(bits.length, "0");
}

function stateField(id) {
  return blockById("state", id)?.field ?? null;
}

function stateTextOf(id) {
  return stateText[id] ?? "";
}

function blankDetail(field) {
  return String(field.blank ?? "").replaceAll("{cap}", String(field.cap ?? ""));
}

function stateDetail(id) {
  const field = stateField(id);
  if (!field) return "";
  const text = stateTextOf(id);
  if (field.kind === "bits") {
    if (!text) return blankDetail(field);
    const shown = field.display === "gray" ? grayPrepared(text) : text;
    return `Start in |${shown}>`;
  }
  const values = numberList(text, field.cap);
  if (!values || (field.nonzero && values.every((value) => value === 0))) return blankDetail(field);
  const count = field.match === "padded" ? amplitudeQubits(values.length) : values.length;
  const unit = field.unit || "value";
  return count === 1 ? `1 ${unit}` : `${count} ${unit}s`;
}

function stateReady(id) {
  const field = stateField(id);
  if (!field) return false;
  const text = stateTextOf(id);
  if (field.kind === "bits") return text !== "";
  const values = numberList(text, field.cap);
  if (!values) return false;
  return !field.nonzero || values.some((value) => value !== 0);
}

function writeQubitField() {
  const qubitsInput = document.querySelector('input[aria-label="Qubits"]');
  if (!qubitsInput) return;
  qubitsInput.readOnly = stateOwnsQubits() || factorySetsQubits();
  if (qubitsInput.value !== settings.qubits) qubitsInput.value = settings.qubits;
}

function syncStateQubits() {
  if (!stateOwnsQubits() || factorySetsQubits()) return;
  const count = stateImpliedQubits();
  settings.qubits = count == null ? "" : String(count);
  qubitsSource = count == null ? null : "state";
  syncMeasureChip();
  writeQubitField();
}

function syncModelQubits() {
  if (!factorySetsQubits()) {
    if (qubitsSource !== "model") return;
    if (stateOwnsQubits()) {
      qubitsSource = null;
      syncStateQubits();
    } else {
      qubitsSource = settings.qubits === "" ? null : "user";
      writeQubitField();
    }
    return;
  }
  const fixed = acceptedLayoutQubits();
  settings.qubits = fixed == null ? "" : String(fixed);
  qubitsSource = "model";
  syncMeasureChip();
  writeQubitField();
}

function stateAlertLabel(id) {
  const field = stateField(id);
  if (!field) return "";
  const expected = stateSizeProblem();
  if (expected != null) return String(field.mismatch ?? "").replaceAll("{n}", String(expected));
  return field.empty ?? "";
}

function refreshStateChip(id) {
  if (selection.state === id) syncStateQubits();
  const detail = document.querySelector(".basis-detail");
  if (detail) detail.textContent = stateDetail(id);
  const alert = document.querySelector(".chip.tone-gold .basis-alert");
  if (alert) {
    const label = stateAlertLabel(id);
    alert.hidden = stateReady(id) && stateSizeProblem() == null;
    alert.title = label;
    alert.setAttribute("aria-label", label);
  }
  refreshHamiltonianChips();
  refreshLocalHamiltonianChips();
  refreshSummaryAndPreview();
}

function stateChip(options) {
  const open = stateOpen;
  const input = el("input", {
    type: "text",
    inputmode: options.bits ? "numeric" : "decimal",
    ...(options.bits ? { maxlength: String(options.cap) } : {}),
    "aria-label": options.aria,
    value: options.value,
    spellcheck: "false",
    autocomplete: "off",
    oninput: options.oninput,
  });
  return el(
    "div",
    { className: `chip tone-gold state ${options.id}${open ? " is-editing" : ""}` },
    el(
      "div",
      { className: "basis-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (stateOpen) return;
            stateOpen = true;
            replaceChip(event.currentTarget, stateChip(options));
          },
        },
        el("strong", {}, options.title),
        el("span", { className: "basis-detail" }, stateDetail(options.id)),
      ),
      el(
        "div",
        { className: "basis-actions" },
        el(
          "span",
          {
            className: "basis-alert",
            role: "img",
            "aria-label": stateAlertLabel(options.id),
            title: stateAlertLabel(options.id),
            hidden: stateReady(options.id) && stateSizeProblem() == null,
          },
          "!",
        ),
        open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  stateOpen = false;
                  replaceChip(event.currentTarget, stateChip(options));
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
    open ? el("label", { className: "basis-field" }, options.field, input) : null,
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
      const raw = event.target.value;
      const next = bits ? raw.replace(/[^01]/g, "").slice(0, field.cap) : raw.replace(/[^\d.,\s-]/g, "");
      if (event.target.value !== next) event.target.value = next;
      stateText[block.id] = next;
      refreshStateChip(block.id);
    },
  });
}

function simField(params, key, label, seed) {
  return el(
    "label",
    {},
    label,
    el("input", {
      type: "text",
      inputmode: seed ? "text" : "numeric",
      "aria-label": label,
      value: params[key],
      spellcheck: "false",
      oninput: (event) => {
        const next = seed
          ? event.target.value.replace(/[^\d-]/g, "").replace(/(?!^)-/g, "")
          : event.target.value.replace(/\D/g, "");
        if (event.target.value !== next) event.target.value = next;
        params[key] = next;
        refreshSummaryAndPreview();
      },
    }),
  );
}

function simulatorChip(entry) {
  const block = blockById("simulator", entry.id);
  const params = entry.params;
  if (!block) return null;
  const fields = [
    simField(params, "timeSteps", "Time steps", false),
  ];
  if (!isReference(entry)) {
    const trotter = block.trotter !== false;
    fields.push(simField(params, "numSteps", "Product steps", false));
    if (trotter) fields.push(simField(params, "trotterDepth", "Trotter depth", false));
    fields.push(simField(params, "seed", "Seed", true));
    if (trotter) fields.push(
      el(
        "label",
        {},
        "Order",
        el(
          "select",
          {
            "aria-label": "Order",
            onchange: (event) => {
              params.order = event.target.value;
              refreshSummaryAndPreview();
            },
          },
          el("option", { value: "1", selected: params.order === "1" }, "1"),
          el("option", { value: "2", selected: params.order === "2" }, "2"),
        ),
      ),
    );
  }
  return el(
    "div",
    { className: `chip tone-blue simulator${entry.open ? " is-editing" : ""}` },
    el(
      "div",
      { className: "simulator-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (entry.open) return;
            entry.open = true;
            replaceChip(event.currentTarget, simulatorChip(entry));
          },
        },
        el("strong", {}, block.title),
        el("span", {}, block.detail),
      ),
      el(
        "div",
        { className: "simulator-actions" },
        entry.open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  entry.open = false;
                  replaceChip(event.currentTarget, simulatorChip(entry));
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
    entry.open ? el("div", { className: "sim-fields" }, ...fields) : null,
  );
}

function pathValue(id) {
  if (Object.hasOwn(actionText, id)) return actionText[id];
  return blockById("then", id)?.field?.default ?? "";
}

function pathChip(block) {
  const field = block.field ?? {};
  const open = Boolean(pathOpen[block.id]);
  const path = pathValue(block.id);
  const shown = path.trim();
  const refresh = (event) => replaceChip(event.currentTarget, pathChip(block));
  return el(
    "div",
    { className: `chip tone-rose path ${block.id}${open ? " is-editing" : ""}` },
    el(
      "div",
      { className: "path-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (open) return;
            pathOpen[block.id] = true;
            refresh(event);
          },
        },
        el("strong", {}, block.title),
        el("span", {}, shown || block.detail),
      ),
      el(
        "div",
        { className: "path-actions" },
        open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  pathOpen[block.id] = false;
                  refresh(event);
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
          { className: "path-field" },
          field.label || "Path",
          el("input", {
            type: "text",
            "aria-label": field.aria || "Path",
            value: path,
            spellcheck: "false",
            oninput: (event) => {
              actionText[block.id] = event.target.value;
              const detail = event.target.closest(".chip")?.querySelector("span");
              if (detail) detail.textContent = event.target.value.trim() || block.detail;
              refreshSummaryAndPreview();
            },
          }),
        )
      : null,
  );
}

function backendFieldNumber(field, text) {
  return check(checks.backendFieldNumber, field, text);
}

function gateSummary(field, text) {
  if (check(checks.gateFieldProblem, field, text)) return "";
  const names = check(checks.gateNames, text);
  return names.length ? names.join(", ") : "";
}

function backendSummary(block, entry) {
  const parts = [];
  if (block.shots) {
    const shotText = String(entry.shots ?? "").trim();
    if (!positiveIntText(shotText)) return block.detail;
    parts.push(`${shotText} shots`);
  }
  for (const field of block.fields ?? []) {
    const text = String(entry.backendFields?.[field.name] ?? "").trim();
    if (field.kind === "gates") {
      const gates = gateSummary(field, text);
      if (gates) parts.push(gates);
      continue;
    }
    if (backendFieldNumber(field, text) == null) return block.detail;
    parts.push(`${field.label} ${text}`);
  }
  return parts.length ? parts.join(", ") : block.detail;
}

function backendChip(entry) {
  const block = blockById("backend", entry.backend);
  if (!block) return null;
  const fields = block.fields ?? [];
  const samples = Boolean(block.shots);
  const configurable = samples || fields.length > 0;
  const editing = samples ? Boolean(entry.shotsOpen) : Boolean(entry.backendOpen) && fields.length > 0;
  const shown = backendSummary(block, entry);
  return el(
    "div",
    { className: `chip tone-violet backend${editing ? " is-editing" : ""}` },
    el(
      "div",
      { className: "backend-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (!configurable || editing) return;
            if (samples) entry.shotsOpen = true;
            else entry.backendOpen = true;
            replaceChip(event.currentTarget, backendChip(entry));
          },
        },
        el("strong", {}, block.title),
        el("span", { className: "backend-detail" }, shown),
      ),
      el(
        "div",
        { className: "backend-actions" },
        editing
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  entry.shotsOpen = false;
                  entry.backendOpen = false;
                  replaceChip(event.currentTarget, backendChip(entry));
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
      ? el(
          "label",
          { className: "backend-field" },
          "Shots",
          el("input", {
            type: "text",
            inputmode: "numeric",
            "aria-label": "Shots",
            value: String(entry.shots ?? ""),
            spellcheck: "false",
            oninput: (event) => {
              const next = event.target.value.replace(/\D/g, "");
              if (event.target.value !== next) event.target.value = next;
              entry.shots = next;
              const detail = event.target.closest(".chip")?.querySelector(".backend-detail");
              if (detail) detail.textContent = backendSummary(block, entry);
              refreshSummaryAndPreview();
            },
          }),
        )
      : null,
    editing && fields.length
      ? el(
          "div",
          { className: "backend-fields" },
          ...fields.map((field) =>
            el(
              "label",
              {},
              field.label,
              el("input", {
                type: "text",
                inputmode: field.kind === "gates" ? "text" : "decimal",
                "aria-label": field.label,
                value: String(entry.backendFields?.[field.name] ?? ""),
                spellcheck: "false",
                autocomplete: "off",
                oninput: (event) => {
                  const gates = field.kind === "gates";
                  const next = gates
                    ? event.target.value.toLowerCase().replace(/[^a-z0-9_,\s]/g, "")
                    : event.target.value.replace(/[^0-9.eE+\-infity]/gi, "");
                  if (event.target.value !== next) event.target.value = next;
                  entry.backendFields = entry.backendFields ?? {};
                  entry.backendFields[field.name] = next;
                  const detail = event.target.closest(".chip")?.querySelector(".backend-detail");
                  if (detail) detail.textContent = backendSummary(block, entry);
                  refreshSummaryAndPreview();
                },
              }),
            ),
          ),
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
        if (!dragging || dragging.lane !== "backend") return;
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.classList.add("is-over");
      },
      ondragleave: (event) => event.currentTarget.classList.remove("is-over"),
      ondrop: (event) => {
        if (!dragging || dragging.lane !== "backend") return;
        event.preventDefault();
        event.stopPropagation();
        attachBackend(dragging.id, entry.key);
      },
    },
    "Add a backend",
  );
}

function methodRow(entry) {
  const simulator = simulatorChip(entry);
  if (!simulator) return null;
  if (isReference(entry)) return el("div", { className: "method-row reference" }, simulator);
  const backend = entry.backend ? backendChip(entry) : backendSocket(entry);
  return el("div", { className: "method-row" }, simulator, backend);
}

function squareMatrix(text) {
  return check(checks.squareMatrix, text);
}

function inspectMatrix(text) {
  return check(checks.inspectMatrix, text);
}

function hamiltonianProblem(term) {
  return check(checks.hamiltonianProblem, term);
}

function validHamiltonianQubits() {
  return check(checks.validHamiltonianQubits);
}

function hamiltonianDetail(term) {
  const problem = hamiltonianProblem(term);
  if (!term.matrix.trim()) return "Square Hermitian matrix";
  if (problem) return problem.replace(/\.$/, "");
  const size = inspectMatrix(term.matrix).matrix.length;
  return `${size}×${size}`;
}

function syncHamiltonianQubits() {
  if (stateOwnsQubits() || qubitsSource === "user") return;
  const counts = [...new Set(validHamiltonianQubits())];
  if (counts.length === 1) {
    settings.qubits = String(counts[0]);
    qubitsSource = "hamiltonian";
  } else if (qubitsSource === "hamiltonian") {
    settings.qubits = "";
    qubitsSource = null;
  }
  syncMeasureChip();
  writeQubitField();
  refreshLocalHamiltonianChips();
}

function refreshHamiltonianChips() {
  document.querySelectorAll?.(".chip.hamiltonian")?.forEach((chip) => {
    const term = modelTerms.find((item) => item.key === Number(chip.dataset.key));
    if (!term) return;
    const detail = chip.querySelector(".hamiltonian-detail");
    if (detail) detail.textContent = hamiltonianDetail(term);
    syncOperatorAlert(chip, term);
  });
}

function hamiltonianChip(term) {
  const input = el("textarea", {
    "aria-label": "Hamiltonian matrix",
    spellcheck: "false",
    rows: "4",
    oninput: (event) => {
      term.matrix = event.target.value;
      syncHamiltonianQubits();
      refreshHamiltonianChips();
      refreshSummaryAndPreview();
    },
  });
  input.value = term.matrix;
  const chip = el(
    "div",
    { className: "chip tone-teal hamiltonian is-editing", "data-key": String(term.key) },
    el(
      "div",
      { className: "basis-head" },
      el(
        "div",
        {},
        el("strong", {}, "Add a Hamiltonian"),
        el("span", { className: "hamiltonian-detail" }, hamiltonianDetail(term)),
      ),
      el(
        "div",
        { className: "basis-actions" },
        el("span", { className: "basis-alert", role: "img" }, "!"),
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": "Remove Add a Hamiltonian",
            onclick: (event) => {
              event.stopPropagation();
              removeTerm(term.key);
            },
          },
          "×",
        ),
      ),
    ),
    el("label", { className: "basis-field" }, "Matrix", input),
  );
  syncOperatorAlert(chip, term);
  return chip;
}

function localSites(term, count) {
  return check(checks.localSites, term, count);
}

function localHamiltonianProblem(term) {
  return check(checks.localHamiltonianProblem, term);
}

function lindbladProblem(term) {
  return check(checks.lindbladProblem, term);
}

function actedQubitDetail(term) {
  if (qubitCount() == null) return "Set qubits first";
  const problem = term.id === "lindblad" ? lindbladProblem(term) : localHamiltonianProblem(term);
  if (problem) return problem.replace(/\.$/, "");
  const sites = localSites(term, qubitCount());
  const parsed = term.id === "lindblad" ? squareMatrix(term.matrix) : inspectMatrix(term.matrix);
  const label = sites.length === 1 ? `qubit ${sites[0]}` : `qubits ${sites.join(", ")}`;
  return `${parsed.matrix.length}×${parsed.matrix.length} on ${label}`;
}

function toggleLocalSite(term, site, checked) {
  const next = localSites(term, qubitCount()).filter((index) => index !== site);
  if (checked) next.push(site);
  next.sort((left, right) => left - right);
  term.sites = next;
}

function localSiteFields(term) {
  const count = qubitCount();
  const chosen = new Set(localSites(term, count));
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
            toggleLocalSite(term, site, event.target.checked);
            refreshLocalHamiltonianChips();
            refreshSummaryAndPreview();
          },
        }),
        String(site),
      ),
    );
  }
  return el("div", { className: "measure-fields" }, ...boxes);
}

function localFields(term) {
  const input = el("textarea", {
    "aria-label": term.id === "lindblad" ? "Lindblad matrix" : "Local Hamiltonian matrix",
    spellcheck: "false",
    rows: "4",
    oninput: (event) => {
      term.matrix = event.target.value;
      refreshLocalHamiltonianChips();
      refreshSummaryAndPreview();
    },
  });
  input.value = term.matrix;
  return el("div", { className: "local-fields" }, el("label", { className: "basis-field" }, "Matrix", input), localSiteFields(term));
}

function operatorProblem(term) {
  if (term.id === "lindblad") return lindbladProblem(term);
  if (term.id === "local_hamiltonian") return localHamiltonianProblem(term);
  return hamiltonianProblem(term);
}

function syncOperatorAlert(chip, term) {
  const problem = operatorProblem(term);
  const shown = Boolean(problem) && (term.id === "hamiltonian" || qubitCount() != null);
  const alert = chip.querySelector(".basis-alert");
  const field = chip.querySelector("textarea");
  const alertId = `operator-alert-${term.key}`;
  if (alert) {
    alert.hidden = !shown;
    alert.setAttribute("id", alertId);
    if (problem) {
      alert.setAttribute("aria-label", problem);
      alert.setAttribute("title", problem);
      alert.title = problem;
    }
  }
  if (!field) return;
  if (shown && alert) field.setAttribute("aria-describedby", alertId);
  else field.removeAttribute("aria-describedby");
}

function refreshLocalHamiltonianChips() {
  document.querySelectorAll?.(".chip.local-hamiltonian, .chip.lindblad")?.forEach((chip) => {
    const term = modelTerms.find((item) => item.key === Number(chip.dataset.key));
    if (!term) return;
    const count = qubitCount();
    if (count != null) term.sites = localSites(term, count);
    const open = count != null;
    chip.classList.toggle("is-editing", open);
    const detail = chip.querySelector(".hamiltonian-detail");
    if (detail) detail.textContent = actedQubitDetail(term);
    const fields = chip.querySelector(".local-fields");
    if (!open) fields?.remove();
    else if (!fields) chip.append(localFields(term));
    else fields.querySelector(".measure-fields")?.replaceWith(localSiteFields(term));
    syncOperatorAlert(chip, term);
  });
}

function actedQubitChip(term) {
  const open = qubitCount() != null;
  const lindblad = term.id === "lindblad";
  const title = lindblad ? "Add a Lindblad operator" : "Add a Local Hamiltonian";
  const chip = el(
    "div",
    {
      className: `chip tone-teal ${lindblad ? "lindblad" : "local-hamiltonian"}${open ? " is-editing" : ""}`,
      "data-key": String(term.key),
    },
    el(
      "div",
      { className: "basis-head" },
      el("div", {}, el("strong", {}, title), el("span", { className: "hamiltonian-detail" }, actedQubitDetail(term))),
      el(
        "div",
        { className: "basis-actions" },
        el("span", { className: "basis-alert", role: "img" }, "!"),
        el(
          "button",
          {
            className: "remove",
            type: "button",
            "aria-label": `Remove ${title}`,
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
  syncOperatorAlert(chip, term);
  return chip;
}

function slotChips(lane) {
  const chips = [];
  const chosen = blockById(lane.id, selection[lane.id]);
  if (chosen && !chosen.adds && lane.id !== "then") {
    if (chosen.id === "preexisting") chips.push(preexistingChip());
    else if (lane.id === "state") chips.push(stateFieldChip(chosen));
    else if (lane.id === "measure") chips.push(measureChip(chosen));
    else if (lane.id !== "simulator") {
      chips.push(blockCard(lane, chosen, { inSlot: true, onRemove: () => clearLane(lane.id) }));
    }
  }
  if (lane.id === "then") {
    for (const id of placedThens) {
      const block = blockById("then", id);
      if (!block) continue;
      if (block.field?.kind === "path") chips.push(pathChip(block));
      else chips.push(blockCard(lane, block, { inSlot: true, onRemove: () => removeThen(id) }));
    }
    return chips;
  }
  if (lane.id === "simulator") {
    for (const entry of placedSims) {
      const row = methodRow(entry);
      if (row) chips.push(row);
    }
    return chips;
  }
  if (lane.id !== "model") return chips;
  for (const term of modelTerms) {
    const block = blockById("model", term.id);
    if (!block) continue;
    if (term.id === "hamiltonian") chips.push(hamiltonianChip(term));
    else if (term.id === "local_hamiltonian" || term.id === "lindblad") chips.push(actedQubitChip(term));
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
  if (!dragging) return false;
  if (dragging.lane === laneId) return true;
  return laneId === "simulator" && dragging.lane === "backend";
}

function slotComponent(lane) {
  const slot = el(
    "section",
    {
      className: `slot tone-${lane.tone}`,
      "data-slot": lane.id,
      ondragover: (event) => {
        if (!slotAcceptsDrag(lane.id)) return;
        event.preventDefault();
        slot.classList.add("is-over");
      },
      ondragleave: () => slot.classList.remove("is-over"),
      ondrop: (event) => {
        if (!slotAcceptsDrag(lane.id)) return;
        event.preventDefault();
        if (dragging.lane === "backend") attachBackend(dragging.id);
        else place(lane.id, dragging.id);
      },
    },
    el("h2", {}, lane.title),
    el("p", { className: "hint" }, lane.hint),
    ...slotChips(lane),
  );
  return placeOnGrid(slot, lane, "1");
}

function methodPalette(lane, onPlace) {
  const noteText = laneNotes.simulator || laneNotes.backend;
  const note = noteText ? el("p", { className: "hint" }, noteText) : null;
  const groups = [
    ["Classical references", BLOCKS.simulator.filter((block) => block.observables), lane],
    ["Simulators", BLOCKS.simulator.filter((block) => !block.observables), lane],
    ["Backends", BLOCKS.backend, { id: "backend", tone: "violet" }],
  ];
  return placeOnGrid(
    el(
      "section",
      { className: "lane", "data-palette": lane.id },
      el("h2", {}, lane.pick),
      note,
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
                  onPlace: () => (cardLane.id === "backend" ? attachBackend(block.id) : onPlace(block.id)),
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
  const note = laneNotes[lane.id] ? el("p", { className: "hint" }, laneNotes[lane.id]) : null;
  return placeOnGrid(
    el(
      "section",
      { className: "lane", "data-palette": lane.id },
      el("h2", {}, lane.pick),
      note,
      el(
        "div",
        { className: "cards" },
        ...BLOCKS[lane.id].map((block) =>
          blockCard(lane, block, {
            inSlot: false,
            blocked: lane.id === "model" && modelChoiceBlocked(block),
            onPlace: () => onPlace(block.id),
          }),
        ),
      ),
    ),
    lane,
    "2",
  );
}

function summaryComponent() {
  if (!isComplete()) {
    return el("p", { className: "summary" }, "Place a block in each slot, then run.");
  }
  const state = blockById("state", selection.state);
  const model = selection.model === "preexisting" ? chosenFactory() : null;
  const actions = thenSummary();
  const qubits = qubitPhrase();
  const total = formatSetting("total");
  const modelPhrase = model
    ? [el("strong", {}, model.title), " model", ...termSummary()]
    : [el("strong", {}, "added operators")];
  return el(
    "p",
    { className: "summary" },
    "Start from ",
    el("strong", {}, state.title),
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
  if (running || !accepted()) return;
  const blob = new Blob([acceptedBody], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: "shadowsim-board.json" });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function importBoardFile(file) {
  if (running || !file || typeof file.text !== "function") return;
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
      const chosen = input.files && input.files[0];
      input.value = "";
      if (chosen) void importBoardFile(chosen);
    },
  });
  return el(
    "span",
    { className: "board-import" },
    file,
    el("button", {
      className: "board-file import-board",
      type: "button",
      disabled: running,
      onclick: () => file.click(),
    }, "Import board"),
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
        value: settings[key],
        "aria-label": label,
        readonly: key === "qubits" && (stateOwnsQubits() || factorySetsQubits()),
        oninput: (event) => {
          if (key === "qubits" && (stateOwnsQubits() || factorySetsQubits())) return;
          settings[key] = event.target.value.trim();
          if (key === "qubits") {
            qubitsSource = settings.qubits === "" ? null : "user";
            syncMeasureChip();
            syncHamiltonianQubits();
            refreshHamiltonianChips();
            refreshLocalHamiltonianChips();
          }
          refreshSummaryAndPreview();
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
      el("button", {
        className: "board-file export-board",
        type: "button",
        disabled: running || !accepted(),
        onclick: () => downloadBoard(),
      }, "Export board"),
      importBoardButton(),
      el("button", {
        className: "clear",
        type: "button",
        disabled: running,
        onclick: () => emptyBoard(),
      }, "Clear"),
      el("button", {
        className: "run",
        type: "button",
        disabled: !running && !runAllowed(),
        onclick: () => void (running ? cancelRun() : startRun()),
      }, running ? "Cancel" : "Run simulation"),
    ),
  );
}

function releaseStatusHold() {
  statusHold = null;
}

function documentBody() {
  return JSON.stringify(runRequest());
}

function cancelScheduledCheck() {
  if (checkTimer != null && typeof clearTimeout === "function") clearTimeout(checkTimer);
  checkTimer = null;
}

function dropAcceptance() {
  acceptedBody = null;
  acceptedQubits = null;
  rejectedBody = null;
  checkError = null;
  checkInFlight = false;
  pendingBody = null;
}

function scheduleCheck() {
  if (!locallyReady()) {
    cancelScheduledCheck();
    checkSerial += 1;
    dropAcceptance();
    return;
  }
  const requested = documentBody();
  if (acceptedBody === requested && checkError == null) {
    cancelScheduledCheck();
    pendingBody = null;
    return;
  }
  if (checkError != null && rejectedBody === requested) {
    cancelScheduledCheck();
    pendingBody = null;
    return;
  }
  if (pendingBody === requested) return;
  cancelScheduledCheck();
  checkSerial += 1;
  const serial = checkSerial;
  pendingBody = requested;
  acceptedBody = null;
  acceptedQubits = null;
  rejectedBody = null;
  checkError = null;
  checkInFlight = false;
  if (typeof fetch !== "function" || typeof setTimeout !== "function") {
    pendingBody = null;
    return;
  }
  checkTimer = setTimeout(() => {
    checkTimer = null;
    void postCheck(requested, serial);
  }, CHECK_DELAY);
}

function applyAcceptedQubits() {
  if (!factorySetsQubits() || acceptedQubits == null) return;
  settings.qubits = String(acceptedQubits);
  qubitsSource = "model";
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
    const error = typeof payload.error === "string" && payload.error ? payload.error : "The selection was rejected.";
    return { ok: false, error };
  }
  return { ok: true, qubits: payload.qubits };
}

async function postCheck(requested, serial) {
  if (serial !== checkSerial || requested !== documentBody()) return;
  checkInFlight = true;
  showCheckStatus();
  try {
    const result = await requestCheck(requested);
    if (serial !== checkSerial || requested !== documentBody()) return;
    if (!result.ok) {
      checkError = result.error;
      rejectedBody = requested;
      acceptedBody = null;
      acceptedQubits = null;
      return;
    }
    acceptedQubits = result.qubits;
    applyAcceptedQubits();
    if (documentBody() !== requested) {
      acceptedQubits = null;
      return;
    }
    checkError = null;
    rejectedBody = null;
    acceptedBody = requested;
  } catch {
    if (serial !== checkSerial || requested !== documentBody()) return;
    checkError = "The selection could not be checked.";
    rejectedBody = requested;
    acceptedBody = null;
    acceptedQubits = null;
  } finally {
    if (serial !== checkSerial) return;
    checkInFlight = false;
    pendingBody = null;
    refreshSummaryAndPreview();
  }
}

function applyCheck(qubits) {
  if (!locallyReady()) return false;
  cancelScheduledCheck();
  checkSerial += 1;
  checkError = null;
  rejectedBody = null;
  checkInFlight = false;
  pendingBody = null;
  acceptedQubits = qubits == null ? null : Number(qubits);
  applyAcceptedQubits();
  acceptedBody = documentBody();
  refreshSummaryAndPreview();
  return true;
}

function showCheckStatus() {
  if (running) return;
  const status = document.querySelector(".status");
  if (status) status.replaceWith(statusComponent());
  const panel = document.querySelector('.panel[aria-label="Code preview"]');
  const body = panel?.querySelector("pre.script, p.placeholder");
  if (body) body.replaceWith(codeBody());
  syncBoardJson(panel);
  syncCopyButton();
  syncRunButton();
}

function refreshSummaryAndPreview() {
  scheduleCheck();
  syncModelQubits();
  syncFactoryDetail();
  syncModelAlert();
  const summary = document.querySelector(".summary");
  if (summary) summary.replaceWith(summaryComponent());
  if (!running) {
    releaseStatusHold();
    const status = document.querySelector(".status");
    if (status) status.replaceWith(statusComponent());
  }
  const panel = document.querySelector('.panel[aria-label="Code preview"]');
  const body = panel?.querySelector("pre.script, p.placeholder");
  if (body) body.replaceWith(codeBody());
  syncBoardJson(panel);
  syncCopyButton();
  syncRunButton();
  rememberBoard();
  clearStaleResults();
}

function stateEntryMessage(preview) {
  const field = stateField(selection.state);
  const ending = preview ? " and total time to preview the script." : " and total time.";
  return `${field?.empty || "Enter an initial state"}${ending}`;
}

function statusMessage() {
  if (statusHold) return statusHold;
  if (!isComplete()) return operatorStatus(false) ?? socketStatus(false) ?? "Place a block in each slot.";
  if (factoryAlert()) return `${factoryAlert()}.`;
  if (stateInputProblem() === "size") return stateSizeStatus(false);
  if (stateInputProblem() === "empty") return stateEntryMessage(false);
  const numbers = numberProblem(false);
  if (numbers) return numbers;
  if (simParamProblem(false)) return simParamProblem(false);
  if (!simParamsReady()) return "Enter simulator parameters.";
  if (!sameTimeGrid()) return "Use the same number of time steps for every simulator.";
  if (!measureSitesReady()) return "Pick at least one qubit.";
  if (countsStatus(false)) return countsStatus(false);
  if (shotsProblem(false)) return shotsProblem(false);
  if (!shotsReady()) return "Enter a shot count.";
  if (!check(checks.backendFieldsReady)) return check(checks.backendFieldStatus, false);
  if (!savePathReady()) return pathMessage(false);
  if (checkError) return `${checkError.replace(/[.!?]$/, "")}.`;
  if (checkInFlight || !accepted()) return "Checking the selection.";
  return "Ready to run.";
}

function statusComponent() {
  const ready = !statusHold && runAllowed();
  return el(
    "p",
    { className: ready ? "status ready" : "status", role: "status" },
    statusMessage(),
  );
}

function syncCopyButton() {
  const copy = document.querySelector('.panel[aria-label="Code preview"] .copy');
  if (!copy) return;
  const enabled = Boolean(previewText());
  copy.disabled = !enabled;
  if (enabled) {
    if (typeof copy.removeAttribute === "function") copy.removeAttribute("disabled");
    return;
  }
  copy.setAttribute("disabled", "");
  copy.textContent = "Copy";
}

function showCopied(button, label = "Copy") {
  if (copiedButton && copiedButton !== button && copiedButton.isConnected !== false) {
    copiedButton.textContent = copiedLabel;
  }
  copiedButton = button;
  copiedLabel = label;
  button.textContent = "Copied";
  if (copyTimer) clearTimeout(copyTimer);
  copyTimer = setTimeout(() => {
    copyTimer = 0;
    if (button.isConnected === false) return;
    button.textContent = label;
    if (copiedButton === button) copiedButton = null;
  }, 1500);
}

function copyPreview(event) {
  const code = previewText();
  if (!code) return;
  const pending = navigator.clipboard?.writeText?.(code);
  if (!pending || typeof pending.then !== "function") return;
  const button = event?.currentTarget;
  pending.then(() => {
    if (button) showCopied(button);
  }, () => {});
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
  if (accepted()) return acceptedBody;
  const file = runRequest();
  delete file.server;
  return JSON.stringify(file);
}

function copyBoard(event) {
  const pending = navigator.clipboard?.writeText?.(boardFileText());
  if (!pending || typeof pending.then !== "function") return;
  const button = event?.currentTarget;
  pending.then(() => {
    if (button) showCopied(button, "Copy board");
  }, () => {});
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

function syncBoardJson(panel) {
  const node = panel?.querySelector("pre.board-json");
  if (!node) return;
  const text = boardFileText();
  node.textContent = text;
  node.replaceChildren(document.createTextNode(text));
}

function codeBody() {
  const code = previewText();
  if (code) return el("pre", { className: "script" }, code);
  let message = operatorStatus(true) ?? socketStatus(true) ?? "Place a block in each slot to preview the script.";
  if (isComplete()) {
    const numbers = numberProblem(true);
    if (factoryAlert()) message = `${factoryAlert()} to preview the script.`;
    else if (stateInputProblem() === "size") message = stateSizeStatus(true);
    else if (stateInputProblem() === "empty") message = stateEntryMessage(true);
    else if (numbers) message = numbers;
    else if (simParamProblem(true)) message = simParamProblem(true);
    else if (!simParamsReady()) message = "Enter simulator parameters to preview the script.";
    else if (!sameTimeGrid()) message = "Use the same number of time steps to preview the script.";
    else if (!measureSitesReady()) message = "Pick at least one qubit to preview the script.";
    else if (countsStatus(true)) message = countsStatus(true);
    else if (shotsProblem(true)) message = shotsProblem(true);
    else if (!shotsReady()) message = "Enter a shot count to preview the script.";
    else if (!check(checks.backendFieldsReady)) message = check(checks.backendFieldStatus, true);
    else if (!savePathReady()) message = pathMessage(true);
    else if (checkError) message = `${checkError.replace(/[.!?]$/, "")} to preview the script.`;
    else message = "Checking the selection.";
  }
  return el("p", { className: "placeholder" }, message);
}

function setStatus(message, ready) {
  const status = document.querySelector(".status");
  if (!status) return;
  status.replaceWith(el("p", { className: ready ? "status ready" : "status", role: "status" }, message));
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
  shownRun = null;
  setResults(resultsPlaceholder());
}

function clearStaleResults() {
  if (shownRun == null) return;
  if (shownRun === JSON.stringify(runRequest())) return;
  clearResults();
}

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
    label: typeof shared[index] === "string" && shared[index] ? shared[index] : `Observable ${index}`,
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
  const name = series[0] && series[0].name ? String(series[0].name) : "reference";
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
  const matched = simulator == null ? curves : curves.filter((curve) => curve.simulator === simulator);
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
  const saved = Array.isArray(payload.saved) ? payload.saved.filter((item) => typeof item === "string") : [];
  if (saved.length) notes.push(`Saved to ${saved.join(", ")}`);
  if (typeof payload.exported === "string" && payload.exported) notes.push(`Exported to ${payload.exported}`);
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
    const label = typeof labels[index] === "string" && labels[index] ? labels[index] : `Observable ${index}`;
    choices.push({ key: String(index), label });
  }
  return choices;
}

function chartViews(payload) {
  const series = Array.isArray(payload.series) ? payload.series : [];
  if (series.length < 2) return [];
  const views = [{ key: "curves", label: "Curves" }];
  for (const entry of series) {
    if (!entry || !entry.name) continue;
    views.push({ key: String(entry.name), label: String(entry.name) });
  }
  views.push({ key: "error", label: "Error" });
  return views;
}

function resultsComponent(payload) {
  const note = savedNote(payload);
  const views = chartViews(payload);
  const choices = observableChoices(payload);
  const host = el("div", { className: "chart-host" });
  let view = "curves";
  let observable = null;
  function draw() {
    host.replaceChildren(chartComponent(payload, view, observable));
    for (const button of viewButtons) {
      button.setAttribute("aria-pressed", button.getAttribute("data-view") === view ? "true" : "false");
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
    ? el("div", { className: "chart-switch", role: "tablist", "aria-label": "Observable" }, ...observableButtons)
    : null;
  const viewSwitcher = viewButtons.length
    ? el("div", { className: "chart-switch", role: "tablist", "aria-label": "Chart" }, ...viewButtons)
    : null;
  if (!note && !observableSwitcher && !viewSwitcher && !resources) return host.children[0];
  return el("div", { className: "results" }, note, observableSwitcher, viewSwitcher, host, resources);
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
      fraction == null ? "" : hoverReadout(payload, nearestTimeIndex(payload, fraction), view, observable);
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

function runningLabel(elapsedMs) {
  const total = Math.max(0, Math.floor(elapsedMs / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return `Running · ${minutes}:${seconds}`;
}

function showRunningClock() {
  if (!running) return;
  const status = document.querySelector(".status");
  if (!status) return;
  status.className = "status";
  status.setAttribute("aria-live", "off");
  status.textContent = runningLabel(Date.now() - runStartedAt);
}

function stopRunClock() {
  if (runTimer == null) return;
  clearInterval(runTimer);
  runTimer = null;
}

function setButtonDisabled(button, disabled) {
  if (!button) return;
  button.disabled = disabled;
  if (disabled) {
    button.setAttribute("disabled", "");
    return;
  }
  if (typeof button.removeAttribute === "function") button.removeAttribute("disabled");
}

function syncBoardFileButtons() {
  setButtonDisabled(document.querySelector(".export-board"), running || !accepted());
  setButtonDisabled(document.querySelector(".import-board"), running);
}

function syncRunButton() {
  syncBoardFileButtons();
  const button = document.querySelector(".run");
  if (!button || running) return;
  button.disabled = !runAllowed();
}

function setRunButton(label) {
  const button = document.querySelector(".run");
  if (!button) return;
  button.textContent = label;
  button.disabled = label !== "Cancel" && !runAllowed();
  const clear = document.querySelector(".clear");
  if (clear) clear.disabled = label === "Cancel";
  syncBoardFileButtons();
}

async function cancelRun() {
  if (!running) return;
  try {
    await fetch("/runs/cancel", { method: "POST" });
  } catch {
    // The run request stays open and reports the outcome.
  }
}

function stateValue() {
  const field = stateField(selection.state);
  const text = stateTextOf(selection.state);
  if (!field) return null;
  if (field.kind === "bits") return text;
  return numberList(text, field.cap);
}

function postedMeasure() {
  const measure = { id: selection.measure, sites: explicitSites() };
  const field = blockById("measure", selection.measure)?.field;
  if (field?.kind === "expression") measure.expression = (expressionText[selection.measure] ?? "").trim();
  return measure;
}

function postedActions() {
  const actions = { ids: [...placedThens] };
  for (const block of BLOCKS.then) {
    if (block.field?.kind !== "path") continue;
    actions[block.field.key] = pathValue(block.id).trim();
  }
  return actions;
}

function modelArguments() {
  if (selection.model !== "preexisting") return {};
  const body = { ...(postedFactory() ?? {}) };
  if (chosenFactory()?.qubits) body.n_qubits = settings.qubits;
  return body;
}

function postedModel() {
  const terms = postedTerms();
  if (Array.isArray(terms) && terms.length) return { terms, qubits: settings.qubits };
  return {
    id: selection.model === "preexisting" ? preexistingId : selection.model,
    arguments: modelArguments(),
  };
}

function runRequest() {
  return {
    version: 1,
    total: settings.total,
    state: { id: selection.state, value: stateValue() },
    model: postedModel(),
    simulators: placedSims.map(entryBody),
    measure: postedMeasure(),
    actions: postedActions(),
  };
}

function showRunResult(requested, node) {
  if (JSON.stringify(runRequest()) !== requested) {
    clearResults();
    return false;
  }
  shownRun = requested;
  setResults(node);
  return true;
}

async function startRun() {
  if (running || !runAllowed()) return;
  running = true;
  releaseStatusHold();
  runStartedAt = Date.now();
  setRunButton("Cancel");
  showRunningClock();
  runTimer = setInterval(showRunningClock, 1000);
  const requested = JSON.stringify(runRequest());
  shownRun = requested;
  setResults(el("p", { className: "placeholder" }, "Running."));
  try {
    const response = await fetch("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: requested,
    });
    const payload = await response.json();
    if (payload.cancelled) {
      if (showRunResult(requested, el("p", { className: "placeholder" }, "Cancelled."))) {
        statusHold = "Cancelled.";
      }
      return;
    }
    if (!response.ok) {
      const message = payload.error || "The run failed.";
      if (showRunResult(requested, el("p", { className: "placeholder" }, message))) statusHold = message;
      return;
    }
    releaseStatusHold();
    showRunResult(requested, resultsComponent(payload));
  } catch {
    if (showRunResult(requested, el("p", { className: "placeholder" }, "The run failed."))) {
      statusHold = "The run failed.";
    }
  } finally {
    stopRunClock();
    running = false;
    setRunButton("Run simulation");
    if (statusHold) setStatus(statusHold);
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
  shownRun = null;
  board.replaceChildren(
    layoutComponent(),
    settingsComponent(),
    summaryComponent(),
    statusComponent(),
    panelsComponent(),
  );
  rememberBoard();
  scheduleCheck();
}

function termSummary() {
  const nodes = [];
  modelTerms.forEach((term, index) => {
    const block = blockById("model", term.id);
    if (!block) return;
    nodes.push(index === 0 ? ", plus " : ", ");
    nodes.push(el("strong", {}, block.title));
  });
  return nodes;
}

function measureDetail(count) {
  const block = blockById("measure", selection.measure);
  if (count == null) return block?.detail ?? "";
  const sites = selectedSites(count);
  if (!sites.length) return "No qubits";
  if (sites.length === count) return block?.detail ?? "";
  return `Qubits ${sites.join(", ")}`;
}

function measurePhrase() {
  const block = blockById("measure", selection.measure);
  if (!block) return "";
  const count = qubitCount();
  const sites = selectedSites(count);
  if (count == null || sites.length === count) return block.phrase;
  if (!sites.length) return `${block.title} on no qubits`;
  return `${block.title} on qubits ${sites.join(", ")}`;
}

function explicitSites() {
  const count = qubitCount();
  if (measureSites == null || count == null) return null;
  const sites = selectedSites(count);
  return sites.length === count ? null : sites;
}

function toggleMeasureSite(site, checked) {
  const count = qubitCount();
  if (count == null) return;
  const next = selectedSites(count).filter((index) => index !== site);
  if (checked) next.push(site);
  next.sort((left, right) => left - right);
  measureSites = next.length === count ? null : next;
}

function measureFields() {
  const count = qubitCount();
  const chosen = new Set(selectedSites(count));
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
            toggleMeasureSite(site, event.target.checked);
            const chip = event.target.closest(".chip");
            const detail = chip?.querySelector(".measure-detail");
            if (detail) detail.textContent = measureDetail(qubitCount());
            const hint = chip?.querySelector(".counts-hint");
            if (hint) hint.textContent = countsHint();
            const input = chip?.querySelector(".counts-field input");
            if (input) input.placeholder = countsPlaceholder();
            refreshSummaryAndPreview();
          },
        }),
        String(site),
      ),
    );
  }
  return el("div", { className: "measure-fields" }, ...boxes);
}

function countsHint() {
  const sites = selectedSites(qubitCount());
  if (!sites.length) return "Pick at least one qubit.";
  const label = sites.length === 1 ? "qubit" : "qubits";
  return `Keys list ${label} ${sites.join(", ")} in that order. shots is the total.`;
}

function countsPlaceholder() {
  const width = Math.max(selectedSites(qubitCount()).length, 1);
  return `counts["${"0".repeat(width)}"] / shots`;
}

function countsField() {
  return el(
    "label",
    { className: "counts-field" },
    "Expression",
    el("input", {
      type: "text",
      "aria-label": "Counts expression",
      value: expressionText[selection.measure] ?? "",
      placeholder: countsPlaceholder(),
      spellcheck: "false",
      oninput: (event) => {
        expressionText[selection.measure] = event.target.value;
        refreshSummaryAndPreview();
      },
    }),
    el("span", { className: "counts-hint" }, countsHint()),
  );
}

function syncMeasureChip() {
  const chip = document.querySelector(".chip.measure");
  if (!chip) return;
  const count = qubitCount();
  const detail = chip.querySelector(".measure-detail");
  if (detail) detail.textContent = measureDetail(count);
  if (count == null) {
    measureOpen = false;
    chip.classList.remove("is-editing");
    chip.querySelector(".done")?.remove();
    chip.querySelector(".measure-fields")?.remove();
    chip.querySelector(".counts-field")?.remove();
    return;
  }
  if (!measureOpen) return;
  const fields = chip.querySelector(".measure-fields");
  const next = measureFields();
  if (fields) fields.replaceWith(next);
  else chip.append(next);
  if (blockById("measure", selection.measure)?.field?.kind !== "expression") return;
  const hint = chip.querySelector(".counts-hint");
  if (hint) hint.textContent = countsHint();
  else chip.append(countsField());
}

function measureChip(block) {
  const count = qubitCount();
  const open = measureOpen && count != null;
  return el(
    "div",
    { className: `chip tone-green measure${open ? " is-editing" : ""}` },
    el(
      "div",
      { className: "measure-head" },
      el(
        "button",
        {
          type: "button",
          onclick: (event) => {
            if (open || qubitCount() == null) return;
            measureOpen = true;
            replaceChip(event.currentTarget, measureChip(block));
          },
        },
        el("strong", {}, block.title),
        el("span", { className: "measure-detail" }, measureDetail(count)),
      ),
      el(
        "div",
        { className: "measure-actions" },
        open
          ? el(
              "button",
              {
                className: "done",
                type: "button",
                onclick: (event) => {
                  measureOpen = false;
                  replaceChip(event.currentTarget, measureChip(block));
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

function pathMessage(preview) {
  const missing = missingPaths();
  const tail = preview ? " to preview the script." : ".";
  const names = missing.map((id) => String(blockById("then", id)?.field?.aria || "path").toLowerCase());
  const article = (name) => (/^[aeiou]/i.test(name) ? "an" : "a");
  if (!names.length) return `Enter a path${tail}`;
  return `Enter ${names.map((name) => `${article(name)} ${name}`).join(" and ")}${tail}`;
}

function thenSummary() {
  const phrases = placedThens.map((id) => blockById("then", id)?.phrase).filter(Boolean);
  const nodes = [];
  phrases.forEach((phrase, index) => {
    if (index) nodes.push(index === phrases.length - 1 ? " and " : ", ");
    nodes.push(el("strong", {}, phrase));
  });
  return nodes;
}

function methodPhrase(entry) {
  const title = blockById("simulator", entry.id)?.title;
  if (!title) return null;
  const backend = blockById("backend", entry.backend);
  if (!isReference(entry) && backend) return `${title} on ${backend.phrase}`;
  return title;
}

function simulatorSummary() {
  const titles = placedSims.map(methodPhrase).filter(Boolean);
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

function repaintSlot(laneId) {
  const current = document.querySelector(`.slot[data-slot="${laneId}"]`);
  const lane = laneById(laneId);
  if (current && lane) current.replaceWith(slotComponent(lane));
}

function repaintPalette(laneId) {
  const current = document.querySelector(`.lane[data-palette="${laneId}"]`);
  const lane = laneById(laneId);
  if (!current || !lane) return;
  current.replaceWith(paletteComponent(lane, (blockId) => place(lane.id, blockId)));
}

function commitLane(laneId, palette) {
  repaintSlot(laneId);
  if (palette) repaintPalette(laneId);
  refreshHamiltonianChips();
  refreshLocalHamiltonianChips();
  refreshSummaryAndPreview();
  clearResults();
}

function place(laneId, blockId) {
  if (running) return;
  const block = blockById(laneId, blockId);
  if (laneId === "model" && modelChoiceBlocked(block)) return;
  if (laneId === "simulator") {
    placedSims.push({
      id: blockId,
      key: ++simKey,
      params: freshParams(blockId),
      open: true,
      backend: null,
      shots: DEFAULT_SHOTS,
      shotsOpen: false,
    });
    selection.simulator = placedSims[0].id;
  } else if (laneId === "model" && block?.adds) {
    modelTerms.push({ id: blockId, key: ++modelTermKey, matrix: "", sites: [] });
  }
  else if (laneId === "model" && blockId === "preexisting") {
    selection.model = "preexisting";
    if (!preexistingId) preexistingId = modelFactories[0]?.id ?? null;
    preexistingOpen = true;
  } else if (laneId === "state") {
    selection.state = blockId;
    stateOpen = true;
  } else if (laneId === "measure") {
    selection.measure = blockId;
    measureOpen = qubitCount() != null;
  } else if (laneId === "then") {
    if (!placedThens.includes(blockId)) placedThens.push(blockId);
    selection.then = placedThens[0] ?? null;
    if (block?.field?.kind === "path") pathOpen[blockId] = true;
  } else selection[laneId] = blockId;
  syncModelQubits();
  syncStateQubits();
  dragging = null;
  releaseStatusHold();
  commitLane(laneId, laneId === "model");
}

function removeThen(id) {
  if (running) return;
  const index = placedThens.indexOf(id);
  if (index >= 0) placedThens.splice(index, 1);
  selection.then = placedThens[0] ?? null;
  releaseStatusHold();
  commitLane("then");
}

function attachBackend(backendId, key) {
  if (running) return;
  const backend = blockById("backend", backendId);
  if (!backend) return;
  const target =
    key == null
      ? placedSims.find((entry) => !isReference(entry) && !entry.backend && backendFits(entry, backendId))
      : placedSims.find((entry) => entry.key === key);
  if (!target || isReference(target) || !backendFits(target, backendId)) {
    const open = placedSims.filter((entry) => !isReference(entry) && (key == null ? !entry.backend : entry.key === key));
    const blocked = open.find((entry) => blockById("simulator", entry.id)?.samples && !backend.shots);
    const title = blocked ? blockById("simulator", blocked.id)?.title : null;
    if (title) statusHold = `${title} needs a backend with a shot budget.`;
    else if (!placedSims.some((entry) => !isReference(entry))) statusHold = "Place a simulator before its backend.";
    else statusHold = "Snap a backend onto an open simulator.";
    dragging = null;
    document.querySelectorAll?.(".is-over").forEach((node) => node.classList.remove("is-over"));
    setStatus(statusHold);
    return;
  }
  target.backend = backendId;
  if (backend.fields?.length) {
    target.backendFields = { ...(target.backendFields ?? {}) };
    for (const field of backend.fields) {
      if (!String(target.backendFields[field.name] ?? "").trim()) target.backendFields[field.name] = field.default;
    }
  }
  if (backend.shots) {
    if (!positiveIntText(String(target.shots ?? "").trim())) target.shots = DEFAULT_SHOTS;
    target.shotsOpen = true;
    target.backendOpen = false;
  } else if (backend.fields?.length) {
    target.shotsOpen = false;
    target.backendOpen = true;
  } else {
    target.shotsOpen = false;
    target.backendOpen = false;
  }
  dragging = null;
  releaseStatusHold();
  commitLane("simulator");
}

function removeBackend(key) {
  if (running) return;
  const entry = placedSims.find((item) => item.key === key);
  if (!entry) return;
  entry.backend = null;
  entry.shotsOpen = false;
  entry.backendOpen = false;
  releaseStatusHold();
  commitLane("simulator");
}

function removeSimulator(key) {
  if (running) return;
  const index = placedSims.findIndex((entry) => entry.key === key);
  if (index >= 0) placedSims.splice(index, 1);
  selection.simulator = placedSims[0]?.id ?? null;
  releaseStatusHold();
  commitLane("simulator");
}

function removeTerm(key) {
  if (running) return;
  const index = modelTerms.findIndex((term) => term.key === key);
  if (index >= 0) modelTerms.splice(index, 1);
  if (!modelTerms.some((term) => term.id === "hamiltonian") && qubitsSource === "hamiltonian") {
    settings.qubits = "";
    qubitsSource = null;
    syncMeasureChip();
    writeQubitField();
  } else syncHamiltonianQubits();
  releaseStatusHold();
  commitLane("model", true);
}

function clearLane(laneId) {
  if (running) return;
  if (laneId === "simulator") placedSims.splice(0, placedSims.length);
  if (laneId === "then") placedThens.splice(0, placedThens.length);
  if (laneId === "state") stateOpen = false;
  if (laneId === "measure") {
    measureOpen = false;
    measureSites = null;
  }
  if (laneId === "state" && qubitsSource === "state" && settings.qubits !== "") qubitsSource = "user";
  if (laneId === "model" && qubitsSource === "hamiltonian") {
    settings.qubits = "";
    qubitsSource = null;
    syncMeasureChip();
    writeQubitField();
  }
  if (laneId === "model" && qubitsSource === "model") {
    selection.model = null;
    syncModelQubits();
  }
  selection[laneId] = null;
  releaseStatusHold();
  commitLane(laneId, laneId === "model");
}

function knownBlock(laneId, blockId) {
  return typeof blockId === "string" && Boolean(blockById(laneId, blockId));
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
  const rows = matrix.map((row) => `[${(Array.isArray(row) ? row : []).map((entry) => complexText(entry)).join(", ")}]`);
  return `[${rows.join(", ")}]`;
}

function resetBoard() {
  selection.state = null;
  selection.model = null;
  selection.simulator = null;
  selection.backend = null;
  selection.measure = null;
  selection.then = null;
  settings.qubits = "";
  settings.total = "";
  for (const key of Object.keys(stateText)) delete stateText[key];
  qubitsSource = null;
  preexistingId = null;
  factoryText = {};
  modelTerms.splice(0, modelTerms.length);
  placedSims.splice(0, placedSims.length);
  placedThens.splice(0, placedThens.length);
  for (const key of Object.keys(actionText)) delete actionText[key];
  for (const key of Object.keys(pathOpen)) delete pathOpen[key];
  for (const block of BLOCKS.then) {
    if (block.field?.kind === "path") actionText[block.id] = block.field.default ?? "";
  }
  measureSites = null;
  for (const key of Object.keys(expressionText)) delete expressionText[key];
  stateOpen = false;
  measureOpen = false;
  preexistingOpen = false;
}

function applyState(state) {
  if (!plainObject(state)) return;
  const id = knownBlock("state", state.id) ? state.id : null;
  selection.state = id;
  if (!id) return;
  const field = stateField(id);
  if (field?.kind === "bits" && typeof state.value === "string") stateText[id] = state.value;
  else if (field?.kind === "numbers") stateText[id] = numberListText(state.value);
}

function applyModel(model) {
  if (!plainObject(model)) return;
  const terms = Array.isArray(model.terms) ? model.terms : [];
  if (terms.length) {
    settings.qubits = textNumber(model.qubits);
    qubitsSource = "user";
    const next = [];
    for (const term of terms) {
      if (!plainObject(term) || !knownBlock("model", term.id) || !blockById("model", term.id)?.adds) continue;
      next.push({
        id: term.id,
        matrix: matrixText(term.matrix),
        sites: Array.isArray(term.sites) ? term.sites.filter((site) => Number.isInteger(site)) : [],
      });
    }
    modelTerms.splice(0, modelTerms.length, ...next.map((term) => ({ ...term, key: ++modelTermKey })));
    return;
  }
  const id = typeof model.id === "string" && modelFactories.some((item) => item.id === model.id) ? model.id : null;
  if (!id) return;
  selection.model = "preexisting";
  preexistingId = id;
  const args = plainObject(model.arguments) ? model.arguments : {};
  if ("n_qubits" in args) {
    settings.qubits = textNumber(args.n_qubits);
    qubitsSource = "user";
  }
  for (const [key, value] of Object.entries(args)) {
    if (key === "n_qubits") continue;
    if (typeof value === "string" || typeof value === "number") factoryText[key] = textNumber(value);
  }
}

function simParams(args) {
  const params = {};
  if (!plainObject(args)) return params;
  if ("time_steps" in args) params.timeSteps = textNumber(args.time_steps);
  if ("num_steps" in args) params.numSteps = textNumber(args.num_steps);
  if ("seed" in args) params.seed = textNumber(args.seed);
  if ("trotter_depth" in args) params.trotterDepth = textNumber(args.trotter_depth);
  if ("order" in args) params.order = textNumber(args.order);
  return params;
}

function applySims(entries) {
  const next = [];
  for (const entry of Array.isArray(entries) ? entries : []) {
    if (!plainObject(entry) || !knownBlock("simulator", entry.id)) continue;
    const params = simParams(entry.arguments);
    const row = {
      id: entry.id,
      params: Object.keys(params).length ? params : freshParams(entry.id),
      open: false,
      backend: null,
      shots: DEFAULT_SHOTS,
      shotsOpen: false,
      backendOpen: false,
    };
    const backend = entry.backend;
    if (plainObject(backend) && typeof backend.id === "string" && backendFits(row, backend.id)) {
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
  placedSims.splice(0, placedSims.length, ...next.map((entry) => ({ ...entry, key: ++simKey })));
  selection.simulator = placedSims[0]?.id ?? null;
}

function applyMeasure(measure) {
  if (!plainObject(measure)) return;
  selection.measure = knownBlock("measure", measure.id) ? measure.id : null;
  measureSites = Array.isArray(measure.sites) ? measure.sites.filter((site) => Number.isInteger(site)) : null;
  const field = blockById("measure", selection.measure)?.field;
  if (field?.kind === "expression" && typeof measure.expression === "string") {
    expressionText[selection.measure] = measure.expression;
  }
}

function applyActions(actions) {
  if (!plainObject(actions)) return;
  const next = [];
  for (const id of Array.isArray(actions.ids) ? actions.ids : []) {
    if (knownBlock("then", id) && !next.includes(id)) next.push(id);
  }
  placedThens.splice(0, placedThens.length, ...next);
  selection.then = next[0] ?? null;
  for (const block of BLOCKS.then) {
    const field = block.field;
    if (field?.kind === "path" && typeof actions[field.key] === "string") actionText[block.id] = actions[field.key];
  }
}

function applyDocument(saved) {
  if (!plainObject(saved)) return;
  resetBoard();
  if (typeof saved.total === "string" || typeof saved.total === "number") settings.total = textNumber(saved.total);
  applyState(saved.state);
  applyModel(saved.model);
  applySims(saved.simulators);
  applyMeasure(saved.measure);
  applyActions(saved.actions);
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
  if (!plainObject(saved)) {
    forgetBoard();
    return;
  }
  let response = null;
  let payload = {};
  try {
    response = await fetch("/runs/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: raw,
    });
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
  } catch {
    statusHold = "The selection could not be checked.";
    return;
  }
  if (!response.ok || !Number.isInteger(payload.qubits) || payload.qubits < 1) {
    statusHold = typeof payload.error === "string" && payload.error ? payload.error : "The selection was rejected.";
    return;
  }
  applyDocument(saved);
  acceptedQubits = payload.qubits;
  applyAcceptedQubits();
  checkError = null;
  rejectedBody = null;
  checkInFlight = false;
  pendingBody = null;
  if (documentBody() === raw) {
    acceptedBody = raw;
    releaseStatusHold();
  } else acceptedBody = null;
}

function rememberBoard() {
  if (!boardReady || !accepted()) return;
  try {
    localStorage.setItem(BOARD_KEY, acceptedBody);
  } catch {
    // Storage can be unavailable. The page still runs.
  }
}

function holdImportStatus(message) {
  statusHold = message;
  const status = document.querySelector(".status");
  if (status) status.replaceWith(statusComponent());
}

async function importBoardText(raw) {
  if (running) return;
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
  let result = null;
  try {
    result = await requestCheck(raw);
  } catch {
    if (!running) holdImportStatus("The selection could not be checked.");
    return;
  }
  if (running || !result.ok) {
    if (!running) holdImportStatus(result && result.error ? result.error : "The selection was rejected.");
    return;
  }
  cancelScheduledCheck();
  checkSerial += 1;
  applyDocument(saved);
  acceptedQubits = result.qubits;
  applyAcceptedQubits();
  checkError = null;
  rejectedBody = null;
  checkInFlight = false;
  pendingBody = null;
  if (documentBody() === raw) {
    acceptedBody = raw;
    releaseStatusHold();
  } else acceptedBody = null;
  const board = document.querySelector(".board");
  if (board) draw(board);
}

function emptyBoard() {
  if (running) return;
  resetBoard();
  forgetBoard();
  releaseStatusHold();
  const board = document.querySelector(".board");
  if (board) draw(board);
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
  limits = payload;
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

async function loadLane(path, lane, key) {
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
      laneNotes[lane] = payload.error || `Could not load ${key}.`;
      BLOCKS[lane] = [];
      selection[lane] = null;
      return;
    }
    if (lane === "model") {
      modelFactories = items.filter((item) => !item.adds);
      BLOCKS.model = [
        {
          id: "preexisting",
          title: "Preexisting model",
          detail: "Choose a built-in model",
          phrase: "a preexisting model",
        },
        ...items.filter((item) => item.adds),
      ];
      if (preexistingId && !modelFactories.some((item) => item.id === preexistingId)) preexistingId = null;
    } else BLOCKS[lane] = items;
    if (lane === "then") {
      for (const item of items) {
        if (item.field?.kind === "path" && !Object.hasOwn(actionText, item.id)) {
          actionText[item.id] = item.field.default ?? "";
        }
      }
    }
    laneNotes[lane] = "";
    if (selection[lane] != null && !blockById(lane, selection[lane])) selection[lane] = null;
  } catch {
    laneNotes[lane] = `Could not load ${key}.`;
    BLOCKS[lane] = [];
    selection[lane] = null;
  }
}

const builder = document.querySelector("#builder");
if (builder) {
  Promise.all([
    loadLane("/models", "model", "models"),
    loadLane("/simulators", "simulator", "simulators"),
    loadLane("/backends", "backend", "backends"),
    loadLane("/states", "state", "states"),
    loadLane("/measurements", "measure", "measurements"),
    loadLane("/actions", "then", "actions"),
    loadLimits(),
  ]).then(async (results) => {
    if (!results[6]) {
      builder.append(el("p", { className: "placeholder" }, "Could not load limits."));
      return;
    }
    await restoreBoard();
    boardReady = true;
    mount(builder);
  });
}
