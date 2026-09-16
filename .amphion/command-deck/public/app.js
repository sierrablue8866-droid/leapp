
// Generic HTML dialog helper
async function showPrompt(type, title, text, defaultValue = "") {
  return new Promise((resolve) => {
    const dialog = document.getElementById("promptDialog");
    if (!dialog) return resolve(null);

    const titleEl = document.getElementById("promptDialogTitle");
    const textEl = document.getElementById("promptDialogText");
    const inputEl = document.getElementById("promptDialogInput");
    const btnCancel = document.getElementById("promptDialogCancel");
    const btnOk = document.getElementById("promptDialogOk");

    titleEl.textContent = title || "";
    textEl.textContent = text || "";

    if (type === "alert") {
      inputEl.style.display = "none";
      btnCancel.style.display = "none";
      btnOk.textContent = "OK";
    } else if (type === "confirm") {
      inputEl.style.display = "none";
      btnCancel.style.display = "inline-block";
      btnOk.textContent = "Yes";
    } else if (type === "prompt") {
      inputEl.style.display = "block";
      inputEl.value = defaultValue;
      btnCancel.style.display = "inline-block";
      btnOk.textContent = "OK";
    }

    const cleanup = () => {
      btnCancel.removeEventListener("click", onCancel);
      btnOk.removeEventListener("click", onOk);
      dialog.removeEventListener("keydown", onKeydown);
      dialog.close();
    };

    const onCancel = (e) => {
      e.preventDefault();
      cleanup();
      resolve(type === "prompt" ? null : false);
    };

    const onOk = (e) => {
      e.preventDefault();
      cleanup();
      if (type === "prompt") resolve(inputEl.value);
      else resolve(true);
    };

    const onKeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onOk(e);
      } else if (e.key === "Escape") {
        e.preventDefault();
        onCancel(e);
      }
    };

    btnCancel.addEventListener("click", onCancel);
    btnOk.addEventListener("click", onOk);
    dialog.addEventListener("keydown", onKeydown);

    dialog.showModal();
    if (type === "prompt") inputEl.focus();
    else btnOk.focus();
  });
}
const state = {
  data: null,
  charts: [],
  selectedChartId: "",
  milestonePanel: {
    open: false,
    view: null,
    history: [],
  },
  filters: {
    milestoneId: "",
    search: "",
  },
  dragCardId: "",
  currentView: (() => {
    const saved = localStorage.getItem("mcd_current_view");
    return saved === "wiki" ? "board" : (saved || "board");
  })(),
  lastVersion: null,
  pollInterval: null,
};

const FILTERS_STORAGE_KEY = "mcd_board_filters_v1";
const EXPECTED_RUNTIME_FINGERPRINT = "launch-command-deck:python:sqlite";
const MILESTONE_CODE_PATTERN = /^([A-Za-z][A-Za-z0-9]*-\d+)\b/;
const MILESTONE_CODE_TITLE_PREFIX_PATTERN = /^\s*([A-Za-z][A-Za-z0-9]*-\d+)\s*[·:\-]\s*(.+)\s*$/;
let runtimeValidationPromise = null;

const el = {
  boardsList: document.querySelector("#boardsList"),
  boardsSummaryActive: document.querySelector("#boardsSummaryActive"),
  milestoneProgress: document.querySelector("#milestoneProgress"),
  kanbanColumns: document.querySelector("#kanbanColumns"),
  boardName: document.querySelector("#boardName"),
  boardDescription: document.querySelector("#boardDescription"),
  milestonePolicyHint: document.querySelector("#milestonePolicyHint"),
  milestoneFilter: document.querySelector("#milestoneFilter"),
  searchInput: document.querySelector("#searchInput"),
  viewSelector: document.querySelector("#viewSelector"),
  viewSelectorToggle: document.querySelector("#viewSelectorToggle"),
  currentViewLabel: document.querySelector("#currentViewLabel"),
  viewSelectorOptions: document.querySelector("#viewSelectorOptions"),
  navTabs: document.querySelectorAll(".nav-tab"),
  btnNewBoard: document.querySelector("#btnNewBoard"),
  btnCloneBoard: document.querySelector("#btnCloneBoard"),
  btnExportBoard: document.querySelector("#btnExportBoard"),
  btnImportBoard: document.querySelector("#btnImportBoard"),
  btnMilestoneArchives: document.querySelector("#btnMilestoneArchives"),

  dashboardView: document.querySelector("#dashboardView"),
  chartsView: document.querySelector("#chartsView"),
  boardView: document.querySelector("#boardView"),
  guideView: document.querySelector("#guideView"),
  guideContent: document.querySelector("#guideContent"),
  dashboardPhase: document.querySelector("#dashboardPhase"),
  dashboardBurndown: document.querySelector("#dashboardBurndown"),
  dashboardBlockers: document.querySelector("#dashboardBlockers"),
  dashboardMetrics: document.querySelector("#dashboardMetrics"),
  dashboardGitLog: document.querySelector("#dashboardGitLog"),
  docDialog: document.querySelector("#docDialog"),
  docDialogTitle: document.querySelector("#docDialogTitle"),
  docDialogContent: document.querySelector("#docDialogContent"),
  chartsList: document.querySelector("#chartsList"),
  chartsListEmpty: document.querySelector("#chartsListEmpty"),
  chartsPanel: document.querySelector("#chartsPanel"),
  chartsPanelTitle: document.querySelector("#chartsPanelTitle"),
  chartsPanelContent: document.querySelector("#chartsPanelContent"),
  btnCloseChartsPanel: document.querySelector("#btnCloseChartsPanel"),
  btnDeleteChart: document.querySelector("#btnDeleteChart"),

  importFile: document.querySelector("#importFile"),
  btnSaveBoard: document.querySelector("#btnSaveBoard"),
  btnDeleteBoard: document.querySelector("#btnDeleteBoard"),
  btnAddCard: document.querySelector("#btnAddCard"),
  btnAddMilestone: document.querySelector("#btnAddMilestone"),
  btnAddList: document.querySelector("#btnAddList"),
  cardDialog: document.querySelector("#cardDialog"),
  cardDialogTitle: document.querySelector("#cardDialogTitle"),
  cardDialogIssueNumber: document.querySelector("#cardDialogIssueNumber"),
  cardForm: document.querySelector("#cardForm"),
  cardId: document.querySelector("#cardId"),
  cardTitle: document.querySelector("#cardTitle"),
  cardMilestone: document.querySelector("#cardMilestone"),
  cardPriority: document.querySelector("#cardPriority"),
  cardList: document.querySelector("#cardList"),
  cardTargetDate: document.querySelector("#cardTargetDate"),
  cardOwner: document.querySelector("#cardOwner"),
  cardKind: document.querySelector("#cardKind"),
  cardDescription: document.querySelector("#cardDescription"),
  cardAcceptance: document.querySelector("#cardAcceptance"),
  btnDeleteCard: document.querySelector("#btnDeleteCard"),
  btnCancelCard: document.querySelector("#btnCancelCard"),
  cardTemplate: document.querySelector("#cardTemplate"),
  milestoneDetailPanel: document.querySelector("#milestoneDetailPanel"),
  milestoneDetailContent: document.querySelector("#milestoneDetailContent"),
  milestonePanelTitle: document.querySelector("#milestonePanelTitle"),
  btnMilestonePanelClose: document.querySelector("#btnMilestonePanelClose"),
  btnMilestonePanelBack: document.querySelector("#btnMilestonePanelBack"),
  whyMcdDialog: document.querySelector("#whyMcdDialog"),
  attributionDialog: document.querySelector("#attributionDialog"),
  milestoneArchivesDialog: document.querySelector("#milestoneArchivesDialog"),
  milestoneArchivesList: document.querySelector("#milestoneArchivesList"),
  milestoneArchivesEmpty: document.querySelector("#milestoneArchivesEmpty"),
  btnWhyMcd: document.querySelector("#btnWhyMcd"),
  btnAttributionInfo: document.querySelector("#btnAttributionInfo"),
  themeCheckbox: document.querySelector("#themeCheckbox"),
  btnToggleSidebar: document.querySelector("#btnToggleSidebar"),
};

async function api(path, method = "GET", body = null) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });

  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    const reason = payload.error || `Request failed: ${response.status}`;
    throw new Error(reason);
  }
  return payload;
}

function getCurrentTheme() {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

function normalizeFilters(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    milestoneId: String(source.milestoneId || "").trim(),
    search: String(source.search || ""),
  };
}

function readBoardFilterStore() {
  try {
    const raw = localStorage.getItem(FILTERS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (error) {
    return {};
  }
}

function writeBoardFilterStore(store) {
  try {
    localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(store));
  } catch (error) {
    // Ignore storage write failures and continue with in-memory filters.
  }
}

function restoreFiltersForActiveBoard() {
  const boardId = String(state.data?.activeBoardId || "").trim();
  if (!boardId) {
    state.filters.milestoneId = "";
    state.filters.search = "";
    return;
  }

  const store = readBoardFilterStore();
  const saved = normalizeFilters(store[boardId]);
  state.filters.milestoneId = saved.milestoneId;
  state.filters.search = saved.search;
}

function persistFiltersForActiveBoard() {
  const boardId = String(state.data?.activeBoardId || "").trim();
  if (!boardId) return;

  const store = readBoardFilterStore();
  const next = normalizeFilters(state.filters);

  if (!next.milestoneId && !next.search) {
    delete store[boardId];
  } else {
    store[boardId] = next;
  }

  writeBoardFilterStore(store);
}

function syncFilterInputs() {
  if (el.milestoneFilter && el.milestoneFilter.value !== state.filters.milestoneId) {
    el.milestoneFilter.value = state.filters.milestoneId;
  }
  if (el.searchInput && el.searchInput.value !== state.filters.search) {
    el.searchInput.value = state.filters.search;
  }
}

function configureMermaidTheme() {
  if (!window.mermaid) return;
  const isLight = getCurrentTheme() === "light";
  window.mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    themeVariables: isLight
      ? {
        background: "#ffffff",
        primaryTextColor: "#0f172a",
        secondaryTextColor: "#334155",
        lineColor: "#475569",
        primaryColor: "#f8fafc",
        primaryBorderColor: "#94a3b8",
        clusterBorder: "#94a3b8",
      }
      : {
        background: "#0f2131",
        primaryTextColor: "#e9f5ff",
        secondaryTextColor: "#c5deef",
        lineColor: "#8bb4cf",
        primaryColor: "#13283a",
        primaryBorderColor: "#5a7d97",
        clusterBorder: "#5a7d97",
      },
  });
}

const MERMAID_VIEWPORT_CLASS = "mcd-mermaid-viewport";
const MERMAID_CONTROLS_CLASS = "mcd-mermaid-controls";
const MERMAID_DEFAULT_SCALE = 0.25;
const MERMAID_MIN_SCALE = 0.08;
const MERMAID_MAX_SCALE = 3;
const MERMAID_BUTTON_ZOOM_FACTOR = 1.18;
const MERMAID_WHEEL_SENSITIVITY = 0.0014;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function applyMermaidTransform(controller) {
  const svg = controller.svg;
  if (!svg || !svg.isConnected) return;
  svg.style.transformOrigin = "0 0";
  svg.style.transform = `translate(${controller.tx}px, ${controller.ty}px) scale(${controller.scale})`;
}

function mermaidZoomAtPoint(controller, host, x, y, nextScale) {
  const targetScale = clamp(nextScale, MERMAID_MIN_SCALE, MERMAID_MAX_SCALE);
  if (Math.abs(targetScale - controller.scale) < 0.0001) return;
  const localX = (x - controller.tx) / controller.scale;
  const localY = (y - controller.ty) / controller.scale;
  controller.scale = targetScale;
  controller.tx = x - localX * targetScale;
  controller.ty = y - localY * targetScale;
  applyMermaidTransform(controller);
  host.dataset.mcdScale = targetScale.toFixed(2);
}

const MERMAID_FIT_PADDING = 0.92;

function fitMermaidToViewport(controller, host) {
  const svg = controller.svg;
  if (!svg || !svg.isConnected) {
    controller.scale = MERMAID_DEFAULT_SCALE;
    controller.tx = 0;
    controller.ty = 0;
    applyMermaidTransform(controller);
    host.dataset.mcdScale = controller.scale.toFixed(2);
    return;
  }

  // Read SVG natural size from viewBox (most reliable post-render)
  let svgW = 0;
  let svgH = 0;
  const vb = svg.getAttribute("viewBox");
  if (vb) {
    const parts = vb.trim().split(/[\s,]+/);
    if (parts.length >= 4) {
      svgW = parseFloat(parts[2]) || 0;
      svgH = parseFloat(parts[3]) || 0;
    }
  }
  // Fallback: read rendered bounding rect at natural scale
  if (!svgW || !svgH) {
    const saved = svg.style.transform;
    svg.style.transform = "none";
    const rect = svg.getBoundingClientRect();
    svg.style.transform = saved;
    svgW = rect.width || 0;
    svgH = rect.height || 0;
  }

  const hostRect = host.getBoundingClientRect();
  const hostW = hostRect.width || 0;
  const hostH = hostRect.height || 0;

  if (!svgW || !svgH || !hostW || !hostH) {
    controller.scale = MERMAID_DEFAULT_SCALE;
    controller.tx = 0;
    controller.ty = 0;
    applyMermaidTransform(controller);
    host.dataset.mcdScale = controller.scale.toFixed(2);
    return;
  }

  const scale = clamp(
    Math.min(hostW / svgW, hostH / svgH) * MERMAID_FIT_PADDING,
    MERMAID_MIN_SCALE,
    MERMAID_MAX_SCALE
  );
  controller.scale = scale;
  controller.tx = (hostW - svgW * scale) / 2;
  controller.ty = (hostH - svgH * scale) / 2;
  applyMermaidTransform(controller);
  host.dataset.mcdScale = scale.toFixed(2);
}

function resetMermaidTransform(controller, host) {
  fitMermaidToViewport(controller, host);
}

function ensureMermaidControls(host, controller) {
  let controls = host.querySelector(`:scope > .${MERMAID_CONTROLS_CLASS}`);
  if (controls) return;

  controls = document.createElement("div");
  controls.className = MERMAID_CONTROLS_CLASS;
  controls.innerHTML = `
    <button type="button" data-mermaid-control="zoom-out" aria-label="Zoom out">-</button>
    <button type="button" data-mermaid-control="reset" aria-label="Reset zoom">Reset</button>
    <button type="button" data-mermaid-control="zoom-in" aria-label="Zoom in">+</button>
  `;

  controls.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-mermaid-control]");
    if (!button || !controller.svg || !controller.svg.isConnected) return;
    const rect = host.getBoundingClientRect();
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const action = button.dataset.mermaidControl;

    if (action === "zoom-in") {
      mermaidZoomAtPoint(controller, host, centerX, centerY, controller.scale * MERMAID_BUTTON_ZOOM_FACTOR);
      return;
    }
    if (action === "zoom-out") {
      mermaidZoomAtPoint(controller, host, centerX, centerY, controller.scale / MERMAID_BUTTON_ZOOM_FACTOR);
      return;
    }
    resetMermaidTransform(controller, host);
  });

  host.appendChild(controls);
}

function bindMermaidInteractions(host, controller) {
  const state = {
    pointerId: null,
    startX: 0,
    startY: 0,
    startTx: 0,
    startTy: 0,
  };

  host.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    if (event.target.closest(`.${MERMAID_CONTROLS_CLASS}`)) return;
    if (!controller.svg || !controller.svg.isConnected) return;
    state.pointerId = event.pointerId;
    state.startX = event.clientX;
    state.startY = event.clientY;
    state.startTx = controller.tx;
    state.startTy = controller.ty;
    host.classList.add("is-panning");
    if (host.setPointerCapture) host.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  host.addEventListener("pointermove", (event) => {
    if (state.pointerId === null || event.pointerId !== state.pointerId) return;
    controller.tx = state.startTx + (event.clientX - state.startX);
    controller.ty = state.startTy + (event.clientY - state.startY);
    applyMermaidTransform(controller);
  });

  const endPan = (event) => {
    if (state.pointerId === null || event.pointerId !== state.pointerId) return;
    if (host.hasPointerCapture && host.hasPointerCapture(event.pointerId)) {
      host.releasePointerCapture(event.pointerId);
    }
    state.pointerId = null;
    host.classList.remove("is-panning");
  };

  host.addEventListener("pointerup", endPan);
  host.addEventListener("pointercancel", endPan);
  host.addEventListener("lostpointercapture", () => {
    state.pointerId = null;
    host.classList.remove("is-panning");
  });

  host.addEventListener(
    "wheel",
    (event) => {
      if (event.target.closest(`.${MERMAID_CONTROLS_CLASS}`)) return;
      if (!controller.svg || !controller.svg.isConnected) return;
      const rect = host.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const zoomFactor = Math.exp(-event.deltaY * MERMAID_WHEEL_SENSITIVITY);
      mermaidZoomAtPoint(controller, host, x, y, controller.scale * zoomFactor);
      event.preventDefault();
    },
    { passive: false }
  );
}

function attachMermaidPanZoom(container) {
  if (!container) return;
  const svgNodes = container.querySelectorAll(".language-mermaid svg, .mermaid svg, svg[id^='mermaid-']");
  svgNodes.forEach((svg) => {
    const host = svg.closest(".language-mermaid, .mermaid") || svg.parentElement;
    if (!host) return;
    host.classList.add(MERMAID_VIEWPORT_CLASS);

    if (host.__mcdMermaidController) {
      host.__mcdMermaidController.svg = svg;
      fitMermaidToViewport(host.__mcdMermaidController, host);
      return;
    }

    const controller = {
      svg,
      scale: MERMAID_DEFAULT_SCALE,
      tx: 0,
      ty: 0,
    };
    host.__mcdMermaidController = controller;
    ensureMermaidControls(host, controller);
    bindMermaidInteractions(host, controller);
    fitMermaidToViewport(controller, host);
  });
}

function scheduleMermaidPanZoomAttach(container) {
  if (!container) return;
  requestAnimationFrame(() => attachMermaidPanZoom(container));
}

function renderMermaidBlocks(container) {
  if (!window.mermaid || !container) return;
  // Support both .language-mermaid (standard) and .mermaid (legacy/custom)
  const nodes = container.querySelectorAll(".language-mermaid, .mermaid, pre.mermaid");
  if (!nodes.length) return;

  try {
    configureMermaidTheme();
    nodes.forEach((node) => node.removeAttribute("data-processed"));
    const attachInteractions = () => scheduleMermaidPanZoomAttach(container);

    if (typeof window.mermaid.run === "function") {
      const renderPromise = window.mermaid.run({ nodes });
      if (renderPromise && typeof renderPromise.then === "function") {
        renderPromise.then(attachInteractions).catch((error) => {
          console.warn("Mermaid render failed:", error);
        });
      } else {
        attachInteractions();
      }
    } else if (typeof window.mermaid.init === "function") {
      window.mermaid.init(undefined, nodes);
      attachInteractions();
    }
  } catch (err) {
    console.error("Critical error in Mermaid rendering:", err);
  }
}

function loadChartsFromState() {
  const raw = state.data && Array.isArray(state.data.charts) ? state.data.charts : [];
  state.charts = raw
    .filter((item) => item && typeof item.id === "string" && typeof item.title === "string")
    .map((item) => ({
      id: item.id,
      title: item.title,
      description: item.description || "",
      markdown: item.markdown || "",
    }));
}

function setChartsPanelOpen(isOpen) {
  if (!el.chartsPanel) return;
  el.chartsPanel.classList.toggle("is-open", isOpen);
}

function renderChartsPreview() {
  const selected = state.charts.find((item) => item.id === state.selectedChartId) || null;
  if (!selected) {
    if (el.chartsPanelTitle) el.chartsPanelTitle.textContent = "Chart Preview";
    if (el.chartsPanelContent) {
      el.chartsPanelContent.innerHTML = "Select a chart from the left to preview it.";
    }
    setChartsPanelOpen(false);
    return;
  }

  if (el.chartsPanelTitle) el.chartsPanelTitle.textContent = selected.title;
  if (el.chartsPanelContent) {
    if (window.marked && selected.markdown) {
      el.chartsPanelContent.innerHTML = window.marked.parse(selected.markdown);
      renderMermaidBlocks(el.chartsPanelContent);
    } else {
      const desc = selected.description || "No chart preview content available.";
      el.chartsPanelContent.textContent = desc;
    }
  }
  setChartsPanelOpen(true);
}

function renderCharts() {
  if (!el.chartsList || !el.chartsListEmpty) return;
  el.chartsList.innerHTML = "";

  if (!state.charts.length) {
    el.chartsListEmpty.style.display = "block";
    state.selectedChartId = "";
    renderChartsPreview();
    return;
  }

  el.chartsListEmpty.style.display = "none";
  for (const chart of state.charts) {
    const button = document.createElement("button");
    button.className = `chart-item ${chart.id === state.selectedChartId ? "active" : ""}`;
    button.type = "button";
    button.dataset.chartId = chart.id;
    button.innerHTML = `<strong>${chart.title}</strong><span>${chart.description || "Chart artifact"}</span>`;
    button.addEventListener("click", () => {
      state.selectedChartId = chart.id;
      renderCharts();
    });
    el.chartsList.appendChild(button);
  }

  renderChartsPreview();
}

function getActiveBoard() {
  if (!state.data) return null;
  return state.data.boards.find((item) => item.id === state.data.activeBoardId) || null;
}

function sorted(items) {
  return [...items].sort((a, b) => (a.order || 0) - (b.order || 0));
}

function getListKeyMap(board) {
  const map = new Map();
  board.lists.forEach((item) => map.set(item.id, item.key || ""));
  return map;
}

function boardSummary(board) {
  const description = String(board?.description || "").trim();
  if (description) {
    return description.length > 72 ? `${description.slice(0, 69)}...` : description;
  }
  const code = String(board?.codename || "").trim();
  return code ? `Code: ${code}` : "No description";
}

function isPreflightMilestone(milestone) {
  return String(milestone?.kind || "").toLowerCase() === "preflight";
}

function isArchivedMilestone(milestone) {
  return Boolean(String(milestone?.archivedAt || "").trim());
}

function isWriteClosedPreflight(milestone) {
  if (!milestone) return false;
  const accepts = Number(milestone.acceptsNewCards ?? 1);
  return isPreflightMilestone(milestone) && accepts !== 1;
}

function milestoneDisplayTitle(milestone) {
  if (!milestone) return "Unassigned";
  const displayName = milestoneDisplayName(milestone);
  if (isArchivedMilestone(milestone)) {
    return `${displayName} (Archived)`;
  }
  if (isWriteClosedPreflight(milestone)) {
    return `${displayName} (Closed)`;
  }
  return displayName;
}

function extractMilestoneCode(text) {
  const source = String(text || "").trim();
  if (!source) return "";
  const match = source.match(MILESTONE_CODE_PATTERN);
  return match ? String(match[1] || "").toUpperCase() : "";
}

function parseMilestoneTitleParts(text) {
  const source = String(text || "").trim();
  if (!source) return { code: "", title: "" };
  const split = source.match(MILESTONE_CODE_TITLE_PREFIX_PATTERN);
  if (split) {
    return {
      code: String(split[1] || "").toUpperCase(),
      title: String(split[2] || "").trim(),
    };
  }
  return {
    code: extractMilestoneCode(source),
    title: source,
  };
}

function milestoneDisplayName(milestone) {
  if (!milestone) return "Unassigned";
  const sourceTitle = String(milestone.title || "").trim();
  const explicitCode = extractMilestoneCode(String(milestone.code || ""));
  const parsed = parseMilestoneTitleParts(sourceTitle);

  if (parsed.title && parsed.code) {
    if (!explicitCode || explicitCode === parsed.code) {
      return parsed.title;
    }
  }
  return sourceTitle || "Untitled Milestone";
}

function milestoneDisplayIdentifier(milestone) {
  if (!milestone) return "";
  const code = extractMilestoneCode(String(milestone.code || ""));
  if (code) return code;
  const title = String(milestone.title || "").trim();
  return extractMilestoneCode(title);
}

function getActiveMilestones(board) {
  return sorted(board.milestones).filter((milestone) => !isArchivedMilestone(milestone));
}

function getArchivedMilestones(board) {
  return sorted(board.milestones).filter((milestone) => isArchivedMilestone(milestone));
}

function getOpenMilestones(board) {
  return getActiveMilestones(board).filter((milestone) => !isWriteClosedPreflight(milestone));
}

function milestoneTitle(board, milestoneId) {
  const item = board.milestones.find((ms) => ms.id === milestoneId);
  return milestoneDisplayTitle(item);
}

function getListMeta(board, listId) {
  return board.lists.find((item) => item.id === listId) || null;
}

function getMilestoneMetaText(value, fallback) {
  const text = String(value || "").trim();
  return text || fallback;
}

function getTaskCompletionBucket(listKey) {
  const key = String(listKey || "").toLowerCase();
  if (key === "qa" || key === "done") return "complete";
  return "incomplete";
}

function getDismissibleDialogs() {
  return [
    el.cardDialog,
    el.docDialog,
    el.whyMcdDialog,
    el.attributionDialog,
    el.milestoneArchivesDialog,
  ].filter(Boolean);
}

function hasOpenDismissibleDialog() {
  return getDismissibleDialogs().some((dialog) => dialog.open);
}

function registerDialogBackdropDismiss(dialog) {
  if (!dialog) return;
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      dialog.close();
    }
  });
}

function mountMilestonePanelLayer() {
  if (!el.milestoneDetailPanel) return;
  if (el.milestoneDetailPanel.dataset.layerMounted === "1") return;
  document.body.appendChild(el.milestoneDetailPanel);
  el.milestoneDetailPanel.dataset.layerMounted = "1";
}

function openMilestonePanel(milestoneId) {
  if (!milestoneId) return;
  state.milestonePanel.open = true;
  state.milestonePanel.view = { type: "milestone", milestoneId };
  state.milestonePanel.history = [];
  renderMilestoneDetailPanel();
}

function openMilestoneTaskDetail(milestoneId, taskId) {
  if (!milestoneId || !taskId) return;
  if (state.milestonePanel.view) {
    state.milestonePanel.history.push({ ...state.milestonePanel.view });
  }
  state.milestonePanel.open = true;
  state.milestonePanel.view = { type: "task", milestoneId, taskId };
  renderMilestoneDetailPanel();
}

function openMilestoneArtifactDetail(milestoneId, artifactType) {
  if (!milestoneId || !artifactType) return;
  state.milestonePanel.history = [{ type: "milestone", milestoneId }];
  state.milestonePanel.open = true;
  state.milestonePanel.view = { type: "artifact", milestoneId, artifactType: String(artifactType).toLowerCase() };
  renderMilestoneDetailPanel();
}

function closeMilestonePanel() {
  state.milestonePanel.open = false;
  state.milestonePanel.view = null;
  state.milestonePanel.history = [];
  renderMilestoneDetailPanel();
}

function milestonePanelBack() {
  if (!state.milestonePanel.history.length) return;
  const previous = state.milestonePanel.history.pop();
  state.milestonePanel.view = previous;
  renderMilestoneDetailPanel();
}

function buildDetailSection(title, text) {
  const section = document.createElement("section");
  section.className = "milestone-detail-section";

  const heading = document.createElement("h4");
  heading.textContent = title;
  section.appendChild(heading);

  const body = document.createElement("p");
  body.className = "milestone-detail-text";
  body.textContent = text;
  section.appendChild(body);

  return section;
}

function buildMilestoneArtifactActionRow() {
  const row = document.createElement("div");
  row.className = "milestone-artifact-actions";

  const actions = [
    { key: "findings", label: "Findings" },
    { key: "outcomes", label: "Outcomes" },
  ];

  for (const action of actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-sm milestone-artifact-action-btn";
    button.dataset.artifactType = action.key;
    button.setAttribute("aria-label", `Open ${action.label}`);
    button.textContent = action.label;
    row.appendChild(button);
  }

  return row;
}

async function fetchLatestMilestoneArtifact(milestoneId, artifactType) {
  const safeMilestoneId = String(milestoneId || "").trim();
  const safeType = String(artifactType || "").trim().toLowerCase();
  if (!safeMilestoneId || !safeType) {
    throw new Error("milestoneId and artifactType are required");
  }
  await assertCanonicalRuntime();
  const query = new URLSearchParams({ artifactType: safeType });
  const response = await fetch(`/api/milestones/${encodeURIComponent(safeMilestoneId)}/artifacts/latest?${query.toString()}`, {
    method: "GET",
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    const parseError = new Error(`Invalid JSON response from Command Deck API (${response.status}).`);
    parseError.status = response.status;
    throw parseError;
  }
  if (!response.ok || !payload.ok) {
    const reason = payload.error || `Request failed: ${response.status}`;
    const error = new Error(reason);
    error.status = response.status;
    throw error;
  }
  return payload.artifact;
}

async function assertCanonicalRuntime() {
  if (!runtimeValidationPromise) {
    runtimeValidationPromise = (async () => {
      const response = await fetch("/api/health", { method: "GET" });
      let payload = null;
      try {
        payload = await response.json();
      } catch (error) {
        const parseError = new Error(`Invalid health response from Command Deck API (${response.status}).`);
        parseError.status = response.status;
        throw parseError;
      }
      if (!response.ok || !payload || payload.ok !== true) {
        const reason = payload?.error || `Health check failed: ${response.status}`;
        const healthError = new Error(reason);
        healthError.status = response.status;
        throw healthError;
      }

      const runtime = payload.runtime || {};
      const explicit = String(runtime.fingerprint || "").trim();
      const computed = [runtime.server, runtime.implementation, runtime.datastore]
        .map((value) => String(value || "").trim())
        .join(":");
      const observed = explicit || computed;
      if (observed !== EXPECTED_RUNTIME_FINGERPRINT) {
        const mismatch = new Error(
          `Non-canonical Command Deck runtime detected (${observed || "unknown"}). Expected ${EXPECTED_RUNTIME_FINGERPRINT}.`
        );
        mismatch.status = 409;
        throw mismatch;
      }
      return true;
    })().catch((error) => {
      runtimeValidationPromise = null;
      throw error;
    });
  }
  return runtimeValidationPromise;
}

function renderArtifactPlaceholderView(artifactType) {
  const normalized = String(artifactType || "").toLowerCase();
  const title = normalized === "outcomes" ? "Outcomes" : "Findings";
  const message = normalized === "outcomes"
    ? "Outcomes are recorded during milestone closeout. No closeout artifact is available yet."
    : "No findings artifact is recorded for this milestone yet.";

  const container = document.createElement("div");
  container.className = "milestone-artifact-detail-view";
  container.appendChild(buildDetailSection(title, message));
  return container;
}

function renderArtifactErrorView(artifactType, errorMessage) {
  const normalized = String(artifactType || "").toLowerCase();
  const title = normalized === "outcomes" ? "Outcomes" : "Findings";
  const container = document.createElement("div");
  container.className = "milestone-artifact-detail-view";
  const message = String(errorMessage || "").trim() || "Unable to load artifact.";
  container.appendChild(buildDetailSection(title, `Unable to load artifact.\n${message}`));
  return container;
}

function renderArtifactDetailView(artifact, artifactType) {
  if (!artifact || typeof artifact !== "object") {
    return renderArtifactPlaceholderView(artifactType);
  }

  const normalized = String(artifactType || "").toLowerCase();
  const fallbackTitle = normalized === "outcomes" ? "Outcomes" : "Findings";
  const container = document.createElement("div");
  container.className = "milestone-artifact-detail-view";

  container.appendChild(buildDetailSection("Type", fallbackTitle));
  container.appendChild(buildDetailSection("Revision", String(artifact.revision || "1")));
  container.appendChild(buildDetailSection("Title", getMilestoneMetaText(artifact.title, `Untitled ${fallbackTitle}`)));
  container.appendChild(buildDetailSection("Summary", getMilestoneMetaText(artifact.summary, "No summary provided.")));
  container.appendChild(buildDetailSection("Body", getMilestoneMetaText(artifact.body, "No body provided.")));

  const provenance = [
    artifact.sourceCardId ? `Card: ${artifact.sourceCardId}` : "",
    artifact.sourceEventId ? `Event: ${artifact.sourceEventId}` : "",
    artifact.updatedAt ? `Updated: ${artifact.updatedAt}` : "",
  ]
    .filter(Boolean)
    .join("\n");
  container.appendChild(buildDetailSection("Provenance", provenance || "No provenance recorded."));

  return container;
}

function renderMilestoneTaskList(board, milestoneId, title, cards) {
  const wrapper = document.createElement("section");
  wrapper.className = "milestone-task-group";

  const heading = document.createElement("h4");
  heading.className = "milestone-task-group-title";
  heading.textContent = title;
  wrapper.appendChild(heading);

  if (!cards.length) {
    const empty = document.createElement("div");
    empty.className = "milestone-detail-empty";
    empty.textContent = "No tasks in this section.";
    wrapper.appendChild(empty);
    return wrapper;
  }

  const list = document.createElement("div");
  list.className = "milestone-task-list";

  for (const card of cards) {
    const listMeta = getListMeta(board, card.listId);
    const statusTitle = listMeta?.title || "Unknown Status";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "milestone-task-link";

    const taskTitle = document.createElement("strong");
    taskTitle.textContent = `${card.issueNumber || "—"} · ${card.title}`;
    button.appendChild(taskTitle);

    const taskMeta = document.createElement("span");
    taskMeta.textContent = `${statusTitle} · ${card.priority || "P2"}`;
    button.appendChild(taskMeta);

    button.addEventListener("click", () => openMilestoneTaskDetail(milestoneId, card.id));
    list.appendChild(button);
  }

  wrapper.appendChild(list);
  return wrapper;
}

function renderMilestoneView(board, milestone) {
  const container = document.createElement("div");
  container.className = "milestone-detail-view";
  container.appendChild(buildDetailSection("Meta Contract", getMilestoneMetaText(milestone.metaContract, "No meta contract recorded yet.")));
  container.appendChild(buildDetailSection("Goals", getMilestoneMetaText(milestone.goals, "No goals recorded yet.")));
  container.appendChild(buildDetailSection("Non-Goals", getMilestoneMetaText(milestone.nonGoals, "No non-goals recorded yet.")));
  container.appendChild(buildDetailSection("Risks", getMilestoneMetaText(milestone.risks, "No risks recorded yet.")));

  const milestoneCards = sorted(board.cards.filter((card) => card.milestoneId === milestone.id));
  const grouped = { incomplete: [], complete: [] };
  for (const card of milestoneCards) {
    const listMeta = getListMeta(board, card.listId);
    const bucket = getTaskCompletionBucket(listMeta?.key);
    grouped[bucket].push(card);
  }

  container.appendChild(renderMilestoneTaskList(board, milestone.id, "Incomplete", grouped.incomplete));
  container.appendChild(renderMilestoneTaskList(board, milestone.id, "Complete", grouped.complete));
  return container;
}

function renderTaskDetailView(board, milestone, card) {
  const container = document.createElement("div");
  container.className = "milestone-task-detail-view";
  const listMeta = getListMeta(board, card.listId);

  const detailGrid = document.createElement("div");
  detailGrid.className = "task-detail-grid";
  detailGrid.appendChild(buildDetailSection("Issue", card.issueNumber || "—"));
  detailGrid.appendChild(buildDetailSection("Status", listMeta?.title || "Unknown"));
  detailGrid.appendChild(buildDetailSection("Priority", card.priority || "P2"));
  detailGrid.appendChild(buildDetailSection("Milestone", milestoneDisplayTitle(milestone)));
  detailGrid.appendChild(buildDetailSection("Owner", card.owner ? `@${card.owner}` : "Unassigned"));
  detailGrid.appendChild(buildDetailSection("Target Date", card.targetDate || "Not set"));
  container.appendChild(detailGrid);
  container.appendChild(buildDetailSection("Description", getMilestoneMetaText(card.description, "No description provided.")));
  container.appendChild(buildDetailSection("Acceptance", getMilestoneMetaText(card.acceptance, "No acceptance criteria provided.")));
  return container;
}

async function renderMilestoneDetailPanel() {
  const board = getActiveBoard();
  if (!board || !el.milestoneDetailPanel || !el.milestoneDetailContent || !el.milestonePanelTitle || !el.btnMilestonePanelBack) return;

  const view = state.milestonePanel.view;
  const canRender = state.milestonePanel.open && view && view.milestoneId;
  if (!canRender) {
    el.milestoneDetailPanel.classList.remove("is-open");
    el.boardView.classList.remove("panel-open");
    el.milestonePanelTitle.textContent = "Milestone Details";
    el.milestoneDetailContent.textContent = "Select a milestone to inspect its contract details and tasks.";
    el.btnMilestonePanelBack.style.visibility = "hidden";
    return;
  }

  const milestone = board.milestones.find((item) => item.id === view.milestoneId);
  if (!milestone) {
    closeMilestonePanel();
    return;
  }

  el.milestoneDetailPanel.classList.add("is-open");
  el.boardView.classList.add("panel-open");
  el.btnMilestonePanelBack.style.visibility = state.milestonePanel.history.length ? "visible" : "hidden";
  el.milestonePanelTitle.textContent = milestoneDisplayTitle(milestone);
  el.milestoneDetailContent.innerHTML = "";
  const artifactActions = buildMilestoneArtifactActionRow();
  artifactActions.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const button = target.closest(".milestone-artifact-action-btn");
    if (!(button instanceof HTMLButtonElement)) return;
    const artifactType = String(button.dataset.artifactType || "").trim().toLowerCase();
    if (!artifactType) return;
    openMilestoneArtifactDetail(milestone.id, artifactType);
  });
  el.milestoneDetailContent.appendChild(artifactActions);

  const detailBody = document.createElement("div");
  detailBody.className = "milestone-detail-body";
  el.milestoneDetailContent.appendChild(detailBody);

  if (view.type === "artifact" && view.artifactType) {
    const artifactType = String(view.artifactType || "").toLowerCase();
    const heading = artifactType === "outcomes" ? "Outcomes" : "Findings";
    el.milestonePanelTitle.textContent = `${milestoneDisplayTitle(milestone)} · ${heading}`;
    try {
      const artifact = await fetchLatestMilestoneArtifact(milestone.id, artifactType);
      const latestView = state.milestonePanel.view;
      if (!latestView || latestView.type !== "artifact" || latestView.milestoneId !== milestone.id || latestView.artifactType !== artifactType) {
        return;
      }
      detailBody.innerHTML = "";
      detailBody.appendChild(renderArtifactDetailView(artifact, artifactType));
    } catch (error) {
      const latestView = state.milestonePanel.view;
      if (!latestView || latestView.type !== "artifact" || latestView.milestoneId !== milestone.id || latestView.artifactType !== artifactType) {
        return;
      }
      detailBody.innerHTML = "";
      const reason = String(error?.message || "").toLowerCase();
      const isArtifactMissing = error && Number(error.status) === 404 && reason.includes("artifact not found");
      if (isArtifactMissing) {
        detailBody.appendChild(renderArtifactPlaceholderView(artifactType));
      } else {
        detailBody.appendChild(renderArtifactErrorView(artifactType, error?.message));
      }
    }
    return;
  }

  if (view.type === "task" && view.taskId) {
    const task = board.cards.find((item) => item.id === view.taskId && item.milestoneId === milestone.id);
    if (!task) {
      milestonePanelBack();
      return;
    }
    el.milestonePanelTitle.textContent = `${task.issueNumber || "—"} · ${task.title}`;
    detailBody.appendChild(renderTaskDetailView(board, milestone, task));
    return;
  }

  detailBody.appendChild(renderMilestoneView(board, milestone));
}

function formatDate(value) {
  if (!value) return "";
  return value;
}

function priorityClass(priority) {
  return `priority-${String(priority || "P2").toLowerCase()}`;
}

function cardMatchesFilter(board, card) {
  if (state.filters.milestoneId && card.milestoneId !== state.filters.milestoneId) {
    return false;
  }

  // Hide completed tasks (done/qa) whose milestone is archived from the main board view.
  const milestone = board.milestones.find((m) => m.id === card.milestoneId);
  if (milestone && isArchivedMilestone(milestone)) {
    const listMeta = getListMeta(board, card.listId);
    const bucket = getTaskCompletionBucket(listMeta?.key);
    if (bucket === "complete") return false;
  }

  const query = state.filters.search.trim().toLowerCase();
  if (!query) return true;

  const haystack = [
    card.title,
    card.description,
    card.acceptance,
    card.owner,
    milestoneTitle(board, card.milestoneId),
  ]
    .join(" ")
    .toLowerCase();

  return haystack.includes(query);
}

function renderKanbanList() {
  const activeBoard = getActiveBoard();
  if (el.boardsSummaryActive) {
    el.boardsSummaryActive.textContent = activeBoard?.name || "No active board";
  }
  if (!el.boardsList) return;
  el.boardsList.innerHTML = "";

  if (!state.data.boards.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No boards available.";
    el.boardsList.appendChild(empty);
    return;
  }

  for (const board of state.data.boards) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "board-item";
    if (activeBoard && board.id === activeBoard.id) {
      button.classList.add("active");
    }

    const title = document.createElement("strong");
    title.textContent = board.name || "Untitled board";

    const description = document.createElement("span");
    description.className = "board-item-desc";
    description.textContent = boardSummary(board);

    button.appendChild(title);
    button.appendChild(description);
    button.addEventListener("click", async () => {
      if (board.id === state.data?.activeBoardId) return;
      await api(`/api/boards/${board.id}/activate`, "POST", {});
      await refresh();
    });
    el.boardsList.appendChild(button);
  }
}

function renderKanbanMeta() {
  const board = getActiveBoard();
  if (!board) return;
  el.boardName.value = board.name;
  el.boardDescription.value = board.description || "";
}

function renderMilestoneFilter() {
  const board = getActiveBoard();
  if (!board) return;
  const activeMilestones = getActiveMilestones(board);

  if (state.filters.milestoneId && !activeMilestones.some((milestone) => milestone.id === state.filters.milestoneId)) {
    state.filters.milestoneId = "";
    persistFiltersForActiveBoard();
  }

  el.milestoneFilter.innerHTML = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All";
  el.milestoneFilter.appendChild(all);

  for (const milestone of activeMilestones) {
    const option = document.createElement("option");
    option.value = milestone.id;
    option.textContent = milestoneDisplayTitle(milestone);
    if (state.filters.milestoneId === milestone.id) {
      option.selected = true;
    }
    el.milestoneFilter.appendChild(option);
  }

  syncFilterInputs();
}

function renderMilestonePolicyHint(board) {
  if (!el.milestonePolicyHint) return;
  el.milestonePolicyHint.classList.remove("warning");

  const activeMilestones = getActiveMilestones(board);
  if (!activeMilestones.length) {
    el.milestonePolicyHint.textContent = "No active milestones exist yet. Add a milestone before creating new tasks.";
    el.milestonePolicyHint.classList.add("warning");
    return;
  }

  const openMilestones = activeMilestones.filter((milestone) => !isWriteClosedPreflight(milestone));
  if (!openMilestones.length) {
    el.milestonePolicyHint.textContent = "All milestones are write-closed. Add a new milestone to start new work.";
    el.milestonePolicyHint.classList.add("warning");
    return;
  }

  el.milestonePolicyHint.textContent = "New work must be attached to an active milestone. Continue in an existing milestone or add a new milestone.";
}

function renderMilestoneProgress() {
  const board = getActiveBoard();
  if (!board) return;
  const activeMilestones = getActiveMilestones(board);

  const listKeyMap = getListKeyMap(board);
  const doneListIds = board.lists.filter((item) => item.key === "done").map((item) => item.id);

  el.milestoneProgress.innerHTML = "";

  if (!activeMilestones.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No active milestones yet. Add one from the Milestone panel.";
    el.milestoneProgress.appendChild(empty);
    return;
  }

  for (const milestone of activeMilestones) {
    const cards = board.cards.filter((card) => card.milestoneId === milestone.id);
    const done = cards.filter((card) => doneListIds.includes(card.listId)).length;
    const total = cards.length || 0;
    const ratio = total === 0 ? 0 : Math.round((done / total) * 100);
    const writeClosed = isWriteClosedPreflight(milestone);
    const readyToClose = total > 0 && done === total;

    const wrapper = document.createElement("div");
    wrapper.className = "milestone-item";
    wrapper.tabIndex = 0;
    if (writeClosed) {
      wrapper.classList.add("is-write-closed");
    }
    if (readyToClose) {
      wrapper.classList.add("is-ready-to-close");
    }
    wrapper.addEventListener("click", () => openMilestonePanel(milestone.id));
    wrapper.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openMilestonePanel(milestone.id);
      }
    });

    const name = document.createElement("div");
    name.className = "milestone-title-row";
    name.textContent = milestoneDisplayTitle(milestone);

    const utilityRow = document.createElement("div");
    utilityRow.className = "milestone-utility-row";

    const score = document.createElement("span");
    score.className = "milestone-score";
    score.textContent = `${done}/${total}`;
    utilityRow.appendChild(score);

    const canArchive = total > 0 && done === total;
    const archiveButton = document.createElement("button");
    archiveButton.className = "btn btn-sm milestone-archive-btn";
    archiveButton.textContent = "Archive";

    archiveButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      event.preventDefault();

      if (!canArchive) {
        await showPrompt("alert", "Error", `Cannot archive: All tasks must be complete (${total - done}/${total} remaining).`);
        return;
      }
      const warning = `Archive milestone "${milestone.title}"? It will be hidden from active work until restored.`;
      if (!(await showPrompt("confirm", "Confirm Archive", warning))) return;
      try {
        await api(`/api/milestones/${milestone.id}`, "DELETE");
        if (state.filters.milestoneId === milestone.id) {
          state.filters.milestoneId = "";
        }
        if (state.milestonePanel.view?.milestoneId === milestone.id) {
          closeMilestonePanel();
        }
        await refresh();
      } catch (error) {
        await showPrompt("alert", "Error", error.message);
      }
    });
    utilityRow.appendChild(archiveButton);

    const disposition = document.createElement("div");
    disposition.className = "milestone-disposition";
    disposition.textContent = readyToClose ? "Ready to Close" : "Accepting Work";
    if (readyToClose) {
      disposition.classList.add("is-ready-to-close");
    }

    const track = document.createElement("div");
    track.className = "progress-track";
    const fill = document.createElement("div");
    fill.className = "progress-fill";
    fill.style.width = `${ratio}%`;
    track.appendChild(fill);

    const milestoneIdentifier = document.createElement("div");
    milestoneIdentifier.className = "milestone-identifier";
    milestoneIdentifier.textContent = milestoneDisplayIdentifier(milestone) || "—";

    wrapper.appendChild(name);
    wrapper.appendChild(utilityRow);
    wrapper.appendChild(disposition);
    wrapper.appendChild(track);
    wrapper.appendChild(milestoneIdentifier);
    el.milestoneProgress.appendChild(wrapper);
  }
}

function formatArchiveTimestamp(value) {
  const raw = String(value || "").trim();
  if (!raw) return "Unknown";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleString();
}

function renderMilestoneArchives() {
  const board = getActiveBoard();
  if (!board || !el.milestoneArchivesList || !el.milestoneArchivesEmpty) return;
  const archivedMilestones = getArchivedMilestones(board);

  el.milestoneArchivesList.innerHTML = "";
  if (!archivedMilestones.length) {
    el.milestoneArchivesEmpty.style.display = "block";
    return;
  }

  el.milestoneArchivesEmpty.style.display = "none";
  for (const milestone of archivedMilestones) {
    const row = document.createElement("div");
    row.className = "milestone-archive-item";

    const info = document.createElement("div");
    info.className = "milestone-archive-info";

    const title = document.createElement("strong");
    title.textContent = milestone.title;
    info.appendChild(title);

    const meta = document.createElement("span");
    meta.textContent = `Archived ${formatArchiveTimestamp(milestone.archivedAt)}`;
    info.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "milestone-archive-actions";

    const viewButton = document.createElement("button");
    viewButton.className = "btn btn-sm";
    viewButton.type = "button";
    viewButton.textContent = "View";
    viewButton.addEventListener("click", () => {
      if (el.milestoneArchivesDialog?.open) {
        el.milestoneArchivesDialog.close();
      }
      openMilestonePanel(milestone.id);
    });

    const restoreButton = document.createElement("button");
    restoreButton.className = "btn btn-sm";
    restoreButton.type = "button";
    restoreButton.textContent = "Restore";
    restoreButton.addEventListener("click", async () => {
      try {
        await api(`/api/milestones/${milestone.id}/restore`, "POST", {});
        await refresh();
        renderMilestoneArchives();
      } catch (error) {
        await showPrompt("alert", "Error", error.message);
      }
    });

    actions.appendChild(viewButton);
    actions.appendChild(restoreButton);

    row.appendChild(info);
    row.appendChild(actions);
    el.milestoneArchivesList.appendChild(row);
  }
}

function createCardNode(board, card) {
  const fragment = el.cardTemplate.content.cloneNode(true);
  const node = fragment.querySelector(".card");

  node.dataset.cardId = card.id;
  node.draggable = true;

  if (card.kind === "bug") {
    node.classList.add("card-kind-bug");
    const bugBadge = node.querySelector(".bug-badge");
    if (bugBadge) bugBadge.hidden = false;
  }

  const priority = node.querySelector(".priority-badge");
  priority.textContent = card.priority || "P2";
  priority.classList.add(priorityClass(card.priority));

  node.querySelector("h4").textContent = card.title;
  node.querySelector(".description").textContent = card.description || "No description";
  node.querySelector(".issue-badge").textContent = card.issueNumber || "—";
  node.querySelector(".owner").textContent = card.owner ? `@${card.owner}` : "";
  node.querySelector(".target-date").textContent = card.targetDate ? `Due ${formatDate(card.targetDate)}` : "";

  node.addEventListener("dragstart", (event) => {
    state.dragCardId = card.id;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.id);
  });

  node.addEventListener("click", () => {
    openCardDialog(card.id);
  });

  return fragment;
}

function renderColumns() {
  const board = getActiveBoard();
  if (!board) return;

  el.kanbanColumns.innerHTML = "";

  const orderedLists = sorted(board.lists);
  for (const list of orderedLists) {
    const column = document.createElement("section");
    column.className = "column";
    column.dataset.listId = list.id;

    const header = document.createElement("header");
    const title = document.createElement("h3");
    title.textContent = list.title;
    title.title = "Double-click to rename column";
    title.addEventListener("dblclick", async () => {
      const next = await showPrompt("prompt", "Rename Column", "", list.title);
      if (!next || !next.trim()) return;
      await api(`/api/lists/${list.id}`, "PATCH", { title: next.trim() });
      await refresh();
    });

    const count = document.createElement("span");
    const listCards = sorted(board.cards.filter((card) => card.listId === list.id));
    const visibleCards = listCards.filter((card) => cardMatchesFilter(board, card));
    count.textContent = `${visibleCards.length}`;

    header.appendChild(title);
    header.appendChild(count);

    const body = document.createElement("div");
    body.className = "column-body";
    body.dataset.listId = list.id;

    body.addEventListener("dragover", (event) => {
      event.preventDefault();
      body.classList.add("drag-target");
    });

    body.addEventListener("dragleave", () => {
      body.classList.remove("drag-target");
    });

    body.addEventListener("drop", async (event) => {
      event.preventDefault();
      body.classList.remove("drag-target");
      const cardId = event.dataTransfer.getData("text/plain") || state.dragCardId;
      if (!cardId) return;
      await api(`/api/cards/${cardId}/move`, "POST", { listId: list.id });
      await refresh();
    });

    if (!visibleCards.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No tasks in this column";
      body.appendChild(empty);
    } else {
      for (const card of visibleCards) {
        body.appendChild(createCardNode(board, card));
      }
    }

    const footer = document.createElement("footer");
    const addButton = document.createElement("button");
    addButton.className = "btn";
    addButton.textContent = "+ Add Task";
    addButton.addEventListener("click", () => openCardDialog("", list.id));
    footer.appendChild(addButton);

    column.appendChild(header);
    column.appendChild(body);
    column.appendChild(footer);
    el.kanbanColumns.appendChild(column);
  }
}

function populateCardSelects(board, selectedMilestoneId = "") {
  el.cardMilestone.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select milestone (required)";
  placeholder.disabled = Boolean(selectedMilestoneId);
  placeholder.selected = !selectedMilestoneId;
  el.cardMilestone.appendChild(placeholder);

  const visibleMilestones = sorted(board.milestones).filter((milestone) => (
    !isArchivedMilestone(milestone) || milestone.id === selectedMilestoneId
  ));
  for (const milestone of visibleMilestones) {
    const option = document.createElement("option");
    option.value = milestone.id;
    option.textContent = milestoneDisplayTitle(milestone);
    if (isWriteClosedPreflight(milestone) && milestone.id !== selectedMilestoneId) {
      option.disabled = true;
    }
    if (milestone.id === selectedMilestoneId) {
      option.selected = true;
    }
    el.cardMilestone.appendChild(option);
  }

  el.cardList.innerHTML = "";
  for (const list of sorted(board.lists)) {
    const option = document.createElement("option");
    option.value = list.id;
    option.textContent = list.title;
    el.cardList.appendChild(option);
  }
}

function openCardDialog(cardId = "", defaultListId = "") {
  const board = getActiveBoard();
  if (!board) return;
  let selectedMilestoneId = "";
  if (cardId) {
    const card = board.cards.find((item) => item.id === cardId);
    if (!card) return;
    selectedMilestoneId = card.milestoneId || "";
  } else {
    selectedMilestoneId = getOpenMilestones(board)[0]?.id || "";
  }
  populateCardSelects(board, selectedMilestoneId);

  if (cardId) {
    const card = board.cards.find((item) => item.id === cardId);
    if (!card) return;

    el.cardDialogTitle.textContent = card.kind === "bug" ? "Edit Bug" : "Edit Task";
    el.cardId.value = card.id;
    el.cardTitle.value = card.title;
    el.cardMilestone.value = selectedMilestoneId;
    el.cardDialog.dataset.originalMilestoneId = card.milestoneId || "";
    el.cardPriority.value = card.priority || "P2";
    el.cardList.value = card.listId;
    el.cardTargetDate.value = card.targetDate || "";
    el.cardOwner.value = card.owner || "";
    if (el.cardKind) el.cardKind.value = card.kind || "task";
    el.cardDescription.value = card.description || "";
    el.cardAcceptance.value = card.acceptance || "";
    if (el.cardDialogIssueNumber) {
      el.cardDialogIssueNumber.textContent = card.issueNumber || "—";
      el.cardDialogIssueNumber.classList.remove("is-hidden");
    }
    el.btnDeleteCard.style.display = "inline-block";
  } else {
    const fallbackListId = defaultListId || sorted(board.lists)[0]?.id || "";
    el.cardDialogTitle.textContent = "New Task";
    el.cardId.value = "";
    el.cardTitle.value = "";
    el.cardMilestone.value = selectedMilestoneId;
    el.cardDialog.dataset.originalMilestoneId = "";
    el.cardPriority.value = "P1";
    if (el.cardKind) el.cardKind.value = "task";
    el.cardList.value = fallbackListId;
    el.cardTargetDate.value = "";
    el.cardOwner.value = "";
    el.cardDescription.value = "";
    el.cardAcceptance.value = "";
    if (el.cardDialogIssueNumber) {
      el.cardDialogIssueNumber.textContent = "—";
      el.cardDialogIssueNumber.classList.add("is-hidden");
    }
    el.btnDeleteCard.style.display = "none";
  }

  el.cardDialog.showModal();
}

async function saveCardFromDialog() {
  const board = getActiveBoard();
  if (!board) return;

  const payload = {
    boardId: board.id,
    listId: el.cardList.value,
    title: el.cardTitle.value.trim(),
    milestoneId: el.cardMilestone.value,
    priority: el.cardPriority.value,
    kind: el.cardKind ? el.cardKind.value : "task",
    targetDate: el.cardTargetDate.value,
    owner: el.cardOwner.value.trim(),
    description: el.cardDescription.value.trim(),
    acceptance: el.cardAcceptance.value.trim(),
  };

  if (!payload.title) {
    await showPrompt("alert", "Error", "Task title is required.");
    return;
  }

  if (!payload.milestoneId) {
    await showPrompt("alert", "Error", "Milestone is required. Add to an active milestone or create a new milestone.");
    return;
  }

  const selectedMilestone = board.milestones.find((item) => item.id === payload.milestoneId);
  if (!selectedMilestone) {
    await showPrompt("alert", "Error", "Selected milestone was not found. Reload and try again.");
    return;
  }
  const originalMilestoneId = String(el.cardDialog.dataset.originalMilestoneId || "");
  if (isArchivedMilestone(selectedMilestone) && payload.milestoneId !== originalMilestoneId) {
    await showPrompt("alert", "Error", "Milestone is archived. Restore it from Archives before assigning new work.");
    return;
  }
  if (isWriteClosedPreflight(selectedMilestone) && payload.milestoneId !== originalMilestoneId) {
    await showPrompt("alert", "Error", "Pre-flight milestone is write-closed. Select an active milestone or create a new one.");
    return;
  }

  if (el.cardId.value) {
    await api(`/api/cards/${el.cardId.value}`, "PATCH", payload);
  } else {
    await api("/api/cards", "POST", payload);
  }

  el.cardDialog.close();
  await refresh();
}

async function refresh() {
  const payload = await api("/api/state");
  state.data = payload.state;
  restoreFiltersForActiveBoard();

  loadChartsFromState();
  if (state.selectedChartId && !state.charts.some((item) => item.id === state.selectedChartId)) {
    state.selectedChartId = "";
  }

  try {
    const vRes = await api("/api/state/version");
    state.lastVersion = vRes.version;
  } catch (e) { }

  render();
}

function render() {
  const board = getActiveBoard();
  if (!board) return;
  renderKanbanList();
  renderKanbanMeta();
  renderMilestonePolicyHint(board);
  renderMilestoneProgress();
  if (el.milestoneArchivesDialog?.open) {
    renderMilestoneArchives();
  }

  // Update View Selector UI State
  const viewMap = {
    board: "Kanban",
    dashboard: "Dashboard",
    charts: "Charts Library",
    guide: "MCD Guide",
  };
  el.currentViewLabel.textContent = viewMap[state.currentView] || "Kanban";

  el.navTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === state.currentView);
  });

  el.boardView.style.display = "none";
  el.dashboardView.style.display = "none";
  el.chartsView.style.display = "none";
  el.guideView.style.display = "none";

  if (state.currentView === "dashboard") {
    el.dashboardView.style.display = "block";
    renderDashboard();
  } else if (state.currentView === "charts") {
    el.chartsView.style.display = "grid";
    renderCharts();
  } else if (state.currentView === "guide") {
    el.guideView.style.display = "block";
    renderGuide();
  } else {
    el.boardView.style.display = "grid";
    renderMilestoneFilter();
    renderColumns();
  }

  renderMilestoneDetailPanel();
}

async function renderGuide() {
  try {
    const res = await api("/api/docs/playbook");
    if (window.marked) {
      el.guideContent.innerHTML = window.marked.parse(res.content);
      renderMermaidBlocks(el.guideContent);
    } else {
      el.guideContent.innerHTML = `<pre style="white-space:pre-wrap; font-family:var(--font);">${res.content}</pre>`;
    }
  } catch (e) {
    el.guideContent.innerHTML = `<span style="color:var(--danger)">Failed to load playbook: ${e.message}</span>`;
  }
}

async function renderDashboard() {
  const board = getActiveBoard();
  if (!board) return;

  // 1. Vitals
  const activeLists = board.lists.filter(l => ["active", "qa"].includes(l.key));
  const blockedList = board.lists.find(l => l.key === "blocked");

  let phaseText = "Planning / Backlog";
  if (board.cards.some(c => activeLists.some(l => l.id === c.listId))) {
    phaseText = "Execute";
  } else if (board.cards.some(c => blockedList && c.listId === blockedList.id)) {
    phaseText = "Blocked";
  } else if (board.cards.every(c => board.lists.find(l => l.id === c.listId)?.key === "done")) {
    phaseText = "Closeout Ready";
  }
  el.dashboardPhase.textContent = `Active Phase: ${phaseText}`;

  // Burn-down (Current Milestone)
  const ms = getActiveMilestones(board)[0];
  if (ms) {
    const msCards = board.cards.filter(c => c.milestoneId === ms.id);
    const doneCards = msCards.filter(c => board.lists.find(l => l.id === c.listId)?.key === "done").length;
    el.dashboardBurndown.innerHTML = `<strong>${ms.title}</strong><br/>${doneCards} / ${msCards.length} tasks completed`;
  } else {
    el.dashboardBurndown.textContent = "No active milestone";
  }

  // Blockers
  const blockedCards = board.cards.filter(c => blockedList && c.listId === blockedList.id);
  if (blockedCards.length > 0) {
    el.dashboardBlockers.innerHTML = blockedCards.map(c => `• ${c.title}`).join("<br/>");
  } else {
    el.dashboardBlockers.textContent = "None";
  }

  // Metrics
  el.dashboardMetrics.textContent = `Project Type: ${board.projectType || 'standard'}`;

  // Traceability
  try {
    const logRes = await api("/api/git/log");
    el.dashboardGitLog.textContent = logRes.log || "No git history found.";
  } catch (e) {
    el.dashboardGitLog.textContent = "Could not load git history.";
  }
}

async function showDocument(docId, title) {
  el.docDialogTitle.textContent = title;
  el.docDialogContent.innerHTML = "<em>Loading...</em>";
  el.docDialog.showModal();

  try {
    const res = await api(`/api/docs/${docId}`);
    if (window.marked) {
      el.docDialogContent.innerHTML = window.marked.parse(res.content);
      renderMermaidBlocks(el.docDialogContent);
    } else {
      el.docDialogContent.innerHTML = `<pre style="white-space:pre-wrap; font-family:var(--font);">${res.content}</pre>`;
    }
  } catch (e) {
    el.docDialogContent.innerHTML = `<span style="color:var(--danger)">Failed to load document: ${e.message}</span>`;
  }
}


function download(filename, text) {
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function registerEvents() {
  el.viewSelectorToggle.addEventListener("click", () => {
    el.viewSelector.classList.toggle("is-open");
  });

  document.addEventListener("click", (e) => {
    if (!el.viewSelector.contains(e.target)) {
      el.viewSelector.classList.remove("is-open");
    }
  });

  for (const dialog of getDismissibleDialogs()) {
    registerDialogBackdropDismiss(dialog);
  }

  document.addEventListener("pointerdown", (event) => {
    if (!state.milestonePanel.open || !el.milestoneDetailPanel?.classList.contains("is-open")) return;
    if (hasOpenDismissibleDialog()) return;
    const target = event.target;
    if (!(target instanceof Node)) return;
    if (el.milestoneDetailPanel.contains(target)) return;
    closeMilestonePanel();
  }, true);

  el.navTabs.forEach((tab) => {
    tab.addEventListener("click", (e) => {
      const nextView = e.target.closest(".nav-tab").dataset.view;
      state.currentView = nextView === "wiki" ? "board" : nextView;
      localStorage.setItem("mcd_current_view", state.currentView);
      document.documentElement.setAttribute("data-current-view", state.currentView);
      el.viewSelector.classList.remove("is-open");
      render();
    });
  });

  document.querySelectorAll(".btn-doc").forEach(btn => {
    btn.addEventListener("click", (e) => {
      showDocument(e.target.dataset.doc, e.target.textContent);
    });
  });

  el.docDialog.querySelector("button[value='close']").addEventListener("click", (e) => {
    e.preventDefault();
    el.docDialog.close();
  });

  el.btnWhyMcd.addEventListener("click", () => {
    el.whyMcdDialog.showModal();
  });

  el.whyMcdDialog.querySelector("button[value='close']").addEventListener("click", (e) => {
    e.preventDefault();
    el.whyMcdDialog.close();
  });

  if (el.btnAttributionInfo && el.attributionDialog) {
    el.btnAttributionInfo.addEventListener("click", () => {
      el.attributionDialog.showModal();
    });

    const attributionClose = el.attributionDialog.querySelector("button[value='close']");
    if (attributionClose) {
      attributionClose.addEventListener("click", (e) => {
        e.preventDefault();
        el.attributionDialog.close();
      });
    }
  }

  if (el.btnNewBoard) el.btnNewBoard.onclick = createNewBoard;

  el.btnCloneBoard.addEventListener("click", async () => {
    const board = getActiveBoard();
    if (!board) return;
    await api(`/api/boards/${board.id}/clone`, "POST", {});
    await refresh();
  });

  el.btnSaveBoard.addEventListener("click", async () => {
    const board = getActiveBoard();
    if (!board) return;
    await api(`/api/boards/${board.id}`, "PATCH", {
      name: el.boardName.value.trim(),
      description: el.boardDescription.value.trim(),
    });
    await refresh();
  });

  el.btnDeleteBoard.addEventListener("click", async () => {
    const board = getActiveBoard();
    if (!board) return;
    if (!(await showPrompt("confirm", "Delete Board", `Delete Kanban "${board.name}"?`))) return;
    await api(`/api/boards/${board.id}`, "DELETE");
    await refresh();
  });

  el.btnAddMilestone.addEventListener("click", async () => {
    const board = getActiveBoard();
    if (!board) return;
    const titleInput = await showPrompt("prompt", "New Milestone", "Milestone title");
    if (!titleInput || !titleInput.trim()) return;
    const parsed = parseMilestoneTitleParts(titleInput);
    const defaultCode = parsed.code || extractMilestoneCode(titleInput);
    const codeInput = await showPrompt("prompt", "Milestone Code", "Milestone code (e.g., AMV2-005). Leave blank for none.", defaultCode);
    if (codeInput === null) return;
    const code = extractMilestoneCode(codeInput);
    const title = (parsed.title || String(titleInput || "").trim());
    if (!title) return;
    await api("/api/milestones", "POST", {
      boardId: board.id,
      code,
      title,
    });
    await refresh();
  });

  if (el.btnMilestoneArchives && el.milestoneArchivesDialog) {
    el.btnMilestoneArchives.addEventListener("click", () => {
      renderMilestoneArchives();
      el.milestoneArchivesDialog.showModal();
    });

    const archivesClose = el.milestoneArchivesDialog.querySelector("button[value='close']");
    if (archivesClose) {
      archivesClose.addEventListener("click", (event) => {
        event.preventDefault();
        el.milestoneArchivesDialog.close();
      });
    }
  }

  if (el.btnMilestonePanelClose) {
    el.btnMilestonePanelClose.addEventListener("click", () => {
      closeMilestonePanel();
    });
  }

  if (el.btnMilestonePanelBack) {
    el.btnMilestonePanelBack.addEventListener("click", () => {
      milestonePanelBack();
    });
  }

  el.btnAddList.addEventListener("click", async () => {
    const board = getActiveBoard();
    if (!board) return;
    const title = await showPrompt("prompt", "New Column", "Column title");
    if (!title || !title.trim()) return;
    await api("/api/lists", "POST", {
      boardId: board.id,
      title: title.trim(),
    });
    await refresh();
  });

  el.btnAddCard.addEventListener("click", () => {
    const board = getActiveBoard();
    if (!board) return;
    const backlog = sorted(board.lists)[0]?.id;
    openCardDialog("", backlog);
  });

  el.btnExportBoard.addEventListener("click", () => {
    const board = getActiveBoard();
    if (!board) return;
    const safeName = board.name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    download(`${safeName}.json`, JSON.stringify(board, null, 2));
  });

  el.btnImportBoard.addEventListener("click", () => {
    el.importFile.click();
  });



  el.importFile.addEventListener("change", async () => {
    const file = el.importFile.files?.[0];
    if (!file) return;

    try {
      const raw = await file.text();
      const board = JSON.parse(raw);
      await api("/api/boards/import", "POST", { board });
      await refresh();
    } catch (error) {
      await showPrompt("alert", "Error", `Import failed: ${error.message}`);
    } finally {
      el.importFile.value = "";
    }
  });

  el.milestoneFilter.addEventListener("change", () => {
    state.filters.milestoneId = el.milestoneFilter.value;
    persistFiltersForActiveBoard();
    renderColumns();
  });

  el.searchInput.addEventListener("input", () => {
    state.filters.search = el.searchInput.value;
    persistFiltersForActiveBoard();
    renderColumns();
  });

  el.cardForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveCardFromDialog();
    } catch (error) {
      await showPrompt("alert", "Error", error.message);
    }
  });

  el.btnCancelCard.addEventListener("click", () => {
    el.cardDialog.close();
  });

  el.btnDeleteCard.addEventListener("click", async () => {
    if (!el.cardId.value) return;
    if (!(await showPrompt("confirm", "Delete Task", "Delete this task?"))) return;
    await api(`/api/cards/${el.cardId.value}`, "DELETE");
    el.cardDialog.close();
    await refresh();
  });

  if (el.btnCloseChartsPanel) {
    el.btnCloseChartsPanel.addEventListener("click", () => {
      state.selectedChartId = "";
      renderCharts();
    });
  }

  if (el.btnDeleteChart) {
    el.btnDeleteChart.addEventListener("click", async () => {
      if (!state.selectedChartId) return;
      if (!(await showPrompt("confirm", "Delete Chart", "Delete this Mermaid chart?"))) return;
      await api(`/api/charts/${state.selectedChartId}`, "DELETE");
      state.selectedChartId = "";
      await refresh();
    });
  }

  if (el.themeCheckbox) el.themeCheckbox.addEventListener("change", toggleTheme);
  if (el.btnToggleSidebar) el.btnToggleSidebar.onclick = toggleSidebar;
  if (el.btnNewBoard) el.btnNewBoard.onclick = createNewBoard;
}

function startPolling() {
  if (state.pollInterval) clearInterval(state.pollInterval);
  state.pollInterval = setInterval(async () => {
    // Only poll if tab is focused to save local resources
    if (document.visibilityState !== "visible") return;

    try {
      const vRes = await api("/api/state/version");
      if (vRes.ok && vRes.version && state.lastVersion && vRes.version !== state.lastVersion) {
        console.log("State mutation detected. Hot reloading...");
        await refresh();
      }
    } catch (e) {
      // fail silently
    }
  }, 10000);
}

async function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("mcd_theme", next);
  if (el.themeCheckbox) {
    el.themeCheckbox.checked = next === "dark";
  }

  configureMermaidTheme();
  if (state.currentView === "guide") {
    renderMermaidBlocks(el.guideContent);
  }
  if (state.currentView === "charts") {
    renderChartsPreview();
  }
  if (el.docDialog && el.docDialog.open) {
    renderMermaidBlocks(el.docDialogContent);
  }
}

async function createNewBoard() {
  const name = await showPrompt("prompt", "New Board", "Kanban name");
  if (!name || !name.trim()) return;
  const useTemplate = await showPrompt("confirm", "Seed Board", "Seed with launch template?\nOK = yes, Cancel = empty board");
  await api("/api/boards", "POST", {
    name: name.trim(),
    description: "",
    seedTemplate: useTemplate,
  });
  await refresh();
}

function toggleSidebar() {
  const isCollapsed = document.documentElement.getAttribute("data-sidebar-collapsed") === "true";
  const nextState = !isCollapsed;
  if (nextState) {
    document.documentElement.setAttribute("data-sidebar-collapsed", "true");
    el.btnToggleSidebar.textContent = "»";
  } else {
    document.documentElement.removeAttribute("data-sidebar-collapsed");
    el.btnToggleSidebar.textContent = "«";
  }
  localStorage.setItem("mcd_sidebar_collapsed", nextState);
}

async function bootstrap() {
  if (window.marked) {
    const renderer = new window.marked.Renderer();
    const originalCode = renderer.code.bind(renderer);
    renderer.code = function (token) {
      const code = token.text || "";
      const lang = token.lang || "";
      if (lang === "mermaid") {
        return `<div class="mermaid">${code}</div>`;
      }
      return originalCode(token);
    };
    window.marked.use({ renderer });
  }

  mountMilestonePanelLayer();
  registerEvents();
  if (el.themeCheckbox) {
    const theme = localStorage.getItem("mcd_theme") || "dark";
    el.themeCheckbox.checked = theme === "dark";
  }
  if (localStorage.getItem("mcd_sidebar_collapsed") === "true") {
    el.btnToggleSidebar.textContent = "»";
  }
  configureMermaidTheme();
  try {
    await refresh();
    startPolling();
  } catch (error) {
    await showPrompt("alert", "Error", `Failed to load board: ${error.message}`);
  }
}

bootstrap();
