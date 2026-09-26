(function () {
  "use strict";

  const WORKFLOW_ID = "qfw-slurm-cluster";
  document.title = "Dashboard";
  const IDENTITIES = ["user-a", "user-b", "user-c", "root"];
  const WIDGET_GROUPS = [
    {
      id: "operations",
      label: "Operations",
      widgets: [
        ["cluster-control", "Cluster control"],
        ["service-control", "Service control"],
        ["node-control", "Node control"],
        ["cluster-access", "Cluster access"],
      ],
    },
    {
      id: "experiments",
      label: "Experiments and results",
      widgets: [
        ["experiments", "Running Experiments"],
        ["results", "Result summary"],
      ],
      experimentLauncher: true,
    },
    {
      id: "allocations",
      label: "Allocations and service topology",
      widgets: [
        ["allocations", "Allocations"],
        ["services", "Services"],
        ["topology", "Topology", "wide"],
      ],
    },
    {
      id: "infrastructure",
      label: "Cluster state and configuration",
      widgets: [
        ["health", "Cluster health"],
        ["inventory", "Version and configuration inventory"],
        ["nodes", "Nodes"],
        ["alerts", "Alerts"],
      ],
    },
  ];
  const WIDGETS = WIDGET_GROUPS.flatMap((group) => group.widgets);
  const NON_FILTERABLE_WIDGETS = new Set([
    "cluster-control", "service-control", "node-control", "cluster-access",
  ]);
  const OPERATION_WIDGET_GROUPS = {
    "cluster-control": "cluster",
    "service-control": "services",
    "node-control": "nodes",
  };
  const JOB_COLORS = [
    "#32d6c5", "#75d982", "#54b8ff", "#8fa3ff", "#c893ff",
    "#ef8fd2", "#e6dc68", "#68d8f0", "#a8dc72", "#d4a5ff",
  ];
  const TOPOLOGY_CONNECTOR_COLORS = [
    "#5ee8ff", "#9b8cff", "#2df4c3", "#ffc76b", "#54b8ff",
    "#ef8fd2", "#75d982", "#c893ff", "#68d8f0", "#e6dc68",
  ];
  const CANVAS_ZOOM_MIN = 5;
  const CANVAS_ZOOM_MAX = 1000;
  const CANVAS_ZOOM_STEP = 5;
  const TOPOLOGY_ZOOM_MIN = 10;
  const TOPOLOGY_ZOOM_MAX = 1000;
  const TOPOLOGY_ZOOM_STEP = 10;
  const SCROLL_INTERACTION_GRACE_MS = 1200;
  const ACTIVE_EXPERIMENT_STATES = new Set([
    "created", "submitting", "submitted", "pending",
    "configuring", "running", "completing", "cancel-requested",
  ]);
  const DEFW_OUT_LOG_LEVELS = [
    ["error", "Error"],
    ["message", "Message"],
    ["debug", "Debug"],
    ["all", "All"],
  ];
  const DEFW_PY_LOG_LEVELS = [
    ["critical", "Critical"],
    ["error", "Error"],
    ["warning", "Warning"],
    ["info", "Info"],
    ["debug", "Debug"],
    ["DEFW_CORE", "DEFw core"],
    ["DEFW_WORKER", "DEFw worker"],
    ["DEFW_SERVICE", "DEFw service"],
    ["DEFW_APP", "DEFw app"],
    ["DEFW_RPC", "DEFw RPC"],
    ["DEFW_STACKTRACE", "DEFw stacktrace"],
    ["DEFW_ALL", "DEFw all"],
  ];
  const SERVICE_ARCHIVE_IDS = new Set([
    "directory-service",
    "qfw-slurm-gateway",
    "nwqsim",
    "nwqsim-dvm",
    "iqm-ornl-20q",
    "shim-ornl-20q",
    "fake-iqm",
  ]);
  const FALLBACK_BACKENDS = [
    {
      name: "nwqsim", label: "NWQSim", provider: "nwqsim", qpu: "nwqsim",
      service_target: "nwqsim", service_id: "nwqsim",
      max_time_minutes: 240, max_shots: 65536,
      requires_hardware_confirmation: false,
    },
    {
      name: "iqm", label: "IQM", provider: "iqm", qpu: "ornl-iqm-20q",
      service_target: "iqm", service_id: "iqm-ornl-20q",
      max_time_minutes: 15, max_shots: 256,
      requires_hardware_confirmation: true,
    },
    {
      name: "shim", label: "IQM shim", provider: "shim",
      qpu: "ornl-shim-20q", service_target: "shim",
      service_id: "shim-ornl-20q", max_time_minutes: 15, max_shots: 256,
      requires_hardware_confirmation: true,
    },
    {
      name: "fake-iqm", label: "Fake IQM", provider: "fake-iqm",
      qpu: "fake-iqm-20q", service_target: "fake-iqm",
      service_id: "fake-iqm", max_time_minutes: 240, max_shots: 65536,
      requires_hardware_confirmation: false,
    },
  ];
  let runtimeApi = null;
  let activeIdentity = "user-a";
  let state = {
    health: "unavailable",
    sources: {},
    operations: [],
    experiments: [],
    backends: FALLBACK_BACKENDS,
  };
  let polling = null;
  let eventPolling = null;
  let eventCursor = 0;
  const logCursors = {};
  let progressEvents = [];
  let progressIdentity = "user-a";
  let progressPaused = false;
  let dashboardRoot = null;
  let originalStatusOutput = null;
  const dashboardMirrors = new Set();
  let activeCanvasPans = 0;
  let dashboardRenderPending = false;
  const pendingOperationGroups = new Set();
  const pendingAbortGroups = new Set();
  let widgetChannel = null;
  let widgetStates = {};
  let selectedDashboardWidget = null;
  let selectedExperimentPhase = null;
  let dashboardResetGeneration = 0;
  let dashboardResetStatus = "idle";
  let experimentResultsClearStatus = "idle";
  const nonPrimarySelectionPointers = new Set();
  const activeScrollPointers = new Map();
  const recentScrollInteractions = new Map();
  const popupWindows = new Map();
  const activeDashboardDialogs = new Set();

  function backendCatalog() {
    return Array.isArray(state.backends) && state.backends.length
      ? state.backends : FALLBACK_BACKENDS;
  }

  function backendSpec(name) {
    return backendCatalog().find((backend) => backend.name === name)
      || backendCatalog()[0] || FALLBACK_BACKENDS[0];
  }

  function backendChoices() {
    return backendCatalog().map((backend) => [
      backend.name,
      backend.label || backend.name,
    ]);
  }

  function hardwareBackends() {
    return new Set(
      backendCatalog()
        .filter((backend) => backend.requires_hardware_confirmation)
        .map((backend) => backend.name),
    );
  }

  function serviceTargetChoices() {
    const choices = [["all", "All services"], ["directory", "Directory"]];
    const seen = new Set(["all", "directory", "gateway"]);
    backendCatalog().forEach((backend) => {
      const target = backend.service_target;
      if (!target || seen.has(target)) return;
      choices.push([target, backend.label || target]);
      seen.add(target);
    });
    choices.push(["gateway", "Gateway"]);
    return choices;
  }

  function contextId() {
    return String(runtimeApi?.state.contextId || "detached");
  }

  function storageKey() {
    return `qfw.dashboard.v1.${contextId()}`;
  }

  function loadPresentation() {
    try {
      const value = JSON.parse(window.localStorage.getItem(storageKey()) || "{}");
      activeIdentity = IDENTITIES.includes(value.identity) ? value.identity : "user-a";
      widgetStates = value.widgets && typeof value.widgets === "object"
        ? value.widgets : {};
    } catch (error) {
      activeIdentity = "user-a";
      widgetStates = {};
    }
  }

  function savePresentation() {
    window.localStorage.setItem(storageKey(), JSON.stringify({
      identity: activeIdentity,
      widgets: widgetStates,
    }));
  }

  function requestUrl(path) {
    return runtimeApi.http.contextUrl(path);
  }

  async function request(path, options = {}) {
    const response = await runtimeApi.http.fetch(requestUrl(path), {
      cache: "no-store",
      headers: { "content-type": "application/json" },
      ...options,
    });
    const payload = await response.json().catch(() => ({ error: "invalid response" }));
    if (!response.ok) {
      const error = new Error(payload.error?.message || payload.error
        || `${response.status} ${response.statusText}`);
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function clearClientDashboardState() {
    dashboardResetGeneration += 1;
    window.localStorage.removeItem(storageKey());
    widgetStates = {};
    Object.keys(selectedOperations).forEach((key) => delete selectedOperations[key]);
    pendingOperationGroups.clear();
    pendingAbortGroups.clear();
    eventCursor = 0;
    Object.keys(logCursors).forEach((key) => delete logCursors[key]);
    progressEvents = [];
    progressPaused = false;
    progressIdentity = activeIdentity;
    selectedDashboardWidget = null;
    selectedExperimentPhase = null;
    state = {
      ...state,
      operations: [],
      experiments: [],
      running_experiments: [],
    };
    window.ElectroBoyFrontend.invokeModule("progress", "clearProgressOutput");
    widgetChannel?.postMessage({ type: "reset" });
  }

  async function clearDashboardState() {
    if (activeIdentity !== "root") {
      throw new Error("clearing Dashboard state requires the root identity");
    }
    if (!await confirmDashboardAction(
      "Clear Dashboard state",
      "Clear saved Dashboard operations, experiments, events, progress, and layout? "
        + "This does not cancel Slurm jobs, release reservations, stop services, "
        + "delete logs, or change credentials.",
      { severity: "danger", confirmLabel: "Clear Dashboard state" },
    )) return;
    dashboardResetStatus = "running";
    renderDashboard();
    publishWidgets();
    try {
      await request("/api/qfw-dashboard/reset", {
        method: "POST",
        body: JSON.stringify({ identity: activeIdentity }),
      });
      clearClientDashboardState();
      dashboardResetStatus = "succeeded";
      renderDashboard();
      await refreshState();
    } catch (error) {
      dashboardResetStatus = "failed";
      renderDashboard();
      publishWidgets();
      await notifyDashboard("Dashboard reset failed", error.message, "danger");
    }
  }

  async function clearExperimentResults() {
    if (!await confirmDashboardAction(
      "Clear experiment results",
      "Clear historical experiment result records for the selected identity? "
        + "Running experiments, Slurm jobs, reservations, downloaded artifacts, "
        + "service state, operations, progress, and layout are not removed.",
      { severity: "danger", confirmLabel: "Clear results" },
    )) return;
    experimentResultsClearStatus = "running";
    renderDashboard();
    publishWidgets();
    try {
      await request("/api/qfw-dashboard/experiments/clear", {
        method: "POST",
        body: JSON.stringify({ identity: activeIdentity }),
      });
      experimentResultsClearStatus = "succeeded";
      renderDashboard();
      await refreshState();
    } catch (error) {
      experimentResultsClearStatus = "failed";
      renderDashboard();
      publishWidgets();
      await notifyDashboard("Experiment results clear failed", error.message, "danger");
    }
  }

  function selectedSource(name) {
    return state.sources?.[name] || {
      name, status: "unavailable", records: [], error: "source has not been observed",
    };
  }

  function element(name, className = "", content = "") {
    const node = document.createElement(name);
    if (className) node.className = className;
    if (content !== "") node.append(document.createTextNode(String(content ?? "")));
    return node;
  }

  function iconButton(iconName, label) {
    const button = element("button", "qfw-icon-button");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const definitions = {
      view: [
        "M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z",
        "M9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0Z",
      ],
      edit: [
        "M4 20h4l11-11-4-4L4 16v4Z",
        "m13-13 4 4",
      ],
      save: [
        "M4 3h13l3 3v15H4V3Z",
        "M8 3v6h8V3",
        "M8 21v-7h8v7",
      ],
      cancel: ["M6 6l12 12", "M18 6 6 18"],
      trash: [
        "M4 7h16",
        "M9 11v6",
        "M15 11v6",
        "M6 7l1 14h10l1-14",
        "M9 7V4h6v3",
      ],
    };
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    (definitions[iconName] || []).forEach((description) => {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", description);
      svg.append(path);
    });
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.append(svg);
    return button;
  }

  function preserveScroll(node) {
    node.dataset.qfwPreserveScroll = "";
    return node;
  }

  function showDashboardOverlay({
    title, message, severity = "info", confirmLabel = "Dismiss", cancelLabel = "",
  }) {
    return new Promise((resolve) => {
      const previousFocus = document.activeElement;
      const overlay = element(
        "div", `qfw-notification-overlay qfw-notification-${severity}`,
      );
      const dialog = element("section", "qfw-notification-dialog");
      dialog.setAttribute("role", cancelLabel ? "alertdialog" : "dialog");
      dialog.setAttribute("aria-modal", "true");
      const heading = element("header", "qfw-notification-header");
      heading.append(
        element("span", "qfw-notification-indicator", severity.toUpperCase()),
        element("h2", "", title),
      );
      const body = element("p", "qfw-notification-message", message);
      const actions = element("footer", "qfw-notification-actions");
      const confirm = element("button", "qfw-notification-confirm", confirmLabel);
      confirm.type = "button";
      let cancel = null;
      if (cancelLabel) {
        cancel = element("button", "qfw-notification-cancel", cancelLabel);
        cancel.type = "button";
        actions.append(cancel);
      }
      actions.append(confirm);
      dialog.append(heading, body, actions);
      overlay.append(dialog);

      function finish(accepted) {
        document.removeEventListener("keydown", onKeyDown, true);
        activeDashboardDialogs.delete(finish);
        overlay.remove();
        if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
          previousFocus.focus({ preventScroll: true });
        }
        resolve(accepted);
      }

      function onKeyDown(event) {
        if (event.key === "Escape") {
          event.preventDefault();
          finish(false);
        }
      }

      confirm.addEventListener("click", () => finish(true));
      cancel?.addEventListener("click", () => finish(false));
      overlay.addEventListener("pointerdown", (event) => {
        if (event.target === overlay) finish(false);
      });
      document.addEventListener("keydown", onKeyDown, true);
      activeDashboardDialogs.add(finish);
      document.body.append(overlay);
      window.requestAnimationFrame(() => confirm.focus({ preventScroll: true }));
    });
  }

  function confirmDashboardAction(title, message, options = {}) {
    return showDashboardOverlay({
      title,
      message,
      severity: options.severity || "warning",
      confirmLabel: options.confirmLabel || "Continue",
      cancelLabel: options.cancelLabel || "Cancel",
    });
  }

  function notifyDashboard(title, message, severity = "info") {
    return showDashboardOverlay({ title, message, severity });
  }

  function selectServiceLogs(service) {
    if (activeIdentity !== "root") {
      return notifyDashboard(
        "Service logs restricted",
        "Select the root cluster identity to inspect service logs.",
        "danger",
      );
    }
    runtimeApi.layout.showProgressPane();
    const pane = runtimeApi.elements.progressOutputPane;
    const mode = pane.querySelector("[data-qfw-filter=mode]");
    const source = pane.querySelector("[data-qfw-filter=source]");
    const component = pane.querySelector("[data-qfw-filter=component]");
    progressIdentity = "root";
    if (mode) mode.value = "logs";
    if (source && service.log_source) source.value = service.log_source;
    if (component && service.log_component) component.value = service.log_component;
    [mode, source, component].filter(Boolean).forEach((control) => {
      control.dispatchEvent(new Event("input"));
      control.dispatchEvent(new Event("change"));
    });
    void refreshEvents();
  }

  async function downloadServiceArchive(serviceId, button = null) {
    if (activeIdentity !== "root") {
      await notifyDashboard(
        "Service logs restricted",
        "Select the root cluster identity to download service diagnostics.",
        "danger",
      );
      return;
    }
    if (!serviceId) {
      await notifyDashboard(
        "Diagnostic download failed",
        "The selected service does not have a service identifier.",
        "danger",
      );
      return;
    }
    if (button) button.disabled = true;
    try {
      const payload = await request(
        "/api/qfw-dashboard/services/archive"
          + `?service_id=${encodeURIComponent(serviceId)}`
          + `&identity=${encodeURIComponent(activeIdentity)}`,
      );
      downloadBase64(payload);
    } catch (error) {
      await notifyDashboard("Diagnostic download failed", error.message, "danger");
    } finally {
      if (button) button.disabled = activeIdentity !== "root"
        || !SERVICE_ARCHIVE_IDS.has(serviceId);
    }
  }

  function showFailedService(service) {
    const overlay = element("div", "qfw-notification-overlay qfw-notification-danger");
    const dialog = element("section", "qfw-notification-dialog qfw-service-failure-dialog");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    const heading = element("header", "qfw-notification-header");
    heading.append(
      element("span", "qfw-notification-indicator", "FAILED"),
      element("h2", "", service.id),
    );
    const detail = element("dl", "qfw-service-failure-detail");
    [
      ["Role", service.role],
      ["Node", service.parent],
      ["State", service.state],
      ["Error", service.detail || "No error detail was reported."],
    ].forEach(([label, value]) => {
      detail.append(element("dt", "", label), element("dd", "", value || "—"));
    });
    const actions = element("footer", "qfw-notification-actions");
    const view = element("button", "", "View logs");
    const download = element("button", "", "Download logs");
    const close = element("button", "qfw-notification-confirm", "Close");
    [view, download, close].forEach((button) => { button.type = "button"; });
    const allowed = activeIdentity === "root";
    view.disabled = !allowed || !service.log_source;
    download.disabled = !allowed;
    const finish = () => {
      document.removeEventListener("keydown", onKeyDown, true);
      activeDashboardDialogs.delete(finish);
      overlay.remove();
    };
    function onKeyDown(event) {
      if (event.key === "Escape") finish();
    }
    view.addEventListener("click", () => {
      finish();
      void selectServiceLogs(service);
    });
    download.addEventListener("click", async () => {
      await downloadServiceArchive(service.id, download);
    });
    close.addEventListener("click", finish);
    overlay.addEventListener("pointerdown", (event) => {
      if (event.target === overlay) finish();
    });
    actions.append(view, download, close);
    dialog.append(heading, detail, actions);
    overlay.append(dialog);
    document.addEventListener("keydown", onKeyDown, true);
    activeDashboardDialogs.add(finish);
    document.body.append(overlay);
    close.focus({ preventScroll: true });
  }

  function downloadBase64(payload) {
    const bytes = Uint8Array.from(
      atob(payload.content_base64),
      (character) => character.charCodeAt(0),
    );
    const anchor = document.createElement("a");
    const url = URL.createObjectURL(new Blob(
      [bytes], { type: payload.mime_type || "application/octet-stream" },
    ));
    anchor.href = url;
    anchor.download = payload.name;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function jobColor(jobId) {
    let hash = 2166136261;
    for (const character of String(jobId)) {
      hash ^= character.charCodeAt(0);
      hash = Math.imul(hash, 16777619) >>> 0;
    }
    return JOB_COLORS[hash % JOB_COLORS.length];
  }

  function topologyState(value) {
    return String(value || "unknown").toLowerCase().match(/^[a-z0-9_-]+/)?.[0]
      || "unknown";
  }

  function sortableValue(value) {
    const text = String(value ?? "").trim();
    if (!text || text === "—") return { type: "empty", value: "" };
    const number = Number(text.replace(/,/g, ""));
    if (/^-?\d+(?:\.\d+)?$/.test(text.replace(/,/g, ""))) {
      return { type: "number", value: number };
    }
    const timestamp = Date.parse(text);
    if (Number.isFinite(timestamp) && /\d{4}-\d{2}-\d{2}/.test(text)) {
      return { type: "date", value: timestamp };
    }
    return { type: "string", value: text.toLowerCase() };
  }

  function compareSortableValues(left, right) {
    const leftValue = sortableValue(left);
    const rightValue = sortableValue(right);
    if (leftValue.type === "empty" && rightValue.type !== "empty") return 1;
    if (rightValue.type === "empty" && leftValue.type !== "empty") return -1;
    if (leftValue.type === rightValue.type
        && ["date", "number"].includes(leftValue.type)) {
      return leftValue.value - rightValue.value;
    }
    return String(leftValue.value).localeCompare(String(rightValue.value), undefined, {
      numeric: true,
    });
  }

  function table(records, columns) {
    const wrapper = preserveScroll(element("div", "qfw-table-wrap"));
    const value = element("table", "qfw-table");
    const head = element("thead");
    const header = element("tr");
    let sortedRecords = [...records];
    columns.forEach(([key, label]) => {
      const heading = element("th");
      const sort = element("button", "qfw-table-sort", label);
      sort.type = "button";
      sort.addEventListener("click", () => {
        sortedRecords.sort((left, right) =>
          compareSortableValues(left[key], right[key]));
        renderRows();
      });
      heading.append(sort);
      header.append(heading);
    });
    head.append(header);
    const body = element("tbody");
    function renderRows() {
      body.replaceChildren();
      sortedRecords.forEach((record) => {
        const row = element("tr");
        columns.forEach(([key]) => row.append(element("td", "", record[key] ?? "—")));
        body.append(row);
      });
      if (!sortedRecords.length) {
        const row = element("tr");
        const cell = element("td", "qfw-empty", "No records");
        cell.colSpan = columns.length;
        row.append(cell);
        body.append(row);
      }
    }
    renderRows();
    value.append(head, body);
    wrapper.append(value);
    return wrapper;
  }

  function serviceTable(records) {
    const wrapper = preserveScroll(element("div", "qfw-table-wrap"));
    const value = element("table", "qfw-table");
    const head = element("thead");
    const header = element("tr");
    const columns = [
      ["service_id", "Service"],
      ["node", "Node"],
      ["state", "State"],
      ["backend", "Backend"],
      ["active_reservations", "Reservations"],
      ["logs", "Logs"],
    ];
    columns.forEach(([, label]) => header.append(element("th", "", label)));
    head.append(header);
    const body = element("tbody");
    records.forEach((service) => {
      const row = element("tr");
      columns.slice(0, -1).forEach(([key]) => {
        row.append(element("td", "", service[key] ?? "—"));
      });
      const logs = element("td");
      const serviceId = String(service.service_id || service.name || "");
      const download = element("button", "", "Download logs");
      download.type = "button";
      download.disabled = activeIdentity !== "root"
        || !SERVICE_ARCHIVE_IDS.has(serviceId);
      if (activeIdentity !== "root") {
        download.title = "Select root identity to download service diagnostics.";
      } else if (!SERVICE_ARCHIVE_IDS.has(serviceId)) {
        download.title = "No diagnostics archive is configured for this service.";
      }
      download.addEventListener("click", async () => {
        await downloadServiceArchive(serviceId, download);
      });
      logs.append(download);
      row.append(logs);
      body.append(row);
    });
    if (!records.length) {
      const row = element("tr");
      const cell = element("td", "qfw-empty", "No records");
      cell.colSpan = columns.length;
      row.append(cell);
      body.append(row);
    }
    value.append(head, body);
    wrapper.append(value);
    return wrapper;
  }

  function experimentModifiedAt(experiment) {
    return experiment.modified_at
      || experiment.completed_at
      || experiment.manifest?.submitted_at
      || experiment.created_at
      || "";
  }

  function experimentTable(records, results) {
    const wrapper = preserveScroll(element("div", "qfw-table-wrap"));
    if (results) {
      const controls = element("div", "qfw-widget-actions");
      const clear = element(
        "button", "qfw-experiment-results-clear danger", "Clear results",
      );
      const status = element("output", "qfw-experiment-results-clear-status");
      clear.type = "button";
      clear.disabled = experimentResultsClearStatus === "running";
      clear.classList.toggle(
        "is-pressed", experimentResultsClearStatus === "running",
      );
      clear.setAttribute(
        "aria-pressed", String(experimentResultsClearStatus === "running"),
      );
      status.setAttribute("aria-live", "polite");
      status.textContent = {
        idle: "", running: "Clearing…", succeeded: "Cleared", failed: "Failed",
      }[experimentResultsClearStatus] || experimentResultsClearStatus;
      clear.addEventListener("click", () => { void clearExperimentResults(); });
      controls.append(clear, status);
      wrapper.append(controls);
    }
    const value = element("table", "qfw-table");
    const head = element("thead");
    const header = element("tr");
    const columns = [
      ["experiment_id", "Experiment"],
      ["identity", "User"],
      ["backend", "Backend"],
      ["example", "Example"],
      ["status", "State"],
      ["modified_at", "Modified At"],
      ["slurm_job_id", "Job"],
      ["action", results ? "Download" : "Action"],
    ];
    const display = (experiment, key) => {
      if (key === "modified_at") return experimentModifiedAt(experiment) || "—";
      return experiment[key] ?? "—";
    };
    let sortKey = results ? "modified_at" : "";
    let sortDirection = results ? -1 : 1;
    let sortedRecords = [...records];
    const compare = (left, right, key) =>
      compareSortableValues(display(left, key), display(right, key)) * sortDirection;
    const body = element("tbody");
    function sortRecords() {
      sortedRecords = [...records];
      if (sortKey) {
        sortedRecords.sort((left, right) => compare(left, right, sortKey));
      }
    }
    columns.forEach(([key, label]) => {
      const heading = element("th");
      if (key === "action") {
        heading.textContent = label;
      } else {
        const sort = element("button", "qfw-table-sort", label);
        sort.type = "button";
        sort.addEventListener("click", () => {
          sortDirection = sortKey === key ? -sortDirection : 1;
          sortKey = key;
          sortRecords();
          renderRows();
        });
        heading.append(sort);
      }
      header.append(heading);
    });
    head.append(header);
    function renderRows() {
      body.replaceChildren();
      sortedRecords.forEach((experiment) => {
        const row = element("tr");
        columns.slice(0, -1).forEach(([key]) => {
          row.append(element("td", "", display(experiment, key)));
        });
        const action = element("td");
        if (results) {
          const download = element("button", "", "Download ZIP");
          download.type = "button";
          download.addEventListener("click", async () => {
            try {
              const payload = await request(
                "/api/qfw-dashboard/experiments/archive"
                  + `?experiment_id=${encodeURIComponent(experiment.experiment_id)}`
                  + `&identity=${encodeURIComponent(activeIdentity)}`,
              );
              downloadBase64(payload);
            } catch (error) {
              await notifyDashboard("Download failed", error.message, "danger");
            }
          });
          action.append(download);
        } else if (experiment.slurm_job_id) {
          const cancel = element("button", "danger", "Cancel");
          cancel.type = "button";
          cancel.addEventListener("click", async () => {
            if (!await confirmDashboardAction(
              "Cancel experiment",
              `Cancel ${experiment.experiment_id}? Its Slurm allocation will be terminated.`,
              { severity: "danger", confirmLabel: "Cancel experiment" },
            )) return;
            try {
              await request("/api/qfw-dashboard/experiments/cancel", {
                method: "POST",
                body: JSON.stringify({
                  experiment_id: experiment.experiment_id,
                  identity: activeIdentity,
                }),
              });
            } catch (error) {
              await notifyDashboard("Cancellation failed", error.message, "danger");
            }
          });
          action.append(cancel);
        } else {
          action.textContent = "—";
        }
        row.append(action);
        body.append(row);
      });
      if (!sortedRecords.length) {
        const row = element("tr");
        const cell = element("td", "qfw-empty", "No records");
        cell.colSpan = columns.length;
        row.append(cell);
        body.append(row);
      }
    }
    sortRecords();
    renderRows();
    value.append(head, body);
    wrapper.append(value);
    return wrapper;
  }

  function combinedServiceRecords(catalog, managed) {
    const records = new Map();
    const key = (item) => `${item.service_id}:${item.node || item.component || ""}`;
    managed.forEach((item) => {
      if (!item.service_id) return;
      records.set(key(item), { ...item });
    });
    catalog.forEach((item) => {
      if (!item.service_id) return;
      records.set(key(item), {
        ...(records.get(key(item)) || {}),
        ...item,
      });
    });
    return [...records.values()].sort((left, right) =>
      String(left.service_id).localeCompare(String(right.service_id)));
  }

  function widgetPayload(id) {
    const docker = selectedSource("docker");
    const slurm = selectedSource("slurm");
    const services = selectedSource("services");
    const servicePlane = selectedSource("service-plane");
    const allocations = selectedSource("allocations");
    if (id === "health") {
      return {
        health: state.health,
        observed_at: state.observed_at,
        sources: Object.values(state.sources || {}).map((source) => ({
          name: source.name,
          status: source.status,
          observed_at: source.observed_at,
          error: source.error,
        })),
      };
    }
    if (id === "inventory") return selectedSource("inventory").records;
    if (id === "nodes") return slurm.records.filter((item) => item.kind === "node");
    if (id === "services") {
      return combinedServiceRecords(services.records, servicePlane.records);
    }
    if (id === "allocations") {
      return [
        ...slurm.records.filter((item) => item.kind === "job"),
        ...allocations.records,
      ];
    }
    if (id === "experiments") return state.running_experiments || [];
    if (id === "results") return state.experiments || [];
    if (id === "alerts") {
      return Object.values(state.sources || {})
        .filter((source) => source.status !== "ready")
        .map((source) => ({
          component: source.name,
          state: source.status,
          detail: source.error || "not ready",
        }));
    }
    if (id === "topology") {
      return {
        containers: docker.records,
        nodes: slurm.records.filter((item) => item.kind === "node"),
        allocations: [
          ...slurm.records.filter((item) => item.kind === "job"),
          ...allocations.records,
        ],
        services: combinedServiceRecords(services.records, servicePlane.records),
        service_plane: servicePlane.records,
        experiments: state.running_experiments || [],
        source_status: {
          slurm: slurm.status,
          services: services.status,
          allocations: allocations.status,
          service_plane: servicePlane.status,
        },
      };
    }
    return {};
  }

  function renderHealth(payload) {
    const root = element("div", "qfw-health");
    root.append(element("strong", `qfw-state qfw-${payload.health}`, payload.health));
    root.append(element("span", "qfw-freshness", payload.observed_at || "not observed"));
    root.append(table(payload.sources || [], [
      ["name", "Source"], ["status", "State"], ["observed_at", "Observed"],
    ]));
    return root;
  }

  function renderAlerts(payload) {
    const root = element("div", "qfw-alerts");
    if (!payload.length) {
      root.append(element("p", "qfw-empty", "No active alerts"));
      return root;
    }
    payload.forEach((alert) => {
      const panel = element("article", "qfw-alert");
      const header = element("header", "qfw-alert-header");
      header.append(
        element("strong", "qfw-alert-component", alert.component || "unknown component"),
        element("span", `qfw-state qfw-${alert.state || "unavailable"}`,
          alert.state || "unavailable"),
      );
      const detail = preserveScroll(element(
        "pre", "qfw-alert-detail qfw-resizable-text",
      ));
      detail.textContent = typeof alert.detail === "string"
        ? alert.detail : JSON.stringify(alert.detail, null, 2);
      panel.append(header, detail);
      root.append(panel);
    });
    return root;
  }

  function renderTopology(payload) {
    const root = preserveScroll(element("div", "qfw-topology"));
    const controls = element("div", "qfw-inline-controls");
    const projection = element("select");
    projection.className = "qfw-topology-projection";
    ["Cluster", "Experiment"].forEach((label) => {
      const option = element("option", "", label);
      option.value = label.toLowerCase();
      projection.append(option);
    });
    projection.value = widgetStates.topology?.projection || "cluster";
    projection.selectedOptions[0]?.setAttribute("selected", "selected");
    projection.addEventListener("change", () => {
      widgetStates.topology = { ...widgetStates.topology, projection: projection.value };
      savePresentation();
      renderDashboard();
      publishWidgets();
    });
    const filter = element("input");
    filter.className = "qfw-topology-filter";
    filter.placeholder = "filter objects";
    filter.value = widgetStates.topology?.filter || "";
    filter.setAttribute("value", filter.value);
    const zoom = element("input");
    zoom.className = "qfw-topology-zoom";
    zoom.type = "range";
    zoom.min = String(TOPOLOGY_ZOOM_MIN);
    zoom.max = String(TOPOLOGY_ZOOM_MAX);
    zoom.step = String(TOPOLOGY_ZOOM_STEP);
    const savedTopologyZoom = Number(widgetStates.topology?.zoom || 100);
    const safeTopologyZoom = Number.isFinite(savedTopologyZoom)
      ? savedTopologyZoom : 100;
    zoom.value = String(Math.min(
      TOPOLOGY_ZOOM_MAX,
      Math.max(TOPOLOGY_ZOOM_MIN, safeTopologyZoom),
    ));
    zoom.setAttribute("value", zoom.value);
    const zoomValue = element("output", "qfw-topology-zoom-value", `${zoom.value}%`);
    const projectionLabel = element("label", "qfw-control-group", "Projection ");
    projectionLabel.append(projection);
    const filterLabel = element("label", "qfw-control-group", "Filter ");
    filterLabel.append(filter);
    const zoomControlLabel = element("label", "qfw-control-group", "Zoom ");
    zoomControlLabel.append(zoom, zoomValue);
    controls.append(projectionLabel, filterLabel, zoomControlLabel);
    const hover = element("div", "qfw-topology-hover");
    hover.hidden = true;
    root.append(controls, hover);
    function showTopologyHover(anchor, event, item, jobs = item.jobs || []) {
      const title = element(
        "strong", "qfw-topology-hover-title",
        `${item.type}: ${item.id}`,
      );
      const summary = element(
        "span", "qfw-topology-hover-summary",
        `${item.role ? `${item.role} · ` : ""}${item.state || "unknown"}`,
      );
      const entries = jobs.map((job) => {
        const row = element("div", "qfw-topology-hover-job");
        const swatch = element("span", "qfw-topology-hover-swatch");
        swatch.style.background = job.color;
        row.append(
          swatch,
          element("span", "", `Job ${job.job_id} · ${job.application}`),
          element("small", "", `${job.user} · ${job.qpm_state || job.state}`),
        );
        return row;
      });
      hover.replaceChildren(title, summary, ...entries);
      hover.hidden = false;
      const rootBounds = root.getBoundingClientRect();
      const anchorBounds = anchor.getBoundingClientRect();
      const clientX = event?.clientX ?? anchorBounds.right;
      const clientY = event?.clientY ?? anchorBounds.top;
      const scaleX = root.offsetWidth > 0
        ? rootBounds.width / root.offsetWidth : 1;
      const scaleY = root.offsetHeight > 0
        ? rootBounds.height / root.offsetHeight : 1;
      const safeScaleX = Number.isFinite(scaleX) && scaleX > 0 ? scaleX : 1;
      const safeScaleY = Number.isFinite(scaleY) && scaleY > 0 ? scaleY : 1;
      hover.style.left = `${root.scrollLeft
        + (clientX - rootBounds.left + 14) / safeScaleX}px`;
      hover.style.top = `${root.scrollTop
        + (clientY - rootBounds.top + 14) / safeScaleY}px`;
    }
    function hideTopologyHover() {
      hover.hidden = true;
    }
    const pendingSources = Object.entries(payload.source_status || {})
      .filter(([, status]) => status === "loading")
      .map(([name]) => name);
    if (pendingSources.length) {
      root.append(element(
        "p", "qfw-topology-loading",
        `Loading live topology sources: ${pendingSources.join(", ")}`,
      ));
    }
    const slurmJobs = (payload.allocations || []).filter((item) =>
      item.kind === "job" && item.job_id);
    const canonicalJobId = (value) => String(value || "").split("+")[0];
    const jobDetails = new Map();
    slurmJobs.forEach((job) => {
      const jobId = canonicalJobId(job.job_id);
      const current = jobDetails.get(jobId) || {};
      jobDetails.set(jobId, {
        job_id: jobId,
        application: current.application || job.job_name || "Slurm job",
        user: current.user || job.user || "unknown",
        state: job.state || current.state || "unknown",
        color: jobColor(jobId),
      });
    });
    function nodeHasJob(node, job) {
      const nodeList = String(job.nodes || "");
      if (!nodeList || nodeList.startsWith("(")) return false;
      if (nodeList.split(",").includes(node)) return true;
      const match = node.match(/^(.*?)(\d+)$/);
      if (!match) return false;
      const [, prefix, numberText] = match;
      const bracket = nodeList.match(new RegExp(
        `^${prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\[([^\\]]+)\\]$`,
      ));
      if (!bracket) return false;
      const number = Number(numberText);
      return bracket[1].split(",").some((part) => {
        const [first, last = first] = part.split("-").map(Number);
        return number >= first && number <= last;
      });
    }
    const topologyServices = new Map();
    (payload.services || []).forEach((item) => {
      const serviceId = item.service_id || item.name;
      if (!serviceId) return;
      const current = topologyServices.get(serviceId);
      const primaryNode = item.assigned_hosts?.[0];
      if (!current || item.node === primaryNode) topologyServices.set(serviceId, item);
    });
    const serviceRoles = {
      directory: ["Directory Service", "directory"],
      gateway: ["Slurm Gateway", "gateway"],
      dvm: ["PRTE DVM", "dvm"],
    };
    const qpmJobs = new Map();
    (payload.allocations || []).filter((item) =>
      Array.isArray(item.allocations)).forEach((allocation) => {
      const jobId = canonicalJobId(allocation.job_id);
      if (!jobId) return;
      const detail = jobDetails.get(jobId) || {
        job_id: jobId,
        application: "Slurm job",
        user: allocation.user || "unknown",
        state: allocation.state || "unknown",
        color: jobColor(jobId),
      };
      allocation.allocations.forEach((reservation) => {
        const serviceId = reservation.service_id;
        if (!serviceId) return;
        if (!qpmJobs.has(serviceId)) qpmJobs.set(serviceId, new Map());
        qpmJobs.get(serviceId).set(jobId, {
          ...detail,
          qpm_state: reservation.state || allocation.qstate || "unknown",
        });
      });
    });
    const clusterNodes = new Map();
    clusterNodes.set("slurmctld", {
      type: "node", id: "slurmctld", state: "registered",
      role: "Slurm controller",
    });
    (payload.nodes || []).forEach((item) => {
      const jobs = slurmJobs.filter((job) => nodeHasJob(item.node, job))
        .map((job) => jobDetails.get(canonicalJobId(job.job_id)))
        .filter((job, index, values) => job
          && values.findIndex((value) => value.job_id === job.job_id) === index);
      clusterNodes.set(item.node, {
        type: "node", id: item.node, state: item.state,
        partition: String(item.partition || "").replace(/\*$/, ""),
        activity: jobs.map((job) => (
          `${job.application} [${job.job_id}] · ${job.state} · ${job.user}`
        )).join("\n"),
        jobs,
      });
    });
    const objects = projection.value === "cluster"
      ? [
          ...clusterNodes.values(),
          ...[...topologyServices.values()].map((item) => {
            const [role, logComponent] = serviceRoles[item.component]
              || ["QPMd", "qpmd"];
            return {
              type: "service",
              id: item.service_id || item.name,
              role,
              log_component: logComponent,
              log_source: {
                "directory-service": "directory",
                "qfw-slurm-gateway": "gateway",
                "nwqsim-dvm": "nwqsim-dvm",
                nwqsim: "nwqsim-qpm",
                "iqm-ornl-20q": "iqm-qpm",
                "shim-ornl-20q": "shim-qpm",
                "fake-iqm": "fake-iqm-qpm",
              }[item.service_id || item.name] || "",
              jobs: [...(qpmJobs.get(item.service_id || item.name)?.values() || [])],
              state: item.state || item.status,
              detail: item.detail || item.error || "",
              parent: item.node || "slurmctld",
            };
          }),
        ]
      : (payload.experiments || []).flatMap((item) => {
          const jobs = (payload.allocations || []).filter((job) =>
            String(job.job_id || "").split("+")[0] === String(item.slurm_job_id));
          const records = item.result?.records || [];
          const slurmRecords = item.result?.slurm_records || [];
          const providerJobs = records.flatMap((record) => {
            const identifier = record.provider_job_id || record.iqm_job_id
              || record.details?.provider_job_id;
            return identifier ? [{
              type: "provider-job", id: String(identifier), state: record.status,
              parent: item.slurm_job_id,
            }] : [];
          });
          return [
            { type: "experiment", id: item.experiment_id, state: item.status },
            {
              type: "job", id: item.slurm_job_id, state: item.status,
              parent: item.experiment_id,
            },
            ...jobs.map((job) => ({
              type: String(job.job_id).includes("+") ? "heterogeneous-group" : "job-state",
              id: String(job.job_id), state: job.state, parent: item.slurm_job_id,
            })),
            ...jobs.filter((job) => job.nodes).map((job) => ({
              type: "allocated-nodes", id: `${job.job_id}:${job.nodes}`,
              state: job.state, parent: String(job.job_id),
            })),
            ...slurmRecords.map((record) => ({
              type: record.kind === "step" ? "job-step" : "accounting-job",
              id: String(record.job_id), state: record.state,
              parent: item.slurm_job_id,
            })),
            ...(item.reservations || []).map((entry) => ({
              type: "reservation", id: entry.join(":"), state: item.status,
              parent: item.slurm_job_id,
            })),
            ...providerJobs,
            ...(item.result && Object.keys(item.result).length ? [{
              type: "result", id: `${item.experiment_id}:result`,
              state: item.status, parent: item.experiment_id,
            }] : []),
            ...(item.artifacts || []).map((path, index) => ({
              type: "artifact", id: `${item.experiment_id}:artifact:${index}`,
              path, state: "retained", parent: `${item.experiment_id}:result`,
            })),
          ];
        }).filter((item) => item.id);
    objects.sort((left, right) => `${left.type}:${left.id}`
      .localeCompare(`${right.type}:${right.id}`));
    const visibleObjects = objects.filter((item) => !filter.value
      || JSON.stringify(item).toLowerCase().includes(filter.value.toLowerCase()));
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("qfw-topology-graph");
    svg.style.width = `${Number(zoom.value)}%`;
    const positions = new Map();
    const partitionFrames = [];
    function objectHeight(item) {
      return item?.type === "service" && item.jobs?.length
        ? 68 + item.jobs.length * 7 : 64;
    }
    function placeObjectRows(items, startY, startX = 35) {
      let rowY = startY;
      for (let index = 0; index < items.length; index += 4) {
        const row = items.slice(index, index + 4);
        row.forEach((item, column) => positions.set(item.id, {
          x: startX + column * 215,
          y: rowY,
        }));
        rowY += Math.max(...row.map(objectHeight), 64) + 20;
      }
      return rowY;
    }
    let graphHeight = 500;
    if (projection.value === "cluster") {
      const objectsById = new Map(objects.map((item) => [item.id, item]));
      const partitionCache = new Map();
      function objectPartition(item, visited = new Set()) {
        if (!item || visited.has(item.id)) return "";
        if (item.partition) return item.partition;
        if (partitionCache.has(item.id)) return partitionCache.get(item.id);
        visited.add(item.id);
        const resolved = objectPartition(objectsById.get(item.parent), visited);
        partitionCache.set(item.id, resolved);
        return resolved;
      }
      const partitioned = new Map();
      const unpartitioned = [];
      visibleObjects.forEach((item) => {
        const partition = objectPartition(item);
        item.partition = partition;
        if (!partition) {
          unpartitioned.push(item);
          return;
        }
        if (!partitioned.has(partition)) partitioned.set(partition, []);
        partitioned.get(partition).push(item);
      });
      const controller = unpartitioned.find((item) => item.type === "controller");
      if (controller) positions.set(controller.id, { x: 357, y: 25 });
      const controllerObjects = unpartitioned.filter((item) => item !== controller);
      const controllerBottom = placeObjectRows(controllerObjects, 110);
      let partitionY = controllerObjects.length ? controllerBottom + 5 : 115;
      [...partitioned.entries()].sort(([left], [right]) =>
        left.localeCompare(right)).forEach(([partition, items], partitionIndex) => {
        items.sort((left, right) => {
          const typeOrder = { node: 0, job: 1, service: 2, dvm: 3 };
          return (typeOrder[left.type] ?? 4) - (typeOrder[right.type] ?? 4)
            || String(left.id).localeCompare(String(right.id));
        });
        const frame = {
          id: partition,
          x: 20,
          y: partitionY,
          width: 860,
          height: 0,
          index: partitionIndex,
        };
        partitionFrames.push(frame);
        const itemBottom = placeObjectRows(items, frame.y + 50, frame.x + 22);
        frame.height = Math.max(142, itemBottom - frame.y + 4);
        partitionY += frame.height + 24;
      });
      graphHeight = Math.max(500, partitionY + 20);
    } else {
      visibleObjects.forEach((item, index) => positions.set(item.id, {
        x: 35 + (index % 4) * 215,
        y: 35 + Math.floor(index / 4) * 100,
      }));
      graphHeight = Math.max(500, 135 + Math.ceil(visibleObjects.length / 4) * 100);
    }
    svg.setAttribute("viewBox", `0 0 900 ${graphHeight}`);
    const connectorSourceColors = new Map();
    [...new Set(visibleObjects.filter((item) =>
      item.parent && positions.has(item.parent) && positions.has(item.id))
      .map((item) => item.parent))]
      .sort((left, right) => String(left).localeCompare(String(right)))
      .forEach((sourceId, index) => {
        connectorSourceColors.set(
          sourceId,
          TOPOLOGY_CONNECTOR_COLORS[index % TOPOLOGY_CONNECTOR_COLORS.length],
        );
      });
    function topologyConnectorColor(sourceId) {
      return connectorSourceColors.get(sourceId) || TOPOLOGY_CONNECTOR_COLORS[0];
    }
    partitionFrames.forEach((frame) => {
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      group.classList.add(
        "qfw-topology-partition",
        `qfw-topology-partition-${frame.index % 4}`,
      );
      const box = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      box.classList.add("qfw-topology-partition-box");
      box.setAttribute("x", String(frame.x));
      box.setAttribute("y", String(frame.y));
      box.setAttribute("width", String(frame.width));
      box.setAttribute("height", String(frame.height));
      box.setAttribute("rx", "14");
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.classList.add("qfw-topology-partition-label");
      label.setAttribute("x", String(frame.x + 18));
      label.setAttribute("y", String(frame.y + 28));
      label.textContent = `PARTITION · ${frame.id}`;
      group.append(box, label);
      svg.append(group);
    });
    visibleObjects.forEach((item) => {
      const source = positions.get(item.parent);
      const target = positions.get(item.id);
      if (!source || !target) return;
      const parentObject = objects.find((candidate) => candidate.id === item.parent);
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(source.x + 92));
      line.setAttribute("y1", String(source.y + objectHeight(parentObject) / 2));
      line.setAttribute("x2", String(target.x + 92));
      line.setAttribute("y2", String(target.y + objectHeight(item) / 2));
      const serviceEdge = item.type === "service" || parentObject?.type === "service";
      line.setAttribute(
        "class",
        `qfw-topology-edge ${serviceEdge
          ? "qfw-topology-edge-service" : "qfw-topology-edge-object"}`,
      );
      line.dataset.sourceObject = item.parent;
      line.style.setProperty(
        "--qfw-topology-edge-color",
        topologyConnectorColor(item.parent),
      );
      svg.append(line);
    });
    visibleObjects.forEach((item) => {
      const position = positions.get(item.id);
      if (!position) return;
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      group.setAttribute("transform", `translate(${position.x} ${position.y})`);
      group.setAttribute("tabindex", "0");
      group.setAttribute("role", "button");
      group.dataset.objectId = item.id;
      group.classList.add(
        "qfw-topology-object",
        `qfw-topology-state-${topologyState(item.state)}`,
      );
      if (item.type === "service") group.classList.add("qfw-topology-service");
      if (item.activity) group.classList.add("has-activity");
      if (item.jobs?.length && item.type !== "service") {
        group.classList.add("qfw-topology-job-active");
        group.style.setProperty("--qfw-job-color", item.jobs[0].color);
      }
      const box = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      box.setAttribute("width", "185");
      box.setAttribute("height", String(objectHeight(item)));
      box.setAttribute("rx", item.type === "service" ? "16" : "8");
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", item.type === "service" ? "92.5" : "10");
      label.setAttribute("y", "25");
      if (item.type === "service") label.setAttribute("text-anchor", "middle");
      label.textContent = `${item.type}: ${item.id}`;
      const status = document.createElementNS("http://www.w3.org/2000/svg", "text");
      status.setAttribute("x", item.type === "service" ? "92.5" : "10");
      status.setAttribute("y", "48");
      if (item.type === "service") status.setAttribute("text-anchor", "middle");
      status.textContent = item.role
        ? `${item.role} · ${item.state || "unknown"}` : item.state || "unknown";
      const select = () => {
        widgetStates.topology = { ...widgetStates.topology, selected: item.id };
        savePresentation();
        const component = runtimeApi.elements.progressOutputPane
          .querySelector("[data-qfw-filter=component]");
        const contextFilter = runtimeApi.elements.progressOutputPane
          .querySelector("[data-qfw-filter=context]");
        if (component) {
          const mapping = {
            "job": "slurm", "job-state": "slurm", "job-step": "slurm",
            "accounting-job": "slurm", "service": "qpmd",
            "directory": "directory", "gateway": "gateway", "dvm": "dvm",
            "provider-job": "provider", "experiment": "application",
            "result": "application", "artifact": "application",
          };
          const serviceComponent = item.type === "service" ? item.log_component : "";
          component.value = serviceComponent || mapping[item.type] || "";
          component.dispatchEvent(new Event("change"));
        }
        if (contextFilter && [...contextFilter.options]
          .some((option) => option.value === item.id)) {
          contextFilter.value = item.id;
          renderProgress();
        }
        if (item.type === "result" || item.type === "artifact") {
          const resultWidget = root.closest(".qfw-dashboard")
            ?.querySelector("[data-widget=results]");
          if (resultWidget) {
            resultWidget.open = true;
            resultWidget.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }
        const failedStates = new Set([
          "down", "failed", "stopped", "unavailable", "drained", "cancelled",
        ]);
        if (item.type === "service"
          && failedStates.has(topologyState(item.state))) {
          showFailedService(item);
        }
        renderDashboard();
        publishWidgets();
      };
      group.addEventListener("pointerenter", (event) => {
        showTopologyHover(group, event, item);
      });
      group.addEventListener("pointermove", (event) => {
        showTopologyHover(group, event, item);
      });
      group.addEventListener("pointerleave", hideTopologyHover);
      group.addEventListener("focus", () => showTopologyHover(group, null, item));
      group.addEventListener("blur", hideTopologyHover);
      group.addEventListener("click", select);
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") select();
      });
      group.append(box, label, status);
      if (item.type === "service" && item.jobs?.length
        && !["down", "failed", "stopped", "unavailable"].includes(
          topologyState(item.state)
        )) {
        item.jobs.forEach((job, jobIndex) => {
          const stripe = document.createElementNS(
            "http://www.w3.org/2000/svg", "rect",
          );
          stripe.classList.add("qfw-topology-job-stripe");
          stripe.setAttribute("x", "8");
          stripe.setAttribute("y", String(62 + jobIndex * 7));
          stripe.setAttribute("width", "169");
          stripe.setAttribute("height", "5");
          stripe.setAttribute("rx", "2.5");
          stripe.style.fill = job.color;
          stripe.addEventListener("pointerenter", (event) => {
            event.stopPropagation();
            showTopologyHover(stripe, event, item, [job]);
          });
          stripe.addEventListener("pointermove", (event) => {
            event.stopPropagation();
            showTopologyHover(stripe, event, item, [job]);
          });
          group.append(stripe);
        });
      }
      svg.append(group);
    });
    filter.addEventListener("input", () => {
      widgetStates.topology = { ...widgetStates.topology, filter: filter.value };
      savePresentation();
      renderDashboard();
      publishWidgets();
    });
    zoom.addEventListener("input", () => {
      if (!Number.isFinite(Number(zoom.value)) || Number(zoom.value) <= 0) return;
      widgetStates.topology = { ...widgetStates.topology, zoom: Number(zoom.value) };
      svg.style.width = `${zoom.value}%`;
      zoomValue.textContent = `${zoom.value}%`;
      savePresentation();
      publishWidgets();
    });
    root.append(svg, table(visibleObjects, [
      ["type", "Object"], ["role", "Role"], ["id", "Identifier"],
      ["state", "State"],
      ["partition", "Partition"], ["activity", "Active work"],
    ]));
    const selected = visibleObjects.find((item) =>
      item.id === widgetStates.topology?.selected);
    if (selected) {
      root.append(element("h4", "", "Selected object"));
      root.append(element("pre", "qfw-topology-selection",
        JSON.stringify(selected, null, 2)));
    }
    return root;
  }

  function renderWidgetBody(id, payload) {
    if (id === "cluster-control") return renderClusterControl();
    if (id === "service-control") return renderServiceControl();
    if (id === "node-control") return renderNodeControl();
    if (id === "cluster-access") return renderClusterAccess();
    const query = String(widgetStates[id]?.filter || "").toLowerCase();
    if (query && Array.isArray(payload)) {
      payload = payload.filter((item) => JSON.stringify(item).toLowerCase().includes(query));
    }
    if (id === "health") return renderHealth(payload);
    if (id === "inventory") {
      return table(payload, [
        ["kind", "Kind"], ["component", "Component"],
        ["value", "Version, revision, or fingerprint"], ["path", "Path"],
      ]);
    }
    if (id === "nodes") {
      return table(payload, [
        ["node", "Node"], ["partition", "Partition"], ["state", "State"],
        ["cpus", "CPUs"], ["memory", "Memory"], ["reason", "Reason"],
      ]);
    }
    if (id === "services") {
      return serviceTable(payload);
    }
    if (id === "allocations") {
      return table(payload, [
        ["job_id", "Job"], ["user", "User"], ["state", "State"],
        ["partition", "Partition"], ["nodes", "Nodes"], ["reason", "Reason"],
      ]);
    }
    if (id === "experiments") return experimentTable(payload, false);
    if (id === "results") return experimentTable(payload, true);
    if (id === "alerts") {
      return renderAlerts(payload);
    }
    if (id === "topology") return renderTopology(payload);
    return element("pre", "", JSON.stringify(payload, null, 2));
  }

  function openWidget(id, label) {
    const instanceId = `${contextId()}:${id}`;
    const existing = popupWindows.get(instanceId);
    if (existing && !existing.closed) {
      existing.focus();
      return;
    }
    const parameters = new URLSearchParams({
      widget: id, label, instance_id: instanceId, context_id: contextId(),
    });
    const popup = window.open(
      `/qfw-dashboard/widget?${parameters.toString()}`,
      `qfw-widget-${instanceId.replace(/[^A-Za-z0-9_-]/g, "-")}`,
      "popup=yes,width=1000,height=720,resizable=yes,scrollbars=yes",
    );
    if (!popup) {
      void notifyDashboard(
        "Pop-out blocked",
        "The browser blocked the dashboard widget window.",
        "danger",
      );
      return;
    }
    popupWindows.set(instanceId, popup);
    window.setTimeout(publishWidgets, 100);
  }

  function buildWidget(id, label) {
    const details = element("details", "qfw-widget");
    let pulseHash = 0;
    for (const character of id) {
      pulseHash = ((pulseHash * 33) + character.charCodeAt(0)) >>> 0;
    }
    const traceDuration = 10000 + (pulseHash % 6000);
    const tracePhase = (Date.now() + (pulseHash * 104729)) % traceDuration;
    details.style.setProperty("--qfw-border-duration", `${traceDuration}ms`);
    details.style.setProperty("--qfw-border-delay", `${-tracePhase}ms`);
    details.dataset.widget = id;
    details.classList.toggle("is-active", id === selectedDashboardWidget);
    const operationGroup = OPERATION_WIDGET_GROUPS[id];
    details.classList.toggle(
      "has-error",
      Boolean(operationGroup && operationForGroup(operationGroup)?.status === "failed"),
    );
    details.open = widgetStates[id]?.expanded !== false;
    const summary = element("summary");
    const chevron = element("span", "qfw-widget-chevron", "›");
    chevron.setAttribute("aria-hidden", "true");
    summary.append(chevron);
    summary.append(element("span", "qfw-widget-title", label));
    const filter = element("input", "qfw-widget-filter");
    filter.type = "search";
    filter.placeholder = "filter";
    filter.value = widgetStates[id]?.filter || "";
    filter.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
    filter.addEventListener("input", (event) => {
      event.preventDefault();
      event.stopPropagation();
      widgetStates[id] = { ...widgetStates[id], filter: filter.value };
      savePresentation();
      const body = details.children[1];
      body.replaceWith(renderWidgetBody(id, widgetPayload(id)));
      publishWidgets();
    });
    const pop = element("button", "qfw-popout", "Pop out");
    pop.type = "button";
    pop.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openWidget(id, label);
    });
    if (!NON_FILTERABLE_WIDGETS.has(id)) summary.append(filter);
    summary.append(pop);
    details.append(summary, renderWidgetBody(id, widgetPayload(id)));
    details.addEventListener("toggle", () => {
      widgetStates[id] = { ...widgetStates[id], expanded: details.open };
      savePresentation();
      publishWidgets();
    });
    return details;
  }

  function buildWidgetGroup(group) {
    const section = element("section", "qfw-widget-group");
    section.dataset.group = group.id;
    const heading = element("h3", "qfw-widget-group-title");
    heading.append(element("span", "", group.label));
    section.append(heading);
    const grid = element("div", "qfw-widget-grid");
    if (group.experimentLauncher) renderExperimentForm(grid);
    group.widgets.forEach(([id, label, layout]) => {
      const widget = buildWidget(id, label);
      if (layout === "wide") widget.classList.add("qfw-grid-wide");
      grid.append(widget);
    });
    section.append(grid);
    return section;
  }

  function canvasCamera() {
    const saved = widgetStates.canvas || {};
    const savedScale = Number(saved.scale);
    const safeScale = Number.isFinite(savedScale) && savedScale > 0
      ? savedScale : 1;
    return {
      x: Number.isFinite(Number(saved.x)) ? Number(saved.x) : 32,
      y: Number.isFinite(Number(saved.y)) ? Number(saved.y) : 32,
      scale: Math.min(
        CANVAS_ZOOM_MAX / 100,
        Math.max(CANVAS_ZOOM_MIN / 100, safeScale),
      ),
    };
  }

  function saveCanvasCamera(camera) {
    widgetStates.canvas = { x: camera.x, y: camera.y, scale: camera.scale };
    savePresentation();
  }

  function scrollableWheelTarget(event, boundary) {
    return event.composedPath().some((target) => {
      if (!(target instanceof Element) || target === boundary) return false;
      if (!boundary.contains(target)) return false;
      const style = window.getComputedStyle(target);
      const scrollsVertically = event.deltaY !== 0
        && /^(auto|scroll)$/.test(style.overflowY)
        && target.scrollHeight > target.clientHeight;
      const scrollsHorizontally = event.deltaX !== 0
        && /^(auto|scroll)$/.test(style.overflowX)
        && target.scrollWidth > target.clientWidth;
      return scrollsVertically || scrollsHorizontally;
    });
  }

  function installCanvasInteraction(viewport, stage, zoomLabel, zoomSlider = null) {
    const camera = canvasCamera();
    let pan = null;

    function apply() {
      stage.style.left = `${camera.x / camera.scale}px`;
      stage.style.top = `${camera.y / camera.scale}px`;
      stage.style.zoom = String(camera.scale);
      const percent = Math.round(camera.scale * 100);
      zoomLabel.textContent = `${percent}%`;
      if (zoomSlider) zoomSlider.value = String(percent);
    }

    function zoomAt(clientX, clientY, factor) {
      const bounds = viewport.getBoundingClientRect();
      const localX = clientX - bounds.left;
      const localY = clientY - bounds.top;
      const previous = camera.scale;
      const requested = previous * factor;
      const next = Math.min(
        CANVAS_ZOOM_MAX / 100,
        Math.max(CANVAS_ZOOM_MIN / 100, requested),
      );
      if (!Number.isFinite(next) || next <= 0) return;
      const worldX = (localX - camera.x) / previous;
      const worldY = (localY - camera.y) / previous;
      camera.scale = next;
      camera.x = localX - worldX * next;
      camera.y = localY - worldY * next;
      apply();
      saveCanvasCamera(camera);
    }

    function setZoomAt(clientX, clientY, percent) {
      const next = Number(percent) / 100;
      if (!Number.isFinite(next) || next <= 0) return;
      zoomAt(clientX, clientY, next / camera.scale);
    }

    viewport.addEventListener("wheel", (event) => {
      if (scrollableWheelTarget(event, viewport)) return;
      event.preventDefault();
      zoomAt(event.clientX, event.clientY, Math.exp(-event.deltaY * 0.0015));
    }, { passive: false });
    viewport.addEventListener("pointerdown", (event) => {
      if (event.button !== 1 || pan) return;
      event.preventDefault();
      pan = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
      viewport.setPointerCapture(event.pointerId);
      activeCanvasPans += 1;
      viewport.classList.add("is-panning");
    });
    viewport.addEventListener("pointermove", (event) => {
      if (!pan || pan.pointerId !== event.pointerId) return;
      camera.x += event.clientX - pan.x;
      camera.y += event.clientY - pan.y;
      pan.x = event.clientX;
      pan.y = event.clientY;
      apply();
    });
    function finishPan(event) {
      if (!pan || pan.pointerId !== event.pointerId) return;
      pan = null;
      activeCanvasPans = Math.max(0, activeCanvasPans - 1);
      viewport.classList.remove("is-panning");
      saveCanvasCamera(camera);
      if (!activeCanvasPans && dashboardRenderPending) {
        dashboardRenderPending = false;
        window.requestAnimationFrame(renderDashboard);
      }
    }
    viewport.addEventListener("pointerup", finishPan);
    viewport.addEventListener("pointercancel", finishPan);
    viewport.addEventListener("lostpointercapture", finishPan);
    viewport.addEventListener("auxclick", (event) => {
      if (event.button === 1) event.preventDefault();
    });
    apply();

    return {
      reset() {
        camera.x = 32;
        camera.y = 32;
        camera.scale = 1;
        apply();
        saveCanvasCamera(camera);
      },
      zoom(factor) {
        const bounds = viewport.getBoundingClientRect();
        zoomAt(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2, factor);
      },
      setZoom(percent) {
        const bounds = viewport.getBoundingClientRect();
        setZoomAt(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2, percent);
      },
    };
  }

  const selectedOperations = {};

  function controlValue(widget, name, fallback) {
    return widgetStates[widget]?.[name] ?? fallback;
  }

  function rememberControl(widget, name, value) {
    widgetStates[widget] = { ...widgetStates[widget], [name]: value };
    savePresentation();
    publishWidgets();
  }

  function selectControl(widget, name, choices, fallback) {
    const control = element("select");
    control.dataset.qfwControl = name;
    choices.forEach(([value, label]) => {
      const option = element("option", "", label);
      option.value = value;
      control.append(option);
    });
    const requested = controlValue(widget, name, fallback);
    control.value = choices.some(([value]) => value === requested)
      ? requested : fallback;
    control.selectedOptions[0]?.setAttribute("selected", "selected");
    control.addEventListener("change", () => {
      rememberControl(widget, name, control.value);
    });
    return control;
  }

  function textControl(widget, name, fallback, placeholder) {
    const control = element("input");
    control.dataset.qfwControl = name;
    control.placeholder = placeholder;
    control.value = controlValue(widget, name, fallback);
    control.setAttribute("value", control.value);
    control.addEventListener("input", () => {
      rememberControl(widget, name, control.value);
    });
    return control;
  }

  function operationField(label, control) {
    const field = element("label", "qfw-operation-field");
    field.append(element("span", "", label), control);
    return field;
  }

  function operationForGroup(group) {
    const matching = (state.operations || []).filter((item) => {
      if (group === "cluster") return item.action?.startsWith("cluster-");
      if (group === "services") return item.action?.startsWith("service-");
      return item.action?.startsWith("node-");
    }).sort((left, right) => String(right.created_at)
      .localeCompare(String(left.created_at)));
    return matching.find((item) => item.operation_id === selectedOperations[group])
      || matching[0] || null;
  }

  function operationMode(widget) {
    return widgetStates[widget]?.operation_mode === "dry-run" ? "dry-run" : "run";
  }

  function operationModeLabel(mode) {
    return mode === "dry-run" ? "Dry-Run" : "Run";
  }

  function setOperationMode(widget, mode) {
    widgetStates[widget] = {
      ...widgetStates[widget],
      operation_mode: mode === "dry-run" ? "dry-run" : "run",
    };
    savePresentation();
    renderDashboard();
    publishWidgets();
  }

  async function runOperation(group, payload) {
    pendingOperationGroups.add(group);
    refreshDashboardData();
    publishWidgets();
    try {
      const response = await request("/api/qfw-dashboard/operations", {
        method: "POST",
        body: JSON.stringify({
          ...payload,
          identity: activeIdentity,
          request_id: window.crypto.randomUUID(),
        }),
      });
      selectedOperations[group] = response.operation_id;
      upsertOperation(response);
      refreshDashboardData();
      publishWidgets();
      if (pendingAbortGroups.delete(group)) {
        await request("/api/qfw-dashboard/operations/abort", {
          method: "POST",
          body: JSON.stringify({
            operation_id: response.operation_id,
            identity: activeIdentity,
          }),
        });
      }
      await refreshState();
    } finally {
      pendingOperationGroups.delete(group);
      pendingAbortGroups.delete(group);
      refreshDashboardData();
      publishWidgets();
    }
  }

  function upsertOperation(operation) {
    if (!operation?.operation_id) return;
    const operations = state.operations || [];
    const index = operations.findIndex((item) =>
      item.operation_id === operation.operation_id);
    state = {
      ...state,
      operations: index >= 0
        ? operations.map((item, itemIndex) =>
          itemIndex === index ? operation : item)
        : [...operations, operation],
    };
  }

  async function abortOperation(group) {
    if (pendingOperationGroups.has(group)) {
      pendingAbortGroups.add(group);
      refreshDashboardData();
      publishWidgets();
      return;
    }
    const operation = operationForGroup(group);
    if (!operation) return;
    await request("/api/qfw-dashboard/operations/abort", {
      method: "POST",
      body: JSON.stringify({
        operation_id: operation.operation_id,
        identity: activeIdentity,
      }),
    });
    await refreshState();
  }

  function operationOutput(group) {
    const operation = operationForGroup(group);
    const output = preserveScroll(element(
      "pre", "qfw-operation-output qfw-resizable-text",
    ));
    if (!operation) {
      output.textContent = "No operation has run in this group.";
      return output;
    }
    const headingStatus = operation.dry_run ? "DRY-RUN" : operation.status.toUpperCase();
    const heading = [
      `${headingStatus} · ${operation.action}`,
      `target=${operation.target} operation=${operation.operation_id}`,
      `created=${operation.created_at || "unknown"} completed=${operation.completed_at || "pending"}`,
    ];
    output.textContent = [...heading, ...(operation.output || [])].join("\n");
    output.scrollTop = output.scrollHeight;
    return output;
  }

  function operationButtons(widget, group, submit) {
    const buttons = element("div", "qfw-operation-buttons");
    const mode = operationMode(widget);
    const split = element("div", "qfw-operation-run-split");
    const run = element("button", "qfw-operation-run", operationModeLabel(mode));
    run.type = "button";
    run.dataset.qfwAction = "run";
    run.dataset.qfwWidget = widget;
    run.addEventListener("click", async () => {
      try {
        await submit(operationMode(widget));
      } catch (error) {
        await notifyDashboard("Operation failed", error.message, "danger");
      }
    });
    const modeValue = element("input");
    modeValue.type = "hidden";
    modeValue.dataset.qfwControl = "operation_mode";
    modeValue.value = mode;
    const modePicker = element("details", "qfw-operation-mode-picker");
    const modeToggle = element("summary", "qfw-operation-mode-toggle", "▾");
    modeToggle.setAttribute("aria-label", "Choose operation mode");
    const modeMenu = element("div", "qfw-operation-mode-menu");
    [["run", "Run"], ["dry-run", "Dry-Run"]].forEach(([value, label]) => {
      const choice = element("button", "", label);
      choice.type = "button";
      choice.dataset.qfwModeChoice = value;
      choice.setAttribute("aria-pressed", String(value === mode));
      choice.addEventListener("click", () => setOperationMode(widget, value));
      modeMenu.append(choice);
    });
    modePicker.append(modeToggle, modeMenu);
    split.append(run, modeValue, modePicker);
    const abort = element("button", "danger", "Abort");
    abort.type = "button";
    abort.dataset.qfwAction = "abort";
    abort.dataset.qfwWidget = widget;
    abort.addEventListener("click", async () => {
      const operation = operationForGroup(group);
      if (!await confirmDashboardAction(
        "Abort operation",
        `Abort ${operation?.action || "operation"}? The active process will be terminated.`,
        { severity: "danger", confirmLabel: "Abort operation" },
      )) return;
      try {
        await abortOperation(group);
      } catch (error) {
        await notifyDashboard("Abort failed", error.message, "danger");
      }
    });
    const status = element("output", "qfw-operation-status");
    status.dataset.qfwOperationStatus = group;
    status.setAttribute("aria-live", "polite");
    buttons.append(split, status, abort);
    applyOperationControlState(buttons, group);
    return buttons;
  }

  function operationControlState(group) {
    const operation = operationForGroup(group);
    const pending = pendingOperationGroups.has(group);
    const abortPending = pendingAbortGroups.has(group);
    const status = abortPending ? "aborting"
      : pending ? "running" : operation?.status || "idle";
    const busy = pending || ["queued", "running", "aborting"].includes(status);
    const labels = {
      idle: "Idle",
      queued: "Queued",
      running: "Running",
      aborting: "Aborting",
      aborted: "Aborted",
      succeeded: "Succeeded",
      failed: "Failed",
    };
    return { abortPending, busy, label: labels[status] || status, operation, status };
  }

  function applyOperationControlState(container, group) {
    const control = operationControlState(group);
    const run = container.querySelector("[data-qfw-action=run]");
    const abort = container.querySelector("[data-qfw-action=abort]");
    const status = container.querySelector("[data-qfw-operation-status]");
    if (run) {
      run.disabled = activeIdentity !== "root" || control.busy;
      run.classList.toggle("is-pressed", control.busy);
      run.setAttribute("aria-pressed", String(control.busy));
    }
    if (abort) {
      abort.disabled = activeIdentity !== "root" || !control.busy
        || control.abortPending;
    }
    if (status) {
      status.className = `qfw-operation-status qfw-operation-${control.status}`;
      status.replaceChildren(element("span", "", control.label));
      if (control.busy) {
        const dots = element("span", "qfw-operation-busy-dots");
        dots.setAttribute("aria-hidden", "true");
        [0, 1, 2].forEach(() => dots.append(element("span", "", "·")));
        status.append(dots);
      }
    }
  }

  function renderClusterControl() {
    const widget = "cluster-control";
    const cluster = element("div", "qfw-operation-control qfw-operation-cluster");
    const clusterAction = selectControl(widget, "operation", [
      ["status", "Status"], ["synchronize", "Synchronize with upstream"],
      ["start", "Start"], ["stop", "Stop"], ["restart", "Restart"],
      ["rebuild", "Rebuild"],
    ], "status");
    const rebuildMode = selectControl(widget, "rebuild_mode", [
      ["incremental", "Incremental (use cache)"],
      ["clean", "Clean (no cache)"],
    ], "incremental");
    cluster.append(
      operationField("Operation", clusterAction),
      operationField("Rebuild mode", rebuildMode),
      operationButtons(widget, "cluster", async (mode) => {
        const operation = clusterAction.value;
        const action = operation === "rebuild"
          ? `cluster-rebuild-${rebuildMode.value}` : `cluster-${operation}`;
        const dryRun = mode === "dry-run";
        if (!dryRun && operation !== "status") {
          const clean = operation === "rebuild" && rebuildMode.value === "clean";
          const consequence = operation === "rebuild"
            ? ` This performs a ${clean ? "no-cache" : "cached"} image build, then restarts and provisions the cluster without deleting named volumes.`
            : "";
          const dangerous = ["stop", "restart", "rebuild"].includes(operation);
          if (!await confirmDashboardAction(
            `${operation[0].toUpperCase()}${operation.slice(1)} cluster`,
            `${operation} cluster as root?${consequence}`,
            {
              severity: dangerous ? "danger" : "warning",
              confirmLabel: `${operation[0].toUpperCase()}${operation.slice(1)} cluster`,
            },
          )) return;
        }
        await runOperation("cluster", { action, target: "cluster", dry_run: dryRun });
      }),
      operationOutput("cluster"),
    );
    return cluster;
  }

  function renderServiceControl() {
    const widget = "service-control";
    const services = element("div", "qfw-operation-control qfw-operation-services");
    const serviceTarget = selectControl(widget, "target", serviceTargetChoices(), "all");
    const serviceAction = selectControl(widget, "operation", [
      ["status", "Status"], ["start", "Start"], ["stop", "Stop"],
      ["restart", "Restart"],
      ["recover", "Recover"],
    ], "status");
    const serviceOutLogLevel = selectControl(
      widget, "defw_log_level", DEFW_OUT_LOG_LEVELS, "error",
    );
    const servicePyLogLevel = selectControl(
      widget, "defw_py_loglevel", DEFW_PY_LOG_LEVELS, "DEFW_ALL",
    );
    const loggingNote = element(
      "p", "qfw-operation-help",
      "These levels are passed to qfw-site-services when the selected service "
        + "is started, restarted, or recovered.",
    );
    services.append(
      operationField("Target", serviceTarget),
      operationField("Operation", serviceAction),
      operationField("Next defw_out.log level", serviceOutLogLevel),
      operationField("Next defw_py.log level", servicePyLogLevel),
      loggingNote,
      operationButtons(widget, "services", async (mode) => {
        const action = serviceAction.value;
        const dryRun = mode === "dry-run";
        const dangerous = ["stop", "restart"].includes(action);
        if (!dryRun && action !== "status" && !await confirmDashboardAction(
          `${action[0].toUpperCase()}${action.slice(1)} service`,
          `${action} ${serviceTarget.value} as root?`,
          {
            severity: dangerous ? "danger" : "warning",
            confirmLabel: `${action[0].toUpperCase()}${action.slice(1)} service`,
          },
        )) return;
        await runOperation("services", {
          action: `service-${action}`,
          target: serviceTarget.value,
          dry_run: dryRun,
          options: ["start", "restart", "recover"].includes(action) ? {
            defw_log_level: serviceOutLogLevel.value,
            defw_py_loglevel: servicePyLogLevel.value,
          } : {},
        });
      }),
      operationOutput("services"),
    );
    return services;
  }

  function slurmNodeNames() {
    return [...new Set(
      selectedSource("slurm").records
        .filter((record) => record.kind === "node" && record.node)
        .map((record) => String(record.node)),
    )].sort((left, right) => left.localeCompare(right));
  }

  function renderNodeControl() {
    const widget = "node-control";
    const nodes = element("div", "qfw-operation-control qfw-operation-nodes");
    const nodeNames = slurmNodeNames();
    const nodeChoices = nodeNames.length
      ? nodeNames.map((name) => [name, name])
      : [["", "No nodes available"]];
    const node = selectControl(widget, "node", nodeChoices, nodeNames[0] || "");
    const nodeAction = selectControl(widget, "operation", [
      ["drain", "Drain"], ["resume", "Resume"],
    ], "drain");
    const reason = textControl(widget, "reason", "qfw-dashboard", "drain reason");
    nodes.append(
      operationField("Node", node),
      operationField("Operation", nodeAction),
      operationField("Reason", reason),
      operationButtons(widget, "nodes", async (mode) => {
        const action = nodeAction.value;
        const dryRun = mode === "dry-run";
        if (!dryRun && !await confirmDashboardAction(
          `${action[0].toUpperCase()}${action.slice(1)} node`,
          `${action} ${node.value} as root?`,
          {
            severity: action === "drain" ? "danger" : "warning",
            confirmLabel: `${action[0].toUpperCase()}${action.slice(1)} node`,
          },
        )) return;
        await runOperation("nodes", {
          action: `node-${action}`,
          target: node.value,
          reason: reason.value,
          dry_run: dryRun,
        });
      }),
      operationOutput("nodes"),
    );
    return nodes;
  }

  function refreshNodeControlChoices(widget) {
    const control = widget.querySelector('[data-qfw-control="node"]');
    if (!control || control === document.activeElement) return;
    const names = slurmNodeNames();
    const available = names.length ? names : [""];
    const existing = [...control.options].map((option) => option.value);
    if (existing.length === available.length
        && existing.every((name, index) => name === available[index])) return;
    const selected = control.value;
    control.replaceChildren();
    if (names.length) {
      names.forEach((name) => {
        const option = element("option", "", name);
        option.value = name;
        control.append(option);
      });
    } else {
      const option = element("option", "", "No nodes available");
      option.value = "";
      control.append(option);
    }
    control.value = names.includes(selected) ? selected : names[0] || "";
  }

  async function openClusterShell(target, confirmRoot = true) {
    if (confirmRoot && activeIdentity === "root"
        && !await confirmDashboardAction(
          "Open root shell",
          `Open a privileged root shell in ${target}?`,
          { severity: "warning", confirmLabel: "Open shell" },
        )) return;
    await request("/api/qfw-dashboard/shell", {
      method: "POST",
      body: JSON.stringify({ identity: activeIdentity, target }),
    });
    runtimeApi.layout.ensurePane("shell", "status", "column");
    window.ElectroBoyFrontend.invokeModule("project-shell", "connectProjectShellEvents");
  }

  function renderClusterAccess() {
    const widget = "cluster-access";
    const access = element("div", "qfw-access-control");
    const shellTarget = element("select");
    shellTarget.dataset.qfwControl = "node";
    ["slurmctld", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8",
      "nwqsim-head", "nwqsim-worker-1", "nwqsim-worker-2", "iqm-head",
      "shim-head", "fake-iqm-head"]
      .forEach((name) => {
        const option = element("option", "", name);
        option.value = name;
        option.disabled = activeIdentity !== "root"
          && (name.startsWith("nwqsim-") || name === "iqm-head"
            || name === "shim-head" || name === "fake-iqm-head");
        shellTarget.append(option);
      });
    shellTarget.value = controlValue(widget, "node", "slurmctld");
    shellTarget.selectedOptions[0]?.setAttribute("selected", "selected");
    shellTarget.addEventListener("change", () => {
      rememberControl(widget, "node", shellTarget.value);
    });
    const shell = element("button", "", "Open cluster shell");
    shell.type = "button";
    shell.dataset.qfwAction = "open-shell";
    shell.dataset.qfwWidget = widget;
    shell.addEventListener("click", async () => {
      try {
        await openClusterShell(shellTarget.value);
      } catch (error) {
        await notifyDashboard("Shell failed", error.message, "danger");
      }
    });
    access.append(operationField("Node", shellTarget), shell);
    return access;
  }

  function packagedExamples() {
    return state.examples?.length
      ? state.examples
      : [{
        name: "qiskit-simple",
        backends: backendCatalog().map((backend) => backend.name),
        parameters: [{
          name: "qubits", label: "Qubits", type: "integer",
          default: 4, minimum: 1, maximum: 10000,
          help: "Number of qubits used by the circuit.",
        }],
      }];
  }

  function refreshPackagedExamples(root) {
    const control = root.querySelector("[data-qfw-application-example]");
    if (!control || control === document.activeElement) return;
    const records = packagedExamples();
    const desired = records.map((record) => ({
      name: String(record.name),
      backends: (record.backends || []).map(String).join(","),
    }));
    const existing = [...control.options].map((option) => ({
      name: option.value,
      backends: option.dataset.backends || "",
    }));
    if (JSON.stringify(existing) === JSON.stringify(desired)) return;
    const selected = control.value;
    const backend = root.querySelector("[data-qfw-application-backend]")?.value || "";
    control.replaceChildren();
    desired.forEach((record) => {
      const option = element("option", "", record.name);
      option.value = record.name;
      option.dataset.backends = record.backends;
      option.disabled = !record.backends.split(",").includes(backend);
      control.append(option);
    });
    const selectable = [...control.options].filter((option) => !option.disabled);
    control.value = selectable.some((option) => option.value === selected)
      ? selected : selectable[0]?.value || "";
    if (control.value !== selected) control.dispatchEvent(new Event("change"));
  }

  function submissionSetEntries() {
    return Array.isArray(widgetStates.submissionSet)
      ? widgetStates.submissionSet : [];
  }

  function visibleSubmissionSetEntries() {
    return submissionSetEntries().filter((entry) =>
      entry.request?.identity === activeIdentity);
  }

  function experimentsForSubmissionEntry(entry) {
    const knownIds = new Set([
      ...(entry.execution_ids || []),
      entry.active_experiment_id,
      entry.request?.experiment_id,
    ].filter(Boolean));
    return (state.experiments || []).filter((item) =>
      item.manifest?.submission_entry_id === entry.draft_id
      || knownIds.has(item.experiment_id)).sort((left, right) =>
      String(left.created_at || "").localeCompare(String(right.created_at || "")));
  }

  function latestSubmissionEntryExperiment(entry) {
    const executions = experimentsForSubmissionEntry(entry);
    if (entry.active_experiment_id) {
      const active = executions.find((item) =>
        item.experiment_id === entry.active_experiment_id);
      if (active) return active;
      if (ACTIVE_EXPERIMENT_STATES.has(String(entry.status || "").toLowerCase())) {
        return undefined;
      }
    }
    return executions[executions.length - 1];
  }

  function submissionEntryIsInFlight(entry) {
    const entryStatus = String(entry.status || "staged").toLowerCase();
    if (
      entryStatus === "staged" &&
      !entry.active_experiment_id &&
      !(entry.execution_ids || []).length
    ) {
      return false;
    }
    const experiment = latestSubmissionEntryExperiment(entry);
    const status = String(experiment?.status || entry.status || "").toLowerCase();
    const liveIds = new Set((state.running_experiments || []).map((item) =>
      item.experiment_id));
    const experimentId = experiment?.experiment_id || entry.active_experiment_id;
    return ACTIVE_EXPERIMENT_STATES.has(status)
      || (experimentId && liveIds.has(experimentId));
  }

  function submissionDefinition(payload, draftId) {
    const definition = {
      ...payload,
      ...editableBatchScriptFields(payload),
      submission_entry_id: draftId,
    };
    delete definition.experiment_id;
    return definition;
  }

  function allowsEditableBatchScript(payload) {
    return payload?.application_source === "path"
      && payload?.application_submission_type === "executable";
  }

  function editableBatchScriptFields(payload, previewPayload = {}) {
    if (!allowsEditableBatchScript(payload)) {
      return {
        batch_script: "",
        application_batch_script_save_path: "",
      };
    }
    return {
      batch_script: payload.batch_script || previewPayload.batch_script || "",
      application_batch_script_save_path:
        previewPayload.application_batch_script_save_path
        || payload.application_batch_script_save_path
        || "",
    };
  }

  function trackedExperimentSubmission() {
    const selectedId = widgetStates.submissionSetSelected;
    const entry = visibleSubmissionSetEntries().find((item) =>
      item.draft_id === selectedId);
    if (!entry) return {};
    return latestSubmissionEntryExperiment(entry) || {
      experiment_id: entry.active_experiment_id || "",
      status: entry.status || "staged",
      slurm_job_id: entry.slurm_job_id || "",
      manifest: entry.manifest || {},
      result: entry.result || {},
      preview: entry.preview || "",
      error: entry.error || "",
    };
  }

  function selectionIntersects(container) {
    if (!container) return false;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) return false;
    for (let index = 0; index < selection.rangeCount; index += 1) {
      const range = selection.getRangeAt(index);
      if (container.contains(range.startContainer)
          || container.contains(range.endContainer)) return true;
      try {
        if (range.intersectsNode(container)) return true;
      } catch (_error) {
        // Detached nodes cannot intersect the current document selection.
      }
    }
    return false;
  }

  function userIsInteractingWith(container) {
    if (!container) return false;
    const active = document.activeElement;
    const editing = active instanceof Element
      && active.matches("input, textarea, select, [contenteditable=true]")
      && container.contains(active);
    const expandedSelect = container.querySelector("select[aria-expanded=true]");
    const expandedDisclosure = container.querySelector("details[open]");
    const scrolling = [...activeScrollPointers.values()].some((target) =>
      container.contains(target));
    return Boolean(expandedSelect || expandedDisclosure)
      || editing
      || scrolling
      || recentlyScrolledInside(container)
      || selectionIntersects(container);
  }

  function refreshExperimentSubmissionStatus(root) {
    const form = root?.querySelector(".qfw-experiment-form");
    if (!form) return;
    if (userIsInteractingWith(form)) return;
    const submit = form.querySelector("[data-qfw-submit-set]");
    const output = form.querySelector("[data-qfw-submission-status]");
    const terminal = form.querySelector("[data-qfw-submission-output]");
    if (!submit || !output || !terminal) return;
    const entries = visibleSubmissionSetEntries();
    const staged = entries.filter((entry) => !submissionEntryIsInFlight(entry));
    const batchStatus = widgetStates.submissionSetStatus || {};
    const editing = Boolean(widgetStates.submissionSetEditing);
    const requestPending = batchStatus.status === "requesting";
    form.querySelectorAll(".qfw-submission-set-row").forEach((row) => {
      const entry = entries.find((item) => item.draft_id === row.dataset.draftId);
      if (!entry) return;
      const experiment = latestSubmissionEntryExperiment(entry);
      const rowStatus = experiment?.status || entry.status || "staged";
      const statusNode = row.querySelector(".qfw-submission-set-state");
      if (statusNode) {
        statusNode.className = `qfw-submission-set-state state-${rowStatus}`;
        statusNode.textContent = rowStatus;
      }
      row.classList.toggle(
        "has-error", ["failed", "invalid"].includes(rowStatus),
      );
      row.classList.toggle("is-in-flight", submissionEntryIsInFlight(entry));
    });
    const submission = trackedExperimentSubmission();
    const status = String(submission.status || "idle").toLowerCase();
    const active = [
      "created", "submitting", "submitted", "pending",
      "configuring", "running", "completing",
    ].includes(status);
    const failed = status === "failed" || batchStatus.status === "failed";
    form.classList.toggle("is-submitting", requestPending);
    form.classList.toggle("has-error", failed);
    submit.classList.toggle("is-depressed", requestPending);
    submit.disabled = requestPending || editing || entries.length === 0;
    submit.textContent = `Submit All (${staged.length})`;
    submit.setAttribute("aria-pressed", requestPending ? "true" : "false");
    submit.setAttribute("aria-busy", requestPending ? "true" : "false");
    if (requestPending) {
      output.textContent = `Submitting ${staged.length} applications …`;
      output.dataset.state = "running";
      return;
    }
    if (batchStatus.status === "failed") {
      output.textContent = `Submission failed · ${batchStatus.error || "unknown error"}`;
      output.dataset.state = "failed";
      const invalid = entries.find((entry) =>
        entry.draft_id === batchStatus.draft_id);
      terminal.textContent = invalid?.error
        ? `Validation error for ${invalid.request?.example || "application"}:\n\n${invalid.error}`
        : String(batchStatus.error || "Submission failed");
      return;
    }
    if (!status || status === "idle") {
      output.textContent = staged.length
        ? `${staged.length} applications staged` : "Submission Set is empty";
      output.dataset.state = "idle";
      return;
    }
    const job = submission.slurm_job_id ? ` · job ${submission.slurm_job_id}` : "";
    if (failed) {
      const detail = submission.result?.error || submission.error || "submission failed";
      output.textContent = `Failed${job} · ${String(detail).trim()}`;
    } else if (status === "succeeded") {
      output.textContent = `Succeeded${job}`;
    } else if (active) {
      const label = status === "requesting" ? "Sending request to Slurm" : status;
      output.textContent = `${label}${job} …`;
    } else {
      output.textContent = `${status}${job}`;
    }
    output.dataset.state = failed ? "failed" : active ? "running" : status;
    const canonicalJobId = String(submission.slurm_job_id || "").split("+")[0];
    const liveJobs = selectedSource("slurm").records.filter((item) =>
      item.kind === "job"
      && String(item.job_id || "").split("+")[0] === canonicalJobId);
    const liveStatus = liveJobs.map((item) => {
      const identity = item.job_id ? `job ${item.job_id}` : "Slurm";
      const summary = `${identity} · ${item.state || status}`;
      return item.reason ? `${summary}\n${item.reason}` : summary;
    }).join("\n\n");
    const applicationOutput = String(
      submission.result?.output_tail || submission.preview || "",
    ).trim();
    const command = String(submission.manifest?.command || "").trim();
    terminal.textContent = [
      command ? `$ ${command}` : "",
      liveStatus,
      applicationOutput,
    ].filter(Boolean).join("\n\n") || `${status}${job} …`;
  }

  function renderExperimentForm(root) {
    const form = element("form", "qfw-experiment-form");
    form.classList.add("qfw-grid-wide");
    form.append(element("h3", "", "Submit Application"));
    const draft = widgetStates.experimentDraft || {};

    function phase(number, title, description) {
      const section = element("section", "qfw-experiment-phase");
      section.dataset.phase = String(number);
      section.classList.toggle(
        "is-active", section.dataset.phase === selectedExperimentPhase,
      );
      const heading = element("header", "qfw-experiment-phase-header");
      heading.append(
        element("span", "qfw-experiment-phase-number", String(number).padStart(2, "0")),
        element("h4", "", title),
      );
      section.append(heading, element("p", "qfw-experiment-phase-help", description));
      const fields = element("div", "qfw-experiment-fields");
      section.append(fields);
      return { section, fields };
    }

    function field(label, control, help = "") {
      const wrapper = element("label", "qfw-experiment-field");
      wrapper.append(element("span", "", label), control);
      if (help) wrapper.append(element("small", "", help));
      return wrapper;
    }

    const phases = element("div", "qfw-experiment-phases");

    const reservationPhase = phase(
      1, "Reservation",
      "Choose the quantum service and how Slurm should create the allocation.",
    );
    const backend = element("select");
    backend.dataset.qfwApplicationBackend = "";
    backendChoices().forEach(([name, label]) => {
      const option = element("option", "", label);
      option.value = name;
      backend.append(option);
    });
    backend.value = draft.backend || "nwqsim";
    const mode = element("select");
    ["normal", "heterogeneous"].forEach((name) => {
      const option = element("option", "", name);
      option.value = name;
      mode.append(option);
    });
    mode.value = draft.allocation_mode || "normal";
    const workload = element("select");
    ["quantum", "hybrid"].forEach((name) => {
      const option = element("option", "", name);
      option.value = name;
      workload.append(option);
    });
    workload.value = draft.workload_kind || "quantum";
    const partition = element("select");
    const partitions = [...new Set(
      selectedSource("slurm").records
        .filter((item) => item.kind === "node")
        .map((item) => String(item.partition || "").replace(/\*$/, ""))
        .filter((name) => name && name !== "qfw-services"),
    )];
    (partitions.length ? partitions : ["normal"]).forEach((name) => {
      const option = element("option", "", name);
      option.value = name;
      partition.append(option);
    });
    const requestedPartition = draft.partition || "normal";
    partition.value = [...partition.options]
      .some((option) => option.value === requestedPartition)
      ? requestedPartition : partition.options[0]?.value || "normal";
    reservationPhase.fields.append(
      field("Backend", backend),
      field("Allocation", mode),
      field("Workload", workload),
      field("Classical partition", partition),
    );

    const applicationPhase = phase(
      2, "Application",
      "Run a packaged QFw example or an application from the shared workspace.",
    );
    const applicationSource = element("select");
    [["example", "Packaged QFw example"], ["path", "Application path"]]
      .forEach(([value, label]) => {
        const option = element("option", "", label);
        option.value = value;
        applicationSource.append(option);
      });
    applicationSource.value = draft.application_source || "example";
    const applicationSubmissionType = element("select");
    [
      ["executable", "Executable"],
      ["sbatch", "Existing sbatch script"],
    ].forEach(([value, label]) => {
      const option = element("option", "", label);
      option.value = value;
      applicationSubmissionType.append(option);
    });
    applicationSubmissionType.value =
      draft.application_submission_type === "sbatch" ? "sbatch" : "executable";
    const example = element("select");
    example.dataset.qfwApplicationExample = "";
    const discoveredExamples = packagedExamples();
    discoveredExamples.forEach((record) => {
      const option = element("option", "", record.name);
      option.value = record.name;
      option.dataset.backends = (record.backends || []).join(",");
      example.append(option);
    });
    example.value = draft.example || "qiskit-simple";
    const applicationPath = element("input");
    applicationPath.placeholder = "/workspace/path/to/application";
    applicationPath.value = draft.application_path || "";
    const applicationArguments = element("input");
    applicationArguments.placeholder = "--flag value";
    applicationArguments.value = draft.application_arguments || "";
    const batchScriptEditor = element(
      "textarea",
      "qfw-command-preview qfw-batch-script-editor qfw-resizable-text",
    );
    batchScriptEditor.value = draft.batch_script || "";
    batchScriptEditor.placeholder = "Preview to generate an sbatch script.";
    batchScriptEditor.spellcheck = false;
    const batchScriptPath = element(
      "span", "qfw-batch-script-save-path", "Save path appears after preview.",
    );
    const saveBatchScript = iconButton("save", "Save sbatch beside application");
    const batchScriptStatus = element("span", "qfw-batch-script-status");
    const batchScriptActions = element("div", "qfw-batch-script-actions");
    batchScriptActions.append(saveBatchScript, batchScriptPath, batchScriptStatus);
    const sourceField = field("Application source", applicationSource);
    const submissionTypeField = field(
      "Submission type",
      applicationSubmissionType,
      "Executable mode generates an editable sbatch script.",
    );
    const exampleField = field("QFw example", example);
    const pathField = field("Application path", applicationPath,
      "Use an absolute path beneath /workspace.");
    const argumentsField = field(
      "Command-line parameters",
      applicationArguments,
      "Shell-style arguments for executable mode.",
    );
    const batchScriptField = field(
      "Generated sbatch",
      batchScriptEditor,
      "Submit uses the text currently shown here.",
    );
    batchScriptField.classList.add("qfw-batch-script-field");
    const applicationParameterFields = element(
      "div", "qfw-application-parameters",
    );
    const applicationParameterControls = new Map();
    applicationPhase.fields.append(
      sourceField,
      submissionTypeField,
      exampleField,
      pathField,
      argumentsField,
      batchScriptField,
      batchScriptActions,
      applicationParameterFields,
    );

    function selectedExampleRecord() {
      return packagedExamples().find((record) => record.name === example.value);
    }

    function currentApplicationParameters() {
      return Object.fromEntries(
        [...applicationParameterControls].map(([name, control]) => [
          name,
          control.type === "number" ? Number(control.value) : control.value,
        ]),
      );
    }

    function renderApplicationParameters(values = {}) {
      applicationParameterFields.replaceChildren();
      applicationParameterControls.clear();
      if (applicationSource.value !== "example") return;
      const definitions = selectedExampleRecord()?.parameters || [];
      if (!definitions.length) {
        applicationParameterFields.append(element(
          "p", "qfw-application-parameter-empty",
          "This example has no configurable runtime parameters.",
        ));
        return;
      }
      definitions.forEach((definition) => {
        const control = element("input");
        control.type = definition.type === "integer" ? "number" : "text";
        if (definition.minimum !== undefined) {
          control.min = String(definition.minimum);
        }
        if (definition.maximum !== undefined) {
          control.max = String(definition.maximum);
        }
        control.value = String(values[definition.name] ?? definition.default ?? "");
        applicationParameterControls.set(definition.name, control);
        applicationParameterFields.append(field(
          definition.label || definition.name, control, definition.help || "",
        ));
      });
    }

    const quantumPhase = phase(
      3, "Quantum requirements",
      "Declare upper bounds used by QPM admission control.",
    );
    const shots = element("input");
    shots.type = "number";
    shots.min = "1";
    shots.value = String(draft.shots ?? 16);
    const requirements = {};
    [
      ["circ_count", "Circuit count", 1, 1],
      ["max_qubits", "Maximum qubits", 5, 1],
      ["max_depth", "Maximum depth", 100, 1],
      ["max_one_q_gates", "Maximum 1Q gates", 0, 0],
      ["max_two_q_gates", "Maximum 2Q gates", 0, 0],
      ["max_measurements", "Maximum measurements", 0, 0],
    ].forEach(([name, label, initial, minimum]) => {
      const input = element("input");
      input.type = "number";
      input.min = String(minimum);
      input.value = String(draft[name] ?? initial);
      requirements[name] = input;
      quantumPhase.fields.append(field(label, input));
    });
    quantumPhase.fields.append(field("Maximum shots", shots));

    const classicalPhase = phase(
      4, "Classical requirements",
      "Reserve nodes now and add only the optional resources the application needs.",
    );
    const nodes = element("input");
    nodes.type = "number";
    nodes.min = "1";
    nodes.max = "8";
    nodes.value = String(draft.nodes ?? 1);
    classicalPhase.fields.append(field("Nodes", nodes, "Required."));
    const addRequirement = element("select");
    const optionalRequirements = {
      tasks: { label: "MPI ranks", kind: "number", initial: 1, min: 1 },
      tasks_per_node: { label: "Ranks per node", kind: "number", initial: 1, min: 1 },
      cpus_per_task: { label: "CPUs per rank", kind: "number", initial: 1, min: 1 },
      memory: { label: "Memory", kind: "memory", initial: "4G" },
      gpus: { label: "GPUs", kind: "gpus", initial: 1, min: 1 },
      constraint: { label: "Node features", kind: "text", initial: "" },
      exclusive: { label: "Exclusive allocation", kind: "boolean", initial: true },
    };
    const activeClassical = new Map();
    const optionalFields = element("div", "qfw-optional-requirements");
    const addField = field("Add requirement", addRequirement,
      "Optional Slurm resources appear only when selected.");
    addField.classList.add("qfw-add-requirement");
    classicalPhase.fields.append(addField, optionalFields);

    function renderRequirementMenu() {
      addRequirement.replaceChildren(element("option", "", "Select a requirement…"));
      addRequirement.firstElementChild.value = "";
      Object.entries(optionalRequirements).forEach(([name, definition]) => {
        if (activeClassical.has(name)) return;
        const option = element("option", "", definition.label);
        option.value = name;
        addRequirement.append(option);
      });
      addRequirement.value = "";
    }

    function addClassicalRequirement(name, payload = {}) {
      const definition = optionalRequirements[name];
      if (!definition || activeClassical.has(name)) return;
      const row = element("div", "qfw-optional-requirement");
      const controls = { row };
      if (definition.kind === "boolean") {
        const input = element("input");
        input.type = "checkbox";
        input.checked = payload[name] ?? definition.initial;
        controls.input = input;
        row.append(field(definition.label, input));
      } else {
        const input = element("input");
        input.type = definition.kind === "number" || definition.kind === "gpus"
          ? "number" : "text";
        if (definition.min !== undefined) input.min = String(definition.min);
        input.value = String(payload[name] ?? definition.initial);
        controls.input = input;
        const requirementField = field(definition.label, input);
        if (definition.kind === "memory" || definition.kind === "gpus") {
          const scope = element("select");
          const scopes = definition.kind === "memory"
            ? [["node", "Per node"], ["cpu", "Per CPU"]]
            : [["node", "Per node"], ["task", "Per rank"]];
          scopes.forEach(([value, label]) => {
            const option = element("option", "", label);
            option.value = value;
            scope.append(option);
          });
          scope.value = payload[`${name}_scope`] || "node";
          controls.scope = scope;
          requirementField.append(scope);
        }
        row.append(requirementField);
      }
      const remove = element("button", "qfw-remove-requirement", "Remove");
      remove.type = "button";
      remove.addEventListener("click", () => {
        activeClassical.delete(name);
        row.remove();
        renderRequirementMenu();
        saveDraft();
        updatePhaseStatus();
      });
      row.append(remove);
      activeClassical.set(name, controls);
      optionalFields.append(row);
      renderRequirementMenu();
    }

    addRequirement.addEventListener("change", () => {
      if (addRequirement.value) addClassicalRequirement(addRequirement.value);
      saveDraft();
      updatePhaseStatus();
    });

    const runtimePhase = phase(
      5, "Runtime",
      "Bound how long Slurm may keep the allocation.",
    );
    const timeMinutes = element("input");
    timeMinutes.type = "number";
    timeMinutes.min = "1";
    timeMinutes.max = "240";
    timeMinutes.value = String(draft.time_minutes ?? 45);
    const defwOutLogLevel = element("select");
    DEFW_OUT_LOG_LEVELS.forEach(([value, label]) => {
      const option = element("option", "", label);
      option.value = value;
      defwOutLogLevel.append(option);
    });
    defwOutLogLevel.value = DEFW_OUT_LOG_LEVELS.some(
      ([value]) => value === draft.defw_log_level,
    ) ? draft.defw_log_level : "error";
    const defwPyLogLevel = element("select");
    DEFW_PY_LOG_LEVELS.forEach(([value, label]) => {
      const option = element("option", "", label);
      option.value = value;
      defwPyLogLevel.append(option);
    });
    defwPyLogLevel.value = DEFW_PY_LOG_LEVELS.some(
      ([value]) => value === draft.defw_py_loglevel,
    ) ? draft.defw_py_loglevel : "critical";
    runtimePhase.fields.append(
      field("Wall time (minutes)", timeMinutes),
      field(
        "defw_out.log",
        defwOutLogLevel,
        "Native DEFw log verbosity for this application run.",
      ),
      field(
        "defw_py.log",
        defwPyLogLevel,
        "Python DEFw log verbosity for this application run.",
      ),
    );

    function updateBackendConstraints() {
      const selectedBackend = backendSpec(backend.value);
      const maxTime = Number(selectedBackend.max_time_minutes || 240);
      const maxShots = Number(selectedBackend.max_shots || 65536);
      timeMinutes.max = String(maxTime);
      shots.max = String(maxShots);
      if (Number(timeMinutes.value) > maxTime) {
        timeMinutes.value = String(maxTime);
      }
      if (Number(shots.value) > maxShots) {
        shots.value = String(maxShots);
      }
      [...example.options].forEach((option) => {
        option.disabled = !String(option.dataset.backends || "")
          .split(",").includes(backend.value);
      });
      if (example.selectedOptions[0]?.disabled) {
        example.value = [...example.options]
          .find((option) => !option.disabled)?.value || "";
      }
      updateApplicationFields();
    }

    function updateApplicationFields() {
      const custom = applicationSource.value === "path";
      const executable = custom && applicationSubmissionType.value === "executable";
      exampleField.hidden = custom;
      submissionTypeField.hidden = !custom;
      pathField.hidden = !custom && example.value !== "chemistry";
      argumentsField.hidden = !executable;
      batchScriptField.hidden = !executable;
      batchScriptActions.hidden = !executable;
      pathField.firstElementChild.textContent = custom
        ? (applicationSubmissionType.value === "sbatch"
          ? "SBATCH script path" : "Application path")
        : "Chemistry application path";
      saveBatchScript.disabled = !executable || !batchScriptEditor.value.trim();
    }

    backend.addEventListener("change", updateBackendConstraints);
    applicationSource.addEventListener("change", () => {
      updateApplicationFields();
      renderApplicationParameters();
    });
    applicationSubmissionType.addEventListener("change", updateApplicationFields);
    batchScriptEditor.addEventListener("input", () => {
      batchScriptStatus.textContent = "";
      updateApplicationFields();
    });
    example.addEventListener("change", () => {
      updateApplicationFields();
      renderApplicationParameters();
    });

    const previewPhase = phase(
      6, "Preview and stage",
      "Review the application, then add it to the Submission Set.",
    );
    const addToSet = element("button", "", "Add to Submission Set");
    addToSet.type = "button";
    addToSet.dataset.qfwAddToSubmissionSet = "";
    const preview = element("button", "", "Preview batch file");
    preview.type = "button";
    const previewOutput = preserveScroll(
      element(
        "pre", "qfw-command-preview qfw-resizable-text", "Batch preview not generated.",
      ),
    );
    previewOutput.dataset.qfwSubmissionOutput = "";
    let experimentId = draft.experiment_id || window.crypto.randomUUID();
    let applicationBatchScriptSavePath =
      draft.application_batch_script_save_path || "";

    function setBatchScriptPreview(payload) {
      if (payload.batch_script !== undefined) {
        batchScriptEditor.value = payload.batch_script || "";
      }
      applicationBatchScriptSavePath =
        payload.application_batch_script_save_path || applicationBatchScriptSavePath;
      batchScriptPath.textContent = applicationBatchScriptSavePath
        ? `Save beside application: ${applicationBatchScriptSavePath}`
        : "Save path appears after preview.";
      batchScriptStatus.textContent = "";
      updateApplicationFields();
    }

    function formPayload() {
      const payload = {
        experiment_id: experimentId,
        identity: activeIdentity,
        backend: backend.value,
        application_source: applicationSource.value,
        application_submission_type: applicationSubmissionType.value,
        example: applicationSource.value === "example" ? example.value : "custom",
        application_path: applicationPath.value.trim(),
        application_arguments: applicationArguments.value.trim(),
        application_parameters: currentApplicationParameters(),
        batch_script: applicationSource.value === "path"
          && applicationSubmissionType.value === "executable"
          ? batchScriptEditor.value : "",
        application_batch_script_save_path: applicationBatchScriptSavePath,
        allocation_mode: mode.value,
        shots: Number(shots.value),
        time_minutes: Number(timeMinutes.value),
        defw_log_level: defwOutLogLevel.value,
        defw_py_loglevel: defwPyLogLevel.value,
        workload_kind: workload.value,
        partition: partition.value.trim(),
        nodes: Number(nodes.value),
        ...Object.fromEntries(
          Object.entries(requirements).map(([name, input]) => [
            name, Number(input.value),
          ]),
        ),
      };
      activeClassical.forEach((controls, name) => {
        if (controls.input.type === "checkbox") {
          payload[name] = controls.input.checked;
        } else if (controls.input.type === "number") {
          payload[name] = Number(controls.input.value);
        } else {
          payload[name] = controls.input.value.trim();
        }
        if (controls.scope) payload[`${name}_scope`] = controls.scope.value;
      });
      return payload;
    }

    function saveDraft() {
      widgetStates.experimentDraft = formPayload();
      savePresentation();
    }

    function updatePhaseStatus() {
      const sourceValid = applicationSource.value === "example"
        ? Boolean(example.value) && (example.value !== "chemistry"
          || applicationPath.value.startsWith("/workspace/"))
        : applicationPath.value.startsWith("/workspace/");
      const quantumValid = Number(shots.value) > 0
        && Object.values(requirements).every((input) => input.checkValidity());
      [
        [reservationPhase.section, Boolean(backend.value && mode.value && partition.value)],
        [applicationPhase.section, sourceValid],
        [quantumPhase.section, quantumValid],
        [classicalPhase.section, nodes.checkValidity()],
        [runtimePhase.section, timeMinutes.checkValidity()],
      ].forEach(([section, valid]) => section.classList.toggle("is-complete", valid));
    }

    function applyDraft(payload) {
      backend.value = payload.backend || "nwqsim";
      example.value = payload.example || "qiskit-simple";
      applicationSource.value = payload.application_source || "example";
      applicationSubmissionType.value =
        payload.application_submission_type === "sbatch" ? "sbatch" : "executable";
      applicationPath.value = payload.application_path || "";
      applicationArguments.value = payload.application_arguments || "";
      batchScriptEditor.value = payload.batch_script || "";
      applicationBatchScriptSavePath =
        payload.application_batch_script_save_path || "";
      batchScriptPath.textContent = applicationBatchScriptSavePath
        ? `Save beside application: ${applicationBatchScriptSavePath}`
        : "Save path appears after preview.";
      mode.value = payload.allocation_mode || "normal";
      workload.value = payload.workload_kind || "quantum";
      shots.value = String(payload.shots || 16);
      timeMinutes.value = String(payload.time_minutes || 45);
      defwOutLogLevel.value = DEFW_OUT_LOG_LEVELS.some(
        ([value]) => value === payload.defw_log_level,
      ) ? payload.defw_log_level : "error";
      defwPyLogLevel.value = DEFW_PY_LOG_LEVELS.some(
        ([value]) => value === payload.defw_py_loglevel,
      ) ? payload.defw_py_loglevel : "critical";
      partition.value = payload.partition || "normal";
      nodes.value = String(payload.nodes || 1);
      Object.entries(requirements).forEach(([name, input]) => {
        if (payload[name] !== undefined) input.value = String(payload[name]);
      });
      activeClassical.forEach((controls) => controls.row.remove());
      activeClassical.clear();
      Object.keys(optionalRequirements).forEach((name) => {
        if (payload[name] !== undefined) addClassicalRequirement(name, payload);
      });
      renderRequirementMenu();
      updateBackendConstraints();
      updateApplicationFields();
      renderApplicationParameters(payload.application_parameters || {});
      updatePhaseStatus();
      saveDraft();
    }
    applyDraft(draft);
    const previewActions = element("div", "qfw-experiment-actions");
    const stageStatus = element(
      "span", "qfw-experiment-submission-status", "Ready to stage",
    );
    previewActions.append(preview, stageStatus, addToSet);
    previewPhase.fields.append(previewActions);

    const submissionSetSection = element("section", "qfw-submission-set");
    const submissionSetHeader = element("header", "qfw-submission-set-header");
    const submissionSetTitle = element("h4", "", "Submission Set");
    const submissionSetCount = element("span", "qfw-submission-set-count");
    submissionSetHeader.append(submissionSetTitle, submissionSetCount);
    const submissionSetList = element("div", "qfw-submission-set-list");
    const submissionSetEmpty = element(
      "p", "qfw-submission-set-empty", "No applications have been staged.",
    );
    const submissionActions = element("div", "qfw-experiment-actions");
    const submissionStatus = element(
      "span", "qfw-experiment-submission-status", "Submission Set is empty",
    );
    submissionStatus.dataset.qfwSubmissionStatus = "";
    submissionStatus.dataset.state = "idle";
    const submitSet = element("button", "qfw-submit-set", "Submit All (0)");
    submitSet.type = "button";
    submitSet.dataset.qfwSubmitSet = "";
    submissionActions.append(submissionStatus, submitSet);
    submissionSetSection.append(
      submissionSetHeader, submissionSetList, submissionActions, previewOutput,
    );
    phases.append(
      reservationPhase.section,
      applicationPhase.section,
      quantumPhase.section,
      classicalPhase.section,
      runtimePhase.section,
      previewPhase.section,
    );
    form.append(phases, submissionSetSection);
    form.addEventListener("input", () => {
      saveDraft();
      updatePhaseStatus();
    });
    form.addEventListener("change", () => {
      saveDraft();
      updatePhaseStatus();
    });
    updateApplicationFields();
    renderApplicationParameters(draft.application_parameters || {});
    updatePhaseStatus();
    refreshExperimentSubmissionStatus(form);
    preview.addEventListener("click", async () => {
      try {
        const payload = await request("/api/qfw-dashboard/preview", {
          method: "POST", body: JSON.stringify(formPayload()),
        });
        experimentId = payload.experiment_id;
        setBatchScriptPreview(payload);
        saveDraft();
        previewOutput.textContent = payload.command;
      } catch (error) {
        await notifyDashboard("Preview failed", error.message, "danger");
      }
    });

    saveBatchScript.addEventListener("click", async () => {
      try {
        let payload = formPayload();
        if (!payload.batch_script.trim()) {
          const previewPayload = await request("/api/qfw-dashboard/preview", {
            method: "POST", body: JSON.stringify(payload),
          });
          setBatchScriptPreview(previewPayload);
          payload = formPayload();
          previewOutput.textContent = previewPayload.command;
        }
        batchScriptStatus.textContent = "Saving…";
        let result;
        try {
          result = await request("/api/qfw-dashboard/applications/batch-script", {
            method: "POST", body: JSON.stringify(payload),
          });
        } catch (error) {
          if (error.payload?.error?.type !== "FileExistsError"
              || !await confirmDashboardAction(
                "Overwrite saved sbatch",
                `${applicationBatchScriptSavePath} already exists. Overwrite it?`,
                { severity: "warning", confirmLabel: "Overwrite" },
              )) {
            throw error;
          }
          result = await request("/api/qfw-dashboard/applications/batch-script", {
            method: "POST",
            body: JSON.stringify({ ...payload, overwrite: true }),
          });
        }
        applicationBatchScriptSavePath = result.path || applicationBatchScriptSavePath;
        batchScriptPath.textContent =
          `Save beside application: ${applicationBatchScriptSavePath}`;
        batchScriptStatus.textContent = "Saved";
        saveDraft();
      } catch (error) {
        batchScriptStatus.textContent = "Save failed";
        await notifyDashboard("SBATCH save failed", error.message, "danger");
      }
    });

    function replaceSubmissionSet(entries) {
      const hidden = submissionSetEntries().filter((entry) =>
        entry.request?.identity !== activeIdentity);
      widgetStates.submissionSet = [...hidden, ...entries];
    }

    function finishEditing() {
      widgetStates.experimentDraft =
        widgetStates.submissionSetEditReturnDraft || {};
      delete widgetStates.submissionSetEditing;
      delete widgetStates.submissionSetEditReturnDraft;
    }

    function renderSubmissionSet() {
      const entries = visibleSubmissionSetEntries();
      const editingId = widgetStates.submissionSetEditing;
      const selectedId = widgetStates.submissionSetSelected;
      submissionSetCount.textContent = `${entries.length} applications`;
      submissionSetList.replaceChildren();
      if (!entries.length) submissionSetList.append(submissionSetEmpty);
      entries.forEach((entry) => {
        const experiment = latestSubmissionEntryExperiment(entry);
        const status = experiment?.status || entry.status || "staged";
        const row = element("div", "qfw-submission-set-row");
        row.dataset.draftId = entry.draft_id;
        row.classList.toggle("is-editing", editingId === entry.draft_id);
        row.classList.toggle("is-viewing", selectedId === entry.draft_id);
        row.classList.toggle("has-error", ["failed", "invalid"].includes(status));
        row.classList.toggle("is-in-flight", submissionEntryIsInFlight(entry));
        const source = entry.request?.application_source || "example";
        const name = source === "path"
          ? String(entry.request?.application_path || "application").split("/").pop()
          : entry.request?.example || "application";
        const identity = element("div", "qfw-submission-set-identity");
        identity.append(
          element("strong", "", name),
          element("span", `qfw-submission-set-state state-${status}`, status),
        );
        const actions = element("div", "qfw-submission-set-row-actions");
        const view = iconButton("view", "View application");
        const edit = iconButton("edit", "Edit application");
        const save = iconButton("save", "Save application changes");
        const cancel = iconButton("cancel", "Cancel application changes");
        const remove = iconButton("trash", "Remove application");
        edit.disabled = Boolean(editingId);
        save.disabled = editingId !== entry.draft_id;
        cancel.disabled = editingId !== entry.draft_id;
        remove.disabled = Boolean(editingId && editingId !== entry.draft_id);
        view.addEventListener("click", async () => {
          widgetStates.submissionSetSelected = entry.draft_id;
          if (!entry.preview) {
            try {
              const result = await request("/api/qfw-dashboard/preview", {
                method: "POST", body: JSON.stringify(entry.request),
              });
              entry.preview = result.command;
              Object.assign(
                entry.request, editableBatchScriptFields(entry.request, result),
              );
              replaceSubmissionSet(entries);
            } catch (error) {
              await notifyDashboard("Preview failed", error.message, "danger");
              return;
            }
          }
          savePresentation();
          renderDashboard();
          publishWidgets();
        });
        edit.addEventListener("click", () => {
          widgetStates.submissionSetEditReturnDraft = formPayload();
          widgetStates.submissionSetEditing = entry.draft_id;
          widgetStates.submissionSetSelected = entry.draft_id;
          widgetStates.experimentDraft = structuredClone(entry.request);
          savePresentation();
          renderDashboard();
          publishWidgets();
        });
        save.addEventListener("click", () => {
          const inFlight = submissionEntryIsInFlight(entry);
          entry.request = submissionDefinition(formPayload(), entry.draft_id);
          entry.preview = "";
          if (!inFlight) entry.status = "staged";
          delete entry.error;
          replaceSubmissionSet(entries);
          if (widgetStates.submissionSetStatus?.draft_id === entry.draft_id) {
            widgetStates.submissionSetStatus = { status: "staged" };
          }
          finishEditing();
          savePresentation();
          renderDashboard();
          publishWidgets();
        });
        cancel.addEventListener("click", () => {
          finishEditing();
          savePresentation();
          renderDashboard();
          publishWidgets();
        });
        remove.addEventListener("click", async () => {
          if (!await confirmDashboardAction(
            "Remove staged application",
            `Remove ${name} from the Submission Set?`,
            { severity: "danger", confirmLabel: "Remove application" },
          )) return;
          replaceSubmissionSet(entries.filter((item) => item !== entry));
          if (editingId === entry.draft_id) finishEditing();
          if (widgetStates.submissionSetSelected === entry.draft_id) {
            delete widgetStates.submissionSetSelected;
          }
          savePresentation();
          renderDashboard();
          publishWidgets();
        });
        actions.append(view, edit, save, cancel, remove);
        row.append(identity, actions);
        submissionSetList.append(row);
      });
    }

    addToSet.disabled = Boolean(widgetStates.submissionSetEditing);
    addToSet.addEventListener("click", async () => {
      try {
        const payload = formPayload();
        const result = await request("/api/qfw-dashboard/preview", {
          method: "POST", body: JSON.stringify(payload),
        });
        setBatchScriptPreview(result);
        const requestPayload = {
          ...payload,
          ...editableBatchScriptFields(payload, result),
        };
        const draftId = window.crypto.randomUUID();
        const entries = visibleSubmissionSetEntries();
        entries.push({
          draft_id: draftId,
          request: submissionDefinition(requestPayload, draftId),
          preview: result.command,
          status: "staged",
          execution_ids: [],
        });
        replaceSubmissionSet(entries);
        widgetStates.submissionSetSelected = draftId;
        widgetStates.submissionSetStatus = { status: "staged" };
        experimentId = window.crypto.randomUUID();
        saveDraft();
        savePresentation();
        renderDashboard();
        publishWidgets();
      } catch (error) {
        await notifyDashboard("Unable to stage application", error.message, "danger");
      }
    });

    submitSet.addEventListener("click", async () => {
      const entries = visibleSubmissionSetEntries();
      const staged = entries.filter((entry) => !submissionEntryIsInFlight(entry));
      if (!staged.length) {
        submissionStatus.textContent =
          "All submission entries already have an in-flight execution.";
        submissionStatus.dataset.state = "idle";
        return;
      }
      const hardwareBackendNames = hardwareBackends();
      const hardware = staged.some((entry) => (
        hardwareBackendNames.has(entry.request?.backend)
      ));
      if (hardware && !await confirmDashboardAction(
        "Submit real-hardware applications",
        "This Submission Set contains bounded work for real IQM hardware.",
        { severity: "warning", confirmLabel: "Submit all applications" },
      )) return;
      widgetStates.submissionSetStatus = {
        status: "requesting", count: staged.length,
      };
      const executionEntries = new Map();
      const executionRequests = staged.map((entry) => {
        const experimentId = window.crypto.randomUUID();
        executionEntries.set(experimentId, entry);
        entry.active_experiment_id = experimentId;
        entry.status = "submitting";
        delete entry.error;
        return {
          ...submissionDefinition(entry.request, entry.draft_id),
          identity: activeIdentity,
          submission_entry_id: entry.draft_id,
          experiment_id: experimentId,
        };
      });
      replaceSubmissionSet(entries);
      savePresentation();
      refreshExperimentSubmissionStatus(form);
      try {
        const result = await request("/api/qfw-dashboard/experiments/batch", {
          method: "POST",
          body: JSON.stringify({
            identity: activeIdentity,
            submit_real_hardware: hardware,
            experiments: executionRequests,
          }),
        });
        const accepted = new Map(result.experiments.map((item) => [
          item.experiment_id, item,
        ]));
        accepted.forEach((experiment, experimentId) => {
          const entry = executionEntries.get(experimentId);
          if (!entry) return;
          entry.execution_ids = [...new Set([
            ...(entry.execution_ids || []), experimentId,
          ])];
          entry.active_experiment_id = experimentId;
          entry.status = experiment.status;
          entry.slurm_job_id = experiment.slurm_job_id || "";
          entry.manifest = experiment.manifest || {};
        });
        replaceSubmissionSet(entries);
        widgetStates.submissionSetStatus = {
          status: "accepted", count: accepted.size,
        };
        savePresentation();
        await refreshState();
      } catch (error) {
        const failure = error.payload?.error?.submission || {};
        const failed = executionEntries.get(failure.experiment_id)
          || staged[Number(failure.index)];
        staged.forEach((entry) => {
          if (entry.active_experiment_id
              && executionEntries.has(entry.active_experiment_id)) {
            delete entry.active_experiment_id;
            entry.status = latestSubmissionEntryExperiment(entry)?.status || "staged";
          }
        });
        if (failed) {
          failed.status = "invalid";
          failed.error = error.message;
          widgetStates.submissionSetSelected = failed.draft_id;
        }
        replaceSubmissionSet(entries);
        widgetStates.submissionSetStatus = {
          status: "failed",
          error: error.message,
          draft_id: failed?.draft_id || "",
        };
        savePresentation();
        renderDashboard();
        publishWidgets();
      }
    });

    form.addEventListener("submit", (event) => event.preventDefault());
    renderSubmissionSet();
    refreshExperimentSubmissionStatus(form);
    root.append(form);
  }

  function captureWidgetScrollPositions(root) {
    const positions = {};
    if (!root) return positions;
    root.querySelectorAll("[data-qfw-preserve-scroll]").forEach((container) => {
      const scope = container.closest(".qfw-widget[data-widget], .qfw-experiment-form")
        || root;
      const scopeName = scope.dataset.widget || (scope === root ? "root" : "experiment-form");
      const siblings = [...scope.querySelectorAll("[data-qfw-preserve-scroll]")];
      const key = `${scopeName}:${siblings.indexOf(container)}`;
      positions[key] = {
        height: container.style.height,
        left: container.scrollLeft,
        top: container.scrollTop,
      };
    });
    return positions;
  }

  function restoreWidgetScrollPositions(root, positions) {
    if (!root) return;
    root.querySelectorAll("[data-qfw-preserve-scroll]").forEach((container) => {
      const scope = container.closest(".qfw-widget[data-widget], .qfw-experiment-form")
        || root;
      const scopeName = scope.dataset.widget || (scope === root ? "root" : "experiment-form");
      const siblings = [...scope.querySelectorAll("[data-qfw-preserve-scroll]")];
      const offset = positions[`${scopeName}:${siblings.indexOf(container)}`];
      if (!offset) return;
      if (offset.height) container.style.height = offset.height;
      container.scrollLeft = offset.left;
      container.scrollTop = offset.top;
    });
  }

  function resetDashboardGeometry(root) {
    root.querySelectorAll("[data-qfw-preserve-scroll]").forEach((container) => {
      container.style.removeProperty("height");
      container.scrollLeft = 0;
      container.scrollTop = 0;
    });
    const topologyZoom = root.querySelector(".qfw-topology-zoom");
    const topologyZoomValue = root.querySelector(".qfw-topology-zoom-value");
    const topologyGraph = root.querySelector(".qfw-topology-graph");
    if (topologyZoom) topologyZoom.value = "100";
    if (topologyZoomValue) topologyZoomValue.textContent = "100%";
    if (topologyGraph) topologyGraph.style.width = "100%";
    widgetStates.topology = { ...widgetStates.topology, zoom: 100 };
    savePresentation();
    publishWidgets();
  }

  function renderDashboardRoot(root) {
    if (!root) return;
    const scrollPositions = captureWidgetScrollPositions(root);
    root.replaceChildren();
    const header = element("header", "qfw-dashboard-header");
    const title = element("div", "qfw-dashboard-title");
    title.append(
      element("span", "qfw-dashboard-eyebrow", "OPENQSE OPERATIONS"),
      element("h2", "", "QFw Slurm Cluster"),
    );
    header.append(title);
    const identity = element("select", "qfw-identity");
    IDENTITIES.forEach((name) => {
      const option = element("option", "", name);
      option.value = name;
      identity.append(option);
    });
    identity.value = activeIdentity;
    identity.addEventListener("change", () => {
      activeIdentity = identity.value;
      savePresentation();
      renderDashboard();
      publishWidgets();
    });
    const identityLabel = element("label", "qfw-identity-label", "Cluster identity ");
    identityLabel.append(identity);
    const viewControls = element("div", "qfw-view-controls");
    const zoomSlider = element("input", "qfw-canvas-zoom");
    zoomSlider.type = "range";
    zoomSlider.min = String(CANVAS_ZOOM_MIN);
    zoomSlider.max = String(CANVAS_ZOOM_MAX);
    zoomSlider.step = String(CANVAS_ZOOM_STEP);
    zoomSlider.value = "100";
    zoomSlider.setAttribute("aria-label", "Zoom");
    const zoomLabel = element("output", "qfw-zoom-label", "100%");
    const reset = element("button", "", "Reset view");
    const clear = element("button", "qfw-dashboard-clear danger", "Clear state");
    const clearStatus = element("output", "qfw-dashboard-clear-status");
    clearStatus.setAttribute("aria-live", "polite");
    clearStatus.textContent = {
      idle: "", running: "Clearing…", succeeded: "Cleared", failed: "Failed",
    }[dashboardResetStatus] || dashboardResetStatus;
    clear.disabled = activeIdentity !== "root" || dashboardResetStatus === "running";
    clear.classList.toggle("is-pressed", dashboardResetStatus === "running");
    clear.setAttribute("aria-pressed", String(dashboardResetStatus === "running"));
    [reset, clear].forEach((button) => { button.type = "button"; });
    viewControls.append(
      element("span", "qfw-canvas-hint", "Wheel zoom · middle-drag pan"),
      zoomSlider, zoomLabel, reset, clear, clearStatus,
    );
    header.append(viewControls, identityLabel);
    root.append(header);
    const viewport = element("div", "qfw-canvas-viewport");
    viewport.setAttribute("aria-label", "Zoomable dashboard canvas");
    const stage = element("main", "qfw-canvas-stage");
    const sections = element("div", "qfw-widget-sections");
    WIDGET_GROUPS.forEach((group) => sections.append(buildWidgetGroup(group)));
    stage.append(sections);
    viewport.append(stage);
    root.append(viewport);
    const camera = installCanvasInteraction(viewport, stage, zoomLabel, zoomSlider);
    zoomSlider.addEventListener("input", () => camera.setZoom(Number(zoomSlider.value)));
    reset.addEventListener("click", () => {
      camera.reset();
      resetDashboardGeometry(root);
    });
    clear.addEventListener("click", () => { void clearDashboardState(); });
    restoreWidgetScrollPositions(root, scrollPositions);
  }

  function refreshOperationWidget(widget, group) {
    if (group === "nodes") refreshNodeControlChoices(widget);
    const output = widget.querySelector(".qfw-operation-output");
    if (output) output.replaceWith(operationOutput(group));
    const operation = operationForGroup(group);
    widget.classList.toggle("has-error", operation?.status === "failed");
    const buttons = widget.querySelector(".qfw-operation-buttons");
    if (buttons) applyOperationControlState(buttons, group);
  }

  function refreshDashboardDataRoot(root) {
    if (!root?.isConnected) return;
    const scrollPositions = captureWidgetScrollPositions(root);
    refreshPackagedExamples(root);
    refreshExperimentSubmissionStatus(root);
    WIDGETS.forEach(([id]) => {
      const widget = root.querySelector(`.qfw-widget[data-widget="${id}"]`);
      if (!widget) return;
      if (userIsInteractingWith(widget)) return;
      if (OPERATION_WIDGET_GROUPS[id]) {
        refreshOperationWidget(widget, OPERATION_WIDGET_GROUPS[id]);
        return;
      }
      if (id === "cluster-access") return;
      const body = widget.children[1];
      if (body) body.replaceWith(renderWidgetBody(id, widgetPayload(id)));
    });
    restoreWidgetScrollPositions(root, scrollPositions);
  }

  function refreshDashboardData() {
    if (dashboardRoot?.isConnected) refreshDashboardDataRoot(dashboardRoot);
    [...dashboardMirrors].forEach((mirror) => {
      if (!mirror.isConnected) {
        dashboardMirrors.delete(mirror);
        return;
      }
      refreshDashboardDataRoot(mirror);
    });
  }

  function renderDashboard() {
    if (activeCanvasPans) {
      dashboardRenderPending = true;
      return;
    }
    dashboardRenderPending = false;
    if (dashboardRoot?.isConnected) renderDashboardRoot(dashboardRoot);
    [...dashboardMirrors].forEach((mirror) => {
      if (!mirror.isConnected) {
        dashboardMirrors.delete(mirror);
        return;
      }
      renderDashboardRoot(mirror);
    });
  }

  function publishWidgets() {
    if (!widgetChannel) return;
    WIDGETS.forEach(([id, label]) => {
      const payload = widgetPayload(id);
      const rendered = renderWidgetBody(id, payload);
      widgetChannel.postMessage({
        type: "state",
        instance_id: `${contextId()}:${id}`,
        widget: id,
        label,
        cluster: "QFw-SLURM-Cluster",
        identity: activeIdentity,
        freshness: state.observed_at || "not observed",
        operation_failed: OPERATION_WIDGET_GROUPS[id]
          ? operationForGroup(OPERATION_WIDGET_GROUPS[id])?.status === "failed"
          : false,
        payload,
        markup: rendered.outerHTML,
        presentation: widgetStates[id] || {},
      });
    });
  }

  function connectWidgetChannel() {
    if (widgetChannel) widgetChannel.close();
    widgetChannel = new BroadcastChannel(`qfw-dashboard-widget-v1:${contextId()}`);
    widgetChannel.addEventListener("message", (event) => {
      const message = event.data || {};
      if (message.type === "request") {
        publishWidgets();
      } else if (message.type === "presentation" && message.widget) {
        widgetStates[message.widget] = {
          ...widgetStates[message.widget], ...message.presentation,
        };
        savePresentation();
        renderDashboard();
        publishWidgets();
      } else if (message.type === "control-action" && message.widget) {
        runPopoutControlAction(message).catch((error) => {
          void notifyDashboard("Operation failed", error.message, "danger");
        });
      }
    });
  }

  async function runPopoutControlAction(message) {
    const values = message.values || {};
    widgetStates[message.widget] = { ...widgetStates[message.widget], ...values };
    savePresentation();
    if (message.widget !== "cluster-access" && activeIdentity !== "root") {
      throw new Error("administrative operations require the root identity");
    }
    if (message.action === "abort") {
      const group = {
        "cluster-control": "cluster",
        "service-control": "services",
        "node-control": "nodes",
      }[message.widget];
      if (group) await abortOperation(group);
      return;
    }
    if (message.action === "open-shell" && message.widget === "cluster-access") {
      await openClusterShell(values.node || "slurmctld", false);
      return;
    }
    if (message.action !== "run") return;
    const dryRun = values.operation_mode === "dry-run";
    if (message.widget === "cluster-control") {
      if (!["status", "synchronize", "start", "stop", "restart", "rebuild"].includes(
        values.operation,
      )) return;
      if (!["incremental", "clean"].includes(values.rebuild_mode)) return;
      const action = values.operation === "rebuild"
        ? `cluster-rebuild-${values.rebuild_mode}`
        : `cluster-${values.operation}`;
      await runOperation("cluster", {
        action, target: "cluster", dry_run: dryRun,
      });
    } else if (message.widget === "service-control") {
      if (!["status", "start", "stop", "restart", "recover"].includes(
        values.operation,
      )) return;
      if (!serviceTargetChoices().some(([target]) => target === values.target)) return;
      await runOperation("services", {
        action: `service-${values.operation}`, target: values.target,
        dry_run: dryRun,
      });
    } else if (message.widget === "node-control") {
      if (!["drain", "resume"].includes(values.operation)) return;
      await runOperation("nodes", {
        action: `node-${values.operation}`,
        target: values.node || "",
        reason: values.reason || "qfw-dashboard",
        dry_run: dryRun,
      });
    }
  }

  async function refreshState() {
    try {
      state = await request("/api/qfw-dashboard/state");
    } catch (error) {
      state = {
        health: "unavailable",
        observed_at: new Date().toISOString(),
        sources: {}, operations: [], experiments: [], error: error.message,
      };
    }
    refreshDashboardData();
    publishWidgets();
  }

  function progressMatches(event) {
    const pane = runtimeApi.elements.progressOutputPane;
    const component = pane.querySelector("[data-qfw-filter=component]")?.value || "";
    const severity = pane.querySelector("[data-qfw-filter=severity]")?.value || "";
    const search = pane.querySelector("[data-qfw-filter=search]")?.value.toLowerCase() || "";
    const contextValue = pane.querySelector("[data-qfw-filter=context]")?.value || "";
    const since = Number(pane.querySelector("[data-qfw-filter=time]")?.value || 0);
    const mode = pane.querySelector("[data-qfw-filter=mode]")?.value || "timeline";
    const timestamp = Date.parse(event.timestamp || 0);
    return (mode !== "logs" || event.kind === "log")
      && (!component || event.component === component)
      && (!contextValue || [event.instance, event.node, event.job_id,
        event.service_id, event.reservation_id,
        event.experiment_id].includes(contextValue))
      && (!severity || event.severity === severity)
      && (!since || timestamp >= Date.now() - since)
      && (!search || JSON.stringify(event).toLowerCase().includes(search));
  }

  function renderProgress() {
    const pane = runtimeApi?.elements.progressOutputPane;
    if (!pane || userIsInteractingWith(pane)) return;
    const filtered = progressEvents.filter(progressMatches).slice(-500);
    window.ElectroBoyFrontend.invokeModule("progress", "clearProgressOutput");
    filtered.forEach((event) => {
      const prefix = `${event.timestamp || ""} ${event.identity || ""} `
        + `${event.component || event.kind || "event"} ${event.severity || "info"}`;
      window.ElectroBoyFrontend.invokeModule(
        "progress", "appendProgressOutput",
        `${prefix} ${event.message || ""}\r\n`,
        event.severity === "error" ? "error" : "",
      );
    });
  }

  function installProgressTools() {
    const pane = runtimeApi.elements.progressOutputPane;
    const header = pane.querySelector(".pane-header");
    if (!header || header.querySelector(".qfw-progress-tools")) return;
    const tools = element("div", "qfw-progress-tools");
    const component = element("select");
    component.dataset.qfwFilter = "component";
    ["", "application", "gateway", "directory", "qpmd", "dvm", "simulator", "provider"]
      .forEach((name) => {
        const option = element("option", "", name || "all components");
        option.value = name;
        component.append(option);
      });
    const source = element("select");
    source.dataset.qfwFilter = "source";
    ["application", "slurm", "gateway", "directory", "nwqsim-qpm",
      "nwqsim-dvm", "nwqsim-simulator", "iqm-qpm", "iqm-provider",
      "shim-qpm", "shim-provider", "fake-iqm-qpm", "fake-iqm-provider"]
      .forEach((name) => {
        const option = element("option", "", name);
        option.value = name;
        source.append(option);
      });
    const severity = element("select");
    severity.dataset.qfwFilter = "severity";
    ["", "debug", "info", "warning", "error", "critical"].forEach((name) => {
      const option = element("option", "", name || "all severities");
      option.value = name;
      severity.append(option);
    });
    const search = element("input");
    search.placeholder = "filter logs";
    search.dataset.qfwFilter = "search";
    const contextFilter = element("select");
    contextFilter.dataset.qfwFilter = "context";
    contextFilter.append(element("option", "", "all instances"));
    const time = element("select");
    time.dataset.qfwFilter = "time";
    [[0, "all time"], [300000, "5 minutes"], [3600000, "1 hour"]]
      .forEach(([value, label]) => {
        const option = element("option", "", label);
        option.value = String(value);
        time.append(option);
      });
    const pause = element("button", "", "Pause");
    pause.type = "button";
    pause.addEventListener("click", () => {
      progressPaused = !progressPaused;
      pause.textContent = progressPaused ? "Resume" : "Pause";
    });
    const mode = element("select");
    mode.dataset.qfwFilter = "mode";
    ["Timeline", "Logs"].forEach((label) => {
      const option = element("option", "", label);
      option.value = label.toLowerCase();
      mode.append(option);
    });
    [mode, source, component, contextFilter, severity, time, search].forEach((control) => {
      control.addEventListener("input", renderProgress);
      tools.append(control);
    });
    component.addEventListener("change", () => {
      const values = new Set();
      progressEvents.filter((item) => !component.value
        || item.component === component.value).forEach((item) => {
        [item.instance, item.node, item.job_id, item.service_id,
          item.reservation_id, item.experiment_id]
          .filter(Boolean).forEach((value) => values.add(value));
      });
      contextFilter.replaceChildren(element("option", "", "all instances"));
      [...values].sort().forEach((value) => {
        const option = element("option", "", value);
        option.value = value;
        contextFilter.append(option);
      });
    });
    tools.append(pause, element("span", "qfw-progress-context",
      `${progressIdentity} · connected · live`));
    header.insertBefore(tools, header.querySelector(".pane-actions"));
  }

  async function refreshEvents() {
    if (progressPaused) return;
    const resetGeneration = dashboardResetGeneration;
    try {
      const payload = await request(
        `/api/qfw-dashboard/events?cursor=${eventCursor}&limit=500`
          + `&identity=${encodeURIComponent(progressIdentity)}`,
      );
      if (resetGeneration !== dashboardResetGeneration) return;
      if (payload.gap) {
        progressEvents.push({ severity: "warning", message: "log cursor gap" });
      }
      eventCursor = Number(payload.cursor || eventCursor);
      progressEvents = [...progressEvents, ...(payload.events || [])].slice(-2000);
      const pane = runtimeApi.elements.progressOutputPane;
      const mode = pane.querySelector("[data-qfw-filter=mode]")?.value;
      const source = pane.querySelector("[data-qfw-filter=source]")?.value;
      const instance = pane.querySelector("[data-qfw-filter=context]")?.value || "";
      if (mode === "logs" && source && (source !== "application" || instance)) {
        const key = `${source}:${instance}`;
        const logs = await request(
          `/api/qfw-dashboard/logs?source=${encodeURIComponent(source)}`
            + `&cursor=${Number(logCursors[key] || 0)}&limit=500`
            + `&identity=${encodeURIComponent(progressIdentity)}`
            + `&instance=${encodeURIComponent(instance)}`,
        );
        if (resetGeneration !== dashboardResetGeneration) return;
        if (logs.gap) {
          progressEvents.push({
            kind: "gap", component: source, severity: "warning",
            message: "log source rotated or exceeded the bounded read window",
          });
        }
        logCursors[key] = Number(logs.cursor || logCursors[key] || 0);
        progressEvents = [...progressEvents, ...(logs.events || [])].slice(-2000);
      }
      renderProgress();
    } catch (error) {
      // Other dashboard state remains usable when logs are unavailable.
    }
  }

  async function pollState() {
    await refreshState();
    if (runtimeApi) polling = window.setTimeout(pollState, 2500);
  }

  async function pollEvents() {
    await refreshEvents();
    if (runtimeApi) eventPolling = window.setTimeout(pollEvents, 1200);
  }

  function trackDashboardSelection(event) {
    const phase = event.target instanceof Element
      ? event.target.closest(".qfw-dashboard .qfw-experiment-phase") : null;
    const widget = !phase && event.target instanceof Element
      ? event.target.closest(".qfw-dashboard .qfw-widget") : null;
    selectedExperimentPhase = phase?.dataset.phase || null;
    selectedDashboardWidget = widget?.dataset.widget || null;
    document.querySelectorAll(".qfw-dashboard .qfw-experiment-phase")
      .forEach((item) => {
        item.classList.toggle(
          "is-active", item.dataset.phase === selectedExperimentPhase,
        );
      });
    document.querySelectorAll(".qfw-dashboard .qfw-widget")
      .forEach((item) => {
        item.classList.toggle(
          "is-active", item.dataset.widget === selectedDashboardWidget,
        );
      });
  }

  function trackDashboardPointerSelection(event) {
    if (event.button !== 0) {
      nonPrimarySelectionPointers.add(event.pointerId);
      return;
    }
    nonPrimarySelectionPointers.clear();
    trackDashboardSelection(event);
  }

  function trackDashboardFocusSelection(event) {
    if (!nonPrimarySelectionPointers.size) trackDashboardSelection(event);
  }

  function finishNonPrimarySelectionPointer(event) {
    if (!nonPrimarySelectionPointers.has(event.pointerId)) return;
    window.setTimeout(() => {
      nonPrimarySelectionPointers.delete(event.pointerId);
    }, 0);
  }

  function scrollInteractionTarget(event) {
    return event.composedPath().find((target) => {
      if (!(target instanceof Element)) return false;
      const style = window.getComputedStyle(target);
      const vertical = /^(auto|scroll)$/.test(style.overflowY)
        && target.scrollHeight > target.clientHeight;
      const horizontal = /^(auto|scroll)$/.test(style.overflowX)
        && target.scrollWidth > target.clientWidth;
      return vertical || horizontal;
    }) || null;
  }

  function trackScrollPointer(event) {
    if (event.button !== 0) return;
    const target = scrollInteractionTarget(event);
    if (target) activeScrollPointers.set(event.pointerId, target);
  }

  function finishScrollPointer(event) {
    activeScrollPointers.delete(event.pointerId);
  }

  function rememberScrollInteraction(target) {
    if (!(target instanceof Element)) return;
    const expiresAt = Date.now() + SCROLL_INTERACTION_GRACE_MS;
    recentScrollInteractions.set(target, expiresAt);
    window.setTimeout(() => {
      if ((recentScrollInteractions.get(target) || 0) <= Date.now()) {
        recentScrollInteractions.delete(target);
      }
    }, SCROLL_INTERACTION_GRACE_MS + 50);
  }

  function recentlyScrolledInside(container) {
    const now = Date.now();
    for (const [target, expiresAt] of recentScrollInteractions) {
      if (expiresAt <= now || !target.isConnected) {
        recentScrollInteractions.delete(target);
      } else if (container.contains(target)) {
        return true;
      }
    }
    return false;
  }

  function trackRecentScrollInteraction(event) {
    const target = scrollInteractionTarget(event)
      || (event.target instanceof Element ? event.target : null);
    rememberScrollInteraction(target);
  }

  function activate(runtime) {
    runtimeApi = runtime;
    runtimeApi.ui.setWorkflowSideSheetCollapsed(true);
    runtimeApi.ui.setAgentInputVisible(true);
    loadPresentation();
    progressIdentity = activeIdentity;
    dashboardRoot = element("div", "qfw-dashboard");
    originalStatusOutput = runtime.elements.projectStatusOutput;
    originalStatusOutput.replaceWith(dashboardRoot);
    connectWidgetChannel();
    installProgressTools();
    document.addEventListener("pointerdown", trackDashboardPointerSelection, true);
    document.addEventListener("pointerdown", trackScrollPointer, true);
    document.addEventListener("wheel", trackRecentScrollInteraction, true);
    document.addEventListener("scroll", trackRecentScrollInteraction, true);
    document.addEventListener("pointerup", finishNonPrimarySelectionPointer, true);
    document.addEventListener("pointerup", finishScrollPointer, true);
    document.addEventListener("pointercancel", finishNonPrimarySelectionPointer, true);
    document.addEventListener("pointercancel", finishScrollPointer, true);
    document.addEventListener("lostpointercapture", finishScrollPointer, true);
    document.addEventListener("focusin", trackDashboardFocusSelection, true);
    renderDashboard();
    pollState();
    pollEvents();
  }

  function mountWorkflowPane(kind, target) {
    if (kind !== "status" || !dashboardRoot
        || !target || typeof target.replaceChildren !== "function") {
      return false;
    }
    const mirror = element("div", "qfw-dashboard");
    dashboardMirrors.add(mirror);
    target.replaceChildren(mirror);
    renderDashboardRoot(mirror);
    return () => {
      dashboardMirrors.delete(mirror);
      mirror.remove();
    };
  }

  function deactivate() {
    window.clearTimeout(polling);
    window.clearTimeout(eventPolling);
    polling = null;
    eventPolling = null;
    activeCanvasPans = 0;
    dashboardRenderPending = false;
    pendingOperationGroups.clear();
    pendingAbortGroups.clear();
    selectedDashboardWidget = null;
    selectedExperimentPhase = null;
    nonPrimarySelectionPointers.clear();
    activeScrollPointers.clear();
    recentScrollInteractions.clear();
    document.removeEventListener("pointerdown", trackDashboardPointerSelection, true);
    document.removeEventListener("pointerdown", trackScrollPointer, true);
    document.removeEventListener("wheel", trackRecentScrollInteraction, true);
    document.removeEventListener("scroll", trackRecentScrollInteraction, true);
    document.removeEventListener("pointerup", finishNonPrimarySelectionPointer, true);
    document.removeEventListener("pointerup", finishScrollPointer, true);
    document.removeEventListener("pointercancel", finishNonPrimarySelectionPointer, true);
    document.removeEventListener("pointercancel", finishScrollPointer, true);
    document.removeEventListener("lostpointercapture", finishScrollPointer, true);
    document.removeEventListener("focusin", trackDashboardFocusSelection, true);
    [...activeDashboardDialogs].forEach((close) => close(false));
    widgetChannel?.close();
    widgetChannel = null;
    popupWindows.clear();
    dashboardMirrors.forEach((mirror) => mirror.remove());
    dashboardMirrors.clear();
    if (dashboardRoot?.isConnected && originalStatusOutput) {
      dashboardRoot.replaceWith(originalStatusOutput);
    }
    runtimeApi?.ui.setWorkflowSideSheetCollapsed(false);
    dashboardRoot = null;
    originalStatusOutput = null;
    runtimeApi = null;
  }

  window.ElectroBoyFrontend.registerWorkflow({
    id: WORKFLOW_ID,
    mode: WORKFLOW_ID,
    label: "QFw Slurm Cluster",
    order: 20,
    backendPackage: "qfw_slurm_dashboard",
    navigation: "custom",
    paneKinds: [
      {
        kind: "status",
        label: "Dashboard",
        singleton: true,
        popoutMode: "mirror",
      },
      { kind: "agent", label: "AI Agent" },
      { kind: "progress", label: "Progress" },
      { kind: "artifact", label: "File" },
      { kind: "shell", label: "Shell" },
    ],
    paneStylesheets: ["/assets/service/css/qfw-slurm-cluster.css"],
    defaultPaneLayout: { type: "leaf", kind: "status" },
    layoutClass: "qfw-slurm-cluster-workflow",
    help: {
      summary: "Operate and observe the QFw virtual Slurm cluster.",
      features: [
        "Inspect cluster, Slurm, QPM, allocation, and experiment state.",
        "Run controlled lifecycle actions under an explicit cluster identity.",
        "Keep cluster recipes, progress, and shells beside the dashboard.",
      ],
    },
    renderNavigation(container) {
      container.replaceChildren(element("p", "", "Cluster dashboard"));
    },
    renderProjectStatus() { return true; },
    mountPane: mountWorkflowPane,
    activate,
    deactivate,
    actions: { refresh: () => refreshState() },
  });
})();
