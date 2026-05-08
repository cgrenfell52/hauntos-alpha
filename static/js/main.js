const page = document.body.dataset.page;

let devices = null;
let routines = null;
let statusData = null;
let audioFiles = [];
let videoFiles = [];
let selectedInputId = null;
let expandedTileIndex = null;
let toastTimer = null;
let systemInfo = null;
let recentLogs = [];
let schedulerData = null;
let dirtyRoutineInputs = new Set();
let lastRuntimeKey = "";
let statusPollTimer = null;
let controllerOnline = true;
let logoPreviewOffline = false;
const setupWizardSteps = ["controller", "outputs", "inputs", "review"];
let setupWizardStep = "controller";

document.addEventListener("DOMContentLoaded", () => {
  bindShellActions();
  bindRoutineShell();
  bindMediaUploadForms();
  bindConfigImportForm();
  bindSystemActionButtons();
  bindSetupForm();
  bindSchedulerForm();
  loadPage();
  startStatusPolling();
});

window.addEventListener("beforeunload", (event) => {
  if (dirtyRoutineInputs.size === 0) {
    return;
  }

  event.preventDefault();
  event.returnValue = "";
});

async function loadPage() {
  try {
    const requests = [
      apiGet("/api/devices"),
      apiGet("/api/status"),
      apiGet("/api/routines"),
    ];

    const needsAudio = page === "inputs" || page === "audio";
    const needsVideo = page === "inputs" || page === "video";

    if (needsAudio) {
      requests.push(apiGet("/api/audio"));
    }
    if (needsVideo) {
      requests.push(apiGet("/api/video"));
    }

    const responses = await Promise.all(requests);
    setControllerConnection(true);
    devices = responses[0].devices;
    statusData = responses[1];
    routines = responses[2].routines;
    dirtyRoutineInputs = new Set();

    let responseIndex = 3;
    if (needsAudio) {
      audioFiles = responses[responseIndex].audio || [];
      responseIndex += 1;
    }
    if (needsVideo) {
      videoFiles = responses[responseIndex].video || [];
    }

    renderShellStatus();

    if (page === "dashboard") {
      renderDashboard();
    } else if (page === "outputs") {
      renderOutputsPage();
    } else if (page === "inputs") {
      renderInputsPage();
    } else if (page === "audio") {
      renderAudioPage();
    } else if (page === "video") {
      renderVideoPage();
    } else if (page === "system") {
      await renderSystemPage();
    } else if (page === "setup") {
      renderSetupPage();
    } else if (page === "scheduler") {
      await renderSchedulerPage();
    }
  } catch (error) {
    setControllerConnection(false);
    showMessage(error.message, true);
  }
}

function renderShellStatus() {
  setControllerConnection(true);
  const settings = statusData.settings || {};
  const showArmed = Boolean(settings.show_armed);
  const schedulerEnabled = Boolean(settings.scheduler?.enabled);
  const readyText = statusData.running ? "RUNNING" : showArmed ? "ARMED" : "READY";
  const detailText = statusData.running
    ? showArmed ? "Routine active / show armed" : "Routine finishing / show stopped"
    : showArmed ? "Show is armed" : "Show is stopped";
  const version = statusData.version || settings.version || "v0.1.0-alpha";

  document.body.classList.toggle("is-running", Boolean(statusData.running));
  document.body.classList.toggle("show-armed", showArmed);
  document.body.classList.toggle("scheduler-enabled", schedulerEnabled);
  setText("#shell-status", readyText);
  setText("#shell-running", detailText);
  setText("#top-status", detailText);
  setText("#running-indicator", statusData.running ? "Routine Running" : "Idle");
  setText("#scheduler-indicator", schedulerEnabled ? "Schedule On" : "Schedule Off");
  setText("#dashboard-status-word", readyText);
  setText("#dashboard-status-detail", `Controller Online / Version ${version}`);
  setText("#sidebar-version", version);
  renderShowButtons(showArmed);
}

function renderDashboard() {
  setText("#system-status", statusData.running ? "Routine running" : "Ready");
  setText("#dashboard-input-summary", `${Object.keys(devices.inputs).length} manual triggers`);
  setText("#dashboard-output-summary", outputSummaryText());

  const inputs = document.querySelector("#dashboard-inputs");
  if (inputs) {
    inputs.innerHTML = "";
    Object.entries(devices.inputs).forEach(([inputId, input]) => {
      const button = document.createElement("button");
      button.className = "trigger-button";
      button.type = "button";
      button.innerHTML = `
        <strong>${escapeHtml(input.name)}</strong>
        <span>${routineStepText(inputId)} ready</span>
      `;
      button.addEventListener("click", () => runInput(inputId));
      inputs.appendChild(button);
    });
  }

  const outputs = document.querySelector("#dashboard-outputs");
  if (outputs) {
    outputs.innerHTML = "";
    Object.entries(devices.outputs).forEach(([outputId, output]) => {
      outputs.appendChild(outputStateCard(outputId, output));
    });
  }
}

function renderShowButtons(showArmed) {
  document.querySelectorAll("[data-action='start-show']").forEach((button) => {
    button.textContent = showArmed ? "Stop Show" : "Start Show";
    button.classList.toggle("danger-button", showArmed);
    button.classList.toggle("show-stop-button", showArmed);
    button.title = showArmed
      ? "Disarm future triggers and let active routines finish."
      : "Arm inputs and scheduler for show mode.";
  });
}

function renderOutputsPage() {
  const list = document.querySelector("#outputs-list");
  if (!list) {
    return;
  }

  setText("#outputs-summary", outputSummaryText());
  list.innerHTML = "";
  Object.entries(devices.outputs).forEach(([outputId, output]) => {
    const row = document.createElement("article");
    row.className = "device-row output-row";
    row.dataset.outputId = outputId;

    row.append(
      deviceIcon("OUT"),
      deviceInfo(output.name, output.enabled ? "Enabled output" : "Disabled output"),
      outputStatePill(outputId),
      actionGroup([
        actionButton("ON", () => outputAction(outputId, "on")),
        actionButton("OFF", () => outputAction(outputId, "off")),
        actionButton("PULSE", () => outputAction(outputId, "pulse")),
      ])
    );
    list.appendChild(row);
  });
}

function renderInputsPage() {
  const list = document.querySelector("#inputs-list");
  if (!list) {
    return;
  }

  if (!selectedInputId) {
    selectedInputId = Object.keys(devices.inputs)[0];
  }

  setText("#inputs-summary", `${Object.keys(devices.inputs).length} configured inputs`);
  list.innerHTML = "";
  Object.entries(devices.inputs).forEach(([inputId, input]) => {
    const row = document.createElement("article");
    row.className = `device-row input-row ${selectedInputId === inputId ? "selected" : ""}`;
    row.addEventListener("click", (event) => {
      if (!(event.target instanceof Element) || !event.target.closest("button")) {
        selectInput(inputId);
      }
    });

    row.append(
      deviceIcon("IN"),
      deviceInfo(input.name, inputSummaryText(inputId, input)),
      selectedBadge(selectedInputId === inputId)
    );
    list.appendChild(row);
  });

  renderMediaLists();
  renderInputSettings();
  renderRoutineEditor();
}

function renderAudioPage() {
  setText("#audio-library-count", String(audioFiles.length));
  renderMediaLibrary("audio", audioFiles);
}

function renderVideoPage() {
  setText("#video-library-count", String(videoFiles.length));
  renderMediaLibrary("video", videoFiles);
}

async function renderSystemPage() {
  const [info, logs] = await Promise.all([
    apiGet("/api/system/info"),
    apiGet("/api/logs?errors=true&limit=80"),
  ]);
  systemInfo = info;
  recentLogs = logs.logs || [];

  setText("#system-info-summary", info.running ? "Routine running" : "Idle");
  const list = document.querySelector("#system-info-list");
  if (list) {
    list.innerHTML = "";
    [
      ["Controller", info.controller_name || "HauntOS Controller"],
      ["Version", info.version || "v0.1.0-alpha"],
      ["Controller Mode", info.mock_mode ? "Mock mode" : "Hardware GPIO mode"],
      ["Show Armed", info.settings?.show_armed ? "Yes" : "No"],
      ["Setup Complete", info.settings?.setup_complete ? "Yes" : "No"],
      ["Running Routine", info.running ? "Yes" : "No"],
      ["IP Address", (info.ip_addresses || []).join(", ") || "Unavailable"],
      ["Outputs On", outputNamesFor(Object.entries(info.outputs || {}).filter(([, on]) => on).map(([id]) => id)) || "None"],
    ].forEach(([label, value]) => list.appendChild(descriptionRow(label, value)));
  }

  renderConnectionInfo(info);

  setText("#log-count", String(recentLogs.length));
  const logList = document.querySelector("#log-list");
  if (logList) {
    logList.textContent = recentLogs.length ? recentLogs.join("\n") : "No recent warnings or errors.";
  }
}

function renderConnectionInfo(info) {
  const deployment = info.deployment || {};
  const access = info.access || {};
  const lanUrls = Array.isArray(access.lan_urls) ? access.lan_urls : [];
  const connectionList = document.querySelector("#connection-list");

  setText("#connection-summary", controllerOnline ? "API connected" : "API offline");
  if (!connectionList) {
    return;
  }

  connectionList.innerHTML = "";
  [
    ["Controller Connection", controllerOnline ? "Connected to HauntOS API" : "Offline"],
    ["Running On", deployment.is_raspberry_pi ? deployment.pi_model : `${deployment.platform || "Local"} machine`],
    ["Control Mode", info.mock_mode ? "Mock mode - simulated GPIO/media" : "Hardware mode - GPIO active"],
    ["Current Browser URL", access.current_url || "Unavailable"],
    ["LAN Access URL", lanUrls.join(", ") || "Unavailable until network is connected"],
    ["Hotspot URL", access.hotspot_url || "http://192.168.4.1"],
    ["HauntOS Service", deployment.service || "Unknown"],
  ].forEach(([label, value]) => connectionList.appendChild(descriptionRow(label, value)));
}

function renderSetupPage() {
  if (!devices || !statusData) {
    return;
  }

  const settings = statusData.settings || {};
  const controllerInput = document.querySelector("#setup-controller-name");
  if (controllerInput) {
    controllerInput.value = settings.controller_name || "HauntOS Controller";
  }
  setChecked("#setup-mock-mode", Boolean(settings.mock_mode));

  renderNameFields("#setup-outputs", devices.outputs);
  renderNameFields("#setup-inputs", devices.inputs);
  renderSetupWizard();
}

function renderSetupWizard() {
  const currentIndex = setupWizardSteps.indexOf(setupWizardStep);
  const safeIndex = currentIndex >= 0 ? currentIndex : 0;
  setupWizardStep = setupWizardSteps[safeIndex];

  document.querySelectorAll("[data-setup-step]").forEach((step) => {
    const active = step.dataset.setupStep === setupWizardStep;
    step.classList.toggle("active", active);
    step.setAttribute("aria-hidden", active ? "false" : "true");
  });

  updateSetupWizardNav(safeIndex);

  if (setupWizardStep === "review") {
    renderSetupReview();
  }
}

function updateSetupWizardNav(safeIndex = setupWizardSteps.indexOf(setupWizardStep)) {
  document.querySelectorAll("[data-setup-progress]").forEach((button) => {
    const stepName = button.dataset.setupProgress;
    const index = setupWizardSteps.indexOf(stepName);
    const active = stepName === setupWizardStep;
    button.classList.toggle("active", active);
    button.classList.toggle("complete", index >= 0 && index < safeIndex);
    if (active) {
      button.setAttribute("aria-current", "step");
    } else {
      button.removeAttribute("aria-current");
    }
    button.disabled = !canUseSetupStep(index);
  });

  const backButton = document.querySelector("[data-action='setup-back']");
  const nextButton = document.querySelector("[data-action='setup-next']");
  const saveButton = document.querySelector("[data-action='setup-save']");
  const isReview = setupWizardStep === "review";

  if (backButton) {
    backButton.disabled = safeIndex === 0;
  }
  if (nextButton) {
    nextButton.hidden = isReview;
    nextButton.disabled = setupWizardStep === "controller" && !setupControllerName();
  }
  if (saveButton) {
    saveButton.hidden = !isReview;
  }
}

function canUseSetupStep(index) {
  if (index < 0) {
    return false;
  }
  if (index === 0) {
    return true;
  }
  return Boolean(setupControllerName());
}

function setupControllerName() {
  return (document.querySelector("#setup-controller-name")?.value || "").trim();
}

function goToSetupStep(stepName) {
  const nextIndex = setupWizardSteps.indexOf(stepName);
  if (!canUseSetupStep(nextIndex)) {
    showMessage("Controller name is required before continuing.", true);
    return;
  }

  setupWizardStep = setupWizardSteps[nextIndex];
  renderSetupWizard();
}

function renderSetupReview() {
  const list = document.querySelector("#setup-review-list");
  if (!list) {
    return;
  }

  const payload = setupPayload();
  const outputCount = Object.keys(payload.outputs).length;
  const inputCount = Object.keys(payload.inputs).length;

  list.innerHTML = "";
  [
    ["Controller", payload.controller_name],
    ["Mode", payload.mock_mode ? "Mock mode" : "Hardware GPIO mode"],
    ["Outputs Named", `${outputCount} outputs`],
    ["Inputs Named", `${inputCount} inputs`],
  ].forEach(([label, value]) => list.appendChild(descriptionRow(label, value)));
}

async function renderSchedulerPage() {
  schedulerData = await apiGet("/api/scheduler");
  const settings = schedulerData.settings || {};

  setChecked("#scheduler-enabled", Boolean(settings.enabled));
  setValue("#scheduler-start-time", settings.start_time || "19:00");
  setValue("#scheduler-end-time", settings.end_time || "22:00");
  setValue("#scheduler-mode", settings.mode || "random");
  setValue("#scheduler-interval-min", settings.interval_min || 120);
  setValue("#scheduler-interval-max", settings.interval_max || 300);
  renderSchedulerRoutineOptions(settings.routine || "IN1");
  updateSchedulerModeFields();

  setText("#scheduler-enabled-label", settings.enabled ? "Enabled" : "Disabled");
  setText("#scheduler-thread-status", schedulerData.running ? "Thread Running" : "Thread Stopped");

  const list = document.querySelector("#scheduler-status-list");
  if (list) {
    list.innerHTML = "";
    [
      ["Enabled", settings.enabled ? "Yes" : "No"],
      ["Active Hours", schedulerData.active_hours ? "Active now" : "Outside window"],
      ["System Armed", schedulerData.armed ? "Yes" : "No"],
      ["Mode", formatMode(settings.mode || "random")],
      ["Routine", settings.routine === "random" ? "Random routine" : inputOptionLabel(settings.routine)],
      ["Next Run", schedulerData.next_run_in === null ? "Not scheduled" : `${schedulerData.next_run_in}s`],
    ].forEach(([label, value]) => list.appendChild(descriptionRow(label, value)));
  }
}

function renderSchedulerRoutineOptions(selected) {
  const select = document.querySelector("#scheduler-routine");
  if (!select || !routines) {
    return;
  }
  select.innerHTML = "";
  ["random", ...Object.keys(routines)].forEach((routineId) => {
    const option = document.createElement("option");
    option.value = routineId;
    option.textContent = routineId === "random" ? "Random Routine" : inputOptionLabel(routineId);
    option.selected = routineId === selected;
    select.appendChild(option);
  });
}

function renderNameFields(selector, entries) {
  const container = document.querySelector(selector);
  if (!container) {
    return;
  }
  container.innerHTML = "";
  Object.entries(entries).forEach(([id, item]) => {
    const field = fieldShell(deviceSlotLabel(id));
    const input = document.createElement("input");
    input.type = "text";
    input.value = item.name || id;
    input.dataset.deviceId = id;
    field.appendChild(input);
    container.appendChild(field);
  });
}

function renderSetupSelect(selector, ids, entries = {}) {
  const select = document.querySelector(selector);
  if (!select) {
    return;
  }
  select.innerHTML = "";
  ids.forEach((id) => {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = entries[id]?.name || deviceSlotLabel(id);
    select.appendChild(option);
  });
}

function descriptionRow(label, value) {
  const row = document.createElement("div");
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = label;
  dd.textContent = value;
  row.append(dt, dd);
  return row;
}

function renderMediaLibrary(kind, files) {
  const list = document.querySelector(`#${kind}-library-list`);
  if (!list) {
    return;
  }

  list.innerHTML = "";
  if (!files.length) {
    const empty = document.createElement("div");
    empty.className = "empty-drop";
    empty.textContent = kind === "audio" ? "No audio files uploaded yet." : "No video files uploaded yet.";
    list.appendChild(empty);
    return;
  }

  files.forEach((filename) => {
    const row = document.createElement("article");
    row.className = "library-row";
    row.innerHTML = `
      <div class="library-file">
        <span class="tile-icon media-icon ${kind === "audio" ? "media-audio" : "media-video"}">${kind === "audio" ? "SND" : "VID"}</span>
        <div>
          <strong>${escapeHtml(filename)}</strong>
          <p class="muted">${kind === "audio" ? "Audio file" : "Video file"}</p>
        </div>
      </div>
    `;
    row.appendChild(
      actionGroup([
        actionButton("Test Play", () => testMedia(kind, filename), "secondary-button"),
        actionButton("Delete", () => deleteMedia(kind, filename), "outline-danger"),
      ])
    );
    list.appendChild(row);
  });
}

function renderRoutineEditor() {
  const editor = document.querySelector("#routine-editor");
  if (!editor || !selectedInputId) {
    return;
  }

  const input = devices.inputs[selectedInputId];
  const tiles = getRoutineTiles(selectedInputId);
  editor.innerHTML = "";
  setText("#routine-title", input.name);
  setText("#routine-subtitle", `${routineStepText(selectedInputId)} / ${input.enabled ? "Enabled" : "Disabled"} / ${cooldownText(input)}`);

  const header = document.createElement("div");
  header.className = "editor-header";
  const dirty = hasUnsavedRoutine(selectedInputId);
  header.innerHTML = `
    <div>
      <h2>Routine Sequence</h2>
      <p class="muted">${dirty ? "Unsaved changes. Press Save to update the controller." : "Saved routine. Edits stay local until you press Save."}</p>
    </div>
  `;

  const headerActions = actionGroup([
    actionButton(dirty ? "Save Changes" : "Save", () => saveRoutines(), "primary-purple"),
    actionButton("Duplicate", () => duplicateRoutine(), "secondary-button"),
    actionButton("Clear All", () => clearSelectedRoutine(), "outline-danger"),
  ]);
  if (dirty) {
    const badge = document.createElement("span");
    badge.className = "unsaved-badge";
    badge.textContent = "Unsaved";
    headerActions.prepend(badge);
  }
  header.appendChild(headerActions);

  const body = document.createElement("div");
  body.className = "routine-board";
  if (tiles.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-drop";
    empty.textContent = "Build your routine by adding steps below.";
    body.appendChild(empty);
  } else {
    tiles.forEach((tile, index) => {
      body.appendChild(tileCard(tile, index));
    });
  }

  const drop = inlineTilePicker();
  body.appendChild(drop);

  const tip = document.createElement("p");
  tip.className = "tip";
  tip.textContent = "Tip: use the arrow buttons to reorder tiles. The routine runs from top to bottom.";

  editor.append(header, body, tip);
}

function renderInputSettings() {
  if (!selectedInputId || !devices?.inputs?.[selectedInputId]) {
    return;
  }

  const input = devices.inputs[selectedInputId];
  setText(
    "#input-settings-summary",
    `${input.enabled ? "Enabled" : "Disabled"} / ${cooldownText(input)} / ${input.allow_concurrent ? "Concurrent" : "Exclusive"}`
  );
  setChecked("#input-enabled", Boolean(input.enabled));
  setChecked("#input-allow-concurrent", Boolean(input.allow_concurrent));
  setValue("#input-cooldown", Number(input.cooldown ?? 0));
}

function inlineTilePicker() {
  const picker = document.createElement("div");
  picker.className = "empty-drop add-inline inline-tile-picker";

  const heading = document.createElement("div");
  heading.className = "inline-picker-heading";
  heading.innerHTML = "<strong>+ Add Tile Here</strong><span>Choose the next step for this routine</span>";

  const buttons = document.createElement("div");
  buttons.className = "tile-buttons inline-tile-buttons";
  [
    ["output_pulse", "Output Pulse", "Turn on, wait, off"],
    ["output_on", "Output On", "Turn output on"],
    ["output_off", "Output Off", "Turn output off"],
    ["wait", "Wait", "Add delay"],
    ["sound", "Play Sound", "Play audio file"],
    ["video", "Play Video", "Play video file"],
    ["all_off", "All Off", "Stop everything"],
  ].forEach(([type, title, detail]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.tile = type;
    button.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span>`;
    button.addEventListener("click", () => addTile(type));
    buttons.appendChild(button);
  });

  picker.append(heading, buttons);
  return picker;
}

function tileCard(tile, index) {
  const card = document.createElement("article");
  const active = isActiveRoutineTile(index);
  card.className = `tile-card ${tileClass(tile)} ${expandedTileIndex === index ? "editing" : ""} ${active ? "active-tile" : ""}`;
  if (active) {
    card.setAttribute("aria-current", "step");
  }

  const type = tile.type || "unknown";
  const title = tileTitle(tile);
  const summary = tileSummary(tile);

  const tileMain = document.createElement("div");
  tileMain.className = "tile-main";
  tileMain.innerHTML = `
    <span class="tile-number">${index + 1}</span>
      <span class="tile-icon">${tileIconText(type)}</span>
      <div>
        <strong>${title}${active ? ' <span class="live-tile-badge">Running</span>' : ""}</strong>
        <p>${escapeHtml(summary)}</p>
      </div>
  `;

  const meta = document.createElement("div");
  meta.className = "tile-meta";
  tileMeta(tile).forEach((item) => {
    const block = document.createElement("div");
    block.innerHTML = `<span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong>`;
    meta.appendChild(block);
  });

  const controls = document.createElement("div");
  controls.className = "tile-controls";
  controls.appendChild(tileFields(tile, index));

  const actions = actionGroup(
    [
      actionButton(expandedTileIndex === index ? "Close" : "Edit", () => toggleTileEditor(index), "tile-action-button tile-edit-button"),
      actionButton("Up", () => moveTile(index, -1), "tile-action-button tile-arrow-button", "Move tile up"),
      actionButton("Dn", () => moveTile(index, 1), "tile-action-button tile-arrow-button", "Move tile down"),
      actionButton("Del", () => deleteTile(index), "tile-action-button tile-delete-button", "Delete tile"),
    ],
    "actions tile-actions"
  );

  card.append(tileMain, meta, controls, actions);
  return card;
}

function tileFields(tile, index) {
  const wrapper = document.createElement("div");
  wrapper.className = "field-grid";

  if (tile.type === "output") {
    wrapper.append(
      selectField("Output", tile.target || "OUT1", Object.keys(devices.outputs), (value) => updateTile(index, "target", value), outputOptionLabel)
    );
    if (tile.action === "pulse") {
      wrapper.append(numberField("Duration", tile.duration ?? 1, (value) => updateTile(index, "duration", value)));
    }
  } else if (tile.type === "wait") {
    wrapper.append(numberField("Duration", tile.duration ?? 1, (value) => updateTile(index, "duration", value)));
  } else if (tile.type === "sound") {
    if (!audioFiles.length) {
      wrapper.appendChild(emptyFieldNote("Upload audio files before choosing a sound."));
    }
    wrapper.append(
      selectField("File", tile.file || audioFiles[0] || "", audioFiles, (value) => updateTile(index, "file", value), (value) => value || "Upload audio first"),
      selectField("Mode", tile.mode || "play_and_continue", ["play_and_continue", "wait_until_done"], (value) => updateTile(index, "mode", value)),
      checkboxField("Allow Audio Overlap", Boolean(tile.allow_concurrent), (checked) => updateTile(index, "allow_concurrent", checked))
    );
  } else if (tile.type === "video") {
    if (!videoFiles.length) {
      wrapper.appendChild(emptyFieldNote("Upload video files before choosing a video."));
    }
    wrapper.append(
      selectField("File", tile.file || videoFiles[0] || "", videoFiles, (value) => updateTile(index, "file", value), (value) => value || "Upload video first"),
      checkboxField("Wait Until Done", (tile.mode || "play_and_continue") === "wait_until_done", (checked) => updateTile(index, "mode", checked ? "wait_until_done" : "play_and_continue"))
    );
  } else {
    const note = document.createElement("span");
    note.className = "muted";
    note.textContent = "Turns outputs off and stops audio/video.";
    wrapper.appendChild(note);
  }

  return wrapper;
}

function selectField(label, value, options, onChange, optionLabel = (optionValue) => optionValue || "No files") {
  const field = fieldShell(label);
  const select = document.createElement("select");
  const values = options.length ? options : [""];
  select.disabled = options.length === 0;
  values.forEach((optionValue) => {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = optionLabel(optionValue);
    option.selected = optionValue === value;
    option.disabled = optionValue === "" && options.length === 0;
    select.appendChild(option);
  });
  select.addEventListener("change", () => onChange(select.value));
  field.appendChild(select);
  return field;
}

function emptyFieldNote(text) {
  const note = document.createElement("div");
  note.className = "field-note";
  note.textContent = text;
  return note;
}

function numberField(label, value, onChange) {
  const field = fieldShell(label);
  const input = document.createElement("input");
  input.type = "number";
  input.min = "0";
  input.step = "0.1";
  input.value = value;
  input.addEventListener("change", () => onChange(Number(input.value)));
  field.appendChild(input);
  return field;
}

function checkboxField(label, checked, onChange) {
  const field = fieldShell(label);
  field.classList.add("checkbox-field");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = checked;
  input.addEventListener("change", () => onChange(input.checked));
  field.appendChild(input);
  return field;
}

function fieldShell(label) {
  const field = document.createElement("label");
  field.className = "field";
  const span = document.createElement("span");
  span.textContent = label;
  field.appendChild(span);
  return field;
}

function outputStateCard(outputId, output) {
  const card = document.createElement("article");
  card.className = "state-card";
  card.append(deviceIcon("OUT"), deviceInfo(output.name, isOutputOn(outputId) ? "Currently on" : "Currently off"), outputStatePill(outputId));
  return card;
}

function deviceIcon(text) {
  const icon = document.createElement("span");
  icon.className = "device-icon";
  icon.textContent = text;
  return icon;
}

function deviceInfo(title, meta) {
  const info = document.createElement("div");
  info.className = "device-info";
  info.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(meta)}</span>`;
  return info;
}

function outputStatePill(outputId) {
  const state = document.createElement("span");
  state.className = `state-pill ${isOutputOn(outputId) ? "on" : "off"}`;
  state.textContent = isOutputOn(outputId) ? "ON" : "OFF";
  return state;
}

function selectedBadge(isSelected) {
  const badge = document.createElement("span");
  badge.className = `selector-badge ${isSelected ? "active" : ""}`;
  badge.textContent = isSelected ? "Editing" : "Select";
  return badge;
}

function actionGroup(buttons, className = "actions") {
  const actions = document.createElement("div");
  actions.className = className;
  buttons.forEach((button) => actions.appendChild(button));
  return actions;
}

function actionButton(label, handler, className = "secondary-button", ariaLabel = null) {
  const button = document.createElement("button");
  button.className = className;
  button.type = "button";
  button.textContent = label;
  if (ariaLabel) {
    button.setAttribute("aria-label", ariaLabel);
    button.title = ariaLabel;
  }
  button.addEventListener("click", handler);
  return button;
}

function bindShellActions() {
  document.querySelectorAll("[data-action='stop']").forEach((button) => {
    button.addEventListener("click", stopEverything);
  });
  document.querySelectorAll("[data-action='refresh']").forEach((button) => {
    button.addEventListener("click", () => {
      if (confirmDiscardUnsaved()) {
        loadPage();
      }
    });
  });
  document.querySelectorAll("[data-action='start-show']").forEach((button) => {
    button.addEventListener("click", toggleShowMode);
  });
  document.querySelectorAll("[data-action='run-selected']").forEach((button) => {
    button.addEventListener("click", () => {
      if (selectedInputId) {
        runInput(selectedInputId);
      }
    });
  });
  document.querySelectorAll("[data-action='save-input-settings']").forEach((button) => {
    button.addEventListener("click", saveInputSettings);
  });
}

function bindMediaUploadForms() {
  document.querySelectorAll("[data-media-upload]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      uploadMedia(form.dataset.mediaUpload, form);
    });
  });
}

function bindConfigImportForm() {
  const form = document.querySelector("#config-import-form");
  if (!form) {
    return;
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = form.querySelector("input[type='file']");
    if (!input || !input.files || input.files.length === 0) {
      showToast("Choose a backup file first.", true);
      showMessage("Choose a backup file first.", true);
      return;
    }

    const formData = new FormData();
    formData.append("file", input.files[0]);
    try {
      const data = await apiUpload("/api/config/import", formData);
      devices = data.devices;
      routines = data.routines;
      statusData.settings = data.settings;
      form.reset();
      await refreshStatus();
      await renderSystemPage();
      showToast("Config backup imported");
      showMessage("Config backup imported");
    } catch (error) {
      showToast(error.message, true);
      showMessage(error.message, true);
    }
  });
}

function bindSystemActionButtons() {
  document.querySelectorAll("[data-system-action]").forEach((button) => {
    button.addEventListener("click", () => runGuardedSystemAction(button.dataset.systemAction));
  });
}

function bindSetupForm() {
  const form = document.querySelector("#setup-form");
  if (!form) {
    return;
  }

  const logoPreviewToggle = document.querySelector("#setup-logo-preview");
  if (logoPreviewToggle) {
    logoPreviewToggle.addEventListener("change", () => {
      logoPreviewOffline = Boolean(logoPreviewToggle.checked);
      renderConnectionLogo();
    });
  }

  const controllerInput = document.querySelector("#setup-controller-name");
  if (controllerInput) {
    ["input", "change", "keyup"].forEach((eventName) => {
      controllerInput.addEventListener(eventName, () => {
        renderSetupWizard();
        showMessage("");
      });
    });
  }

  document.querySelectorAll("[data-setup-progress]").forEach((button) => {
    button.addEventListener("click", () => goToSetupStep(button.dataset.setupProgress));
  });

  const backButton = document.querySelector("[data-action='setup-back']");
  if (backButton) {
    backButton.addEventListener("click", () => {
      const index = setupWizardSteps.indexOf(setupWizardStep);
      goToSetupStep(setupWizardSteps[Math.max(0, index - 1)]);
    });
  }

  const nextButton = document.querySelector("[data-action='setup-next']");
  if (nextButton) {
    nextButton.addEventListener("click", () => {
      if (!setupControllerName()) {
        renderSetupWizard();
        showMessage("Controller name is required before continuing.", true);
        return;
      }
      const index = setupWizardSteps.indexOf(setupWizardStep);
      goToSetupStep(setupWizardSteps[Math.min(setupWizardSteps.length - 1, index + 1)]);
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!setupControllerName()) {
      setupWizardStep = "controller";
      renderSetupWizard();
      showMessage("Controller name is required before saving setup.", true);
      return;
    }
    if (setupWizardStep !== "review") {
      const index = setupWizardSteps.indexOf(setupWizardStep);
      goToSetupStep(setupWizardSteps[Math.min(setupWizardSteps.length - 1, index + 1)]);
      return;
    }

    renderSetupWizard();
    try {
      const payload = setupPayload();
      const data = await apiPost("/api/setup", payload);
      devices = data.devices;
      routines = data.routines;
      statusData.settings = data.settings;
      renderShellStatus();
      renderSetupPage();
      showToast("Setup saved");
      showMessage("Setup saved");
      window.location.href = "/";
    } catch (error) {
      showToast(error.message, true);
      showMessage(error.message, true);
    }
  });
}

function bindSchedulerForm() {
  const form = document.querySelector("#scheduler-form");
  if (!form) {
    return;
  }

  const mode = document.querySelector("#scheduler-mode");
  if (mode) {
    mode.addEventListener("change", updateSchedulerModeFields);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const data = await apiPost("/api/scheduler", schedulerPayload());
      schedulerData = data.status;
      await refreshStatus();
      await renderSchedulerPage();
      showToast("Scheduler saved");
      showMessage("Scheduler saved");
    } catch (error) {
      showToast(error.message, true);
      showMessage(error.message, true);
    }
  });
}

function bindRoutineShell() {
  document.querySelectorAll("[data-tile]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!devices || !routines) {
        showMessage("Controller data is still loading.", true);
        return;
      }
      if (!selectedInputId) {
        selectedInputId = Object.keys(devices?.inputs || {})[0];
      }
      if (!selectedInputId) {
        showMessage("No input is available for editing.", true);
        return;
      }
      addTile(button.dataset.tile);
    });
  });
  document.querySelectorAll("[data-action='test-selected']").forEach((button) => {
    button.addEventListener("click", testSelectedRoutine);
  });
}

function selectInput(inputId) {
  selectedInputId = inputId;
  expandedTileIndex = null;
  renderInputsPage();
}

function markRoutineDirty(inputId) {
  if (inputId) {
    dirtyRoutineInputs.add(inputId);
  }
}

function hasUnsavedRoutine(inputId) {
  return dirtyRoutineInputs.has(inputId);
}

function confirmDiscardUnsaved() {
  if (dirtyRoutineInputs.size === 0) {
    return true;
  }

  return window.confirm("Discard unsaved routine changes and reload from the controller?");
}

function getRoutineTiles(inputId) {
  if (!Array.isArray(routines[inputId])) {
    routines[inputId] = [];
  }
  return routines[inputId];
}

function addTile(type) {
  const tiles = getRoutineTiles(selectedInputId);
  tiles.push(defaultTile(type));
  markRoutineDirty(selectedInputId);
  expandedTileIndex = tiles.length - 1;
  renderRoutineEditor();
  requestAnimationFrame(() => {
    const openTile = document.querySelector(".tile-card.editing");
    if (openTile) {
      openTile.scrollIntoView({ behavior: "smooth", block: "center" });
      focusTileControls(openTile);
    }
  });
}

function defaultTile(type) {
  if (type === "output_pulse" || type === "output") {
    return { type: "output", target: "OUT1", action: "pulse", duration: 1 };
  }
  if (type === "output_on") {
    return { type: "output", target: "OUT1", action: "on" };
  }
  if (type === "output_off") {
    return { type: "output", target: "OUT1", action: "off" };
  }
  if (type === "wait") {
    return { type: "wait", duration: 1 };
  }
  if (type === "sound") {
    return { type: "sound", file: audioFiles[0] || "", mode: "play_and_continue", allow_concurrent: false };
  }
  if (type === "video") {
    return { type: "video", file: videoFiles[0] || "", mode: "play_and_continue" };
  }
  return { type: "all_off" };
}

function updateTile(index, key, value) {
  getRoutineTiles(selectedInputId)[index][key] = value;
  markRoutineDirty(selectedInputId);
  expandedTileIndex = index;
  renderRoutineEditor();
}

function moveTile(index, direction) {
  const tiles = getRoutineTiles(selectedInputId);
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= tiles.length) {
    return;
  }
  const tile = tiles.splice(index, 1)[0];
  tiles.splice(nextIndex, 0, tile);
  markRoutineDirty(selectedInputId);
  expandedTileIndex = nextIndex;
  renderRoutineEditor();
}

function deleteTile(index) {
  getRoutineTiles(selectedInputId).splice(index, 1);
  markRoutineDirty(selectedInputId);
  expandedTileIndex = null;
  renderRoutineEditor();
}

async function clearSelectedRoutine() {
  const inputName = inputOptionLabel(selectedInputId);
  getRoutineTiles(selectedInputId).splice(0);
  markRoutineDirty(selectedInputId);
  expandedTileIndex = null;
  renderRoutineEditor();
  showToast(`${inputName} routine cleared locally. Save to keep it.`);
  showMessage(`${inputName} routine cleared locally. Save to keep it.`);
}

function duplicateRoutine() {
  const inputName = inputOptionLabel(selectedInputId);
  const tiles = getRoutineTiles(selectedInputId);
  routines[selectedInputId] = tiles.map((tile) => ({ ...tile }));
  markRoutineDirty(selectedInputId);
  expandedTileIndex = null;
  renderRoutineEditor();
  showToast(`${inputName} routine duplicated locally.`);
  showMessage(`${inputName} routine duplicated locally.`);
}

async function saveRoutines() {
  const inputName = inputOptionLabel(selectedInputId);
  try {
    const data = await apiPost("/api/routines", routines);
    routines = data.routines;
    dirtyRoutineInputs.clear();
    renderInputsPage();
    showToast(`${inputName} routine saved`);
    showMessage(`${inputName} routine saved`);
  } catch (error) {
    showActionError(error);
  }
}

async function saveInputSettings() {
  if (!selectedInputId || !devices?.inputs?.[selectedInputId]) {
    showMessage("Select an input before saving settings.", true);
    return;
  }

  const input = devices.inputs[selectedInputId];
  const cooldownValue = Number(document.querySelector("#input-cooldown")?.value ?? input.cooldown ?? 0);
  input.enabled = Boolean(document.querySelector("#input-enabled")?.checked);
  input.allow_concurrent = Boolean(document.querySelector("#input-allow-concurrent")?.checked);
  input.cooldown = Number.isFinite(cooldownValue) && cooldownValue >= 0 ? Math.round(cooldownValue) : 0;

  try {
    const data = await apiPost("/api/devices", devices);
    devices = data.devices;
    renderInputsPage();
    showToast(`${inputOptionLabel(selectedInputId)} settings saved`);
    showMessage(`${inputOptionLabel(selectedInputId)} settings saved`);
  } catch (error) {
    showActionError(error);
  }
}

async function testSelectedRoutine() {
  if (!selectedInputId) {
    showMessage("Select an input before testing.", true);
    return;
  }
  const inputName = inputOptionLabel(selectedInputId);
  try {
    await apiPost("/api/run/custom", {
      routine_id: selectedInputId,
      tiles: getRoutineTiles(selectedInputId),
      allow_concurrent: Boolean(devices?.inputs?.[selectedInputId]?.allow_concurrent),
    });
    showToast(`${inputName} test routine started`);
    showMessage(`${inputName} test routine started`);
    await refreshStatus();
    renderRoutineEditor();
  } catch (error) {
    showActionError(error);
  }
}

async function stopEverything() {
  await apiPost("/api/stop");
  await refreshStatus();
  renderCurrentPage();
  showToast("STOP sent. Show disarmed, outputs and media stopped.");
  showMessage("Stopped and disarmed");
}

async function toggleShowMode() {
  const showArmed = Boolean(statusData?.settings?.show_armed);
  if (showArmed) {
    await apiPost("/api/show/stop");
    await refreshStatus();
    renderCurrentPage();
    showToast("Show stopped gracefully. Active routines can finish.");
    showMessage("Show stopped gracefully");
    return;
  }

  await apiPost("/api/show/start");
  await refreshStatus();
  renderCurrentPage();
  showToast("Show armed. Inputs and scheduler can trigger routines.");
  showMessage("Show armed");
}

async function runGuardedSystemAction(action) {
  const labels = {
    "factory-reset": "Factory reset will restore default devices, routines, and settings.",
    reboot: "Reboot this Raspberry Pi now?",
    shutdown: "Shutdown this Raspberry Pi now?",
    restart_service: "Restart the HauntOS system service?",
  };
  const confirmed = window.confirm(`${labels[action] || "Run this system action?"}\n\nContinue?`);
  if (!confirmed) {
    return;
  }

  try {
    if (action === "factory-reset") {
      const data = await apiPost("/api/config/factory-reset", { confirm: true });
      devices = data.devices;
      routines = data.routines;
      statusData.settings = data.settings;
      await refreshStatus();
      await renderSystemPage();
      showToast("Factory reset complete");
      showMessage("Factory reset complete");
      return;
    }

    const data = await apiPost(`/api/system/${action}`, { confirm: true });
    showToast(data.message || "System action requested");
    showMessage(data.message || "System action requested");
  } catch (error) {
    showToast(error.message, true);
    showMessage(error.message, true);
  }
}

async function runInput(inputId) {
  const inputName = inputOptionLabel(inputId);
  try {
    await apiPost(`/api/run/input/${inputId}`);
    await refreshStatus();
    renderCurrentPage();
    showToast(`${inputName} routine started`);
    showMessage(`${inputName} started`);
  } catch (error) {
    showActionError(error);
  }
}

async function outputAction(outputId, action) {
  const body = action === "pulse" ? { duration: 1 } : undefined;
  await apiPost(`/api/output/${outputId}/${action}`, body);
  await refreshStatus();
  renderCurrentPage();
  showMessage(`${outputId} ${action.toUpperCase()}`);
}

async function uploadMedia(kind, form) {
  const input = form.querySelector("input[type='file']");
  if (!input || !input.files || input.files.length === 0) {
    showToast("Choose a file before uploading.", true);
    showMessage("Choose a file before uploading.", true);
    return;
  }

  const formData = new FormData();
  formData.append("file", input.files[0]);

  const data = await apiUpload(`/api/${kind}/upload`, formData);
  if (kind === "audio") {
    audioFiles = data.audio || [];
    renderAudioPage();
  } else {
    videoFiles = data.video || [];
    renderVideoPage();
  }
  form.reset();
  showToast(`${data.filename} uploaded`);
  showMessage(`${data.filename} uploaded`);
}

async function deleteMedia(kind, filename) {
  if (!window.confirm(`Delete "${filename}"? This cannot be undone.`)) {
    return;
  }

  try {
    const data = await apiDelete(`/api/${kind}/${encodeURIComponent(filename)}`);
    if (kind === "audio") {
      audioFiles = data.audio || [];
      renderAudioPage();
    } else {
      videoFiles = data.video || [];
      renderVideoPage();
    }
    showToast(`${filename} deleted`);
    showMessage(`${filename} deleted`);
  } catch (error) {
    showActionError(error);
  }
}

async function testMedia(kind, filename) {
  const tile = kind === "audio"
    ? { type: "sound", file: filename, mode: "play_and_continue", allow_concurrent: false }
    : { type: "video", file: filename, mode: "play_and_continue" };
  try {
    await apiPost("/api/run/custom", { tiles: [tile] });
    await refreshStatus();
    showToast(`Testing ${filename}`);
    showMessage(`Testing ${filename}`);
  } catch (error) {
    showActionError(error);
  }
}

async function refreshStatus() {
  statusData = await apiGet("/api/status");
  setControllerConnection(true);
  renderShellStatus();
}

function startStatusPolling() {
  if (statusPollTimer) {
    return;
  }
  statusPollTimer = window.setInterval(refreshRuntimeStatus, 1000);
}

async function refreshRuntimeStatus() {
  if (!statusData) {
    return;
  }

  const before = runtimeKey();
  try {
    await refreshStatus();
  } catch (error) {
    setControllerConnection(false);
    showMessage("Controller disconnected. Waiting for HauntOS to respond.", true);
    return;
  }

  const after = runtimeKey();
  if (after !== before || after !== lastRuntimeKey) {
    lastRuntimeKey = after;
    if (page === "inputs") {
      renderRoutineEditor();
    } else if (page === "dashboard") {
      renderDashboard();
    }
  }
}

function setControllerConnection(isOnline) {
  controllerOnline = Boolean(isOnline);
  renderConnectionLogo();

  if (!controllerOnline) {
    setText("#controller-online", "Offline");
    setText("#shell-status", "OFFLINE");
    setText("#shell-running", "Controller disconnected");
    setText("#top-status", "Controller disconnected");
    setText("#running-indicator", "Offline");
    setText("#scheduler-indicator", "Schedule Unknown");
    setText("#system-status", "Controller disconnected");
  }
}

function renderConnectionLogo() {
  const showOfflineLogo = !controllerOnline || logoPreviewOffline;
  document.body.classList.toggle("controller-offline", showOfflineLogo);
  document.body.classList.toggle("controller-online", controllerOnline);

  const logo = document.querySelector(".brand-logo");
  if (logo) {
    const nextSrc = showOfflineLogo ? logo.dataset.offlineSrc : logo.dataset.onlineSrc;
    if (nextSrc && logo.getAttribute("src") !== nextSrc) {
      logo.setAttribute("src", nextSrc);
    }
    logo.alt = showOfflineLogo
      ? "HauntPI Haunt Controller disconnected"
      : "HauntPI Haunt Controller connected";
  }

  const badge = document.querySelector("#brand-status-badge");
  if (badge) {
    badge.textContent = showOfflineLogo ? "Offline" : "Connected";
  }
}

function runtimeKey() {
  const routine = statusData?.routine || {};
  return [
    statusData?.running ? "running" : "idle",
    routine.routine_id || "",
    routine.tile_index ?? "",
  ].join(":");
}

function isActiveRoutineTile(index) {
  const routine = statusData?.routine || {};
  return Boolean(statusData?.running)
    && routine.routine_id === selectedInputId
    && Number(routine.tile_index) === index;
}

function renderCurrentPage() {
  if (page === "dashboard") {
    renderDashboard();
  } else if (page === "outputs") {
    renderOutputsPage();
  } else if (page === "inputs") {
    renderInputsPage();
  } else if (page === "audio") {
    renderAudioPage();
  } else if (page === "video") {
    renderVideoPage();
  } else if (page === "system") {
    renderSystemPage();
  } else if (page === "setup") {
    renderSetupPage();
  } else if (page === "scheduler") {
    renderSchedulerPage();
  }
}

async function apiGet(path) {
  const response = await fetch(path);
  return handleResponse(response);
}

async function apiPost(path, body) {
  const options = { method: "POST" };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }

  const response = await fetch(path, options);
  return handleResponse(response);
}

async function apiDelete(path) {
  const response = await fetch(path, { method: "DELETE" });
  return handleResponse(response);
}

async function apiUpload(path, formData) {
  const response = await fetch(path, {
    method: "POST",
    body: formData,
  });
  return handleResponse(response);
}

async function handleResponse(response) {
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    const error = new Error(data.error || `Request failed: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function isOutputOn(outputId) {
  return Boolean(statusData.outputs && statusData.outputs[outputId]);
}

function tileSummary(tile) {
  if (tile.type === "output") {
    const output = devices.outputs[tile.target];
    return output ? output.name : tile.target || "Output";
  }
  if (tile.type === "wait") {
    return `Wait ${tile.duration ?? 0}s`;
  }
  if (tile.type === "sound") {
    return tile.file || "No sound selected";
  }
  if (tile.type === "video") {
    return tile.file || "No video selected";
  }
  if (tile.type === "all_off") {
    return "Turn all outputs off";
  }
  return "Unknown tile";
}

function tileTitle(tile) {
  if (tile.type === "output") {
    if (tile.action === "pulse") {
      return "OUTPUT PULSE";
    }
    if (tile.action === "on") {
      return "OUTPUT ON";
    }
    if (tile.action === "off") {
      return "OUTPUT OFF";
    }
    return "OUTPUT";
  }
  if (tile.type === "wait") {
    return "WAIT";
  }
  if (tile.type === "sound") {
    return "PLAY SOUND";
  }
  if (tile.type === "video") {
    return "PLAY VIDEO";
  }
  if (tile.type === "all_off") {
    return "ALL OFF";
  }
  return String(tile.type || "UNKNOWN").replaceAll("_", " ").toUpperCase();
}

function tileClass(tile) {
  if (tile.type === "output") {
    return "tile-output";
  }
  return `tile-${tile.type || "unknown"}`;
}

function tileMeta(tile) {
  if (tile.type === "output") {
    const output = devices.outputs[tile.target];
    const meta = [{ label: "Output", value: output ? output.name : tile.target || "Output" }];
    meta.push({ label: "Action", value: `${(tile.action || "on").toUpperCase()}${tile.action === "pulse" ? " (Pulse)" : ""}` });
    if (tile.action === "pulse") {
      meta.push({ label: "Duration", value: `${tile.duration ?? 0} sec` });
    }
    return meta;
  }
  if (tile.type === "wait") {
    return [{ label: "Duration", value: `${tile.duration ?? 0} sec` }];
  }
  if (tile.type === "sound") {
    return [
      { label: "Mode", value: formatMode(tile.mode || "play_and_continue") },
      { label: "Overlap", value: tile.allow_concurrent ? "Allowed" : "Stops audio" },
    ];
  }
  if (tile.type === "video") {
    return [
      { label: "Mode", value: formatMode(tile.mode || "play_and_continue") },
      { label: "Display", value: "HDMI 1" },
    ];
  }
  return [{ label: "Action", value: "All outputs off" }];
}

function formatMode(mode) {
  return String(mode).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function tileIconText(type) {
  if (type === "output") {
    return "OUT";
  }
  if (type === "wait") {
    return "WAIT";
  }
  if (type === "sound") {
    return "SND";
  }
  if (type === "video") {
    return "VID";
  }
  return "OFF";
}

function toggleTileEditor(index) {
  expandedTileIndex = expandedTileIndex === index ? null : index;
  renderRoutineEditor();
  if (expandedTileIndex !== null) {
    requestAnimationFrame(() => {
      const openTile = document.querySelector(".tile-card.editing");
      if (openTile) {
        focusTileControls(openTile);
      }
    });
  }
}

function focusTileControls(card) {
  const firstInput = card.querySelector("select, input");
  if (firstInput) {
    firstInput.focus();
  }
}

function renderMediaLists() {
  setText("#audio-count", String(audioFiles.length));
  setText("#video-count", String(videoFiles.length));
  renderMediaList("#audio-files-list", audioFiles, "No audio files", "audio");
  renderMediaList("#video-files-list", videoFiles, "No video files", "video");
}

function renderMediaList(selector, files, emptyText, kind) {
  const list = document.querySelector(selector);
  if (!list) {
    return;
  }
  list.innerHTML = "";
  if (!files.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = emptyText;
    list.appendChild(empty);
    return;
  }
  files.slice(0, 4).forEach((file) => {
    const row = document.createElement("div");
    row.className = "media-row";
    const name = document.createElement("span");
    name.textContent = file;
    row.append(
      name,
      actionButton("Play", () => testMedia(kind, file), "secondary-button compact-button")
    );
    list.appendChild(row);
  });
}

function setText(selector, text) {
  const element = document.querySelector(selector);
  if (element) {
    element.textContent = text;
  }
}

function setValue(selector, value) {
  const element = document.querySelector(selector);
  if (element) {
    element.value = value;
  }
}

function setChecked(selector, checked) {
  const element = document.querySelector(selector);
  if (element) {
    element.checked = checked;
  }
}

function showMessage(text, isError = false) {
  const message = document.querySelector("#message");
  if (!message) {
    return;
  }

  message.textContent = text;
  message.classList.toggle("error", isError);
}

function showToast(text, isError = false) {
  const region = document.querySelector("#toast-region");
  if (!region) {
    return;
  }

  region.innerHTML = "";
  const toast = document.createElement("div");
  toast.className = `toast ${isError ? "error" : ""}`;
  toast.textContent = text;
  region.appendChild(toast);

  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.add("leaving");
    setTimeout(() => toast.remove(), 250);
  }, 2600);
}

function showActionError(error) {
  const message = error?.message || "Action failed";
  showToast(message, true);
  showMessage(message, true);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function routineStepText(inputId) {
  const count = Array.isArray(routines?.[inputId]) ? routines[inputId].length : 0;
  return `${count} routine step${count === 1 ? "" : "s"}`;
}

function routineStepShortText(inputId) {
  const count = Array.isArray(routines?.[inputId]) ? routines[inputId].length : 0;
  return `${count} step${count === 1 ? "" : "s"}`;
}

function inputSummaryText(inputId) {
  const concurrentText = devices?.inputs?.[inputId]?.allow_concurrent ? "concurrent" : "exclusive";
  return `${routineStepShortText(inputId)} ready / ${concurrentText}`;
}

function cooldownText(input) {
  const cooldown = Number(input.cooldown ?? 0);
  return cooldown > 0 ? `${cooldown}s cooldown` : "No cooldown";
}

function outputSummaryText() {
  const states = statusData?.outputs || {};
  const total = Object.keys(devices?.outputs || {}).length;
  const onCount = Object.values(states).filter(Boolean).length;
  return `${onCount} on / ${total} total`;
}

function outputOptionLabel(outputId) {
  return devices?.outputs?.[outputId]?.name || deviceSlotLabel(outputId);
}

function inputOptionLabel(inputId) {
  return devices?.inputs?.[inputId]?.name || deviceSlotLabel(inputId);
}

function outputNamesFor(outputIds) {
  return outputIds.map((outputId) => outputOptionLabel(outputId)).join(", ");
}

function deviceSlotLabel(id) {
  const match = String(id).match(/^(IN|OUT)(\d+)$/);
  if (!match) {
    return id;
  }

  return `${match[1] === "IN" ? "Input" : "Output"} ${match[2]}`;
}

function setupPayload() {
  const outputNames = {};
  const inputNames = {};
  document.querySelectorAll("#setup-outputs input[data-device-id]").forEach((input) => {
    outputNames[input.dataset.deviceId] = input.value;
  });
  document.querySelectorAll("#setup-inputs input[data-device-id]").forEach((input) => {
    inputNames[input.dataset.deviceId] = input.value;
  });

  return {
    controller_name: setupControllerName(),
    mock_mode: Boolean(document.querySelector("#setup-mock-mode")?.checked),
    outputs: outputNames,
    inputs: inputNames,
  };
}

function schedulerPayload() {
  const mode = document.querySelector("#scheduler-mode")?.value || "random";
  const intervalMin = Number(document.querySelector("#scheduler-interval-min")?.value || 120);
  const intervalMaxInput = Number(document.querySelector("#scheduler-interval-max")?.value || intervalMin);

  return {
    enabled: Boolean(document.querySelector("#scheduler-enabled")?.checked),
    start_time: document.querySelector("#scheduler-start-time")?.value || "19:00",
    end_time: document.querySelector("#scheduler-end-time")?.value || "22:00",
    mode,
    interval_min: intervalMin,
    interval_max: mode === "fixed" ? intervalMin : intervalMaxInput,
    routine: document.querySelector("#scheduler-routine")?.value || "IN1",
  };
}

function updateSchedulerModeFields() {
  const mode = document.querySelector("#scheduler-mode")?.value || "random";
  const maxField = document.querySelector("#scheduler-interval-max");
  if (maxField) {
    maxField.disabled = mode === "fixed";
  }
}
