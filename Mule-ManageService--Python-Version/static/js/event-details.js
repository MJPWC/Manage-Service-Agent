(function (global) {
  "use strict";

  function setEventDetailsFlowState(nextState) {
    const ctx = global.__eventDetailsContext;
    if (!ctx) return;
    ctx.analysisFlowState = nextState;
    if (global.updateEventDetailFlowButtons) global.updateEventDetailFlowButtons();
  }

  function collectExpectedUploadFiles(logs) {
    const expectedFiles = [];
    const seen = new Set();

    (logs || []).forEach((log) => {
      const fileName = global.getErrorFileNameFromLog ? global.getErrorFileNameFromLog(log) : "";
      if (!fileName || fileName === "N/A") return;
      const normalized = String(fileName).trim();
      const key = normalized.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      expectedFiles.push(normalized);
    });

    return expectedFiles;
  }

  function closeEventDetailsModal() {
    global.AppModalUtils.closeEventDetailsModal();

    if (global.state?.loadingRequests > 0 && global.elements?.loadingOverlay) {
      global.state.loadingRequests = 0;
      global.elements.loadingOverlay.classList.add("hidden");
    }

    if (global.state?.currentTab === "mulesoft") {
      if (global.state.logs && global.state.logs.length > 0 && global.renderLogs) {
        global.renderLogs();
      } else if (global.state.selectedAppId && global.state.currentEnvId && global.loadLogs) {
        global.loadLogs(global.state.selectedAppId);
      }
      if (global.state.selectedAppId && global.startAutoRefresh) {
        global.startAutoRefresh();
      }
    } else if (global.state?.currentTab === "correlation" && global.renderCorrelationIds) {
      global.renderCorrelationIds();
    }
  }

  function getEventDetailFlowButtonsHtml(state, logIndex, fileName) {
    const safeFile = global.escapeHtml ? global.escapeHtml(fileName || "N/A") : (fileName || "N/A");

    if (state === "attach") {
      return `

        <button type="button" class="btn-secondary" data-action="upload-local">Upload from local</button>

        <button type="button" class="btn-secondary" data-action="upload-github" data-file-name="${safeFile}">Upload from GitHub</button>



        <button type="button" class="btn-secondary btn-text" data-action="flow-cancel">Mark as Expected Error</button>

      `;
    }

    if (state === "loading-local") {
      return `

        <div class="analysis-status">Preparing local file for analysis...</div>

      `;
    }

    if (state === "loading-local-multiple") {
      return `

        <div class="analysis-status">Uploading selected local files for analysis...</div>

      `;
    }

    if (state === "loading-github") {
      return `

        <div class="analysis-status">Fetching related files from GitHub...</div>

      `;
    }

    if (state === "attached") {
      return `

        <div class="analysis-status">File attached - Analyzing...</div>

      `;
    }

    return "";
  }

  function updateEventDetailFlowButtons() {
    const modal = document.getElementById("eventDetailsModal");
    if (!modal) return;

    const ctx = global.__eventDetailsContext;
    if (!ctx) return;

    const state = ctx.analysisFlowState;
    modal.querySelectorAll(".event-detail-actions").forEach((container) => {
      const logIndex = parseInt(container.getAttribute("data-log-index") || "0", 10);
      const fileName = container.getAttribute("data-file-name") || "N/A";

      container.innerHTML = getEventDetailFlowButtonsHtml(state, logIndex, fileName);
    });
  }

  global.EventDetails = {
    setEventDetailsFlowState,
    collectExpectedUploadFiles,
    closeEventDetailsModal,
    updateEventDetailFlowButtons,
  };

  global.setEventDetailsFlowState = setEventDetailsFlowState;
  global.closeEventDetailsModal = closeEventDetailsModal;
  global.updateEventDetailFlowButtons = updateEventDetailFlowButtons;
  global.collectExpectedUploadFiles = collectExpectedUploadFiles;
})(typeof window !== "undefined" ? window : this);
