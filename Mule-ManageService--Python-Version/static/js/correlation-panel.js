(function (global) {
  "use strict";

  function getState() {
    return global.state || {};
  }

  function getElements() {
    const shared = global.elements || {};

    return {
      ...shared,
      correlationTab:
        shared.correlationTab || document.getElementById("correlationTab"),
      correlationContent:
        shared.correlationContent ||
        document.getElementById("correlationContent"),
    };
  }

  function escapeHtml(value) {
    if (typeof global.escapeHtml === "function") {
      return global.escapeHtml(value);
    }

    const div = document.createElement("div");
    div.textContent = value || "";
    return div.innerHTML;
  }

  function formatTimestamp(value) {
    if (typeof global.formatTimestamp === "function") {
      return global.formatTimestamp(value);
    }

    if (!value) return "";

    try {
      const date = new Date(value);
      if (isNaN(date.getTime())) return value;

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

  function getSnowStatusText(stateCode) {
    if (typeof global.getSnowStatusText === "function") {
      return global.getSnowStatusText(stateCode);
    }

    return stateCode ? String(stateCode) : "—";
  }

  function getSnowStatusClass(stateCode) {
    if (typeof global.getSnowStatusClass === "function") {
      return global.getSnowStatusClass(stateCode);
    }

    return "pending";
  }

  function getCorrelationStatuses(envId) {
    if (!envId) return {};

    try {
      const key = `correlationStatuses_${envId}`;
      const stored = localStorage.getItem(key);
      return stored ? JSON.parse(stored) : {};
    } catch (error) {
      console.error("Error loading correlation statuses:", error);
      return {};
    }
  }

  function callSyncStatusToBackend(envId, eventId, status) {
    if (typeof global.syncStatusToBackend === "function") {
      global.syncStatusToBackend(envId, eventId, status);
    }
  }

  function updateCorrelationStatus(envId, eventId, status) {
    if (!envId || !eventId) return;

    try {
      const key = `correlationStatuses_${envId}`;
      const statuses = getCorrelationStatuses(envId);

      statuses[eventId] = status;
      localStorage.setItem(key, JSON.stringify(statuses));
      callSyncStatusToBackend(envId, eventId, status);
    } catch (error) {
      console.error("Error updating correlation status:", error);
    }
  }

  function getStatusClassForStatus(status) {
    const statusMap = {
      pending: "status-pending",
      inprogress: "status-inprogress",
      complete: "status-complete",
      resolved: "status-resolved",
      closed: "status-closed",
      expected: "status-expected",
    };

    return statusMap[status] || "status-pending";
  }

  function updateErrorCardStyling(eventId, isExpected) {
    const errorCards = document.querySelectorAll(
      `[data-correlation-id="${eventId}"]`,
    );

    errorCards.forEach((card) => {
      if (isExpected) {
        card.classList.add("expected-error");
      } else {
        card.classList.remove("expected-error");
      }
    });
  }

  function refreshCurrentView() {
    const state = getState();

    if (state.currentTab === "mulesoft" && typeof global.renderLogs === "function") {
      global.renderLogs();
    } else if (
      state.currentTab === "correlation" &&
      typeof global.renderCorrelationIds === "function"
    ) {
      global.renderCorrelationIds();
    }
  }

  function handleExpectedErrorToggle(eventId) {
    const state = getState();
    const envId = state.currentEnvId || "default";
    const statuses = getCorrelationStatuses(envId);
    const currentStatus = statuses[eventId];

    if (currentStatus === "expected") {
      const shouldUnmark = confirm(
        "This correlation ID is already marked as an expected error. Do you want to unmark it?",
      );

      if (shouldUnmark) {
        delete statuses[eventId];
        localStorage.setItem(
          `correlationStatuses_${envId}`,
          JSON.stringify(statuses),
        );
        callSyncStatusToBackend(envId, eventId, "");
        updateErrorCardStyling(eventId, false);
        if (typeof global.closeEventDetailsModal === "function") {
          global.closeEventDetailsModal();
        }
        refreshCurrentView();
      } else if (typeof global.closeEventDetailsModal === "function") {
        global.closeEventDetailsModal();
      }

      return;
    }

    updateCorrelationStatus(envId, eventId, "expected");
    updateErrorCardStyling(eventId, true);
    if (typeof global.closeEventDetailsModal === "function") {
      global.closeEventDetailsModal();
    }
    refreshCurrentView();
  }

  function renderCorrelationIds() {
    const state = getState();
    const elements = getElements();

    if (!elements.correlationContent) return;

    if (!state.correlationData || state.correlationData.length === 0) {
      const source = state.correlationSource || "unknown";
      const sourceText =
        source === "local_file"
          ? "uploaded file"
          : source === "servicenow"
            ? "ServiceNow incidents"
            : "Anypoint Platform logs";

      elements.correlationContent.innerHTML = `
        <div class="no-logs-message">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
          <p>No correlation IDs found in ${sourceText}</p>
        </div>
      `;
      return;
    }

    const sorted = [...state.correlationData].sort((a, b) => {
      if (b.count !== a.count) return b.count - a.count;

      const timeA = a.latest_timestamp || "";
      const timeB = b.latest_timestamp || "";

      return timeB.localeCompare(timeA);
    });

    const envId = state.currentEnvId || "default";
    const statuses = getCorrelationStatuses(envId);

    const rowsHtml = sorted
      .map((item, index) => {
        const apps = (item.applications || []).join(", ");
        const timestamp = formatTimestamp(item.latest_timestamp || "");
        const lastMessage = (item.last_message || "").substring(0, 160);
        const currentStatus = statuses[item.event_id] || "pending";
        const statusClass = getStatusClassForStatus(currentStatus);
        const rcaText = (item.rca || "").trim();
        const rcaTruncated =
          rcaText.length > 160 ? `${rcaText.substring(0, 160)}…` : rcaText;
        const rcaHtml = rcaText
          ? `<span class="snow-rca-text" title="${escapeHtml(rcaText)}">${escapeHtml(rcaTruncated)}</span>`
          : '<span class="snow-no-ticket">—</span>';
        const assignmentGroupName = item.assignmentGroup || "—";
        const isMuledev = assignmentGroupName.toLowerCase() === "muledev";
        const assignmentGroupHtml = `<span class="snow-ag-badge${isMuledev ? " snow-ag-muledev" : ""}">${escapeHtml(assignmentGroupName)}</span>`;
        const ticketHtml = item.incidentNumber
          ? `<a class="snow-ticket-link" href="${state.servicenowBaseUrl}/incident.do?sys_id=${item.incidentSysId || ""}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()" title="Open ${item.incidentNumber} in ServiceNow">${item.incidentNumber}</a>`
          : '<span class="snow-no-ticket">—</span>';

        return `
        <div class="correlation-row" data-event-id="${escapeHtml(item.event_id)}" data-has-correlation-id="${item.has_correlation_id ? "true" : "false"}">
          <div class="correlation-cell index">#${index + 1}</div>
          <div class="correlation-cell id">
            <code class="correlation-id-badge event-id-clickable" data-event-id="${escapeHtml(item.event_id)}" title="${item.has_correlation_id ? `Click to view full chain - Full ID: ${escapeHtml(item.event_id)}` : `Incident number fallback (no correlation_id): ${escapeHtml(item.event_id)}`}">
              ${escapeHtml(item.event_id)}
            </code>
          </div>
          <div class="correlation-cell count">${item.count}</div>
          <div class="correlation-cell apps">${escapeHtml(apps || "—")}</div>
          <div class="correlation-cell ag">${assignmentGroupHtml}</div>
          <div class="correlation-cell time">${escapeHtml(timestamp || "—")}</div>
          <div class="correlation-cell status">
            <span class="snow-status-badge snow-status-${getSnowStatusClass(item.incidentStatus)}">${getSnowStatusText(item.incidentStatus)}</span>
          </div>
          <div class="correlation-cell ticket" onclick="event.stopPropagation()">
            ${ticketHtml}
          </div>
          <div class="correlation-cell rca" title="${escapeHtml(rcaText)}">
            ${rcaHtml}
          </div>
          <div class="correlation-cell message" title="${escapeHtml(item.last_message || "")}">
            ${escapeHtml(lastMessage || "—")}
          </div>
        </div>
      `;
      })
      .join("");

    elements.correlationContent.innerHTML = `
      <div class="logs-summary">
        <div class="logs-summary-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="9" cy="12" r="3"/>
            <circle cx="15" cy="12" r="3"/>
            <line x1="12" y1="12" x2="12" y2="12"/>
          </svg>
          <span>Correlation IDs (${state.correlationSource === "local_file" ? "Local File" : state.correlationSource === "servicenow" ? "ServiceNow" : "Environment"})</span>
        </div>
        <div class="logs-summary-count">${sorted.length} IDs</div>
      </div>
      <div class="correlation-table">
        <div class="correlation-header">
          <div class="correlation-cell index">#</div>
          <div class="correlation-cell id">Correlation ID</div>
          <div class="correlation-cell count">Errors</div>
          <div class="correlation-cell apps">Applications</div>
          <div class="correlation-cell ag">Assignment Group</div>
          <div class="correlation-cell time">Latest Timestamp</div>
          <div class="correlation-cell status">Status</div>
          <div class="correlation-cell ticket">ServiceNow Ticket</div>
          <div class="correlation-cell rca">Root Cause Analysis</div>
          <div class="correlation-cell message">Last Error Message</div>
        </div>
        <div class="correlation-body">
          ${rowsHtml}
        </div>
      </div>
    `;

    elements.correlationContent
      .querySelectorAll(".correlation-row")
      .forEach((row) => {
        row.addEventListener("click", async (event) => {
          if (
            event.target.classList.contains("status-select") ||
            event.target.closest(".status-select")
          ) {
            return;
          }

          const eventId = row.dataset.eventId;
          const hasCorrelationId = row.dataset.hasCorrelationId === "true";

          if (!hasCorrelationId) {
            alert(
              "This incident has no correlation_id in ServiceNow, so log chain details are not available.",
            );
            return;
          }

          if (eventId && typeof global.showEventDetails === "function") {
            await global.showEventDetails(eventId);
          }
        });
      });

    elements.correlationContent
      .querySelectorAll(".status-select")
      .forEach((select) => {
        select.addEventListener("change", (event) => {
          event.stopPropagation();

          const eventId = select.dataset.eventId;
          const newStatus = select.value;
          const currentEnvId = getState().currentEnvId || "default";

          updateCorrelationStatus(currentEnvId, eventId, newStatus);

          const row = select.closest(".correlation-row");
          const badge = row ? row.querySelector(".status-badge") : null;

          if (badge) {
            badge.textContent =
              newStatus.charAt(0).toUpperCase() + newStatus.slice(1);
            badge.className = `status-badge ${getStatusClassForStatus(newStatus)}`;
          }
        });
      });
  }

  async function loadCorrelationIds() {
    const state = getState();

    try {
      if (typeof global.showLoading === "function") {
        global.showLoading();
      }

      let endpoint = `/api/environments/${state.currentEnvId}/correlation-ids`;

      if (state.startTime || state.endTime) {
        const params = [];
        if (state.startTime) params.push(`startTime=${state.startTime}`);
        if (state.endTime) params.push(`endTime=${state.endTime}`);
        if (params.length > 0) {
          endpoint += `?${params.join("&")}`;
        }
      }

      const result = await global.api("GET", endpoint);

      if (result && result.success) {
        state.correlationSource = result.source || "global_storage";

        if (result.servicenow_url) {
          state.servicenowBaseUrl = result.servicenow_url;
        }

        state.correlationData = (result.correlationIds || []).map((item) => ({
          event_id: item.correlationId,
          raw_correlation_id: item.rawCorrelationId || "",
          has_correlation_id: Boolean(item.hasCorrelationId),
          count: 1,
          applications: item.apiName ? [item.apiName] : [],
          latest_timestamp: item.createdAt,
          last_message:
            item.shortDescription ||
            `Incident: ${item.incidentNumber || "N/A"} (Status: ${item.incidentStatus || "N/A"})`,
          incidentSysId: item.incidentSysId,
          incidentNumber: item.incidentNumber,
          incidentStatus: item.incidentStatus,
          assignmentGroup: item.assignmentGroup || "",
          assignedTo: item.assignedTo || "",
          rca: item.rca || "",
        }));
      } else {
        state.correlationData = [];
        state.correlationSource = "unknown";
        console.error(
          "Failed to load correlation IDs:",
          result && result.error,
        );
      }

      renderCorrelationIds();
    } catch (error) {
      console.error("Error loading correlation IDs:", error);
      state.correlationData = [];
      state.correlationSource = "error";
      renderCorrelationIds();
    } finally {
      if (typeof global.hideLoading === "function") {
        global.hideLoading();
      }
    }
  }

  global.CorrelationPanel = {
    getCorrelationStatuses,
    updateCorrelationStatus,
    getStatusClassForStatus,
    updateErrorCardStyling,
    refreshCurrentView,
    handleExpectedErrorToggle,
    renderCorrelationIds,
    loadCorrelationIds,
  };

  global.getCorrelationStatuses = getCorrelationStatuses;
  global.updateCorrelationStatus = updateCorrelationStatus;
  global.getStatusClassForStatus = getStatusClassForStatus;
  global.updateErrorCardStyling = updateErrorCardStyling;
  global.refreshCurrentView = refreshCurrentView;
  global.handleExpectedErrorToggle = handleExpectedErrorToggle;
  global.renderCorrelationIds = renderCorrelationIds;
  global.loadCorrelationIds = loadCorrelationIds;
})(typeof window !== "undefined" ? window : this);
