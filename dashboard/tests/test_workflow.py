from importlib import resources

from qfw_slurm_dashboard.plugin import workflow


def test_workflow_registers_only_public_required_modules() -> None:
    definition = workflow()
    assert definition.id == "qfw-slurm-cluster"
    assert definition.workspace_policy == "shared-singleton"
    assert definition.modules == (
        "core",
        "agent_sessions",
        "markdown_documents",
        "file_browser",
        "project_shell",
        "progress",
    )


def test_frontend_declares_exact_pane_catalog_and_fixed_widgets() -> None:
    frontend = resources.files("qfw_slurm_dashboard").joinpath(
        "assets/frontend.js"
    ).read_text()
    assert 'document.title = "Dashboard";' in frontend
    for label in ("Dashboard", "AI Agent", "Progress", "File", "Shell"):
        assert f'label: "{label}"' in frontend
    assert '{ kind: "agent", label: "AI Agent" }' in frontend
    assert 'kind: "input"' not in frontend
    assert "runtimeApi.ui.setWorkflowSideSheetCollapsed(true);" in frontend
    assert "runtimeApi?.ui.setWorkflowSideSheetCollapsed(false);" in frontend
    assert "runtimeApi.ui.setAgentInputVisible(true);" in frontend
    for widget in (
        "health", "inventory", "cluster-control", "service-control",
        "node-control", "cluster-access", "nodes", "services", "allocations",
        "experiments", "topology", "results", "alerts",
    ):
        assert f'["{widget}",' in frontend
    for group in (
        "Operations", "Experiments and results",
        "Allocations and service topology", "Cluster state and configuration",
    ):
        assert f'label: "{group}"' in frontend
    assert "function buildWidgetGroup(group)" in frontend
    assert "WIDGET_GROUPS.forEach" in frontend
    assert '["experiments", "Running Experiments"]' in frontend
    assert 'form.classList.add("qfw-grid-wide")' in frontend
    assert "connectorSlot" not in frontend
    assert "renderExperimentConnectors" not in frontend
    assert "qfw-phase-arrow" not in frontend
    assert 'const partition = element("select")' in frontend
    assert "let selectedDashboardWidget = null;" in frontend
    assert "let selectedExperimentPhase = null;" in frontend
    assert "function trackDashboardSelection(event)" in frontend
    assert "function trackDashboardPointerSelection(event)" in frontend
    assert "if (event.button !== 0)" in frontend
    assert "const nonPrimarySelectionPointers = new Set();" in frontend
    assert 'document.addEventListener("pointerdown", trackDashboardPointerSelection, true)' in frontend
    assert 'document.removeEventListener("pointerdown", trackDashboardPointerSelection, true)' in frontend
    assert 'const optionalRequirements = {' in frontend
    for requirement in (
        "MPI ranks", "Ranks per node", "CPUs per rank", "Memory", "GPUs",
        "Node features", "Exclusive allocation",
    ):
        assert requirement in frontend
    assert 'application_source: applicationSource.value' in frontend
    assert 'application_submission_type: applicationSubmissionType.value' in frontend
    assert 'application_path: applicationPath.value.trim()' in frontend
    assert 'application_arguments: applicationArguments.value.trim()' in frontend
    assert 'batch_script: applicationSource.value === "path"' in frontend
    assert "function allowsEditableBatchScript(payload)" in frontend
    assert "function editableBatchScriptFields(payload, previewPayload = {})" in frontend
    assert "...editableBatchScriptFields(payload, result)" in frontend
    assert "...submissionDefinition(entry.request, entry.draft_id)" in frontend
    assert 'application_parameters: currentApplicationParameters()' in frontend
    assert '"Existing sbatch script"' in frontend
    assert '"Generated sbatch"' in frontend
    assert 'request("/api/qfw-dashboard/applications/batch-script"' in frontend
    assert "function renderApplicationParameters(values = {})" in frontend
    assert "This example has no configurable runtime parameters." in frontend
    assert '"Preview batch file"' in frontend
    assert 'if (id === "experiments") return state.running_experiments || [];' in frontend
    assert 'if (id === "results") return state.experiments || [];' in frontend
    assert '"Submit Application"' in frontend
    assert '"Submit experiment"' not in frontend
    assert "function packagedExamples()" in frontend
    assert "function refreshPackagedExamples(root)" in frontend
    assert "refreshPackagedExamples(root);" in frontend
    assert "control === document.activeElement" in frontend
    assert 'container.querySelector("select[aria-expanded=true]")' in frontend
    assert "const SCROLL_INTERACTION_GRACE_MS = 1200;" in frontend
    assert "function recentlyScrolledInside(container)" in frontend
    assert 'document.addEventListener("wheel", trackRecentScrollInteraction, true)' in frontend
    assert frontend.index("if (group.experimentLauncher) renderExperimentForm(grid);") < frontend.index(
        "group.widgets.forEach"
    )
    assert "BroadcastChannel" in frontend
    assert "setTimeout(pollState, 2500)" in frontend
    assert "installCanvasInteraction" in frontend
    assert "function scrollableWheelTarget(event, boundary)" in frontend
    assert "if (scrollableWheelTarget(event, viewport)) return;" in frontend
    assert 'event.button !== 1' in frontend
    assert "let activeCanvasPans = 0;" in frontend
    assert "if (activeCanvasPans)" in frontend
    assert "dashboardRenderPending = true;" in frontend
    assert 'viewport.addEventListener("lostpointercapture", finishPan)' in frontend
    assert "stage.style.zoom = String(camera.scale)" in frontend
    assert "stage.style.transform" not in frontend
    assert 'zoom.type = "range"' in frontend
    assert 'zoomSlider.type = "range"' in frontend
    assert "Math.min(2.25" not in frontend
    assert "Math.max(0.35" not in frontend
    assert "Loading live topology sources:" in frontend
    assert "refreshExperimentSubmissionStatus" in frontend
    assert "function visibleSubmissionSetEntries()" in frontend
    assert "function experimentsForSubmissionEntry(entry)" in frontend
    assert "item.manifest?.submission_entry_id === entry.draft_id" in frontend
    assert "function submissionEntryIsInFlight(entry)" in frontend
    assert "function submissionDefinition(payload, draftId)" in frontend
    assert 'statusNode.textContent = rowStatus;' in frontend
    assert 'terminal.textContent = [' in frontend
    assert 'submission.result?.output_tail' in frontend
    assert 'previewOutput.dataset.qfwSubmissionOutput = ""' in frontend
    assert "Submitting ${staged.length} applications" in frontend
    assert "qfwSubmitSet" in frontend
    assert 'const requestPending = batchStatus.status === "requesting";' in frontend
    assert "submit.disabled = requestPending || editing || entries.length === 0;" in frontend
    assert "submit.disabled = active;" not in frontend
    assert '"Add to Submission Set"' in frontend
    assert '"Submit All (0)"' in frontend
    assert 'iconButton("view", "View application")' in frontend
    assert 'iconButton("edit", "Edit application")' in frontend
    assert 'iconButton("save", "Save application changes")' in frontend
    assert 'iconButton("cancel", "Cancel application changes")' in frontend
    assert 'iconButton("trash", "Remove application")' in frontend
    assert 'request("/api/qfw-dashboard/experiments/batch"' in frontend
    assert "error.payload = payload;" in frontend
    assert 'failed.status = "invalid";' in frontend
    assert "widgetStates.submissionSetSelected = failed.draft_id;" in frontend
    assert 'entry.status = "staged";' in frontend
    assert "delete entry.error;" in frontend
    assert "Validation error for ${invalid.request?.example" in frontend
    assert "const draftId = window.crypto.randomUUID();" in frontend
    assert "const experimentId = window.crypto.randomUUID();" in frontend
    assert "execution_ids: []" in frontend
    assert "entry.execution_ids = [...new Set([" in frontend
    assert 'row.classList.toggle("is-in-flight", submissionEntryIsInFlight(entry));' in frontend
    assert "entry.submitted" not in frontend
    assert 'name !== "qfw-services"' in frontend
    assert 'job.job_name || "Slurm job"' in frontend
    assert "qfw-topology-state-" in frontend
    assert '"qfw-topology-partition"' in frontend
    assert 'box.classList.add("qfw-topology-partition-box")' in frontend
    assert 'label.textContent = `PARTITION · ${frame.id}`' in frontend
    assert 'type: "partition"' not in frontend
    assert 'box.setAttribute("rx", item.type === "service" ? "16" : "8")' in frontend
    assert 'label.setAttribute("text-anchor", "middle")' in frontend
    assert '"qfw-topology-edge-service"' in frontend
    assert "const topologyServices" in frontend
    assert "const serviceRoles" in frontend
    assert "function serviceTable(records)" in frontend
    assert '"Download logs"' in frontend
    assert '"/api/qfw-dashboard/services/archive"' in frontend
    assert '"Next defw_out.log level"' in frontend
    assert '"Next defw_py.log level"' in frontend
    assert "const JOB_COLORS" in frontend
    assert "function jobColor(jobId)" in frontend
    assert "const TOPOLOGY_CONNECTOR_COLORS" in frontend
    assert "const connectorSourceColors = new Map();" in frontend
    assert "function topologyConnectorColor(sourceId)" in frontend
    assert '"--qfw-topology-edge-color"' in frontend
    assert "const clusterNodes = new Map();" in frontend
    assert 'type: "node", id: "slurmctld"' in frontend
    assert '...slurmJobs.map((item) => ({' not in frontend
    assert "function topologyState(value)" in frontend
    assert '"qfw-topology-job-active"' in frontend
    assert '"qfw-topology-job-stripe"' in frontend
    assert 'stripe.setAttribute("x", "8")' in frontend
    assert 'stripe.setAttribute("width", "169")' in frontend
    assert "String(62 + jobIndex * 7)" in frontend
    assert "function objectHeight(item)" in frontend
    assert "function placeObjectRows(items, startY, startX = 35)" in frontend
    assert "function showTopologyHover" in frontend
    assert "rootBounds.width / root.offsetWidth" in frontend
    assert "(clientX - rootBounds.left + 14) / safeScaleX" in frontend
    assert "function showFailedService(service)" in frontend
    assert "/api/qfw-dashboard/services/archive" in frontend
    for role in ("QPMd", "Directory Service", "Slurm Gateway", "PRTE DVM"):
        assert f'"{role}"' in frontend
    assert 'details.style.setProperty("--qfw-border-duration"' in frontend
    assert 'details.style.setProperty("--qfw-border-delay"' in frontend
    assert "function captureWidgetScrollPositions(root)" in frontend
    assert "restoreWidgetScrollPositions(root, scrollPositions)" in frontend
    assert "function preserveScroll(node)" in frontend
    assert 'root.querySelectorAll("[data-qfw-preserve-scroll]")' in frontend
    assert "height: container.style.height" in frontend
    assert "container.style.height = offset.height" in frontend
    assert "function resetDashboardGeometry(root)" in frontend
    assert 'container.style.removeProperty("height")' in frontend
    assert 'if (topologyGraph) topologyGraph.style.width = "100%"' in frontend
    assert "resetDashboardGeometry(root);" in frontend
    for scroll_region in (
        "qfw-table-wrap", "qfw-alert-detail", "qfw-topology",
        "qfw-operation-output", "qfw-command-preview",
    ):
        assert scroll_region in frontend
    assert frontend.count("preserveScroll(") == 8
    assert "Save preset" not in frontend
    assert "Compare selected results" not in frontend
    assert "/api/qfw-dashboard/experiments/archive" in frontend
    assert "function renderAlerts(payload)" in frontend
    assert '"pre", "qfw-alert-detail qfw-resizable-text"' in frontend
    assert "function showDashboardOverlay({" in frontend
    assert "function confirmDashboardAction(" in frontend
    assert "function notifyDashboard(" in frontend
    assert "notifiedTerminal" not in frontend
    assert "terminalNotificationsReady" not in frontend
    assert "`QFw ${item.status}`" not in frontend
    assert "window.alert" not in frontend
    assert "window.confirm" not in frontend
    assert "window.Notification" not in frontend
    assert "function renderClusterControl()" in frontend
    assert '"Clear Dashboard state"' in frontend
    assert '"/api/qfw-dashboard/reset"' in frontend
    assert '"Clear experiment results"' in frontend
    assert '"/api/qfw-dashboard/experiments/clear"' in frontend
    assert "window.localStorage.removeItem(storageKey())" in frontend
    assert 'widgetChannel?.postMessage({ type: "reset" })' in frontend
    assert "dashboardResetGeneration" in frontend
    for cluster_operation in (
        "Status", "Synchronize with upstream", "Start", "Stop", "Restart",
        "Rebuild", "Incremental (use cache)", "Clean (no cache)",
    ):
        assert cluster_operation in frontend
    assert "cluster-rebuild-${rebuildMode.value}" in frontend
    assert "cluster-rebuild-${values.rebuild_mode}" in frontend
    assert "function combinedServiceRecords(catalog, managed)" in frontend
    assert "combinedServiceRecords(services.records, servicePlane.records)" in frontend
    assert "function renderServiceControl()" in frontend
    assert '["status", "Status"]' in frontend
    assert 'action !== "status"' in frontend
    assert '`created=${operation.created_at || "unknown"}' in frontend
    assert "const pendingOperationGroups = new Set();" in frontend
    assert "const pendingAbortGroups = new Set();" in frontend
    assert "if (pendingOperationGroups.has(group))" in frontend
    assert "if (pendingAbortGroups.delete(group))" in frontend
    assert "function operationControlState(group)" in frontend
    assert "function applyOperationControlState(container, group)" in frontend
    assert 'status.setAttribute("aria-live", "polite")' in frontend
    assert 'run.classList.toggle("is-pressed", control.busy)' in frontend
    assert "function renderNodeControl()" in frontend
    assert "function slurmNodeNames()" in frontend
    assert "function refreshNodeControlChoices(widget)" in frontend
    assert 'if (group === "nodes") refreshNodeControlChoices(widget);' in frontend
    assert "control === document.activeElement" in frontend
    assert 'selectedSource("slurm").records' in frontend
    assert 'const node = selectControl(widget, "node", nodeChoices' in frontend
    assert 'textControl(widget, "node", "", "node name")' not in frontend
    assert "function renderClusterAccess()" in frontend
    assert 'action: `service-${action}`' in frontend
    assert 'message.type === "control-action"' in frontend
    assert "function mountWorkflowPane(" in frontend
    assert "const dashboardMirrors = new Set();" in frontend
    assert "function renderDashboardRoot(root)" in frontend
    assert "function refreshDashboardDataRoot(root)" in frontend
    assert "function refreshOperationWidget(widget, group)" in frontend
    assert "function selectionIntersects(container)" in frontend
    assert "function userIsInteractingWith(container)" in frontend
    assert 'active.matches("input, textarea, select, [contenteditable=true]")' in frontend
    assert "const activeScrollPointers = new Map();" in frontend
    assert "function scrollInteractionTarget(event)" in frontend
    assert "function trackScrollPointer(event)" in frontend
    assert "function finishScrollPointer(event)" in frontend
    assert "if (userIsInteractingWith(form)) return;" in frontend
    assert "if (userIsInteractingWith(widget)) return;" in frontend
    assert "if (!pane || userIsInteractingWith(pane)) return;" in frontend
    assert 'widget.classList.toggle("has-error", operation?.status === "failed")' in frontend
    assert "operation_failed: OPERATION_WIDGET_GROUPS[id]" in frontend
    assert "refreshDashboardData();" in frontend
    assert "dashboardMountMarker" not in frontend
    assert 'popoutMode: "mirror"' in frontend
    assert 'mountPane: mountWorkflowPane' in frontend
    assert 'paneStylesheets: ["/assets/service/css/qfw-slurm-cluster.css"]' in frontend
    assert "/api/qfw-dashboard/operations/abort" in frontend
    assert '"pre", "qfw-operation-output qfw-resizable-text"' in frontend
    assert "markup: rendered.outerHTML" in frontend

    popout = resources.files("qfw_slurm_dashboard").joinpath(
        "assets/widget.html"
    ).read_text(encoding="utf-8")
    assert "/assets/service/css/selects.css" in popout
    assert "/assets/service/css/qfw-slurm-cluster.css" in popout
    assert "/assets/service/js/core/select-menu.js" in popout
    assert "template.innerHTML = lastMarkup" in popout
    assert "JSON.stringify(lastPayload" not in popout
    assert "function hydrateWidget()" in popout
    assert 'widget === "topology"' in popout
    assert 'type: "control-action"' in popout
    assert 'values.operation !== "status"' in popout
    assert "controlWidgets.has(widget)" in popout
    assert "graph.style.width" in popout
    assert 'zoom?.addEventListener("change"' in popout
    assert 'class="qfw-widget-viewport"' in popout
    assert "function zoomAt(" in popout
    assert 'min="5" max="1000"' in popout
    assert "const CANVAS_ZOOM_MIN = 5;" in popout
    assert "const CANVAS_ZOOM_MAX = 1000;" in popout
    assert "function scrollableWheelTarget(event, boundary)" in popout
    assert "if (scrollableWheelTarget(event, viewport)) return;" in popout
    assert "popout_camera" in popout
    assert "event.button !== 1" in popout
    assert "output.style.zoom = String(camera.scale)" in popout
    assert "output.style.transform" not in popout
    assert "function captureMirrorScrollPositions()" in popout
    assert "restoreMirrorScrollPositions(scrollPositions)" in popout
    assert "function hydrateSortableTables()" in popout
    assert 'table.querySelectorAll("thead .qfw-table-sort")' in popout
    assert "compareSortableValues(" in popout
    assert 'output.querySelectorAll("[data-qfw-preserve-scroll]")' in popout
    assert "height: container.style.height" in popout
    assert "containers[index].style.height = position.height" in popout
    assert 'container.style.removeProperty("height")' in popout
    assert 'if (topologyGraph) topologyGraph.style.width = "100%"' in popout
    assert "function selectionIntersects(container)" in popout
    assert "function userIsInteractingWith(container)" in popout
    assert "const activeScrollPointers = new Map();" in popout
    assert "function scrollInteractionTarget(event)" in popout
    assert "if (userIsInteractingWith(output))" in popout
    assert 'output.addEventListener("focusout"' in popout
    assert "function confirmWidgetAction(" in popout
    assert 'output.classList.toggle("has-error", message.operation_failed === true)' in popout
    assert "window.confirm" not in popout
    assert 'if (message.type === "reset")' in popout


def test_dashboard_uses_electroboy_pane_colors() -> None:
    stylesheet = resources.files("qfw_slurm_dashboard").joinpath(
        "assets/qfw-slurm-cluster.css"
    ).read_text(encoding="utf-8")

    assert "background: var(--terminal, #10141f);" in stylesheet
    assert "--qfw-cyan: #5ee8ff;" in stylesheet
    assert ".qfw-widget-window" in stylesheet
    assert ".qfw-control-group" in stylesheet
    assert ".qfw-topology-zoom" in stylesheet
    assert ".qfw-topology-partition .qfw-topology-partition-box" in stylesheet
    assert ".qfw-topology-service rect" in stylesheet
    assert ".qfw-topology-object.qfw-topology-state-down rect" in stylesheet
    assert ".qfw-topology-object.qfw-topology-state-stopped rect" in stylesheet
    assert ".qfw-topology-edge-service" in stylesheet
    assert ".qfw-topology-edge-object" in stylesheet
    assert "stroke: var(--qfw-topology-edge-color, var(--qfw-violet));" in stylesheet
    assert ".qfw-topology-hover" in stylesheet
    assert ".qfw-topology-job-active" in stylesheet
    assert ".qfw-topology-job-stripe" in stylesheet
    assert ".qfw-service-failure-detail" in stylesheet
    assert ".qfw-alert-detail" in stylesheet
    assert "white-space: pre;" in stylesheet
    assert "@keyframes qfw-telemetry-sweep" not in stylesheet
    assert "@keyframes qfw-widget-border-trace" in stylesheet
    assert "mask-composite: exclude" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert "background: var(--panel" not in stylesheet
    assert "overflow: hidden;" in stylesheet
    assert ".qfw-widget-chevron" in stylesheet
    assert ".qfw-slurm-cluster-workflow .pane-layout-kind" in stylesheet
    assert ':has(.pane-layout-leaf[data-pane-kind="agent"])' in stylesheet
    assert ".input-resize-handle" in stylesheet
    assert ".input-pane" in stylesheet
    assert ".qfw-widget-sections" in stylesheet
    assert ".qfw-widget-group-title::after" in stylesheet
    assert ".qfw-phase-connector" not in stylesheet
    assert ".qfw-phase-arrow" not in stylesheet
    assert ".qfw-experiment-phase" in stylesheet
    assert ".qfw-experiment-phase.is-active" in stylesheet
    assert ".qfw-experiment-phase:focus-within" not in stylesheet
    assert "align-content: start;" in stylesheet
    assert ".qfw-widget.is-active" in stylesheet
    assert ".qfw-widget.is-active::before" in stylesheet
    assert ".qfw-widget[open] { height: 100%; }" in stylesheet
    assert ".qfw-widget:not([open]) { align-self: start; }" in stylesheet
    assert ".qfw-resizable-text" in stylesheet
    assert ".qfw-experiment-field select {\n  height: 2.45em;" in stylesheet
    assert "resize: vertical;" in stylesheet
    assert ".qfw-widget.has-error" in stylesheet
    assert ".qfw-widget-mirror.has-error" in stylesheet
    assert ".qfw-notification-overlay" in stylesheet
    assert ".qfw-notification-danger .qfw-notification-dialog" in stylesheet
    assert "0 0 3.8em rgb(255 50 100 / 32%)" in stylesheet
    assert ".qfw-optional-requirement" in stylesheet
    assert "font-size: 1.05em;" in stylesheet
    assert "font-size: 1.08em;" in stylesheet
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in stylesheet
    assert ".qfw-grid-wide { grid-column: 1 / -1; }" in stylesheet
    assert ".qfw-slurm-cluster-workflow .workspace-pane-kind" in stylesheet
    assert ".qfw-slurm-cluster-workflow .terminal-font-button" not in stylesheet
    assert ".qfw-slurm-cluster-workflow .terminal-font-controls" not in stylesheet
    assert ".qfw-slurm-cluster-workflow .terminal-font-value" not in stylesheet
    assert ".qfw-slurm-cluster-workflow .pane-font-button" in stylesheet
    assert ".qfw-slurm-cluster-workflow input.pane-font-level" in stylesheet
    assert ".qfw-slurm-cluster-workflow .pane-popout-button" in stylesheet
    assert ".qfw-widget-filter + .qfw-popout" in stylesheet
    assert "font-weight: 400;" in stylesheet
    assert "font: inherit;" in stylesheet
    assert "--electroboy-select-picker-bg: #0a2235;" in stylesheet
    assert "--electroboy-select-picker-selected: rgb(31 111 139 / 95%);" in stylesheet
    assert ".qfw-dashboard select option" in stylesheet
    assert ".qfw-progress-tools select option" in stylesheet
    assert ".qfw-widget-window select option" in stylesheet
    assert "background: #0a2235;" in stylesheet
    assert ".qfw-operation-control" in stylesheet
    assert ".qfw-operation-output" in stylesheet
    assert ".qfw-operation-run.is-pressed" in stylesheet
    assert ".qfw-operation-status" in stylesheet
    assert "@keyframes qfw-operation-dot" in stylesheet
    assert "@keyframes qfw-running-entry-pulse" in stylesheet
    assert ".qfw-submission-set-row.is-in-flight:not(.has-error)" in stylesheet
