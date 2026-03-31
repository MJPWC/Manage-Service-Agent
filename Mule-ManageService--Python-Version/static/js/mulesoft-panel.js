(function (global) {
  "use strict";

  function getState() {
    return global.state || {};
  }

  function getElements() {
    const shared = global.elements || {};

    return {
      ...shared,
      apiList: shared.apiList || document.getElementById("apiList"),
      apiSearch: shared.apiSearch || document.getElementById("apiSearch"),
      logsContent:
        shared.logsContent || document.getElementById("logsContent"),
    };
  }

  function getStatusClass(status) {
    if (!status) return "unknown";

    const normalized = status.toUpperCase();

    if (
      normalized === "RUNNING" ||
      normalized === "STARTED" ||
      normalized === "APPLIED"
    ) {
      return "running";
    }

    if (normalized === "STOPPED" || normalized === "UNDEPLOYED") {
      return "stopped";
    }

    if (normalized === "FAILED" || normalized === "ERROR") {
      return "error";
    }

    return "unknown";
  }

  function isLogInTimeRange(log) {
    if (typeof global.isLogInTimeRange === "function") {
      return global.isLogInTimeRange(log);
    }

    const state = getState();

    if (!state.startTime && !state.endTime) {
      return true;
    }

    if (!log.timestamp) {
      return false;
    }

    const logTime = new Date(log.timestamp).getTime();

    if (state.startTime && logTime < state.startTime) {
      return false;
    }

    if (state.endTime && logTime > state.endTime) {
      return false;
    }

    return true;
  }

  function hasValidEventId(log) {
    if (typeof global.hasValidEventId === "function") {
      return global.hasValidEventId(log);
    }

    return !!(log.event_id && log.event_id.trim() !== "");
  }

  function hasErrorDetails(log) {
    if (typeof global.hasErrorDetails === "function") {
      return global.hasErrorDetails(log);
    }

    if (!log.exception) {
      return false;
    }

    const exception = log.exception;
    const hasErrorType = exception.ExceptionType || exception["Error type"];
    const hasErrorMessage =
      exception.Message && exception.Message.trim() !== "";
    const message = log.message || "";
    const isSuccessfulLog =
      message.toLowerCase().includes("successful") &&
      !hasErrorType &&
      !hasErrorMessage;

    return !isSuccessfulLog && (hasErrorType || hasErrorMessage);
  }

  function calculateFilteredErrorCount(appId) {
    if (typeof global.calculateFilteredErrorCount === "function") {
      return global.calculateFilteredErrorCount(appId);
    }

    const state = getState();
    const appLogs = state.appLogs?.[appId] || [];

    if ((state.startTime || state.endTime) && appLogs.length > 0) {
      return appLogs
        .filter((log) => isLogInTimeRange(log))
        .filter((log) => hasValidEventId(log))
        .filter((log) => hasErrorDetails(log)).length;
    }

    return appLogs
      .filter((log) => hasValidEventId(log))
      .filter((log) => hasErrorDetails(log)).length;
  }

  function formatTimestamp(value) {
    if (typeof global.formatTimestamp === "function") {
      return global.formatTimestamp(value);
    }

    if (!value) return "";

    try {
      const date = new Date(value);

      if (isNaN(date.getTime())) {
        return value;
      }

      return date.toLocaleString("en-US", {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
    } catch {
      return value;
    }
  }

  function extractApiAndFileFromFlowStack(eventId) {
    if (typeof global.extractApiAndFileFromFlowStack === "function") {
      return global.extractApiAndFileFromFlowStack(eventId);
    }

    const state = getState();
    const analysis = state.logAnalysis;

    if (!analysis || !analysis.error_location) {
      return { apiName: null, fileName: null };
    }

    const errorLocation = analysis.error_location;

    if (errorLocation && errorLocation.api_name && errorLocation.file_name) {
      return {
        apiName: errorLocation.api_name,
        fileName: errorLocation.file_name,
      };
    }

    return { apiName: null, fileName: null };
  }

  function extractFilenameFromElement(elementStr) {
    if (typeof global.extractFilenameFromElement === "function") {
      return global.extractFilenameFromElement(elementStr);
    }

    if (!elementStr || typeof elementStr !== "string") {
      return "";
    }

    const match = elementStr.match(/(?:file|location|path)[=:]\s*([^\s,\]]+\.(xml|dwl|dw|java|js|py))/i);
    if (match && match[1]) {
      return match[1].split("/").pop();
    }

    const fallback = elementStr.match(/([A-Za-z0-9_.-]+\.(xml|dwl|dw|java|js|py))/i);
    return fallback && fallback[1] ? fallback[1] : "";
  }

  function extractApiNameFromElement(elementStr) {
    if (typeof global.extractApiNameFromElement === "function") {
      return global.extractApiNameFromElement(elementStr);
    }

    if (!elementStr || typeof elementStr !== "string") {
      return "Unknown API";
    }

    const slashMatch = elementStr.match(/\/([A-Za-z0-9_.-]+)\/src\/main\//i);
    if (slashMatch && slashMatch[1]) {
      return slashMatch[1];
    }

    const appMatch = elementStr.match(/app(?:lication)?[=:]\s*([A-Za-z0-9_.-]+)/i);
    if (appMatch && appMatch[1]) {
      return appMatch[1];
    }

    return "Unknown API";
  }

  function renderErrorBanner(message) {
    if (typeof global.renderErrorBanner === "function") {
      global.renderErrorBanner(message);
      return;
    }

    const elements = getElements();
    const container =
      elements.logsContent || document.getElementById("logsContent");

    if (!container) return;

    container.innerHTML = `
      <div class="empty-state">
        <p>${global.escapeHtml ? global.escapeHtml(message || "Something went wrong") : (message || "Something went wrong")}</p>
      </div>
    `;
  }

  function updateFilterVisibility() {
    if (typeof global.updateFilterVisibility === "function") {
      global.updateFilterVisibility();
      return;
    }

    const state = getState();
    const elements = getElements();
    const filterBar =
      elements.logsFilterContainer ||
      elements.filterBar ||
      document.getElementById("filterBar");

    if (!filterBar) return;

    if (state.selectedAppId || state.currentTab === "correlation") {
      filterBar.classList.remove("hidden");
    } else {
      filterBar.classList.add("hidden");
    }
  }

  function groupLogsByCorrelationId(logs) {
    const grouped = {};

    logs.forEach((log, originalIndex) => {
      const correlationId = log.event_id || "unknown";

      if (!grouped[correlationId]) {
        grouped[correlationId] = {
          correlationId,
          logs: [],
          originalIndices: [],
          firstLog: log,
          errorCount: 0,
        };
      }

      grouped[correlationId].logs.push(log);
      grouped[correlationId].originalIndices.push(originalIndex);
      grouped[correlationId].errorCount = grouped[correlationId].logs.length;
    });

    return Object.values(grouped).sort((a, b) => {
      const timeA = new Date(a.firstLog.timestamp || 0).getTime();
      const timeB = new Date(b.firstLog.timestamp || 0).getTime();
      return timeB - timeA;
    });
  }

  function renderApplications() {
    const state = getState();
    const elements = getElements();

    if (!elements.apiList || !elements.apiSearch) return;

    if (state.applications.length === 0) {
      elements.apiList.innerHTML = `
        <div class="empty-state">
          <p>No applications found in this environment</p>
        </div>
      `;
      return;
    }

    const searchTerm = elements.apiSearch.value.toLowerCase();

    let filtered = state.applications.filter((app) =>
      app.name.toLowerCase().includes(searchTerm),
    );

    filtered = filtered.sort((a, b) => {
      const countA = calculateFilteredErrorCount(a.id);
      const countB = calculateFilteredErrorCount(b.id);
      return countB - countA;
    });

    if (filtered.length === 0) {
      elements.apiList.innerHTML = `
        <div class="empty-state">
          <p>No matching applications</p>
        </div>
      `;
      return;
    }

    elements.apiList.innerHTML = filtered
      .map((app) => {
        const statusClass = getStatusClass(app.appStatus);
        const isActive = app.id === state.selectedAppId;
        const errorCount = calculateFilteredErrorCount(app.id);
        const isLoading = errorCount === undefined;
        const badgeClass = isLoading
          ? "error-badge loading"
          : errorCount > 0
            ? "error-badge"
            : "error-badge zero";
        const badgeContent = isLoading ? "..." : errorCount;

        return `
        <div class="api-item ${isActive ? "active" : ""}" data-id="${app.id}">
          <div class="api-header">
            <div class="api-name">${global.escapeHtml(app.name)}</div>
            <span class="${badgeClass}">${badgeContent}</span>
          </div>
          <div class="api-status">
            <span class="status-dot ${statusClass}"></span>
            <span>${app.appStatus || "Unknown"}</span>
          </div>
        </div>
      `;
      })
      .join("");

    elements.apiList.querySelectorAll(".api-item").forEach((item) => {
      item.addEventListener("click", () => {
        selectApplication(item.dataset.id);
      });
    });
  }

  function renderLogs() {
    const state = getState();
    const elements = getElements();

    if (!elements.logsContent) return;

    if (!state.selectedAppId) {
      elements.logsContent.innerHTML = `
        <div class="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <line x1="10" y1="9" x2="8" y2="9"/>
          </svg>
          <p>Select an API to view error logs</p>
        </div>
      `;
      return;
    }

    let filteredLogs = state.logs.filter((log) => isLogInTimeRange(log));
    filteredLogs = filteredLogs.filter((log) => hasValidEventId(log));
    filteredLogs = filteredLogs.filter((log) => hasErrorDetails(log));

    if (filteredLogs.length === 0) {
      elements.logsContent.innerHTML = `
        <div class="no-logs-message">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
          <p>No error logs found${state.startTime ? " for selected time range" : ""}</p>
        </div>
      `;
      return;
    }

    const selectedApp = state.applications.find((app) => app.id === state.selectedAppId);
    const appName = selectedApp ? selectedApp.name : "Application";
    const groupedLogs = groupLogsByCorrelationId(filteredLogs);

    const logsHtml = groupedLogs
      .map((group, groupIndex) => {
        const log = group.firstLog;
        const timestamp = log.timestamp || "";
        const formattedTime = formatTimestamp(timestamp);
        const eventId = log.event_id || "";
        const exception = log.exception || null;
        const errorCount = group.errorCount;

        let errorType = "Unknown Error";
        let errorMessage = log.message || "";
        let filename = "N/A";
        let apiName = null;

        const flowStackInfo = extractApiAndFileFromFlowStack(eventId);
        if (flowStackInfo.apiName) apiName = flowStackInfo.apiName;
        if (flowStackInfo.fileName) filename = flowStackInfo.fileName;

        if (exception) {
          if (exception.ExceptionType) {
            errorType = exception.ExceptionType;
          } else if (exception["Error type"]) {
            errorType = exception["Error type"];
          }

          if (exception.Message) {
            errorMessage = exception.Message;
          } else if (exception.message) {
            errorMessage = exception.message;
          }

          if (!errorMessage && exception.error) {
            errorMessage = exception.error;
          }

          if ((!filename || filename === "N/A") && exception.Element) {
            const extracted = extractFilenameFromElement(exception.Element);
            if (extracted) filename = extracted;
          }

          if (!apiName && exception.Element) {
            const apiNameFromElement = extractApiNameFromElement(
              exception.Element,
            );
            if (apiNameFromElement && apiNameFromElement !== "Unknown API") {
              apiName = apiNameFromElement;
            }
          }
        }

        if (!errorMessage || typeof errorMessage !== "string") {
          errorMessage = "No error details available";
        }

        if (
          !apiName &&
          log.application &&
          log.application !== "DefaultExceptionListener"
        ) {
          apiName = log.application;
        }

        if (!apiName) {
          apiName = "Unknown Application";
        }

        const errorMessages = [];
        const seenMessages = new Set();

        group.logs.forEach((entry) => {
          let message = entry.message || "";

          if (entry.exception && entry.exception.Message) {
            message = entry.exception.Message;
          } else if (entry.exception && entry.exception.message) {
            message = entry.exception.message;
          } else if (entry.exception && entry.exception.error) {
            message = entry.exception.error;
          }

          if (message && !seenMessages.has(message)) {
            seenMessages.add(message);
            errorMessages.push(message);
          }
        });

        if (errorMessages.length === 0) {
          errorMessages.push("No error details available");
        }

        const descriptionHtml = errorMessages
          .map((message, idx) => {
            const fullMessage = global.escapeHtml(message);
            return `<div style="margin: ${idx > 0 ? "6px 0 0 0" : "0"}; padding: ${idx > 0 ? "6px 0 0 0" : "0"}; ${idx > 0 ? "border-top: 1px solid #e5e7eb;" : ""}">${fullMessage}</div>`;
          })
          .join("");

        const occurrencesList = group.logs
          .map((entry, idx) => {
            const ts = formatTimestamp(entry.timestamp || "");
            return `<li>#${idx + 1} - ${ts}</li>`;
          })
          .join("");

        const envId = state.currentEnvId || "default";
        const statuses = global.getCorrelationStatuses(envId);
        const isExpectedError = statuses[eventId] === "expected";
        const expectedErrorClass = isExpectedError ? " expected-error" : "";

        return `
        <div class="error-card${expectedErrorClass}" data-correlation-id="${global.escapeHtml(eventId)}" data-group-index="${groupIndex}">
          <div class="error-card-header">
            <div class="error-card-serial">#${groupIndex + 1}</div>
            <div class="error-card-count-badge">${errorCount} ${errorCount === 1 ? "occurrence" : "occurrences"}</div>
            <div class="error-card-timestamp">${formattedTime}</div>
          </div>
          <div class="error-card-content">
            <div class="error-card-row">
              <span class="error-card-label">API:</span>
              <span class="error-card-value">${global.escapeHtml(apiName)}</span>
            </div>
            <div class="error-card-row">
              <span class="error-card-label">Error Type:</span>
              <span class="error-card-value error-type-badge">${global.escapeHtml(errorType)}</span>
            </div>
            <div class="error-card-row">
              <span class="error-card-label">File:</span>
              <span class="error-card-value">${global.escapeHtml(filename)}</span>
            </div>
            <div class="error-card-row">
              <span class="error-card-label">Description:</span>
              <span class="error-card-value">${descriptionHtml}</span>
            </div>
            <div class="error-card-row">
              <span class="error-card-label">Correlation ID:</span>
              <code class="correlation-id-badge event-id-clickable" data-event-id="${global.escapeHtml(eventId)}" title="Click to view details">${global.escapeHtml(eventId || "N/A")}</code>
            </div>
          </div>
          ${
            errorCount > 1
              ? `
          <div class="error-card-occurrences">
            <div class="occurrences-toggle" data-toggle-id="occurrences-${groupIndex}">
              <span class="occurrences-label">↓ View all ${errorCount} occurrences</span>
            </div>
            <ul class="occurrences-list" id="occurrences-${groupIndex}" style="display: none;">
              ${occurrencesList}
            </ul>
          </div>
          `
              : ""
          }
          ${isExpectedError ? '<div class="error-card-expected-footer">Expected Error</div>' : ""}
        </div>
      `;
      })
      .join("");

    elements.logsContent.innerHTML = `
      <div class="logs-summary">
        <div class="logs-summary-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <span>${global.escapeHtml(appName)}</span>
          <span class="logs-summary-meta">${groupedLogs.length} issue${groupedLogs.length === 1 ? "" : "s"} (${filteredLogs.length} total occurrences)</span>
        </div>
      </div>
      <div class="error-cards-container">
        ${logsHtml}
      </div>
    `;

    document.querySelectorAll(".occurrences-toggle").forEach((toggle) => {
      toggle.addEventListener("click", function () {
        const toggleId = this.getAttribute("data-toggle-id");
        const list = document.getElementById(toggleId);
        const isVisible = list.style.display !== "none";

        list.style.display = isVisible ? "none" : "block";

        const label = this.querySelector(".occurrences-label");
        if (label) {
          const countMatch = label.textContent.match(/(\d+)/);
          const count = countMatch ? countMatch[1] : "?";
          label.textContent = isVisible
            ? `↓ View all ${count} occurrences`
            : "↑ Hide occurrences";
        }
      });
    });
  }

  async function loadApplications(envId) {
    const state = getState();
    const elements = getElements();

    if (!envId) {
      state.applications = [];
      if (!elements.apiList) return;
      elements.apiList.innerHTML = `
        <div class="empty-state">
          <p>Select an environment to view applications</p>
        </div>
      `;
      return;
    }

    if (envId === "local") {
      return loadLocalApplications();
    }

    global.showLoading();

    try {
      const result = await global.api("GET", `/api/environments/${envId}/applications`);

      if (result.success) {
        state.applications = result.applications || [];
        state.errorCounts = {};
        renderApplications();
        fetchErrorCounts(envId);
      } else {
        state.applications = [];
        elements.apiList.innerHTML = `
          <div class="empty-state">
            <p>Failed to load applications</p>
          </div>
        `;
      }
    } catch (error) {
      console.error("Failed to load applications:", error);
      elements.apiList.innerHTML = `
        <div class="empty-state">
          <p>Error loading applications</p>
        </div>
      `;
    } finally {
      global.hideLoading();
    }
  }

  async function loadLocalApplications() {
    const state = getState();
    const elements = getElements();

    global.showLoading();

    try {
      global.resetTimeFilter();

      const result = await global.api(
        "GET",
        "/api/local/environments/local/applications",
      );

      if (result.success) {
        state.applications = result.applications || [];

        const errorResult = await global.api(
          "GET",
          "/api/local/environments/local/error-counts",
        );

        state.errorCounts = errorResult.success
          ? errorResult.errorCounts || {}
          : {};

        renderApplications();

        if (state.applications.length > 0) {
          const appId = state.applications[0].id;
          const logsResult = await global.api(
            "GET",
            "/api/local/environments/local/applications/local-app/logs",
          );

          if (logsResult.success && logsResult.logs) {
            state.appLogs[appId] = logsResult.logs;
          }

          selectApplication(appId);
        }
      } else {
        state.applications = [];
        if (!elements.apiList) return;
        elements.apiList.innerHTML = `
          <div class="empty-state">
            <p>Failed to load local file</p>
          </div>
        `;
      }
    } catch (error) {
      console.error("Failed to load local applications:", error);
      if (!elements.apiList) return;
      elements.apiList.innerHTML = `
        <div class="empty-state">
          <p>Error loading local file</p>
        </div>
      `;
    } finally {
      global.hideLoading();
    }
  }

  async function fetchErrorCounts(envId) {
    const state = getState();

    try {
      const result = await global.api("GET", `/api/environments/${envId}/error-counts`);

      if (result.success && result.errorCounts) {
        state.errorCounts = result.errorCounts;

        for (const app of state.applications) {
          try {
            const logsResult = await global.api(
              "GET",
              `/api/environments/${envId}/applications/${app.id}/logs`,
            );

            if (logsResult.success && logsResult.logs) {
              state.appLogs[app.id] = logsResult.logs;
            }
          } catch (error) {
            console.error(`Failed to fetch logs for ${app.id}:`, error);
            state.appLogs[app.id] = [];
          }
        }

        renderApplications();
      }
    } catch (error) {
      console.error("Failed to fetch error counts:", error);
    }
  }

  async function selectApplication(appId) {
    const state = getState();
    state.selectedAppId = appId;

    updateFilterVisibility();
    await loadLogs(appId);
    renderApplications();
    global.startAutoRefresh();
  }

  async function loadLogs(appId) {
    const state = getState();
    const elements = getElements();

    if (!appId || !state.currentEnvId || !elements.logsContent) return;

    elements.logsContent.innerHTML = `
      <div class="empty-state">
        <div class="spinner"></div>
        <p>Loading logs...</p>
      </div>
    `;

    try {
      let endpoint;

      if (state.currentEnvId === "local") {
        endpoint = "/api/local/environments/local/applications/local-app/logs";
      } else {
        endpoint = `/api/environments/${state.currentEnvId}/applications/${appId}/logs`;
      }

      if (state.startTime || state.endTime) {
        const params = [];
        if (state.startTime) params.push(`startTime=${state.startTime}`);
        if (state.endTime) params.push(`endTime=${state.endTime}`);
        if (params.length > 0) {
          endpoint += `?${params.join("&")}`;
        }
      }

      const result = await global.api("GET", endpoint);

      if (result.success) {
        const logs = result.logs || [];

        logs.sort((a, b) => {
          const timeA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
          const timeB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
          return timeB - timeA;
        });

        state.logs = logs;
        state.appLogs[appId] = logs;
        state.rawLogText = result.rawText || "";
        state.logAnalysis = result.analysis || {};

        renderLogs();
      } else {
        renderErrorBanner(result.error || "Failed to fetch logs");
      }
    } catch (error) {
      console.error("Failed to load logs:", error);
      renderErrorBanner("Error loading logs. Please try again.");
    }
  }

  global.MulesoftPanel = {
    renderApplications,
    getStatusClass,
    groupLogsByCorrelationId,
    renderLogs,
    loadApplications,
    loadLocalApplications,
    fetchErrorCounts,
    selectApplication,
    loadLogs,
  };

  global.renderApplications = renderApplications;
  global.getStatusClass = getStatusClass;
  global.groupLogsByCorrelationId = groupLogsByCorrelationId;
  global.renderLogs = renderLogs;
  global.loadApplications = loadApplications;
  global.loadLocalApplications = loadLocalApplications;
  global.fetchErrorCounts = fetchErrorCounts;
  global.selectApplication = selectApplication;
  global.loadLogs = loadLogs;
})(typeof window !== "undefined" ? window : this);
