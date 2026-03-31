/**
 * ServiceNow integration for ticket creation and management
 */

(function() {
  "use strict";

  // Fallback escapeHtml function if not available globally
  if (!window.escapeHtml) {
    window.escapeHtml = function(text) {
      if (!text) return "";
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
    };
  }

  // ServiceNow status mappings
  function getSnowStatusText(stateCode) {
    const states = {
      1: "New",
      2: "In Progress", 
      3: "On Hold",
      6: "Resolved",
      7: "Closed",
      8: "Canceled"
    };
    return states[String(stateCode)] || (stateCode ? String(stateCode) : "—");
  }

  function getSnowStatusClass(stateCode) {
    const classes = {
      1: "new",
      2: "inprogress",
      3: "onhold", 
      6: "resolved",
      7: "closed",
      8: "canceled"
    };
    return classes[String(stateCode)] || "pending";
  }

  // Custom loading modal for ServiceNow ticket creation
  function showServiceNowLoadingModal() {
    const modal = document.getElementById("serviceNowLoadingModal");
    modal.classList.remove("hidden");
  }

  function hideServiceNowLoadingModal() {
    const modal = document.getElementById("serviceNowLoadingModal");
    modal.classList.add("hidden");
  }

  // Success modal for ServiceNow operations
  function showSuccessModal(message, title = "Success") {
    const modal = document.createElement("div");
    modal.className = "event-details-modal";
    modal.innerHTML = `
      <div class="event-details-backdrop"></div>
      <div class="event-details-content">
        <div class="event-details-header">
          <h3>${title}</h3>
          <button class="btn-icon" onclick="this.parentElement.parentElement.parentElement.remove()">✕</button>
        </div>
        <div class="event-details-body">
          <div style="padding: 20px; text-align: center;">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2" style="margin-bottom: 16px;">
              <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            <h4 style="margin: 0 0 8px 0; color: #16a34a;">${title}</h4>
            <pre style="background: rgba(22,163,74,0.06); border: 1px solid #16a34a; border-radius: 6px; padding: 12px; text-align: left; white-space: pre-wrap; font-family: monospace; font-size: 13px;">${message}</pre>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    
    // Auto-close after 5 seconds
    setTimeout(() => {
      if (modal && modal.parentElement) {
        modal.remove();
      }
    }, 5000);
  }

  // Check if incident exists and show appropriate popup
  async function checkExistingIncidentAndShowPopup(eventId, appName, logs, extraWorkNotes = "") {
    console.log("[ServiceNow] Checking for existing incident for correlation ID:", eventId);

    try {
      showLoading();

      // Check if incident exists for this correlation ID
      const response = await api(
        "GET",
        `/api/incidents/by-correlation-id/${eventId}`,
      );

      if (!response.success) {
        hideLoading();
        console.error("[ServiceNow] Failed to check existing incident:", response);
        alert(`Failed to check existing incident: ${response.error || "Unknown error"}`);
        return;
      }

      hideLoading();

      if (response.incident) {
        // Incident exists - show update popup
        console.log("[ServiceNow] Found existing incident:", response.incident);
        showUpdateIncidentPopup(eventId, response.incident, appName, logs, extraWorkNotes);
      } else {
        // No incident exists - show create popup
        console.log("[ServiceNow] No existing incident found, showing create popup");
        showServiceNowTicketPopup(eventId, appName, logs, extraWorkNotes);
      }
    } catch (error) {
      hideLoading();
      console.error("[ServiceNow] Error checking existing incident:", error);
      alert(`Error checking existing incident: ${error.message}`);
    }
  }

  // Show popup to update existing incident
  function showUpdateIncidentPopup(eventId, incidentData, appName, logs, extraWorkNotes = "") {
    console.log("[ServiceNow] Showing update popup for incident:", incidentData);

    // Remove any existing popup
    const existingPopup = document.getElementById("serviceNowTicketPopup");
    if (existingPopup) {
      existingPopup.remove();
    }

    const baseWorkNotes = incidentData.work_notes || "";
    const appendedWorkNotes = extraWorkNotes
      ? `${baseWorkNotes}\n\n---\n${extraWorkNotes}`
      : baseWorkNotes;

    const modalHtml = `
      <div class="service-now-ticket-modal" id="serviceNowTicketPopup">
        <div class="service-now-backdrop"></div>
        <div class="service-now-content">
          <div class="service-now-header">
            <h3>Update ServiceNow Ticket</h3>
            <button class="btn-icon" id="closeServiceNowPopup" title="Close">✕</button>
          </div>
          <div class="service-now-body">
            <div class="ticket-info">
              <div class="info-row">
                <label>Incident Number:</label>
                <span>${window.escapeHtml(incidentData.incidentNumber || incidentData.incident_number || "N/A")}</span>
              </div>
              <div class="info-row">
                <label>Correlation ID:</label>
                <span>${window.escapeHtml(eventId)}</span>
              </div>
              <div class="info-row">
                <label>Application:</label>
                <span>${window.escapeHtml(appName || "N/A")}</span>
              </div>
              <div class="info-row">
                <label>Status:</label>
                <span class="service-now-status ${getSnowStatusClass(incidentData.incidentStatus)}">
                  ${getSnowStatusText(incidentData.incidentStatus)}
                </span>
              </div>
            </div>
            <div class="ticket-fields">
              <div class="field-group">
                <label for="shortDescription">Short Description:</label>
                <textarea id="shortDescription" class="ticket-textarea" rows="2" maxlength="80">${window.escapeHtml(incidentData.short_description || "")}</textarea>
                <div class="char-count"><span id="shortDescCount">0</span>/80</div>
              </div>
              <div class="field-group">
                <label for="description">Description:</label>
                <textarea id="description" class="ticket-textarea" rows="8">${window.escapeHtml(incidentData.description || "")}</textarea>
              </div>
              <div class="field-group">
                <label for="workNotes">Work Notes:</label>
                <textarea id="workNotes" class="ticket-textarea" rows="6">${window.escapeHtml(appendedWorkNotes || "")}</textarea>
              </div>
              <div class="field-group">
                <label for="rcaField" style="display:flex;align-items:center;gap:6px;">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#d97706" stroke-width="2.5">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  Root Cause Analysis:
                </label>
                <textarea id="rcaField" class="ticket-textarea rca-textarea" rows="4" placeholder="Describe the root cause of this error…">${window.escapeHtml(incidentData.rca || "")}</textarea>
              </div>
            </div>
          </div>
          <div class="service-now-footer">
            <button class="btn btn-secondary" id="cancelServiceNowTicket">Cancel</button>
            <button class="btn btn-primary" id="updateServiceNowTicket">Update Ticket</button>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML("beforeend", modalHtml);
    setupEventListeners(eventId, incidentData, true); // true = update mode
  }

  // Setup event listeners for popup
  function setupEventListeners(eventId, incidentData, isUpdate = false) {
    const closeBtn = document.getElementById("closeServiceNowPopup");
    const backdrop = document.querySelector("#serviceNowTicketPopup .service-now-backdrop");
    const cancelBtn = document.getElementById("cancelServiceNowTicket");
    const actionBtn = document.getElementById(isUpdate ? "updateServiceNowTicket" : "createServiceNowTicket");
    const shortDescTextarea = document.getElementById("shortDescription");

    if (closeBtn) {
      closeBtn.addEventListener("click", closeServiceNowTicketPopup);
    }

    if (backdrop) {
      backdrop.addEventListener("click", closeServiceNowTicketPopup);
    }

    if (cancelBtn) {
      cancelBtn.addEventListener("click", closeServiceNowTicketPopup);
    }

    if (actionBtn) {
      if (isUpdate) {
        actionBtn.addEventListener("click", () => updateExistingIncident(eventId, incidentData));
      } else {
        actionBtn.addEventListener("click", () => createServiceNowTicketFromPopup(eventId));
      }
    }

    if (shortDescTextarea) {
      const updateCharCount = () => {
        const count = shortDescTextarea.value.length;
        const countElement = document.getElementById("shortDescCount");
        if (countElement) {
          countElement.textContent = count;
        }
      };
      shortDescTextarea.addEventListener("input", updateCharCount);
      updateCharCount();
    }

    // ESC key to close
    const escKeyHandler = (e) => {
      if (e.key === "Escape") {
        closeServiceNowTicketPopup();
        document.removeEventListener("keydown", escKeyHandler);
      }
    };
    document.addEventListener("keydown", escKeyHandler);
  }

  // Update existing incident
  async function updateExistingIncident(eventId, incidentData) {
    try {
      const shortDescription = document.getElementById("shortDescription").value.trim();
      const description = document.getElementById("description").value.trim();
      const workNotes = document.getElementById("workNotes").value.trim();
      const rca = (document.getElementById("rcaField")?.value || "").trim();

      if (!shortDescription) {
        alert("Short Description is required.");
        return;
      }

      if (!description) {
        alert("Description is required.");
        return;
      }

      showServiceNowLoadingModal();

      const updateData = {
        correlationId: eventId,
        incidentData: {
          short_description: shortDescription,
          description: description,
          work_notes: workNotes,
          rca: rca,
          category: "software",
          subcategory: "integration",
          impact: "2",
          urgency: "2",
          severity: "3",
          contact_type: "monitoring",
          caller_id: "Mule agent",
          assignment_group: "Muledev",
        },
        incidentSysId: incidentData.incidentSysId || incidentData.sys_id,
      };

      console.log("[ServiceNow] Updating incident:", updateData);

      const response = await api("POST", "/api/incidents/update", updateData);

      hideServiceNowLoadingModal();

      if (response.success) {
        showSuccessModal(`ServiceNow incident ${incidentData.incidentNumber || incidentData.incident_number} updated successfully!`, "Incident Updated");
        closeServiceNowTicketPopup();
      } else {
        alert(`Failed to update ServiceNow incident: ${response.error || "Unknown error"}`);
      }
    } catch (error) {
      hideServiceNowLoadingModal();
      console.error("[ServiceNow] Error updating incident:", error);
      alert(`Error updating ServiceNow incident: ${error.message}`);
    }
  }
  function openServiceNowTicketFromPR(prUrl, branchName, ticketContext) {
    console.log("[ServiceNow] openServiceNowTicketFromPR called with:", { prUrl, branchName, ticketContext });
    
    const ctx = ticketContext || (window.state && window.state.ticketContextForPR);
    console.log("[ServiceNow] Resolved context:", ctx);
    
    if (!ctx || !ctx.eventId || !ctx.logs || ctx.logs.length === 0) {
      console.error("[ServiceNow] Missing correlation/log context for PR -> ServiceNow ticket:", ctx);
      alert("Missing correlation/log context for PR -> ServiceNow ticket.");
      return;
    }

    const extraWorkNotes = [
      `PR URL: ${prUrl}`,
      branchName ? `Branch: ${branchName}` : null,
    ]
      .filter(Boolean)
      .join("\n");

    const eventId = ctx.eventId;
    const appName = ctx.appName || "Unknown Application";

    console.log("[ServiceNow] Checking for existing incident for correlation ID:", eventId);

    // Check if incident exists for this correlation ID
    checkExistingIncidentAndShowPopup(eventId, appName, ctx.logs, extraWorkNotes);
  }

  async function createServiceNowTicket(eventId, appName, logs) {
    try {
      showLoading();

      // Prepare ticket data from correlation context

      const errorDetails = logs.map((log) => ({
        timestamp: log.timestamp || "N/A",

        message: log.message || "No message",

        exception: log.exception || null,

        component: log.component || "N/A",
      }));

      const ticketData = {
        correlationId: eventId,
        appName: appName,
        errorMessage: errorDetails[0]?.message || "No message",
        errorType: errorDetails[0]?.exception?.ExceptionType || "Unknown",
      };

      console.log(
        `[ServiceNow] Creating ticket for correlation ID: ${eventId}`,
        ticketData,
      );

      const response = await api(
        "POST",
        "/api/incidents/create-for-correlation-id",
        ticketData,
      );

      if (response.success) {
        const inc = response.incident || {};
        alert(
          `ServiceNow incident created!\n\nIncident: ${inc.incidentNumber || "N/A"}\nCorrelation ID: ${eventId}\nApplication: ${appName}`,
        );
        console.log(`[ServiceNow] Incident created: ${inc.incidentNumber}`);
      } else {
        alert(
          `Failed to create ServiceNow incident: ${response.error || "Unknown error"}`,
        );
      }
    } catch (error) {
      console.error("[ServiceNow] Error creating ticket:", error);

      alert(`Error creating ServiceNow ticket: ${error.message}`);
    } finally {
      hideLoading();
    }
  }

  async function showServiceNowTicketPopup(
    eventId,
    appName,
    logs,
    extraWorkNotes = "",
  ) {
    console.log("[ServiceNow Popup] showServiceNowTicketPopup called with:", {
      eventId,
      appName,
      logs,
    });

    try {
      showLoading();

      // Prepare ticket data from correlation context

      const errorDetails = logs.map((log) => ({
        timestamp: log.timestamp || "N/A",

        message: log.message || "No message",

        exception: log.exception || null,

        component: log.component || "N/A",
      }));

      const ticketData = {
        correlationId: eventId,

        appName: appName,

        errorLog: {
          timestamp: logs[0]?.timestamp || "N/A",

          message: logs[0]?.message || "No message",

          exception: logs[0]?.exception || null,

          component: logs[0]?.component || "N/A",

          error_details: errorDetails,
        },
      };

      console.log(
        `[ServiceNow Popup] Preparing ticket for correlation ID: ${eventId}`,
        ticketData,
      );

      // Fetch prepared incident data from backend

      console.log(
        "[ServiceNow Popup] Making API call to /api/incidents/prepare",
      );

      const response = await api("POST", "/api/incidents/prepare", ticketData);

      console.log("[ServiceNow Popup] API response:", response);

      console.log(
        "[ServiceNow Popup] response.preparedIncident:",
        response?.preparedIncident,
      );

      if (!response.success) {
        hideLoading();

        console.error(
          "[ServiceNow Popup] API response unsuccessful:",
          response,
        );

        alert(
          `Failed to prepare ServiceNow ticket: ${response.error || "Unknown error"}`,
        );

        return;
      }

      hideLoading();

      // Show popup with the prepared data

      console.log("[ServiceNow Popup] Calling renderServiceNowTicketPopup");

      // Handle different response structures
      let incidentData;

      if (response.preparedIncident) {
        incidentData = response.preparedIncident;
      } else if (response.data && response.data.preparedIncident) {
        incidentData = response.data.preparedIncident;
      } else if (response.data) {
        incidentData = response.data;
      } else if (response.incident) {
        incidentData = response.incident;
      } else {
        console.error(
          "[ServiceNow Popup] Unexpected response structure:",
          response,
        );

        alert("Unexpected response structure from server");

        return;
      }

      console.log("[ServiceNow Popup] Using incidentData:", incidentData);

      renderServiceNowTicketPopup(eventId, incidentData, appName, extraWorkNotes);
    } catch (error) {
      hideLoading();

      console.error("[ServiceNow Popup] Error preparing ticket:", error);
      popup.remove();
    }
  }

  async function createServiceNowTicketFromPopup(eventId) {
    try {
      const shortDescription = document
        .getElementById("shortDescription")
        .value.trim();

      const description = document.getElementById("description").value.trim();

      const workNotes = document.getElementById("workNotes").value.trim();

      const rca = (document.getElementById("rcaField")?.value || "").trim();

      if (!shortDescription) {
        alert("Short Description is required.");

        return;
      }

      if (!description) {
        alert("Description is required.");

        return;
      }

      showServiceNowLoadingModal();

      const ticketData = {
        correlationId: eventId,

        incidentData: {
          short_description: shortDescription,

          description: description,

          work_notes: workNotes,

          category: "software",

          subcategory: "integration",

          impact: "2",

          urgency: "2",

          severity: "3",

          contact_type: "monitoring",

          caller_id: "Mule agent",

          // Always set assignment_group=Muledev so the ticket is returned by
          // the Correlation IDs section query (assignment_group.name=Muledev).
          assignment_group: "Muledev",

          // Always include correlation_id so the ticket can be matched back
          // to the originating event in the Correlation IDs section.
          correlation_id: eventId,

          // Include RCA so it is stored in CSV and shown in the Correlation
          // IDs section dashboard.
          rca: rca,
        },
      };

      console.log(`[ServiceNow Popup] Creating ticket with data:`, ticketData);

      const response = await api("POST", "/api/incidents/create", ticketData);

      if (response.success) {
        closeServiceNowTicketPopup();

        showSuccessModal(
          `ServiceNow ticket created successfully!\n\nTicket Number: ${response.incident.incidentNumber}\nCorrelation ID: ${eventId}`,
        );

        console.log(
          `[ServiceNow Popup] Ticket created: ${response.incident.incidentNumber}`,
        );

        // Refresh the incident action container to show the new incident
        populateIncidentActionContainer(eventId);
      } else {
        alert(
          `Failed to create ServiceNow ticket: ${response.error || "Unknown error"}`,
        );
      }
    } catch (error) {
      console.error("[ServiceNow Popup] Error creating ticket:", error);

      alert(`Error creating ServiceNow ticket: ${error.message}`);
    } finally {
      hideServiceNowLoadingModal();
    }
  }

  // Make handleCorrelationAction globally available for inline onclick

  window.handleCorrelationAction = function () {
    console.log("[ServiceNow] handleCorrelationAction called");

    const ctx = window.__eventDetailsContext;

    if (!ctx) {
      console.error("[ServiceNow] No correlation context available");

      alert("No correlation context available.");

      return;
    }

    const eventId = ctx.logs?.[0]?.event_id;

    const appName = ctx.appName || "Unknown Application";

    console.log("[ServiceNow] Context:", ctx);

    console.log("[ServiceNow] EventId:", eventId);

    console.log("[ServiceNow] AppName:", appName);

    if (!eventId) {
      console.error("[ServiceNow] No event ID found in context");

      alert("No event ID found in context.");

      return;
    }

    // Show ServiceNow popup for ticket creation

    console.log("[ServiceNow] Calling showServiceNowTicketPopup");

    showServiceNowTicketPopup(eventId, appName, ctx.logs);
  };

  // Expose functions to global scope
  window.showServiceNowLoadingModal = showServiceNowLoadingModal;
  window.hideServiceNowLoadingModal = hideServiceNowLoadingModal;
  window.openServiceNowTicketFromPR = openServiceNowTicketFromPR;
  window.showServiceNowTicketPopup = showServiceNowTicketPopup;
  window.createServiceNowTicket = createServiceNowTicket;
  window.renderServiceNowTicketPopup = renderServiceNowTicketPopup;
  window.closeServiceNowTicketPopup = closeServiceNowTicketPopup;
  window.createServiceNowTicketFromPopup = createServiceNowTicketFromPopup;
  window.showUpdateIncidentPopup = showUpdateIncidentPopup;
  window.updateExistingIncident = updateExistingIncident;
  window.checkExistingIncidentAndShowPopup = checkExistingIncidentAndShowPopup;
  window.getSnowStatusText = getSnowStatusText;
  window.getSnowStatusClass = getSnowStatusClass;

})();