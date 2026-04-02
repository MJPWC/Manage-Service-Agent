// Dashboard Application

(function () {
  "use strict";

  // Theme Management

  function initTheme() {
    const savedTheme = localStorage.getItem("dashboard-theme") || "light";

    document.documentElement.setAttribute("data-theme", savedTheme);

    return savedTheme;
  }

  // Initialize theme immediately to prevent flash

  const initialTheme = initTheme();

  // State

  const state = {
    authenticated: false,

    githubAuthenticated: false,

    githubUsername: null, // GitHub username from backend session

    environments: [],

    currentEnvId: null,

    applications: [],

    errorCounts: {},

    filteredErrorCounts: {}, // Error counts filtered by time range

    appLogs: {}, // Store raw logs for each app

    selectedAppId: null,

    logs: [],

    rawLogText: "", // Store raw log text from API response

    logAnalysis: {}, // Store analysis data from API response

    theme: initialTheme,

    lastRefreshTime: null,

    autoRefreshInterval: null,

    autoRefreshEnabled: true,

    // Time range filtering

    startTime: null,

    endTime: null,

    // GitHub state

    githubRepos: [],

    selectedRepo: null,

    githubFiles: [],

    currentPath: "",

    selectedFile: null,

    pendingGitHubErrorContext: null, // { logs, appName, errorDescription } when arriving from Event Details
    ticketContextForPR: null, // Persist eventId/logs across EventDetails -> GitHub -> PR -> ServiceNow popup

    loadingGitHubRepos: false, // Prevent multiple simultaneous repo loading

    currentTab: "mulesoft",

    loadingRequests: 0,

    // Correlation IDs state

    correlationData: [],

    correlationSource: null, // 'local_file' or 'global_storage'

    servicenowBaseUrl: "https://dev339448.service-now.com", // ServiceNow instance URL
  };

  // DOM Elements - will be initialized after DOM is loaded

  let elements = {};

  // API Helper

  async function api(method, endpoint, data = null) {
    const options = {
      method,

      headers: { "Content-Type": "application/json" },
    };

    if (data) {
      options.body = JSON.stringify(data);
    }

    console.log(`[API] ${method} ${endpoint}`, data ? "with data" : "no data");

    try {
      const response = await fetch(endpoint, options);

      console.log(
        `[API] ${method} ${endpoint} - Response status: ${response.status}`,
      );

      const json = await response.json();

      console.log(`[API] ${method} ${endpoint} - Response JSON:`, json);

      if (!response.ok) {
        console.error(
          `[API] ${method} ${endpoint} - HTTP Error ${response.status}:`,

          json,
        );
      }

      return json;
    } catch (err) {
      console.error(`[API] ${method} ${endpoint} - Fetch error:`, err);

      throw err;
    }
  }

  // UI Helpers

  function showLoading() {
    window.AppLoadingUtils.acquire(state, elements.loadingOverlay);
  }

  function hideLoading() {
    window.AppLoadingUtils.release(state, elements.loadingOverlay);
  }

  // Render Functions

  // renderEnvironments function is now in anypoint.js
  const renderApplications = (...args) =>
    window.MulesoftPanel.renderApplications(...args);
  const getStatusClass = (...args) =>
    window.MulesoftPanel.getStatusClass(...args);
  const groupLogsByCorrelationId = (...args) =>
    window.MulesoftPanel.groupLogsByCorrelationId(...args);

  function extractApiAndFileFromFlowStack(eventId) {
    // Extract API name and file name from FlowStack analysis data

    console.log(`[extractApiAndFileFromFlowStack] eventId: ${eventId}`);

    const analysis = state.logAnalysis;

    if (!analysis || !analysis.error_location) {
      return { apiName: null, fileName: null };
    }

    // Try to find the error location for this specific event ID

    // For now, use the global error location from analysis

    // In a more sophisticated implementation, we might need to match by correlation ID

    const errorLocation = analysis.error_location;

    if (errorLocation && errorLocation.api_name && errorLocation.file_name) {
      return {
        apiName: errorLocation.api_name,

        fileName: errorLocation.file_name,
      };
    }

    return { apiName: null, fileName: null };
  }

  const renderLogs = (...args) => window.MulesoftPanel.renderLogs(...args);

  const MAX_SUMMARY_CLARITY_LEVEL = 5;

  function resolveEventDetailsSummaryBody(index) {
    const byId = document.getElementById("eventDetailsAiSummaryBody");

    if (byId) return byId;

    const modal = document.getElementById("eventDetailsModal");

    if (modal) {
      const container = modal.querySelector(".event-details-ai-summary");

      if (container) {
        const el = container.querySelector(`[data-log-index="${index}"]`);

        if (el) return el;
      }
    }

    if (elements.logsContent) {
      const el = elements.logsContent.querySelector(
        `[data-log-index="${index}"]`,
      );

      if (el) return el;
    }

    return (
      document.querySelector(`.summary-loading[data-log-index="${index}"]`) ||
      document.querySelector(`.summary-content[data-log-index="${index}"]`) ||
      document.querySelector(`.summary-error[data-log-index="${index}"]`)
    );
  }

  function updateAiSummaryRefreshButtonState() {
    const btn = document.getElementById("refreshAiErrorSummary");

    if (!btn) return;

    const ctx = window.__eventDetailsContext;

    const busy = !!(ctx && ctx.summaryRequestInFlight);

    const capped = !!(
      ctx && ctx.summaryClarityLevel >= MAX_SUMMARY_CLARITY_LEVEL
    );

    const hasPrior = !!(
      ctx &&
      (ctx.lastSummaryObservations || ctx.lastSummaryRca)
    );

    btn.disabled = busy || capped || !hasPrior;

    if (capped) {
      btn.title = "Maximum simplification passes reached";
    } else if (busy) {
      btn.title = "Generating…";
    } else if (!hasPrior) {
      btn.title = "Available after the first summary loads";
    } else {
      btn.title = "Simpler explanation (plain language)";
    }
  }

  async function generateErrorSummary(log, index, appName, options = {}) {
    const clarityLevel =
      options.clarityLevel !== undefined ? options.clarityLevel : 0;

    const previousObservations = options.previousObservations || "";

    const previousRca = options.previousRca || "";

    let summaryDiv = null;

    const requestContext = window.__eventDetailsContext || null;

    try {
      const exception = log.exception || null;

      let errorMessage = exception.Message || "";

      let errorType = "";

      console.log(
        `[GenerateSummary] Processing log ${index}. Exception:`,

        exception,
      );

      console.log(
        `[GenerateSummary] Log ${index}. Initial errorMessage:`,

        errorMessage.substring(0, 100),
      );

      // Extract error type and message from exception

      if (exception) {
        // Try multiple field names with Message priority
        errorMessage = "";
        let elementInfo = "";

        // Priority 1: Message field (most descriptive)

        if (exception.Message) {
          errorMessage = exception.Message;
        } else if (exception.message) {
          errorMessage = exception.message;
        }

        // Priority 2: Element/Element DSL fields (for context)

        if (exception.Element) {
          elementInfo = `Element: ${exception.Element}`;
        }

        if (exception["Element DSL"]) {
          elementInfo += elementInfo ? " | " : "";

          elementInfo += `Element DSL: ${exception["Element DSL"]}`;
        }

        // Combine Message and Element info for complete context

        if (errorMessage && elementInfo) {
          errorMessage = `${errorMessage} | ${elementInfo}`;
        }

        // Fallback to ExceptionType if no message found

        if (!errorMessage && !elementInfo) {
          if (exception.ExceptionType) {
            errorType = exception.ExceptionType;
          } else if (exception["Error type"]) {
            errorType = exception["Error type"];
          }

          errorMessage = `Error Type: ${errorType}`;
        }
      }

      console.log(
        `[GenerateSummary] Log ${index}. After exception extraction - errorType: "${errorType}", errorMessage: "${errorMessage.substring(0, 100)}"`,
      );

      // If no ExceptionType found, try to extract error type patterns from message

      if (!errorType && errorMessage) {
        // Look for ERROR_TYPE:XXXXX pattern (case-insensitive)

        const errorTypeMatch = errorMessage.match(
          /ERROR_TYPE\s*:\s*([A-Z_0-9]+)/i,
        );

        if (errorTypeMatch) {
          // Keep the full "ERROR_TYPE:XXXXX" format as the key

          errorType = `ERROR_TYPE:${errorTypeMatch[1]}`;
        } else {
          // Look for NAMESPACE:ERROR_CODE pattern - case-insensitive and supports any case

          // Matches: SALESFORCE:INVALID_INPUT, jira:issue, azure:exception, servicenow:table, etc.

          const colonMatch = errorMessage.match(/([a-z0-9_-]+):([a-z0-9_-]+)/i);

          if (colonMatch) {
            errorType = `${colonMatch[1]}:${colonMatch[2]}`;
          } else {
            // Fallback to first 50 chars of message if no pattern found

            // Extract from the beginning of combined message (before any | separators)

            const baseMessage =
              errorMessage.split("|")[0]?.trim() || errorMessage;

            errorType = baseMessage.substring(0, 50) || "Unknown Error";
          }
        }
      }

      if (!errorType) {
        errorType = "Unknown Error";
      }

      if (!errorMessage) {
        console.log("[Summary] Skipping log " + index + " - no error message");

        console.log(
          `[Summary] Log ${index}: log.message="${log.message}", exception.Message="${exception?.Message}"`,
        );

        // Even if no message, try to generate summary from error type if available

        if (!errorType || errorType === "Unknown Error") {
          return;
        }

        // Use error type as message if no message found

        errorMessage = `Error Type: ${errorType}`;
      }

      // CRITICAL: Extract the actual API name from the log, NOT the file name

      // Use helper function to get the real application/API name

      const flowStackInfo = extractApiAndFileFromFlowStack(log.event_id);

      let actualAppName = appName; // fallback to file name

      if (flowStackInfo && flowStackInfo.apiName) {
        actualAppName = flowStackInfo.apiName;
      } else if (
        log.application &&
        log.application !== "DefaultExceptionListener"
      ) {
        actualAppName = log.application;
      } else if (exception) {
        const elementField = exception.Element;

        const elementDslField = exception["Element DSL"];

        const fieldToUse = elementField || elementDslField;

        if (fieldToUse) {
          const apiName = extractApiNameFromElement(fieldToUse);

          if (apiName && apiName !== "Unknown API") {
            actualAppName = apiName;
          }
        }
      }

      console.log(
        `[Summary] Log ${index}: File name: "${appName}", Actual API name: "${actualAppName}"`,
      );

      console.log(`[Summary] Log ${index}: Sending API request...`);

      console.log(
        `[Summary] Log ${index}: ErrorType="${errorType}", MessageLength=${errorMessage.length}`,
      );

      console.log(
        `[Summary] Log ${index}: Message preview="${errorMessage.substring(0, 150)}"`,
      );

      summaryDiv = resolveEventDetailsSummaryBody(index);

      if (summaryDiv) {
        summaryDiv.className = "summary-loading";

        summaryDiv.innerHTML = "<span>⟳</span> Analyzing error with AI...";
      }

      if (requestContext && requestContext === window.__eventDetailsContext) {
        requestContext.summaryRequestInFlight = true;
      }

      updateAiSummaryRefreshButtonState();

      // Call endpoint with all available error context including raw log text

      const requestPayload = {
        error_type: errorType,

        error_message: errorMessage,

        error_log: log, // full log object

        exception: exception, // exception details if present

        app_name: actualAppName,

        raw_log_text: state.rawLogText || "", // Include complete raw log text from API

        clarity_level: clarityLevel,
      };

      if (clarityLevel > 0 && (previousObservations || previousRca)) {
        requestPayload.previous_observations = previousObservations;

        requestPayload.previous_rca = previousRca;
      }

      console.log(`[Summary] Log ${index}: Request payload:`, requestPayload);

      const result = await api("POST", "/api/error/summary", requestPayload);

      console.log(`[Summary] Log ${index}: Raw API Response:`, result);

      console.log(
        `[Summary] Log ${index}: Response structure - success:`,

        result.success,

        ", summary exists:",

        !!result.summary,

        ", observations exists:",

        !!result.observations,

        ", observation exists:",

        !!result.observation,

        ", rca exists:",

        !!result.rca,
      );

      // Debug: Log the complete result object

      console.log(`[Summary] Log ${index}: Complete API response:`, result);

      // Debug: Log the exact condition check

      const hasObservations = !!(result.observations || result.observation);

      const hasRca = !!result.rca;

      const hasStructuredContent = hasObservations || hasRca;

      console.log(
        `[Summary] Log ${index}: Condition check - hasObservations: ${hasObservations}, hasRca: ${hasRca}, hasStructuredContent: ${hasStructuredContent}`,
      );

      console.log(
        `[Summary] Log ${index}: result.success: ${result.success}, going into structured content: ${result.success && hasStructuredContent}`,
      );

      if (!result.success) {
        console.error(
          `[Summary] Log ${index}: API returned error:`,

          result.error,
        );
      }

      if (!document.getElementById("eventDetailsModal")) {
        return;
      }

      if (!summaryDiv) {
        summaryDiv = resolveEventDetailsSummaryBody(index);
      }

      if (summaryDiv) {
        let displayHtml = "";

        console.log(
          `[Summary] Log ${index}: summaryDiv found, proceeding with content rendering`,
        );

        // Check the condition again for debugging

        const shouldUseStructured =
          result.success &&
          (result.observations || result.observation || result.rca);

        console.log(
          `[Summary] Log ${index}: Should use structured content: ${shouldUseStructured}`,
        );

        if (shouldUseStructured) {
          summaryDiv.className = "summary-content";

          console.log(
            `[Summary] Log ${index}: ✓ SUCCESS - Setting structured summary content`,
          );

          // Format as structured sections

          displayHtml = '<div class="summary-structured">';

          // Check for both observations (plural) and observation (singular)

          const observations = result.observations || result.observation;

          if (observations) {
            displayHtml += '<div class="summary-section">';

            displayHtml += '<h4 class="summary-heading">Observations</h4>';

            displayHtml +=
              '<p class="summary-text">' + escapeHtml(observations) + "</p>";

            displayHtml += "</div>";
          }

          if (result.rca) {
            displayHtml += '<div class="summary-section">';

            displayHtml += '<h4 class="summary-heading">RCA</h4>';

            displayHtml +=
              '<p class="summary-text">' + escapeHtml(result.rca) + "</p>";

            displayHtml += "</div>";
          }

          displayHtml += "</div>";

          console.log(
            `[Summary] Log ${index}: Formatted structured summary (${displayHtml.length} chars)`,
          );
        } else if (result.success && result.summary) {
          // Fallback for old format

          summaryDiv.className = "summary-content";

          console.log(
            `[Summary] Log ${index}: ✓ SUCCESS - Setting legacy summary content`,
          );

          console.log(
            `[Summary] Log ${index}: Raw summary length: ${result.summary.length}, preview: "${result.summary.substring(0, 80)}..."`,
          );

          const formatted = formatAnalysis(result.summary);

          if (formatted && formatted.length > 0) {
            displayHtml = formatted;

            console.log(
              `[Summary] Log ${index}: Using formatted analysis (${formatted.length} chars)`,
            );
          } else {
            displayHtml = `<p>${escapeHtml(result.summary)}</p>`;

            console.warn(
              `[Summary] Log ${index}: formatAnalysis returned empty or falsy, wrapping raw summary`,
            );
          }
        } else {
          summaryDiv.className = "summary-error";

          const errorMsg = result.error || "Failed to generate summary";

          console.error(`[Summary] Log ${index}: ✗ API ERROR: ${errorMsg}`);

          console.error(
            `[Summary] Log ${index}: Response fields - success: ${result.success}, observations: ${!!result.observations}, rca: ${!!result.rca}, summary: ${!!result.summary}, error: ${result.error}`,
          );

          // Show error-type specific fallback message

          displayHtml = `<div class="summary-structured">`;

          displayHtml += `<div class="summary-section">`;

          displayHtml += `<h4 class="summary-heading">Observations</h4>`;

          displayHtml += `<p class="summary-text">Error Type: ${escapeHtml(errorType)}<br/>Application: ${escapeHtml(appName)}</p>`;

          displayHtml += `</div>`;

          displayHtml += `<div class="summary-section">`;

          displayHtml += `<h4 class="summary-heading">Issue Details</h4>`;

          displayHtml += `<p class="summary-text">${escapeHtml(errorMsg)}</p>`;

          displayHtml += `</div>`;

          displayHtml += `</div>`;
        }

        // ALWAYS set innerHTML regardless

        console.log(
          `[Summary] Log ${index}: Setting innerHTML with ${displayHtml.length} chars`,
        );

        console.log(
          `[Summary] Log ${index}: About to set innerHTML. Current summaryDiv:`,
          summaryDiv,
        );

        console.log(
          `[Summary] Log ${index}: displayHtml content:`,
          displayHtml,
        );

        summaryDiv.innerHTML = displayHtml;

        console.log(
          `[Summary] Log ${index}: innerHTML set. New summaryDiv.innerHTML:`,
          summaryDiv.innerHTML,
        );
      } else {
        console.error(
          `[Summary] Log ${index}: summaryDiv still not found after all search attempts!`,
        );
      }

      if (
        typeof result !== "undefined" &&
        result &&
        result.success &&
        (result.observations || result.observation || result.rca)
      ) {
        const ctx = window.__eventDetailsContext;

        if (ctx) {
          const obs = result.observations || result.observation;

          if (obs) ctx.lastSummaryObservations = obs;

          if (result.rca) ctx.lastSummaryRca = result.rca;
        }
      }
    } catch (err) {
      console.error("[Summary] Exception:", err);

      console.error("[Summary] Stack:", err.stack);

      summaryDiv = resolveEventDetailsSummaryBody(index);

      if (!summaryDiv) {
        summaryDiv = elements.logsContent.querySelector(
          `.summary-loading[data-log-index="${index}"]`,
        );
      }

      if (!summaryDiv) {
        summaryDiv = document.querySelector(
          `.summary-loading[data-log-index="${index}"]`,
        );
      }

      if (summaryDiv) {
        const exception = log.exception || null;

        const message =
          exception && exception.Message ? exception.Message : log.message;

        summaryDiv.className = "summary-content";

        summaryDiv.innerHTML = `<p>${escapeHtml(message || "Error occurred while generating summary")}</p>`;
      }
    } finally {
      if (requestContext && requestContext === window.__eventDetailsContext) {
        requestContext.summaryRequestInFlight = false;
      }

      updateAiSummaryRefreshButtonState();
    }
  }

  function renderErrorBanner(message) {
    window.AppRefreshUtils.renderErrorBanner(elements, message);
  }

  function escapeHtml(text) {
    if (!text) return "";

    const div = document.createElement("div");

    div.textContent = text;

    return div.innerHTML;
  }

  function extractFilenameFromElement(elementStr) {
    if (!elementStr || typeof elementStr !== "string") return "";

    // Common Mule format examples:

    // - "... @ sf-agent-api:Agent-API.xml:17"

    const afterAt = elementStr.includes("@")
      ? elementStr.split("@").pop().trim()
      : elementStr.trim();

    const cleaned = afterAt.replace(/\s*\([^)]*\)\s*$/, "").trim();

    const parts = cleaned

      .split(":")

      .map((p) => p.trim())

      .filter(Boolean);

    let candidate = parts.find(
      (p) => /\.[a-zA-Z0-9]+$/.test(p) && !/^\d+$/.test(p),
    );

    // If no candidate found with extension, try to extract from the first part

    if (!candidate && parts.length > 0) {
      // Look for any filename pattern in the first part

      const filenameMatch = parts[0].match(/([^\/\\:]+\.[a-zA-Z0-9]+)$/);

      if (filenameMatch) {
        candidate = filenameMatch[1];
      } else {
        // Try to extract after the last colon in the first part

        const lastColonIndex = parts[0].lastIndexOf(":");

        if (lastColonIndex !== -1 && lastColonIndex < parts[0].length - 1) {
          const afterColon = parts[0].substring(lastColonIndex + 1).trim();

          if (afterColon && /\.[a-zA-Z0-9]+$/.test(afterColon)) {
            candidate = afterColon;
          }
        }

        if (!candidate) {
          candidate = parts[0];
        }
      }
    }

    // Fallback to the last path-ish token if nothing matched

    if (!candidate) {
      candidate = parts.length ? parts[0] : cleaned;
    }

    // If candidate includes a path, take the basename

    const pathParts = candidate.split(/[/\\]/);

    return (pathParts[pathParts.length - 1] || "").trim();
  }

  // Extract error location details from Element field

  function extractErrorLocation(elementStr) {
    if (!elementStr || typeof elementStr !== "string") {
      return {
        processorPath: "N/A",

        fileName: "N/A",

        lineNumber: "N/A",

        processorType: "N/A",

        fullLocation: "N/A",
      };
    }

    // Example format: "sf-process-apiFlow/processors/5 @ sf-process-api:sf-process-api.xml:43 (Request)"

    // Extract processor path (before @)

    const processorPath = elementStr.includes("@")
      ? elementStr.split("@")[0].trim()
      : "N/A";

    // Extract the part after @

    const afterAt = elementStr.includes("@")
      ? elementStr.split("@").pop().trim()
      : elementStr.trim();

    // Extract processor type (inside parentheses)

    const processorTypeMatch = afterAt.match(/\(([^)]+)\)/);

    const processorType = processorTypeMatch
      ? processorTypeMatch[1].trim()
      : "N/A";

    // Remove processor type from string for parsing the rest

    const withoutType = afterAt.replace(/\s*\([^)]*\)\s*$/, "").trim();

    // Split by colon: namespace:filename:lineNumber

    const parts = withoutType

      .split(":")

      .map((p) => p.trim())

      .filter(Boolean);

    let fileName = "N/A";

    let lineNumber = "N/A";

    // Extract filename and line number

    for (let i = 0; i < parts.length; i++) {
      if (/\.[a-zA-Z0-9]+$/.test(parts[i])) {
        // Has file extension

        fileName = parts[i];

        if (i + 1 < parts.length && /^\d+$/.test(parts[i + 1])) {
          lineNumber = parts[i + 1];
        }

        break;
      }
    }

    // Build a readable full location string

    let fullLocation = "";

    if (processorPath && processorPath !== "N/A") {
      fullLocation += processorPath;
    }

    if (lineNumber && lineNumber !== "N/A") {
      fullLocation += ` at line ${lineNumber}`;
    }

    if (processorType && processorType !== "N/A") {
      fullLocation += ` (${processorType} processor)`;
    }

    if (fileName && fileName !== "N/A") {
      fullLocation += ` in ${fileName}`;
    }

    return {
      processorPath: processorPath || "N/A",

      fileName: fileName,

      lineNumber: lineNumber,

      processorType: processorType,

      fullLocation: fullLocation || "N/A",
    };
  }

  // Analyze error chain to explain if error originated here or in upstream/downstream APIs

  function analyzeErrorChain(eventId, currentAppName, allLogs) {
    if (!eventId || !allLogs || allLogs.length === 0) {
      return {
        origin: "Unknown",

        chain: "Unable to determine error chain",

        explanation: "Insufficient data to analyze error propagation",
      };
    }

    // Helper function to extract API name from log's FlowStack analysis

    function getApiNameFromLog(log) {
      // First try to get API name from FlowStack analysis for this specific log

      const flowStackInfo = extractApiAndFileFromFlowStack(log.event_id);

      if (
        flowStackInfo &&
        flowStackInfo.apiName &&
        flowStackInfo.apiName !== "Unknown API"
      ) {
        return flowStackInfo.apiName;
      }

      // Fallback to application name if available

      if (log.application && log.application !== "DefaultExceptionListener") {
        return log.application;
      }

      // Final fallback to component name

      const elementField = log.exception?.Element;

      const elementDslField = log.exception?.["Element DSL"];

      const fieldToUse = elementField || elementDslField;

      if (fieldToUse) {
        const apiName = extractApiNameFromElement(fieldToUse);

        if (apiName && apiName !== "Unknown API") {
          return apiName;
        }
      }

      return "Unknown API";
    }

    // Helper function to extract flow name from Element field or FlowStack

    // Example: "invoke-ais-employment-sapi-for-create-referral/processors/2 @ api-name:file.xml:line" → "invoke-ais-employment-sapi-for-create-referral"

    function getFlowNameFromLog(log) {
      let flowName = null;

      // First, try to extract from FlowStack via state analysis

      const analysis = state.logAnalysis;

      if (analysis && analysis.flow_stack && analysis.flow_stack.length > 0) {
        const flowStackEntry = analysis.flow_stack[0];

        if (flowStackEntry.flow_name) {
          flowName = flowStackEntry.flow_name;

          console.log(
            "[ErrorChain] Flow name from FlowStack analysis:",

            flowName,
          );

          return flowName;
        }
      }

      // Try to extract from raw FlowStack text if available

      if (log.flow_stack) {
        // Pattern: "at flow-name(" or just extract the first word-like sequence

        const fsMatch = log.flow_stack.match(/at\s+([a-zA-Z0-9_-]+)/);

        if (fsMatch && fsMatch[1]) {
          console.log(
            "[ErrorChain] Flow name from flow_stack field:",

            fsMatch[1],
          );

          return fsMatch[1];
        }
      }

      // Try Element field as fallback

      const elementField = log.exception?.Element;

      const elementDslField = log.exception?.["Element DSL"];

      let fieldToUse = elementField || elementDslField;

      if (!fieldToUse) {
        console.log("[ErrorChain] No Element or Element DSL field found");

        return null;
      }

      console.log(
        "[ErrorChain] Extracting flow name from Element field:",

        fieldToUse.substring(0, 100),
      );

      // Remove leading "at " if present

      fieldToUse = fieldToUse.replace(/^\s*at\s+/, "").trim();

      // Pattern: "flow-name(flow-name/processors/N @ ...)" or "flow-name/processors/N @..."

      // First try: stop at "(" - handles: "flow-name(flow-name/processors/..."

      const parenMatch = fieldToUse.match(/^([a-zA-Z0-9_-]+)\s*\(/);

      if (parenMatch && parenMatch[1]) {
        flowName = parenMatch[1];

        console.log("[ErrorChain] Flow name from ( delimiter:", flowName);

        return flowName;
      }

      // Second try: stop at "/processors/" - handles: "flow-name/processors/N"

      const processorMatch = fieldToUse.match(
        /^([a-zA-Z0-9_-]+)\/processors\/\d+/,
      );

      if (processorMatch && processorMatch[1]) {
        flowName = processorMatch[1];

        console.log(
          "[ErrorChain] Flow name from /processors/ delimiter:",

          flowName,
        );

        return flowName;
      }

      // Third try: stop at " @" - handles: "flow-name @"

      const atMatch = fieldToUse.match(/^([a-zA-Z0-9_-]+)\s*@/);

      if (atMatch && atMatch[1]) {
        flowName = atMatch[1];

        console.log("[ErrorChain] Flow name from @ delimiter:", flowName);

        return flowName;
      }

      // Fourth try: just get the first word (alphanumeric, underscore, hyphen)

      const firstPartMatch = fieldToUse.match(/^([a-zA-Z0-9_-]+)/);

      if (firstPartMatch && firstPartMatch[1] && firstPartMatch[1] !== "at") {
        flowName = firstPartMatch[1];

        console.log(
          "[ErrorChain] Flow name from first word pattern:",

          flowName,
        );

        return flowName;
      }

      console.log(
        "[ErrorChain] Could not extract flow name from Element field",
      );

      return null;
    }

    // Group logs by extracted API name from FlowStack

    const appErrors = {};

    allLogs.forEach((log) => {
      const appName = getApiNameFromLog(log);

      if (!appName) return; // Skip logs without valid API names

      if (!appErrors[appName]) {
        appErrors[appName] = [];
      }

      appErrors[appName].push(log);
    });

    // If no valid API names found, return unknown

    if (Object.keys(appErrors).length === 0) {
      return {
        origin: "Unknown API",

        chain: "Unable to determine error origin",

        explanation: "Could not extract API information from error logs",

        affectedApps: [],
      };
    }

    // Find the first application (earliest error = root cause)

    let rootCauseApp = null;

    let rootCauseLog = null;

    let earliestTime = null;

    Object.keys(appErrors).forEach((appName) => {
      const logs = appErrors[appName];

      logs.forEach((log) => {
        const logTime = new Date(log.timestamp || log.date || 0).getTime();

        if (earliestTime === null || logTime < earliestTime) {
          earliestTime = logTime;

          rootCauseApp = appName;

          rootCauseLog = log;
        }
      });
    });

    const appCount = Object.keys(appErrors).length;

    let origin = rootCauseApp || "Unknown";

    let chain = "";

    let explanation = "";

    // Extract flow names from logs

    const rootFlowName = rootCauseLog ? getFlowNameFromLog(rootCauseLog) : null;

    const currentApiName =
      allLogs.length > 0 ? getApiNameFromLog(allLogs[0]) : null;

    const currentFlowName =
      allLogs.length > 0 ? getFlowNameFromLog(allLogs[0]) : null;

    console.log(
      "[ErrorChain] Root Flow Name:",

      rootFlowName,

      "Root API Name:",

      rootCauseApp,

      "App Count:",

      appCount,
    );

    console.log(
      "[ErrorChain] Current API Name:",

      currentApiName,

      "Current Flow Name:",

      currentFlowName,
    );

    if (rootCauseLog && rootCauseLog.exception) {
      console.log(
        "[ErrorChain] Root Cause Log Element:",

        rootCauseLog.exception.Element,
      );
    }

    if (appCount === 1) {
      // Error only in one API

      origin = rootCauseApp;

      chain = `Error originated in ${rootCauseApp}`;

      // Only use flow name if we actually found it - never use API name as fallback for flow name

      const flowDisplay = rootFlowName
        ? rootFlowName
        : `${rootCauseApp} (flow unknown)`;

      explanation = `This is the root cause - the error occurred directly in the ${flowDisplay} flow.`;

      console.log(
        "[ErrorChain] Single app case - rootFlowName:",

        rootFlowName,

        "flowDisplay:",

        flowDisplay,
      );
    } else if (rootCauseApp === currentApiName) {
      // Current API is the root cause

      const downstreamApps = Object.keys(appErrors).filter(
        (app) => app !== rootCauseApp,
      );

      origin = rootCauseApp;

      chain = `${rootCauseApp} → ${downstreamApps.join(" → ")}`;

      // Only use flow name if we actually found it

      const flowDisplay = rootFlowName
        ? rootFlowName
        : `${rootCauseApp} (flow unknown)`;

      explanation = `Root error occurred in the ${flowDisplay} flow of ${rootCauseApp}. This error was propagated to ${downstreamApps.length === 1 ? downstreamApps[0] : "other APIs"}.`;

      console.log(
        "[ErrorChain] Root cause API case - rootFlowName:",

        rootFlowName,

        "flowDisplay:",

        flowDisplay,
      );
    } else {
      // Current API is downstream - the error originated elsewhere

      origin = rootCauseApp;

      chain = `${rootCauseApp} → ${currentApiName || "downstream"}`;

      // Only use flow name if we actually found it

      const rootFlowDisplay = rootFlowName
        ? rootFlowName
        : `${rootCauseApp} (flow unknown)`;

      explanation = `This error originated in the ${rootFlowDisplay} flow of ${rootCauseApp} (upstream). The receiving API tried to call it and received the error.`;

      console.log(
        "[ErrorChain] Downstream case - rootFlowName:",

        rootFlowName,

        "rootFlowDisplay:",

        rootFlowDisplay,
      );
    }

    return {
      origin: origin,

      chain: chain,

      explanation: explanation,

      affectedApps: Object.keys(appErrors),
    };
  }

  function formatTimestamp(isoString) {
    if (!isoString) return "";

    try {
      const date = new Date(isoString);

      if (isNaN(date.getTime())) return isoString;

      const options = {
        year: "numeric",

        month: "short",

        day: "2-digit",

        hour: "2-digit",

        minute: "2-digit",

        second: "2-digit",

        hour12: false,
      };

      return date.toLocaleString("en-US", options);
    } catch {
      return isoString;
    }
  }

  // Data Fetching

  async function checkSession() {
    try {
      const result = await api("GET", "/api/session");

      state.authenticated = result.authenticated;

      state.githubAuthenticated = result.github_authenticated || false;

      // Only set environments from session if we have a selected business group
      if (state.selectedBusinessGroup) {
        state.environments = result.environments || [];
      } else {
        state.environments = [];
      }

      state.business_groups = result.business_groups || [];

      state.githubUsername = result.github_username || "MJPWC"; // Get GitHub username from backend

      // Handle local file authentication

      if (result.local_file_loaded) {
        // Add local environment if not present

        const localEnv = {
          id: "local",

          name: result.local_app_name || "Local Log File",

          type: "local",
        };

        // Check if local environment already exists

        const hasLocal = state.environments.some((env) => env.id === "local");

        if (!hasLocal) {
          state.environments.push(localEnv);
        }

        // Auto-select local environment

        state.currentEnvId = "local";

        // Load local applications immediately

        await loadLocalApplications();
      }

      // Update authentication indicators

      updateAuthIndicators(state.authenticated, state.githubAuthenticated);

      // Update business group display
      updateBusinessGroupDisplay(result.business_groups);

      // Show/hide local file controls

      if (elements.localFileControls) {
        // Show local file controls if either:

        // 1. Local file is currently loaded, OR

        // 2. Current environment is "local" (user logged in via local file)

        const shouldShow =
          result.local_file_loaded || state.currentEnvId === "local";

        console.log("Local file controls visibility:", {
          result_local_file_loaded: result.local_file_loaded,

          currentEnvId: state.currentEnvId,

          shouldShow,

          localFileControlsExists: !!elements.localFileControls,
        });

        elements.localFileControls.style.display = shouldShow
          ? "block"
          : "none";
      }

      // Run button state verification after authentication state is determined

      setTimeout(() => {
        resetAllButtonStates();
      }, 200);

      // Show/hide refresh controls based on authentication mode

      if (elements.refreshBtn && elements.lastRefreshDisplay) {
        if (result.local_file_loaded) {
          // Local file mode: hide refresh button and last refresh display

          elements.refreshBtn.style.display = "none";

          elements.lastRefreshDisplay.style.display = "none";
        } else {
          // Anypoint/Connected App mode: show refresh controls

          elements.refreshBtn.style.display = "flex";

          elements.lastRefreshDisplay.style.display = "block";
        }
      }

      if (state.authenticated) {
        elements.refreshBtn.disabled = false;

        if (window.renderEnvironments) window.renderEnvironments();

        // Setup business group and environment handlers from anypoint.js
        if (window.setupBusinessGroupAndEnvironmentHandlers) {
          window.setupBusinessGroupAndEnvironmentHandlers();
        }
      }
    } catch (err) {
      console.error("Session check failed:", err);
    }
  }



  // updateBusinessGroupDisplay function is now in anypoint.js

  function resetAllButtonStates() {
    console.log("Resetting all button states...");

    // Get authentication state

    const isAuthenticated = state.authenticated;

    const isGithubAuth = state.githubAuthenticated;

    console.log("Authentication state:", { isAuthenticated, isGithubAuth });

    // Environment selector

    const envSelect = document.getElementById("envSelect");

    if (envSelect) {
      const shouldEnable = isAuthenticated || state.environments.length > 0;

      envSelect.disabled = !shouldEnable;

      envSelect.style.pointerEvents = shouldEnable ? "auto" : "none";

      envSelect.style.opacity = shouldEnable ? "1" : "0.5";

      envSelect.style.cursor = shouldEnable ? "pointer" : "not-allowed";

      console.log("Environment select:", {
        disabled: envSelect.disabled,
        shouldEnable,
      });
    }

    // Refresh button

    const refreshBtn = document.getElementById("refreshBtn");

    if (refreshBtn) {
      refreshBtn.disabled = !isAuthenticated;

      refreshBtn.style.pointerEvents = isAuthenticated ? "auto" : "none";

      refreshBtn.style.opacity = isAuthenticated ? "1" : "0.5";

      refreshBtn.style.cursor = isAuthenticated ? "pointer" : "not-allowed";

      console.log("Refresh button:", { disabled: refreshBtn.disabled });
    }

    // Logout button

    const logoutBtn = document.getElementById("logoutBtn");

    if (logoutBtn) {
      logoutBtn.disabled = !isAuthenticated;

      logoutBtn.style.pointerEvents = isAuthenticated ? "auto" : "none";

      logoutBtn.style.opacity = isAuthenticated ? "1" : "0.5";

      logoutBtn.style.cursor = isAuthenticated ? "pointer" : "not-allowed";

      console.log("Logout button:", { disabled: logoutBtn.disabled });
    }

    // Search input

    const apiSearch = document.getElementById("apiSearch");

    if (apiSearch) {
      apiSearch.disabled = !isAuthenticated;

      apiSearch.style.pointerEvents = isAuthenticated ? "auto" : "none";

      apiSearch.style.opacity = isAuthenticated ? "1" : "0.5";

      console.log("API search:", { disabled: apiSearch.disabled });
    }

    // Tab buttons

    const tabButtons = document.querySelectorAll(".tab-btn");

    tabButtons.forEach((btn) => {
      const tabName = btn.dataset.tab;

      const shouldEnable = tabName === "mulesoft" || isAuthenticated;

      btn.disabled = !shouldEnable;

      btn.style.pointerEvents = shouldEnable ? "auto" : "none";

      btn.style.opacity = shouldEnable ? "1" : "0.5";

      btn.style.cursor = shouldEnable ? "pointer" : "not-allowed";

      console.log(`Tab ${tabName}:`, { disabled: btn.disabled });
    });

    // Force DOM update

    document.body.offsetHeight;
  }

  function updateAuthIndicators(anypointAuth, githubAuth) {
    const anypointIndicator = document.getElementById("anypointIndicator");

    const githubIndicator = document.getElementById("githubIndicator");

    // Update Anypoint indicator if it exists

    if (anypointIndicator) {
      if (anypointAuth) {
        anypointIndicator.classList.add("authenticated");

        anypointIndicator.title = "Anypoint: Authenticated";
      } else {
        anypointIndicator.classList.remove("authenticated");

        anypointIndicator.title = "Anypoint: Not authenticated";
      }
    }

    // Update GitHub indicator if it exists

    if (githubIndicator) {
      if (githubAuth) {
        githubIndicator.classList.add("authenticated");

        githubIndicator.title = `GitHub: Authenticated as ${state.githubUsername}`;
      } else {
        githubIndicator.classList.remove("authenticated");

        githubIndicator.title = "GitHub: Not authenticated";
      }
    }
  }

  const loadApplications = (...args) =>
    window.MulesoftPanel.loadApplications(...args);
  const loadLocalApplications = (...args) =>
    window.MulesoftPanel.loadLocalApplications(...args);
  const fetchErrorCounts = (...args) =>
    window.MulesoftPanel.fetchErrorCounts(...args);
  const selectApplication = (...args) =>
    window.MulesoftPanel.selectApplication(...args);
  const loadLogs = (...args) => window.MulesoftPanel.loadLogs(...args);

  async function refresh() {
    if (!state.currentEnvId) return;

    showLoading();

    try {
      if (state.currentEnvId === "local") {
        // Refresh local applications

        await loadLocalApplications();

        if (state.selectedAppId) {
          await loadLogs(state.selectedAppId);
        }
      } else {
        // Load Anypoint applications first

        await loadApplications(state.currentEnvId);

        // Fetch logs and error counts for all applications

        // Note: Use /error-count endpoint for refresh (no time filters)

        const newErrorCounts = {};

        for (const app of state.applications) {
          try {
            // Fetch total error count using dedicated error-count endpoint (no time filters)

            const result = await api(
              "GET",

              `/api/environments/${state.currentEnvId}/applications/${app.id}/error-count`,
            );

            if (result.success) {
              // Store raw logs for this app to use in filtered count calculations

              if (result.logs) {
                state.appLogs[app.id] = result.logs;
              }

              // Use error_count from response (already calculated by backend)

              newErrorCounts[app.id] = result.error_count || 0;
            }
          } catch (err) {
            console.error(`Failed to fetch error count for ${app.id}:`, err);

            newErrorCounts[app.id] = 0;
          }
        }

        // Update error counts

        state.errorCounts = newErrorCounts;

        // Re-render applications with updated error counts

        renderApplications();

        // If an app is selected, reload its logs

        if (state.selectedAppId) {
          await loadLogs(state.selectedAppId);
        }
      }

      state.lastRefreshTime = new Date();

      updateLastRefreshDisplay();
    } catch (err) {
      console.error("Failed to refresh:", err);

      renderErrorBanner("Failed to refresh data. Please try again.");
    } finally {
      hideLoading();
    }
  }

  function startAutoRefresh() {
    window.AppRefreshUtils.startAutoRefresh(state, refresh);
  }

  function stopAutoRefresh() {
    window.AppRefreshUtils.stopAutoRefresh(state);
  }

  function updateLastRefreshDisplay() {
    window.AppRefreshUtils.updateLastRefreshDisplay(state, elements);
  }

  // Update refresh display every second

  setInterval(() => {
    if (state.lastRefreshTime) {
      updateLastRefreshDisplay();
    }
  }, 1000);

  async function runRulesetAnalysis(file) {
    const errorText =
      document.getElementById("analysisPrompt")?.value?.trim() || "";

    const resultDiv = document.getElementById("analysisResult");

    if (!resultDiv) return;

    resultDiv.innerHTML = '<div class="loading">Analyzing...</div>';

    try {
      const ext = (file.name.split(".").pop() || "").toLowerCase();

      let payload;

      if (errorText) {
        payload = {
          content: errorText,

          prompt:
            "Analyze this error and the provided source file. Use the Element field to locate the exact line(s) where the error occurs. For each location, show the current code and the exact replacement. Output in the structured format: Error Location, Fix Required (Current code / Suggested replacement), Additional Notes.",

          file_path: file.path,

          reference_file_content: file.content,

          reference_file_name: file.name,

          reference_file_extension: ext,

          ruleset: "error-analysis-rules.txt",
        };
      } else {
        payload = {
          content: file.content,

          prompt:
            "Analyze this source code for potential issues, best practices, and improvements following the ruleset guidelines.",

          file_path: file.path,

          ruleset: "error-analysis-rules.txt",
        };
      }

      const result = await api("POST", "/api/error/analyze", payload);

      if (result.success) {
        // Hide the input section after successful analysis
        const inputSection = document.getElementById("analysisInputSection");
        if (inputSection) {
          inputSection.classList.add("hidden");
        }

        const formattedHtml = `
          <div class="analysis-text">${formatAnalysis(result.analysis)}</div>
        `;

        renderAnalysisWithRefine(
          resultDiv,
          formattedHtml,
          async function regenerateCallback(additionalInput) {
            // Re-run runRulesetAnalysis with the extra input merged into the prompt
            const extraPrompt = additionalInput
              ? "Analyze this error and the provided source file. Use the Element field to locate the exact line(s) where the error occurs. For each location, show the current code and the exact replacement. Output in the structured format: Error Location, Fix Required (Current code / Suggested replacement), Additional Notes." +
                "\n\nAdditional context from user:\n" +
                additionalInput
              : null;
            if (state.selectedFile && extraPrompt) {
              const file = state.selectedFile;
              const ext = (file.name.split(".").pop() || "").toLowerCase();
              resultDiv.innerHTML =
                '<div class="loading">Regenerating analysis...</div>';
              try {
                const r2 = await api("POST", "/api/error/analyze", {
                  content: extraPrompt,
                  prompt: extraPrompt,
                  file_path: file.path,
                  reference_file_content: file.content,
                  reference_file_name: file.name,
                  reference_file_extension: ext,
                  ruleset: "error-analysis-rules.txt",
                });
                if (r2.success) {
                  const html2 = `
                    <div class="analysis-text">${formatAnalysis(r2.analysis)}</div>
                  `;
                  renderAnalysisWithRefine(resultDiv, html2, regenerateCallback);
                } else {
                  resultDiv.innerHTML = `<div class="error">Regeneration failed: ${r2.error}</div>`;
                }
              } catch (e2) {
                resultDiv.innerHTML = `<div class="error">Regeneration failed: ${e2.message}</div>`;
              }
            } else {
              runRulesetAnalysis(state.selectedFile);
            }
          },
        );
      } else {
        resultDiv.innerHTML = `<div class="error">Analysis failed: ${result.error}</div>`;
      }
    } catch (err) {
      resultDiv.innerHTML = `<div class="error">Analysis failed: ${err.message}</div>`;
    }
  }

  async function runGenerateCodeChanges(file) {
    const errorText =
      document.getElementById("analysisPrompt")?.value?.trim() || "";
    const resultDiv =
      document.getElementById("analysisResult") ||
      document.getElementById("errorAnalysisResult") ||
      document.getElementById("eventDetailsAiSummaryBody"); // Add modal analysis container

    if (!resultDiv) return;
    resultDiv.innerHTML =
      '<div class="loading">Generating code changes...</div>';

    try {
      const ext = (file.name.split(".").pop() || "").toLowerCase();

      const ctx = window.__eventDetailsContext || {};
      
      // Extract specific sections from the analysis
      const analysisSections = extractAnalysisSections(ctx.refinedAnalysis || '');
      
      // Check if we have multi-file context from GitHub analysis
      const hasMultiFileContext = ctx.githubSourceFileContentByBasename && 
        Object.keys(ctx.githubSourceFileContentByBasename).length > 1;
      
      // Prepare payload based on single vs multi-file context
      let payload;
      if (hasMultiFileContext) {
        // Multi-file context: pass all available files
        const allFileContents = ctx.githubSourceFileContentByBasename;
        const allFileNames = Object.keys(allFileContents);
        
        payload = {
          content: errorText || file.content,
          file_path: file.path,
          
          // Multi-file support
          reference_files: allFileNames.map(fileName => ({
            name: fileName,
            content: allFileContents[fileName],
            path: ctx.githubRepoPathByBasename?.[fileName] || fileName
          })),
          
          // Backward compatibility - primary file
          reference_file_content: file.referenceSourceContent || file.reference_file_content || "",
          reference_file_name: file.name,
          reference_file_extension: ext,
          
          // Analysis context
          refined_analysis: ctx.refinedAnalysis || "",
          immediate_actions: analysisSections.immediate_actions || "",
          change_summary: analysisSections.change_summary || "",
          ai_error_observations: ctx.lastSummaryObservations || "",
          ai_error_rca: ctx.lastSummaryRca || "",
          user_context: ctx.lastUserContext || "",
        };
        
        console.log(`Multi-file context detected. Passing ${allFileNames.length} files:`, allFileNames);
      } else {
        // Single file context (existing logic)
        payload = {
          content: errorText || file.content,
          file_path: file.path,
          reference_file_content: errorText
            ? file.content
            : file.referenceSourceContent || file.reference_file_content || "",
          reference_file_name: file.name,
          reference_file_extension: ext,
          refined_analysis: ctx.refinedAnalysis || "",
          immediate_actions: analysisSections.immediate_actions || "",
          change_summary: analysisSections.change_summary || "",
          ai_error_observations: ctx.lastSummaryObservations || "",
          ai_error_rca: ctx.lastSummaryRca || "",
          user_context: ctx.lastUserContext || "",
        };
      }

      console.log(`payload for code generation is:`, payload);

      const result = await api(
        "POST",
        "/api/error/generate-code-changes",
        payload,
      );
      
      if (result.success) 
        {

        const narrativeOnlyDiagnosis = !!result.narrative_only_diagnosis;

        let html = `<div class="analysis-text">${formatAnalysis(result.analysis)}</div>`;

        if (result.quick_fixes && result.quick_fixes.length > 0) {
          html += `
            <div class="quick-fixes-section" style="margin-top:16px;padding:12px;border:1px solid var(--accent-color);border-radius:8px;background:rgba(59,130,246,0.08);">
              <h4 style="margin:0 0 8px 0;color:var(--accent-color);">🔧 Quick Fixes</h4>
              ${result.quick_fixes
                .map(
                  (fix) => `
                <div style="margin:4px 0;padding:8px;background:var(--bg-secondary);border-radius:4px;">
                  <div style="font-weight:500;margin-bottom:4px;">${fix.description}</div>
                  ${fix.code ? `<code style="font-size:0.9em;background:var(--bg-tertiary);padding:2px 6px;border-radius:3px;">${fix.code}</code>` : ""}
                  <div style="font-size:0.8em;color:var(--text-secondary);margin-top:4px;">Confidence: ${Math.round(fix.confidence * 100)}%</div>
                </div>`,
                )
                .join("")}
            </div>`;
        }

        if (result.validation && !result.validation.is_valid) {
          html += `
            <div style="margin-top:16px;padding:12px;border:1px solid var(--error-color);border-radius:8px;background:rgba(239,68,68,0.08);">
              <h4 style="margin:0 0 8px 0;color:var(--error-color);">⚠️ Validation Issues</h4>
              ${result.validation.errors.map((e) => `<div style="margin:4px 0;color:var(--error-color);">• ${e}</div>`).join("")}
            </div>`;
        }

        // Only show editor/diff when code changes are actually required.
        // Backend may return analysis that says "no changes required"; in that case, do not show code.
        if (result.suggested_code && !result.no_changes_required) {
          const validationStatus = result.validation
            ? result.validation.is_valid
              ? "✅ Validated"
              : "⚠️ Has validation issues"
            : "";

          // ── Detect context: GitHub panel vs AI Analysis modal ─────────────
          const fileContentWrapper = resultDiv.closest(".file-content-wrapper");
          const isGitHubPanel = !!fileContentWrapper;
          const originalContent = file.content;

          // ── Build diff between original and generated ─────────────────────
          function buildDiff(original, generated) {
            const origLines = (original || "").split("\n");
            const genLines = (generated || "").split("\n");
            const maxLen = Math.max(origLines.length, genLines.length);
            let diffHtml = "";
            let added = 0,
              removed = 0,
              unchanged = 0;
            for (let i = 0; i < maxLen; i++) {
              const o = origLines[i];
              const g = genLines[i];
              if (o === undefined) {
                diffHtml += `<div class="diff-line diff-added"><span class="diff-gutter">+${i + 1}</span><span class="diff-content">${escapeHtml(g)}</span></div>`;
                added++;
              } else if (g === undefined) {
                diffHtml += `<div class="diff-line diff-removed"><span class="diff-gutter">-${i + 1}</span><span class="diff-content">${escapeHtml(o)}</span></div>`;
                removed++;
              } else if (o !== g) {
                diffHtml += `<div class="diff-line diff-removed"><span class="diff-gutter">-${i + 1}</span><span class="diff-content">${escapeHtml(o)}</span></div>`;
                diffHtml += `<div class="diff-line diff-added"><span class="diff-gutter">+${i + 1}</span><span class="diff-content">${escapeHtml(g)}</span></div>`;
                removed++;
                added++;
              } else {
                diffHtml += `<div class="diff-line diff-unchanged"><span class="diff-gutter">&nbsp;${i + 1}</span><span class="diff-content">${escapeHtml(o)}</span></div>`;
                unchanged++;
              }
            }
            return { diffHtml, added, removed, unchanged };
          }

          const { diffHtml, added, removed } = buildDiff(
            originalContent,
            result.suggested_code,
          );

          // ── Render diff + editable panel ──────────────────────────────────
          if (isGitHubPanel) {
            // Replace the file-content area with diff + editable textarea
            const fileContent =
              fileContentWrapper.querySelector(".file-content");
            if (fileContent) {
              fileContent.innerHTML = `
                <div class="diff-toolbar" style="display:flex;align-items:center;gap:12px;padding:8px 12px;background:var(--bg-secondary);border-bottom:1px solid var(--border-color);border-radius:6px 6px 0 0;font-size:13px;">
                  <strong>Changes preview</strong>
                  <span style="color:#16a34a;">+${added} added</span>
                  <span style="color:#dc2626;">-${removed} removed</span>
                  <button id="btnToggleDiff" style="margin-left:auto;font-size:12px;padding:2px 8px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-tertiary);cursor:pointer;">Switch to editor</button>
                </div>
                <div id="diffView" style="overflow:auto;max-height:480px;font-family:monospace;font-size:12px;line-height:1.5;border:2px solid #2563eb;border-top:none;border-radius:0 0 6px 6px;">
                  ${diffHtml}
                </div>
                <textarea id="codeEditor" style="display:none;width:100%;min-height:480px;font-family:monospace;font-size:12px;line-height:1.5;padding:12px;border:2px solid #2563eb;border-top:none;border-radius:0 0 6px 6px;resize:vertical;box-sizing:border-box;background:var(--bg-primary);color:var(--text-primary);">${escapeHtml(result.suggested_code)}</textarea>
              `;
              // Toggle between diff and editor
              fileContent
                .querySelector("#btnToggleDiff")
                .addEventListener("click", function () {
                  const diff = fileContent.querySelector("#diffView");
                  const editor = fileContent.querySelector("#codeEditor");
                  const isDiffVisible = diff.style.display !== "none";
                  diff.style.display = isDiffVisible ? "none" : "block";
                  editor.style.display = isDiffVisible ? "block" : "none";
                  this.textContent = isDiffVisible
                    ? "Switch to diff"
                    : "Switch to editor";
                });
            }
          }

          // ── Confirm prompt in analysis panel ──────────────────────────────
          const locationNote = narrativeOnlyDiagnosis
            ? (isGitHubPanel
                ? "Diagnostic-only analysis (e.g. HTTP 4xx or configuration/properties). Possible causes are shown above; creating a branch or PR is not available for this category."
                : "Diagnostic-only analysis (e.g. HTTP 4xx or configuration/properties). Possible causes are shown above; creating a branch or PR is not available for this category.")
            : (isGitHubPanel
                ? "Review the diff and edit above if needed, then implement to create a branch and PR on GitHub."
                : "Review the generated code below, edit if needed, then implement to create a branch and PR on GitHub.");

          // For modal context: show editable code + diff inline in analysis panel
          const modalCodeSection = !isGitHubPanel
            ? `
            <div style="margin-top:12px;">
              <div class="diff-toolbar" style="display:flex;align-items:center;gap:12px;padding:8px 12px;background:var(--bg-secondary);border-bottom:1px solid var(--border-color);border-radius:6px 6px 0 0;font-size:13px;">
                <strong>Changes preview</strong>
                <span style="color:#16a34a;">+${added} added</span>
                <span style="color:#dc2626;">-${removed} removed</span>
                <button id="btnToggleDiffModal" style="margin-left:auto;font-size:12px;padding:2px 8px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-tertiary);cursor:pointer;">Switch to editor</button>
                <button id="btnDownloadCode" style="font-size:12px;padding:2px 8px;border:1px solid var(--success-green);border-radius:4px;background:var(--success-green);color:white;cursor:pointer;">Download file</button>
              </div>
              <div id="diffViewModal" style="overflow:auto;max-height:320px;font-family:monospace;font-size:12px;line-height:1.5;border:2px solid #2563eb;border-top:none;border-radius:0 0 6px 6px;">
                ${diffHtml}
              </div>
              <textarea id="codeEditorModal" style="display:none;width:100%;min-height:320px;font-family:monospace;font-size:12px;line-height:1.5;padding:12px;border:2px solid #2563eb;border-top:none;border-radius:0 0 6px 6px;resize:vertical;box-sizing:border-box;background:var(--bg-primary);color:var(--text-primary);">${escapeHtml(result.suggested_code)}</textarea>
            </div>` : "";



          const implementHeader = narrativeOnlyDiagnosis
            ? `Diagnostic-only — implement disabled${validationStatus ? " " + validationStatus : ""}`
            : `Ready to implement ${validationStatus}`;

          const implementYesAttrs = narrativeOnlyDiagnosis
            ? ' disabled title="Not available for diagnostic-only analysis"'
            : "";

          // Only show implementation section if code changes are required
          const implementSection = !narrativeOnlyDiagnosis ? `
            <div class="implement-prompt" style="margin-top:16px;padding:12px;border:1px solid var(--border-color);border-radius:8px;background:var(--bg-tertiary);">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
                <span style="font-weight:500;">${implementHeader}</span>
              </div>
              <p style="margin:0 0 12px 0;color:var(--text-secondary);font-size:13px;">${locationNote}</p>
              ${modalCodeSection}
              <div style="display:flex;gap:8px;margin-top:12px;">
                <button class="btn-primary" id="btnImplementYes"${implementYesAttrs}>Yes, implement</button>
                <button class="btn-secondary" id="btnImplementNo">No, discard</button>
                <button class="btn-secondary" id="btnRegenerate" style="margin-left:auto;" title="Re-run code generation">🔄 Regenerate</button>
              </div>

            </div>
          ` : "";

          html += `${implementSection}`;

          console.log("Debug - ResultDiv element:", resultDiv);
          console.log("Debug - ResultDiv ID:", resultDiv.id);
          console.log("Debug - HTML length:", html.length);
          console.log("Debug - HTML preview:", html.substring(0, 200));

          resultDiv.innerHTML = html;

          // Wire toggle for modal diff/editor
          if (!isGitHubPanel) {
            const toggleBtn = resultDiv.querySelector("#btnToggleDiffModal");
            if (toggleBtn) {
              toggleBtn.addEventListener("click", function () {
                const diff = resultDiv.querySelector("#diffViewModal");
                const editor = resultDiv.querySelector("#codeEditorModal");
                const isDiffVisible = diff.style.display !== "none";
                diff.style.display = isDiffVisible ? "none" : "block";
                editor.style.display = isDiffVisible ? "block" : "none";
                this.textContent = isDiffVisible
                  ? "Switch to diff"
                  : "Switch to editor";
              });
            }

            // Add event listener for download code button
            const downloadBtn = resultDiv.querySelector("#btnDownloadCode");
            if (downloadBtn) {
              downloadBtn.addEventListener("click", function () {
                try {
                  // Get the final code (respects user edits)
                  const finalCode = getFinalCode();
                  if (!finalCode) {
                    alert("No code available to download");
                    return;
                  }
                  
                  // Extract filename from result or use default
                  const fileName = result.fileName || result.filename || "modified-file";
                  const fileExtension = fileName.includes('.') ? '' : '.xml';
                  
                  console.log('Downloading file:', fileName + fileExtension);
                  console.log('Code length:', finalCode.length);
                  
                  // Create download
                  var blob = new Blob([finalCode], { type: 'text/plain' });
                  var url = window.URL.createObjectURL(blob);
                  var a = document.createElement('a');
                  a.href = url;
                  a.download = fileName + fileExtension;
                  a.style.display = 'none';
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  window.URL.revokeObjectURL(url);
                  
                  // Update button text temporarily
                  this.textContent = 'Downloaded!';
                  setTimeout(() => {
                    this.textContent = 'Download file';
                  }, 1500);
                  
                  console.log('Download completed successfully');
                } catch (err) {
                  console.error('Download failed:', err);
                  alert('Download failed: ' + err.message);
                }
              });
            }
          }

          // ── Get final code (respects edits made in the textarea) ──────────
          function getFinalCode() {
            if (isGitHubPanel) {
              const editor = fileContentWrapper?.querySelector("#codeEditor");
              return editor && editor.style.display !== "none"
                ? editor.value
                : result.suggested_code;
            } else {
              const editor = resultDiv.querySelector("#codeEditorModal");
              return editor && editor.style.display !== "none"
                ? editor.value
                : result.suggested_code;
            }
          }

          // ── Restore file viewer to a given content ────────────────────────
          function restoreFileViewer(content) {
            if (!isGitHubPanel) return;
            const fileContent =
              fileContentWrapper.querySelector(".file-content");
            if (fileContent) {
              fileContent.innerHTML = `<pre><code>${escapeHtml(content)}</code></pre>`;
            }
          }

          // ── Button handlers ───────────────────────────────────────────────
          const implPrompt = resultDiv.querySelector(".implement-prompt");

          resultDiv.querySelector("#btnImplementYes").addEventListener("click", function() {
            if (narrativeOnlyDiagnosis) return;
            const finalCode = getFinalCode();
            doApplyChanges(file, finalCode, resultDiv, restoreFileViewer);
          });

          resultDiv
            .querySelector("#btnImplementNo")
            .addEventListener("click", function () {
              restoreFileViewer(originalContent);
              implPrompt.remove();
            });

          resultDiv
            .querySelector("#btnRegenerate")
            .addEventListener("click", async function () {
              try {
                restoreFileViewer(originalContent);
                await runGenerateCodeChanges(file);
              } catch (error) {
                console.error('Regenerate failed:', error);
                alert('Regenerate failed: ' + error.message);
              }
            });
        } else {
          // No code generated: keep the (already rendered) formatted analysis,
          // and show a single generic banner (do NOT re-print the analysis again).
          const noCodeHeading = narrativeOnlyDiagnosis
            ? "Diagnostic-only analysis"
            : "No code changes required";
          const noCodeBody = narrativeOnlyDiagnosis
            ? "No automated code patch is offered for this category of error."
            : "Based on the analysis, you don’t need to implement any code changes.";

          html += `
            <div style="margin-top:16px;padding:12px;border:1px solid var(--border-color);border-radius:8px;background:rgba(148,163,184,0.08);">
              <div style="font-weight:600;margin-bottom:4px;">${escapeHtml(noCodeHeading)}</div>
              <div style="color:var(--text-secondary);">${escapeHtml(noCodeBody)}</div>
            </div>`;

          resultDiv.innerHTML = html;
        }
        console.log("Code generation successful:", result);
      } else {
        console.error("Code generation failed:", result);
        resultDiv.innerHTML = `<div class="error">Code generation failed: ${result.error || 'Unknown error'}</div>`;
      }
    } catch (err) {
      console.error("Error in runGenerateCodeChanges:", err);
      resultDiv.innerHTML = `<div class="error">Analysis failed: ${err.message}</div>`;
    }
     finally {
      const regenerateBtn = resultDiv.querySelector("#btnRegenerate");
      if (regenerateBtn) {
        regenerateBtn.disabled = false;
      }
    }
  }

  async function doApplyChanges(
    file,
    suggestedCode,
    resultDiv,
    restoreFileViewer,
  ) {
    // Check if this is local analysis (no GitHub repo info)
    if (file.isLocalAnalysis || (!file.owner && !file.repo)) {
      // For local analysis, only show download option, not GitHub push
      const implPrompt = resultDiv.querySelector(".implement-prompt");
      if (implPrompt) {
        implPrompt.innerHTML = `
          <div style="padding:16px;border:1px solid #16a34a;border-radius:8px;background:rgba(22,163,74,0.06);margin-top:8px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              <strong style="color:#16a34a;">Code Generated Successfully</strong>
            </div>
            <p style="margin:0;color:var(--text-secondary);font-size:13px;">
              This is a local analysis. Download the generated code to apply changes manually.
            </p>
            <div style="margin-top:12px;">
              <button class="btn-primary" id="btnDownloadLocalCode" style="font-size:13px;">
                Download Generated Code
              </button>
              <button class="btn-secondary" id="btnClosePanel" style="margin-left:8px;font-size:13px;">
                Close
              </button>
            </div>
          </div>
        `;
        
        // Add download functionality
        const downloadBtn = implPrompt.querySelector("#btnDownloadLocalCode");
        if (downloadBtn) {
          downloadBtn.addEventListener("click", function() {
            try {
              const fileName = file.name || "generated-code.xml";
              const fileExtension = fileName.includes('.') ? '' : '.xml';
              
              console.log('Downloading local analysis file:', fileName + fileExtension);
              console.log('Code length:', suggestedCode.length);
              
              // Create download
              var blob = new Blob([suggestedCode], { type: 'text/plain' });
              var url = window.URL.createObjectURL(blob);
              var a = document.createElement('a');
              a.href = url;
              a.download = fileName + fileExtension;
              a.style.display = 'none';
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              window.URL.revokeObjectURL(url);
              
              // Update button text temporarily
              this.textContent = 'Downloaded!';
              setTimeout(() => {
                this.textContent = 'Download Generated Code';
              }, 1500);
              
              console.log('Download completed successfully');
            } catch (err) {
              console.error('Download failed:', err);
              alert('Download failed: ' + err.message);
            }
          });
        }
        
        // Add close functionality
        const closeBtn = implPrompt.querySelector("#btnClosePanel");
        if (closeBtn) {
          closeBtn.addEventListener("click", function() {
            implPrompt.remove();
          });
        }
      }
      return;
    }
    
    // Original GitHub push logic for GitHub files
    const owner = file.owner || state.selectedRepo?.owner;
    const repo = file.repo || file.repoName || state.selectedRepo?.repoName;
    if (!owner || !repo) {
      alert("Missing owner/repo. Cannot apply changes.");
      return;
    }

    // Disable buttons while in progress
    resultDiv.querySelectorAll("button").forEach((b) => (b.disabled = true));
    const implPrompt = resultDiv.querySelector(".implement-prompt");
    if (implPrompt)
      implPrompt.innerHTML =
        '<div class="loading">Creating branch and PR…</div>';

    try {
      const response = await api("POST", "/api/github/apply-changes", {
        owner,

        repo,

        file_path: file.path,

        new_content: suggestedCode,

        original_content:
          file.referenceSourceContent != null && file.referenceSourceContent !== ""
            ? file.referenceSourceContent
            : file.content,

        commit_message: "Apply AI-suggested code changes",
      });

      if (response.success) {
        // Show the committed code in the file viewer (not the original)
        if (restoreFileViewer) restoreFileViewer(suggestedCode);

        // Preserve the real correlation/log context for the PR -> ServiceNow flow.
        // If the Event Details modal already captured it earlier, do not overwrite
        // it with a synthetic GitHub-only fallback.
        if (window.__eventDetailsContext && window.__eventDetailsContext.logs) {
          state.ticketContextForPR = {
            eventId: window.__eventDetailsContext.eventId || state.ticketContextForPR?.eventId || "github-analysis-" + Date.now(),
            logs: window.__eventDetailsContext.logs,
            appName: window.__eventDetailsContext.appName || file.repo || "GitHub Analysis"
          };
        } else if (!state.ticketContextForPR?.eventId || !state.ticketContextForPR?.logs?.length) {
          // Fallback only when no real correlation context is available at all.
          state.ticketContextForPR = {
            eventId: "github-analysis-" + Date.now(),
            logs: [{
              message: "GitHub code analysis and PR creation",
              timestamp: new Date().toISOString(),
              component: file.name || "Unknown File",
              file_path: file.path
            }],
            appName: file.repo || "GitHub Analysis"
          };
        }

        // Replace ONLY the implement-prompt section with success card
        // Leave the analysis text above intact
        const promptArea = resultDiv.querySelector(".implement-prompt");
        const successHtml = `
          <div style="padding:16px;border:1px solid #16a34a;border-radius:8px;background:rgba(22,163,74,0.06);margin-top:8px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              <strong style="color:#16a34a;">Changes applied successfully!</strong>
            </div>
            <p style="margin:0 0 6px 0;font-size:13px;">
              Branch <code style="background:var(--bg-secondary);padding:2px 6px;border-radius:4px;">${escapeHtml(response.branch_name)}</code> created with your changes.
            </p>
            <p style="margin:0;font-size:13px;">
              <a href="${escapeHtml(response.pr_url)}" target="_blank" rel="noopener"
                 style="color:#2563eb;font-weight:500;">
                View Pull Request →
              </a>
            </p>
            <div style="margin-top:12px;">
              <button
                class="btn btn-primary"
                id="createTicketFromPRBtn"
                style="background: var(--accent-color, #2563EB); color: white; border: none; padding: 10px 16px; border-radius: 6px; cursor: pointer; font-weight: 600;"
                type="button"
              >
                Create/Update ServiceNow Ticket
              </button>
            </div>
          </div>`;
        if (promptArea) {
          promptArea.outerHTML = successHtml;
        } else {
          resultDiv.insertAdjacentHTML("beforeend", successHtml);
        }

         // Wire PR->ServiceNow button after DOM injection
        setTimeout(() => {
          const btn = document.getElementById("createTicketFromPRBtn");
          if (!btn) return;
          btn.addEventListener("click", () => {
            console.log("[ServiceNow] Resolved context:", state.ticketContextForPR);
            window.openServiceNowTicketFromPR(response.pr_url, response.branch_name, state.ticketContextForPR);
          });
        }, 50);
      } else {
        if (implPrompt)
          implPrompt.innerHTML = `<div class="error">Apply failed: ${response.error}</div>`;
        else
          resultDiv.insertAdjacentHTML(
            "beforeend",
            `<div class="error">Apply failed: ${response.error}</div>`,
          );
      }
    } catch (err) {
      if (implPrompt)
        implPrompt.innerHTML = `<div class="error">Apply failed: ${err.message}</div>`;
      else
        resultDiv.insertAdjacentHTML(
          "beforeend",
          `<div class="error">Apply failed: ${err.message}</div>`,
        );
    }
  }

  async function switchTab(tabName) {
    state.currentTab = tabName;

    // Update tab buttons

    elements.tabBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tabName);
    });

    // Update tab panes

    elements.mulesoftTab.classList.toggle("active", tabName === "mulesoft");

    elements.mulesoftTab.classList.toggle("hidden", tabName !== "mulesoft");

    elements.githubTab.classList.toggle("active", tabName === "github");

    elements.githubTab.classList.toggle("hidden", tabName !== "github");

    elements.correlationTab.classList.toggle(
      "active",
      tabName === "correlation",
    );

    elements.correlationTab.classList.toggle(
      "hidden",
      tabName !== "correlation",
    );

    // Move shared time-filter bar so it is visible in the active tab
    moveFilterBarToActiveTab(tabName);
    updateFilterVisibility();

    // Check GitHub authentication when switching to GitHub tab

    if (tabName === "github") {
      // First refresh session to get latest state

      await checkSession();

      if (!state.githubAuthenticated) {
        // User not authenticated with GitHub, show login modal

        showGithubLoginModal();

        // Switch back to MuleSoft tab

        setTimeout(async () => {
          await switchTab("mulesoft");
        }, 100);

        return;
      }

      // Load GitHub repos if authenticated and not loaded yet

      if (state.githubRepos.length === 0) {
        loadGitHubRepos();
      }
    }

    // Check Anypoint authentication when switching to MuleSoft tab

    if (tabName === "mulesoft") {
      if (!state.authenticated) {
        // User not authenticated with Anypoint, show login modal

        showAnypointLoginModal();

        // Switch back to GitHub tab

        setTimeout(async () => {
          await switchTab("github");
        }, 100);

        return;
      }

      // Load applications if authenticated and not loaded yet

      if (state.applications.length === 0 && state.currentEnvId) {
        loadApplications(state.currentEnvId);
      }
    }

    // Load correlation IDs when opening correlation tab

    if (tabName === "correlation") {
      // Correlation IDs are global, so we can load them without an environment

      // But we still use the environment ID for status tracking

      loadCorrelationIds();
    }
  }

  function moveFilterBarToActiveTab(tabName) {
    if (!elements.filterBar) return;

    const mulesoftLogsPanel = elements.mulesoftTab
      ? elements.mulesoftTab.querySelector(".logs-panel")
      : null;
    const correlationLogsPanel = elements.correlationTab
      ? elements.correlationTab.querySelector(".logs-panel")
      : null;

    // Show the same filter UI in Correlation tab as requested.
    const targetPanel =
      tabName === "correlation" ? correlationLogsPanel : mulesoftLogsPanel;
    if (!targetPanel) return;

    if (!elements.filterBar.parentElement.isSameNode(targetPanel)) {
      targetPanel.insertBefore(elements.filterBar, targetPanel.firstChild);
    }
  }

  // Helper functions

  function getFileIcon(filename) {
    const ext = filename.split(".").pop().toLowerCase();

    const iconMap = {
      js: "📜",

      ts: "📜",

      jsx: "⚛️",

      tsx: "⚛️",

      py: "🐍",

      java: "☕",

      cpp: "⚙️",

      c: "⚙️",

      html: "🌐",

      css: "🎨",

      scss: "🎨",

      sass: "🎨",

      json: "📋",

      xml: "📋",

      yaml: "📋",

      yml: "📋",

      md: "📝",

      txt: "📄",

      pdf: "📕",

      doc: "📘",

      png: "🖼️",

      jpg: "🖼️",

      jpeg: "🖼️",

      gif: "🖼️",

      zip: "📦",

      tar: "📦",

      gz: "📦",
    };

    return iconMap[ext] || "📄";
  }

  function formatFileSize(bytes) {
    if (bytes === 0) return "0 Bytes";

    const k = 1024;

    const sizes = ["Bytes", "KB", "MB", "GB"];

    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  // ─────────────────────────────────────────────────────────────────────────

  // formatAnalysis — comprehensive Markdown-to-HTML renderer for AI responses

  // Handles: all ruleset sections, fenced code blocks with language labels,

  // severity badges, Change Summary tables, inline code, bold/italic text,

  // numbered & bullet lists, and fallback plain-text rendering.

  // ─────────────────────────────────────────────────────────────────────────

  function formatAnalysis(text) {
    if (!text || !text.trim()) return "";

    // ── Language display names for code block headers ──────────────────────

    const LANG_LABELS = {
      xml: "XML",

      dw: "DataWeave",

      dwl: "DataWeave",

      java: "Java",

      json: "JSON",

      yaml: "YAML",

      yml: "YAML",

      properties: "Properties",

      sql: "SQL",

      groovy: "Groovy",

      text: "Log",

      "": "Code",
    };

    // ── Copy-to-clipboard button for code blocks ───────────────────────────

    function copyCodeBtn(id) {
      return (
        `<button class="code-copy-btn" onclick="(function(btn){` +
        `var pre=document.getElementById('${id}');` +
        `if(!pre)return;` +
        `var code=pre.textContent||pre.innerText;` +
        `navigator.clipboard&&navigator.clipboard.writeText(code)` +
        `.then(function(){btn.textContent='Copied!';setTimeout(function(){btn.textContent='Copy';},1500)})` +
        `.catch(function(){btn.textContent='Copy';});` +
        `})(this)" title="Copy code">Copy</button>`
      );
    }

    function downloadCodeBtn(id, filename, lang) {
      return (
        `<button class="code-download-btn" onclick="downloadCodeContent('${id}', '${filename || 'code'}', '${lang || 'txt'}')" title="Download code">Download</button>`
      );
    }

    // Global function for downloading code content
    window.downloadCodeContent = function(id, filename, lang) {
      try {
        console.log('Download clicked for file:', filename + '.' + lang);
        var pre = document.getElementById(id);
        if (!pre) {
          console.error('Code element not found:', id);
          return;
        }
        var code = pre.textContent || pre.innerText || '';
        if (!code) {
          console.error('No code content found');
          return;
        }
        console.log('Code length:', code.length);
        
        // Create download using proper URL object
        var blob = new Blob([code], { type: 'text/plain' });
        var url = window.URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = filename + '.' + lang;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        // Update button text temporarily
        event.target.textContent = 'Downloaded!';
        setTimeout(function() {
          if (event.target) event.target.textContent = 'Download';
        }, 1500);
        
        console.log('Download completed successfully');
      } catch (err) {
        console.error('Download failed:', err);
        alert('Download failed: ' + err.message);
      }
    };

    // ── Fenced code block renderer ─────────────────────────────────────────

    let codeBlockCounter = 0;

    function renderCodeBlock(lang, code, filename = null) {
      const id = "code-block-" + ++codeBlockCounter;

      const label =
        LANG_LABELS[lang.toLowerCase()] || lang.toUpperCase() || "Code";

      const escaped = escapeHtml(code);
      
      // Extract filename from context or use provided filename
      let downloadFilename = filename || 'code';
      if (!filename && window.__eventDetailsContext && window.__eventDetailsContext.logs && window.__eventDetailsContext.logs[0]) {
        const log = window.__eventDetailsContext.logs[0];
        downloadFilename = log.component || log.filename || 'code';
        // Remove extension if present to add it later with correct language
        downloadFilename = downloadFilename.replace(/\.[^.]+$/, '');
      }

      return (
        `<div class="analysis-code-wrapper">` +
        `<div class="analysis-code-header">` +
        `<span class="analysis-code-lang">${label}</span>` +
        copyCodeBtn(id) +
        downloadCodeBtn(id, downloadFilename, lang.toLowerCase()) +
        `</div>` +
        `<pre class="analysis-code-block" id="${id}"><code class="lang-${lang.toLowerCase() || "text"}">${escaped}</code></pre>` +
        `</div>`
      );
    }

    // ── Change Summary table renderer ──────────────────────────────────────

    function renderChangeSummaryTable(tableText) {
      const lines = tableText

        .trim()

        .split("\n")

        .filter((l) => l.trim());

      if (lines.length < 2)
        return `<p class="analysis-paragraph">${escapeHtml(tableText)}</p>`;

      let html = '<table class="change-summary-table"><thead>';

      let inHead = true;

      lines.forEach((line, i) => {
        if (line.match(/^\s*\|?[-:| ]+\|?\s*$/)) {
          inHead = false;

          html += "</thead><tbody>";

          return;
        }

        const cells = line

          .replace(/^\||\|$/g, "")

          .split("|")

          .map((c) => c.trim());

        const tag = inHead ? "th" : "td";

        html +=
          "<tr>" +
          cells.map((c) => `<${tag}>${escapeHtml(c)}</${tag}>`).join("") +
          "</tr>";

        if (
          i === 0 &&
          lines.length > 1 &&
          !lines[1].match(/^\s*\|?[-:| ]+\|?\s*$/)
        ) {
          inHead = false;
        }
      });

      if (inHead) html += "</thead>";

      html += "</tbody></table>";

      return html;
    }

    // ── Inline markdown renderer (bold, italic, inline-code, backtick) ─────

    function renderInline(raw) {
      let s = escapeHtml(raw);

      // Bold **text**

      s = s.replace(
        /\*\*(.+?)\*\*/g,

        '<strong class="analysis-highlight">$1</strong>',
      );

      // Italic *text*

      s = s.replace(/\*(.+?)\*/g, '<em class="analysis-emphasis">$1</em>');

      // Inline code `code`

      s = s.replace(
        /`([^`]+)`/g,

        '<code class="analysis-inline-code">$1</code>',
      );

      // Highlight MuleSoft keywords

      s = s.replace(
        /\b(CRITICAL|ERROR|WARN|WARNING|NULL|TIMEOUT|CONNECTIVITY|DataWeave|FlowStack|Element|payload|config-ref|default|error-handler)\b/g,

        '<span class="analysis-keyword">$1</span>',
      );

      return s;
    }

    // ── Block content renderer (used per section) ─────────────────────────

    function renderBlock(raw) {
      if (!raw || !raw.trim()) return "";

      // First, extract all fenced code blocks and replace with placeholders

      const codePlaceholders = [];

      let processed = raw.replace(
        /```([a-zA-Z0-9_+-]*)\s*\n([\s\S]*?)```/g,

        (_, lang, code) => {
          const idx = codePlaceholders.length;

          codePlaceholders.push(renderCodeBlock(lang.trim(), code.trim()));

          return `\x00CODEBLOCK${idx}\x00`;
        },
      );

      // Also handle backtick-only blocks (no language)

      processed = processed.replace(/```\s*\n([\s\S]*?)```/g, (_, code) => {
        const idx = codePlaceholders.length;

        codePlaceholders.push(renderCodeBlock("", code.trim()));

        return `\x00CODEBLOCK${idx}\x00`;
      });

      // Split into paragraphs / list blocks

      const paragraphs = processed.split(/\n{2,}/);

      const parts = paragraphs.map((para) => {
        para = para.trim();

        if (!para) return "";

        // Restore code block placeholders

        if (para.startsWith("\x00CODEBLOCK")) {
          const m = para.match(/\x00CODEBLOCK(\d+)\x00/);

          if (m) return codePlaceholders[parseInt(m[1], 10)];
        }

        // Table (starts with |)

        if (
          para

            .split("\n")

            .every(
              (l) =>
                !l.trim() || l.trim().startsWith("|") || l.match(/^[-:| ]+$/),
            )
        ) {
          if (para.includes("|")) return renderChangeSummaryTable(para);
        }

        // Numbered list

        if (para.match(/^\d+\.\s/m)) {
          const items = para.split("\n").filter((l) => l.trim());

          let listHtml = '<ol class="analysis-numbered-list">';

          items.forEach((item) => {
            if (item.match(/^\d+\.\s/)) {
              listHtml += `<li class="analysis-numbered-item">${renderInline(item.replace(/^\d+\.\s*/, "").trim())}</li>`;
            }
          });

          listHtml += "</ol>";

          return listHtml;
        }

        // Bullet list

        if (para.match(/^[-*+]\s/m)) {
          const items = para.split("\n").filter((l) => l.trim());

          let listHtml = '<ul class="analysis-bullet-list">';

          items.forEach((item) => {
            if (item.match(/^[-*+]\s/)) {
              listHtml += `<li class="analysis-bullet-item">${renderInline(item.replace(/^[-*+]\s*/, "").trim())}</li>`;
            }
          });

          listHtml += "</ul>";

          return listHtml;
        }

        // Heading lines (## or ###)

        if (para.match(/^#{1,4}\s/)) {
          const level = para.match(/^(#+)/)[1].length;

          const headText = para.replace(/^#+\s*/, "").trim();

          return `<h${Math.min(level + 2, 5)} class="analysis-sub-heading">${renderInline(headText)}</h${Math.min(level + 2, 5)}>`;
        }

        // Restore any inline code placeholders

        if (para.includes("\x00CODEBLOCK")) {
          return para.replace(
            /\x00CODEBLOCK(\d+)\x00/g,

            (_, i) => codePlaceholders[parseInt(i, 10)],
          );
        }

        // Regular paragraph — render inline markdown

        return `<p class="analysis-paragraph">${renderInline(para)}</p>`;
      });

      // Re-inject code blocks by index in a final pass

      return parts.filter(Boolean).join("\n");
    }

    // ── Section layout config ──────────────────────────────────────────────

    // Maps section name → { icon, level (h2/h3/h4), special renderer }

    const SECTION_CONFIG = {
      "Additional Information": {
        icon: "ℹ️",

        level: "h4",

        cls: "section-info",
      },

      Summary: { icon: "📋", level: "h3", cls: "section-summary" },

      "Quick Fix": { icon: "⚡", level: "h4", cls: "section-quickfix" },

      "Error Type": { icon: "🏷️", level: "h4", cls: "section-errortype" },

      Severity: {
        icon: "🔴",

        level: "h4",

        cls: "section-severity",

        special: "severity",
      },

      "Root Cause": { icon: "🔍", level: "h3", cls: "section-rootcause" },

      Impact: { icon: "💥", level: "h3", cls: "section-impact" },

      "Immediate Actions": {
        icon: "✅",

        level: "h3",

        cls: "section-actions",

        special: "actions",
      },
      "Change Summary": {
        icon: "📝",

        level: "h3",

        cls: "section-changesummary",

        special: "table",
      },
    };

    // Known section names for ordered display

    const SECTION_ORDER = [
      "Additional Information",

      "Summary",

      "Quick Fix",

      "Error Type",

      "Severity",

      "Root Cause",

      "Impact",

      "Immediate Actions",
      "Change Summary",
    ];

    // ── Parse structured section headers and their content ────────────────

    function parseSections(src) {
      const result = {};

      // Normalize section headers so small LLM variations don't break UI rendering.
      // Examples handled:
      // - **Summary:**  → Summary
      // - **ROOT CAUSE** → Root Cause
      // - ### Summary    → Summary
      function normalizeSectionName(name) {
        if (!name) return "";
        let s = String(name).trim();
        s = s.replace(/\s+/g, " ");
        s = s.replace(/:$/, "").trim();
        const lower = s.toLowerCase();

        // Canonicalize common variants / synonyms
        if (lower === "additional info" || lower === "additional information") {
          return "Additional Information";
        }
        if (lower === "summary") return "Summary";
        if (lower === "quick fix" || lower === "quickfix") return "Quick Fix";
        if (lower === "error type" || lower === "error category") return "Error Type";
        if (lower === "severity") return "Severity";
        if (lower === "root cause" || lower === "rootcause") return "Root Cause";
        if (lower === "impact") return "Impact";
        if (
          lower === "immediate actions" ||
          lower === "immediate action" ||
          lower === "next steps" ||
          lower === "actions"
        ) {
          return "Immediate Actions";
        }
        if (lower === "change summary" || lower === "changes summary") {
          return "Change Summary";
        }

        // Title-case fallback (keeps unknown sections readable)
        return s
          .split(" ")
          .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
          .join(" ");
      }

      // Match either bold headers (**Header**) or markdown headers (## Header / ### Header)
      const headerRe =
        /(?:^|\n)\s*(?:\*\*([^*\n]{2,60})\*\*|#{2,4}\s*([^\n]{2,80}))\s*(?:\n|$)/g;

      let match;
      const positions = [];

      while ((match = headerRe.exec(src)) !== null) {
        const rawName = (match[1] || match[2] || "").trim();
        const name = normalizeSectionName(rawName);
        if (!name) continue;

        positions.push({
          name,
          start: match.index,
          headerEnd: match.index + match[0].length,
        });
      }

      positions.forEach((pos, i) => {
        const contentEnd =
          i + 1 < positions.length ? positions[i + 1].start : src.length;
        const content = src.substring(pos.headerEnd, contentEnd).trim();
        if (!content) return;

        // If the same section appears more than once, append it (some models repeat headers)
        if (result[pos.name]) {
          result[pos.name] = (result[pos.name] + "\n\n" + content).trim();
        } else {
          result[pos.name] = content;
        }
      });

      return result;
    }

    // ── Render a single parsed section ────────────────────────────────────

    function renderSection(name, content, cfg) {
      if (!content || !content.trim()) return "";

      const lowerName = (name || "").toLowerCase().trim();
      if (lowerName === "code fix" || lowerName === "code fixes") return "";

      let inner;
      
      if (cfg.special === "list") {
        // List rendering
        const lines = content.trim().split(/\n/).filter(l => l.trim());
        inner = '<ol class="analysis-numbered-list">';

        lines.forEach((line) => {
          const cleaned = line
            .replace(/^\d+\.\s*/, "")
            .replace(/^[-*+]\s*/, "")
            .trim();

          if (cleaned)
            inner += `<li class="analysis-numbered-item">${renderInline(cleaned)}</li>`;
        });

        inner += "</ol>";
      } else if (cfg.special === "codefix") {
        // Code Fix: render with special wrapper highlighting the section
        inner = `<div class="code-fix-body">${renderBlock(content)}</div>`;
      } else if (cfg.special === "table") {
        // Change Summary: try table rendering first
        inner = content.includes("|")
          ? renderChangeSummaryTable(content)
          : renderBlock(content);
      } else {
        inner = renderBlock(content);
      }

      return (
        `<div class="analysis-section analysis-section-${cfg.cls || "generic"}">` +
        `<${cfg.level} class="analysis-section-header">` +
        `<span class="section-icon">${cfg.icon}</span> ${escapeHtml(name)}` +
        `</${cfg.level}>` +
        `<div class="analysis-section-content">${inner}</div>` +
        `</div>`
      );
    }

    // ── Main rendering logic ───────────────────────────────────────────────

    // Check if the response looks like it contains structured sections.
    // Be tolerant of common variations: **Summary:**, ### Summary, case differences.
    const hasSections = (() => {
      const t = text || "";
      const boldLike = /\*\*\s*(summary|quick\s*fix|root\s*cause|immediate\s*actions?|error\s*type|severity|impact|additional\s*information)\s*:?\s*\*\*/i.test(
        t,
      );
      if (boldLike) return true;
      const headingLike = /(?:^|\n)\s*#{2,4}\s*(summary|quick\s*fix|root\s*cause|immediate\s*actions?|error\s*type|severity|impact|additional\s*information)\b/i.test(
        t,
      );
      return headingLike;
    })();

    if (hasSections) {
      const parsed = parseSections(text);

      let html = '<div class="analysis-structured">';

      let renderedAny = false;

      SECTION_ORDER.forEach((name) => {
        const content = parsed[name];

        if (content && content.trim()) {
          html += renderSection(name, content, SECTION_CONFIG[name]);

          renderedAny = true;
        }
      });

      // Render any unrecognised sections at the bottom

      Object.keys(parsed).forEach((name) => {
        const lowerName = name.toLowerCase();
        if (
          !SECTION_ORDER.some((o) => o.toLowerCase() === lowerName) &&
          !["code fix", "code fixes"].includes(lowerName) &&
          parsed[name] &&
          parsed[name].trim()
        ) {
          html += renderSection(name, parsed[name], {
            icon: "▪",

            level: "h4",

            cls: "section-generic",
          });

          renderedAny = true;
        }
      });

      html += "</div>";

      if (renderedAny) return html;

      // Fall through to plain rendering if nothing was parsed
    }

    // ── Fallback: old numbered section format (1. **Section** content) ─────

    if (text.match(/^\d+\.\s*\*\*[^*]+\*\*/m)) {
      const knownSections = [
        "Summary",

        "Error Type",

        "Severity",

        "Root Cause",

        "Impact",

        "Immediate Actions",
        "Prevention",
      ];

      let result = '<div class="analysis-structured">';

      let found = false;

      knownSections.forEach((sec) => {
        const re = new RegExp(
          `\\d+\\.\\s*\\*\\*${sec}\\*\\*\\s*([\\s\\S]*?)(?=\\d+\\.\\s*\\*\\*|$)`,

          "i",
        );

        const m = text.match(re);

        if (m && m[1] && m[1].trim()) {
          const cfg = SECTION_CONFIG[sec] || {
            icon: "▪",

            level: "h4",

            cls: "section-generic",
          };

          result += renderSection(sec, m[1].trim(), cfg);

          found = true;
        }
      });

      result += "</div>";

      if (found) return result;
    }

    // ── Final fallback: render as plain structured content ─────────────────

    return `<div class="analysis-plain">${renderBlock(text)}</div>`;
  }

  // Helper function to extract API name from Element field

  function extractApiNameFromElement(elementStr) {
    if (!elementStr || typeof elementStr !== "string") {
      return "Unknown API";
    }

    // Pattern matches: @ api-name:file.xml:line (description)

    // Example: plantumlFlow/processors/3 @ mule-sf-image-agent-api:sf-image-upload.xml:39 (Call PlantUML)

    const match = elementStr.match(/@([^:]+):/);

    if (match && match[1]) {
      return match[1];
    }

    return "Unknown API";
  }

  // Custom confirmation modal to replace native confirm()

  function showConfirmModal(message) {
    return new Promise((resolve) => {
      const modal = document.getElementById("confirmModal");

      const messageDiv = document.getElementById("confirmMessage");

      const okBtn = document.getElementById("confirmOk");

      const cancelBtn = document.getElementById("confirmCancel");

      // Set the message

      messageDiv.textContent = message;

      // Show the modal

      modal.classList.remove("hidden");

      // Remove existing event listeners

      const newOkBtn = okBtn.cloneNode(true);

      const newCancelBtn = cancelBtn.cloneNode(true);

      okBtn.parentNode.replaceChild(newOkBtn, okBtn);

      cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);

      // Add event listeners

      newOkBtn.addEventListener("click", () => {
        modal.classList.add("hidden");

        resolve(true);
      });

      newCancelBtn.addEventListener("click", () => {
        modal.classList.add("hidden");

        resolve(false);
      });

      // Close on backdrop click

      modal.querySelector(".modal-backdrop").addEventListener("click", () => {
        modal.classList.add("hidden");

        resolve(false);
      });

      // Close on Escape key

      const handleEscape = (e) => {
        if (e.key === "Escape") {
          modal.classList.add("hidden");

          document.removeEventListener("keydown", handleEscape);

          resolve(false);
        }
      };

      document.addEventListener("keydown", handleEscape);
    });
  }

  // Custom success modal to show success messages with green theme
  function showSuccessModal(message) {
    return new Promise((resolve) => {
      const modal = document.getElementById("successModal");
      const messageDiv = document.getElementById("successMessage");
      const okBtn = document.getElementById("successOk");

      // Set the message
      messageDiv.textContent = message;

      // Show the modal
      modal.classList.remove("hidden");

      // Remove existing event listeners
      const newOkBtn = okBtn.cloneNode(true);
      okBtn.parentNode.replaceChild(newOkBtn, okBtn);

      // Add event listener
      newOkBtn.addEventListener("click", () => {
        modal.classList.add("hidden");
        resolve(true);
      });

      // Close on backdrop click
      modal.querySelector(".modal-backdrop").addEventListener("click", () => {
        modal.classList.add("hidden");
        resolve(true);
      });

      // Close on Escape key
      const handleEscape = (e) => {
        if (e.key === "Escape") {
          modal.classList.add("hidden");
          document.removeEventListener("keydown", handleEscape);
          resolve(true);
        }
      };
      document.addEventListener("keydown", handleEscape);
    });
  }

  // Function to populate incident action container
  async function populateIncidentActionContainer(eventId) {
    try {
      console.log(
        `[Incident] Checking for existing incident for correlation ID: ${eventId}`,
      );

      // Check if incident exists for this correlation ID
      const response = await api(
        "GET",
        `/api/incidents/by-correlation-id/${eventId}`,
      );

      const container = document.getElementById("incidentActionContainer");
      if (!container) {
        console.error("[Incident] incidentActionContainer not found");
        return;
      }

      if (response.success && response.incident) {
        // Incident exists - show incident ID
        const incidentNumber =
          response.incident.incidentNumber ||
          response.incident.incident_number ||
          "Unknown";
        const incidentStatus =
          response.incident.currentStatus ||
          response.incident.incidentStatus ||
          "Unknown";
        const incidentSysId =
          response.incident.incidentSysId || response.incident.sys_id || "";
        const snowUrl = incidentSysId
          ? `${state.servicenowBaseUrl}/incident.do?sys_id=${encodeURIComponent(incidentSysId)}`
          : `${state.servicenowBaseUrl}/incident.do?number=${encodeURIComponent(incidentNumber)}`;
        const statusText = getSnowStatusText(incidentStatus);
        const statusClass = getSnowStatusClass(incidentStatus);

        container.innerHTML = `
          <a href="${escapeHtml(snowUrl)}" target="_blank" rel="noopener noreferrer"
             title="Open ${escapeHtml(incidentNumber)} in ServiceNow"
             style="display: flex; align-items: center; gap: 12px; padding: 10px 16px;
                    background: var(--success-bg, #f0f9ff); border: 1px solid #0ea5e9;
                    border-radius: 6px; text-decoration: none;
                    cursor: pointer; transition: box-shadow 0.18s ease, transform 0.12s ease;"
             onmouseover="this.style.boxShadow='0 4px 14px rgba(0,161,224,0.25)';this.style.transform='translateY(-1px)'"
             onmouseout="this.style.boxShadow='none';this.style.transform='none'">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0ea5e9" stroke-width="2" style="flex-shrink:0;">
              <path d="M9 11l3 3L22 4"/>
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
            </svg>
            <div style="flex:1; min-width:0;">
              <div style="font-weight: 700; color: #0ea5e9; font-size: 13px;">Incident Created</div>
              <div style="font-size: 12px; color: var(--text-secondary, #52586e); margin-top: 2px;">
                <span style="font-family: 'SF Mono','Monaco',monospace; font-weight: 600;">${escapeHtml(incidentNumber)}</span>
                &nbsp;·&nbsp;
                <span class="snow-status-badge snow-status-${escapeHtml(statusClass)}" style="font-size:10px;">${escapeHtml(statusText)}</span>
              </div>
            </div>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0ea5e9" stroke-width="2.5" style="flex-shrink:0; opacity:0.7;">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
              <polyline points="15 3 21 3 21 9"/>
              <line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </a>
        `;

        console.log(`[Incident] Found existing incident: ${incidentNumber}`);
      } else {
        // No incident exists - show Create ServiceNow Ticket button
        container.innerHTML = `
          <button class="btn" id="correlationActionButton" style="background: var(--accent-color, #2563EB); color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: 500; display: flex; align-items: center; gap: 8px;" onclick="handleCorrelationAction()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10 9 9 9 8 9"/>
            </svg>
            <span>Create ServiceNow Ticket</span>
          </button>
        `;

        console.log(
          `[Incident] No existing incident found, showing Create button`,
        );
      }
    } catch (error) {
      console.error("[Incident] Error checking for existing incident:", error);

      // On error, default to showing the Create button
      const container = document.getElementById("incidentActionContainer");
      if (container) {
        container.innerHTML = `
          <button class="btn" id="correlationActionButton" style="background: var(--accent-color, #2563EB); color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: 500; display: flex; align-items: center; gap: 8px;" onclick="handleCorrelationAction()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10 9 9 9 8 9"/>
            </svg>
            <span>Create ServiceNow Ticket</span>
          </button>
        `;
      }
    }
  }

  window.populateIncidentActionContainer = populateIncidentActionContainer;

  // Event Details Modal

  async function showEventDetails(eventId) {
    try {
      showLoading();

      // Check if we're in local file mode

      if (state.currentEnvId === "local") {
        // For local files, extract information from existing logs instead of API calls

        const allLogs = state.logs || [];

        const matchingLogs = allLogs.filter((log) => log.event_id === eventId);

        console.log(
          `[showEventDetails] eventId: ${eventId}, matchingLogs count: ${matchingLogs.length}`,
        );

        console.log(`[showEventDetails] matchingLogs:`, matchingLogs);

        if (matchingLogs.length > 0) {
          // Extract application name from first matching log

          const firstLog = matchingLogs[0];

          // Check if any log has exception with Element key to extract appName

          let extractedAppName = null;

          for (let i = 0; i < matchingLogs.length; i++) {
            if (
              matchingLogs[i] &&
              matchingLogs[i].exception &&
              matchingLogs[i].exception.Element
            ) {
              const elementValue = matchingLogs[i].exception.Element;

              console.log(
                `[showEventDetails] Found Element in log[${i}]:`,
                elementValue,
              );

              // Extract appName from Element like: "msd-sep-accint-job-candidate-match-papi-v1:api.xml:14"

              const elementMatch = elementValue.match(/@([^:]+):/);

              if (elementMatch) {
                extractedAppName = elementMatch[1];

                console.log(
                  `[showEventDetails] Extracted appName from Element: ${extractedAppName}`,
                );

                break;
              }
            }
          }

          const appName =
            extractedAppName ||
            firstLog.application ||
            firstLog.component ||
            "Local Application";

          console.log(`[showEventDetails] Final appName: ${appName}`);

          // Add application name to all matching logs

          matchingLogs.forEach((log) => {
            log.application = appName;
          });

          console.log(
            `Local mode: Found ${matchingLogs.length} logs for event ID ${eventId}`,
          );

          renderEventDetailsModal(eventId, matchingLogs, appName);
        } else {
          alert("No logs found for this event ID in the local file");
        }
      } else {
        // Anypoint mode: Search across ALL applications in environment for this event ID

        const allApplications = state.applications;

        let allMatchingLogs = []; // Collect ALL logs with this event ID across all apps

        let firstMatchingAppName = "Unknown Application";

        for (const app of allApplications) {
          try {
            const result = await api(
              "GET",

              `/api/environments/${state.currentEnvId}/applications/${app.id}/logs`,
            );

            if (result.success && result.logs.length > 0) {
              console.log(`Full API response for app ${app.name}:`, result);

              const appMatchingLogs = result.logs.filter(
                (log) => log.event_id === eventId,
              );

              if (appMatchingLogs.length > 0) {
                console.log(
                  `Matching log for event ID ${eventId}:`,

                  appMatchingLogs[0],
                );

                // Add app name to each log for chain analysis

                appMatchingLogs.forEach((log) => {
                  log.application = app.name;
                });

                allMatchingLogs.push(...appMatchingLogs);

                if (
                  !firstMatchingAppName ||
                  firstMatchingAppName === "Unknown Application"
                ) {
                  firstMatchingAppName = app.name;
                }
              }
            }
          } catch (appErr) {
            console.error(
              `[showEventDetails] Error fetching logs for app ${app.name}:`,
              appErr,
            );
          }
        }

        if (allMatchingLogs.length > 0) {
          renderEventDetailsModal(
            eventId,

            allMatchingLogs,

            firstMatchingAppName,
          );
        } else {
          alert("No logs found for this event ID in any application");
        }
      }
    } catch (err) {
      console.error("Error fetching event details:", err);

      alert("Failed to fetch event details");
    } finally {
      hideLoading();
    }
  }

  function renderEventDetailsModal(eventId, logs, appName) {
    // Debug: Print function parameters

    console.log(
      `[renderEventDetailsModal] eventId: ${eventId}, logs count: ${logs?.length}, appName: ${appName}`,
    );

    console.log(`[renderEventDetailsModal] logs array:`, logs);

    // Use the provided app name instead of looking it up

    const currentAppName = appName || "Unknown Application";

    // Analyze error chain across all logs

    const errorChainAnalysis = analyzeErrorChain(eventId, currentAppName, logs);

    // Store context for Analyze Error and Custom Prompt (stored-context pattern)

    const errorDescription =
      logs.length > 0
        ? logs[0].message || "Error occurred"
        : "No error details available";

    window.__eventDetailsContext = {
      logs: logs,

      appName: currentAppName,

      eventId: eventId,

      referenceFile: null,

      analysisFlowState: "attach",

      errorDescription: errorDescription,

      summaryClarityLevel: 0,

      lastSummaryObservations: "",

      lastSummaryRca: "",

      summaryRequestInFlight: false,

      expectedUploadFiles: collectExpectedUploadFiles(logs),
    };

    stopAutoRefresh();

    // Ensure hidden file input exists for Open File from Local

    let localFileInput = document.getElementById("localFileInput");

    if (!localFileInput) {
      localFileInput = document.createElement("input");

      localFileInput.type = "file";

      localFileInput.id = "localFileInput";

      localFileInput.style.display = "none";
      
      document.body.appendChild(localFileInput);

      localFileInput.addEventListener(
        "change",

        function handleLocalFileSelect(e) {
          const files = Array.from(e.target.files || []);

          if (!files || files.length === 0) return;

          console.log(`📁 Selected ${files.length} files:`, files.map(f => f.name));

          // For multiple files, use multi-file upload endpoint
          if (files.length > 1) {
            window.uploadMultipleLocalFiles(files);
          } else {
            // For single file, show file selection interface instead of immediate analysis
            const file = files[0];
            window.uploadSingleLocalFile(file);
          }
        },
      );
    }

    // Create modal HTML
    const modalHtml = `
      <div class="event-details-modal" id="eventDetailsModal">
        <div class="event-details-backdrop"></div>
        <div class="event-details-content">
          <div class="event-details-header">
            <div style="display: flex; align-items: center; gap: 12px; flex: 1;">
              <h3 style="margin: 0;">Event Details: ${eventId}</h3>
              <div id="servicenowButtonContainer" class="servicenow-action-container" style="margin-left: auto;"></div>
            </div>
            <button class="btn-icon" id="closeEventDetails" title="Close" onclick="closeEventDetailsModal()">✕</button>
          </div>
          <div class="event-details-body">
            <div class="event-details-copy-bar">
              <button class="btn-copy-logs" id="copyLogContext" title="Copy log context to clipboard">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
                  <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
                </svg>
                <span>Copy logs</span>
              </button>
            </div>
            <div class="reference-file-indicator" id="referenceFileIndicator" style="display:none;"></div>
            <div class="event-chain-analysis">
              <div class="event-chain-title">Error Origin & Chain Analysis</div>
              <div class="event-chain-content">
                <div>
                  <strong>Root API:</strong> ${escapeHtml(errorChainAnalysis.origin)}
                </div>
                <div>
                  <strong>Error Chain:</strong> ${escapeHtml(errorChainAnalysis.chain)}
                </div>
                <div>
                  <strong>Explanation:</strong> ${escapeHtml(errorChainAnalysis.explanation)}
                </div>
                ${
                  errorChainAnalysis.affectedApps.length > 1
                    ? `
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #ddd6fe;">
                  <strong>Affected APIs:</strong> ${escapeHtml(errorChainAnalysis.affectedApps.join(", "))}
                </div>
                `
                    : ""
                }
              </div>
            </div>
            <div class="event-details-ai-summary">
              <div class="summary-header summary-header-row">
                <span class="summary-header-title">AI Error Summary</span>
                <button type="button" class="btn-summary-refresh" id="refreshAiErrorSummary" disabled title="Available after the first summary loads" aria-label="Simpler explanation">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M21 2v6h-6"/>
                    <path d="M3 12a9 9 0 0 1 15-6.7L21 8"/>
                    <path d="M3 22v-6h6"/>
                    <path d="M21 12a9 9 0 0 1-15 6.7L3 16"/>
                  </svg>
                </button>
              </div>
              <div class="summary-loading" id="eventDetailsAiSummaryBody" data-log-index="0">
                <span>⟳</span> Analyzing error with AI...
              </div>
            </div>
            ${(() => {
              // Process all logs into a single consolidated view
              const logDetails = logs.map((log, index) => {
                console.log(
                  `Debug logs[${index}] - FULL EXCEPTION:`,

                  JSON.stringify(log.exception, null, 2),
                );

                let fileName = log.component || "N/A";

                let apiName = "Unknown API";

                const elementField = log.exception?.Element;

                const elementDslField = log.exception?.["Element DSL"];

                const fieldToUse = elementField || elementDslField;

                // Extract API name from Element field

                if (fieldToUse) {
                  apiName = extractApiNameFromElement(fieldToUse);
                }

                console.log(`Debug logs[${index}] - Element:`, elementField);

                console.log(
                  `Debug logs[${index}] - Element DSL:`,

                  elementDslField,
                );

                console.log(`Debug logs[${index}] - fieldToUse:`, fieldToUse);

                console.log(
                  `Debug logs[${index}] - extracted API name:`,

                  apiName,
                );

                // Enhanced file name extraction from multiple sources
                let extractedFileName = null;
                
                // 1. Try to extract from Element field
                if (fieldToUse) {
                  extractedFileName = extractFilenameFromElement(fieldToUse);
                  console.log(`Debug logs[${index}] - extracted from Element:`, extractedFileName);
                }
                
                // 2. Try to extract from exception's file-related fields
                if (!extractedFileName && log.exception) {
                  // Check common file-related fields in exception
                  const fileFields = ['file', 'fileName', 'filename', 'File', 'FileName'];
                  for (const field of fileFields) {
                    if (log.exception[field]) {
                      extractedFileName = log.exception[field];
                      console.log(`Debug logs[${index}] - extracted from exception.${field}:`, extractedFileName);
                      break;
                    }
                  }
                }
                
                // 3. Try to extract from log's direct file fields
                if (!extractedFileName) {
                  const directFileFields = ['fileName', 'filename', 'file', 'File'];
                  for (const field of directFileFields) {
                    if (log[field]) {
                      extractedFileName = log[field];
                      console.log(`Debug logs[${index}] - extracted from log.${field}:`, extractedFileName);
                      break;
                    }
                  }
                }
                
                // 4. Try to extract from message content (look for file patterns)
                if (!extractedFileName && log.message) {
                  const filePattern = /(\w+\.(xml|dwl|dw|java|js|py))/gi;
                  const matches = log.message.match(filePattern);
                  if (matches && matches.length > 0) {
                    extractedFileName = matches[0];
                    console.log(`Debug logs[${index}] - extracted from message:`, extractedFileName);
                  }
                }
                
                // Use extracted file name if found, otherwise keep the default
                if (extractedFileName) {
                  fileName = extractedFileName;
                }

                console.log(`Debug logs[${index}] - final fileName:`, fileName);

                let errorMessage = log.message || "N/A";

                if (log.exception && log.exception.Message) {
                  errorMessage = log.exception.Message;
                }

                const locationDetails = extractErrorLocation(fieldToUse || "");

                return {
                  // Use API name from FlowStack as primary application identifier

                  // Only fall back to log.application if apiName couldn't be extracted

                  application:
                    apiName !== "Unknown API"
                      ? apiName
                      : log.application || currentAppName,

                  fileName: fileName,

                  apiName: apiName,

                  errorLocation: locationDetails.fullLocation,

                  errorMessage: errorMessage,

                  fullMessage: log.message || "N/A",

                  index: index,
                };
              });

              // Deduplication function: keep only first occurrence of each unique key

              function deduplicateByKey(details, keyFn) {
                const seen = new Set();

                return details.filter((d) => {
                  const key = keyFn(d);

                  if (seen.has(key)) return false;

                  seen.add(key);

                  return true;
                });
              }

              // Filter function: exclude DefaultExceptionListener and Unknown API entries

              function filterOutSystemDefaults(details) {
                return details.filter((d) => {
                  // Never show DefaultExceptionListener as application

                  if (d.application === "DefaultExceptionListener")
                    return false;

                  // Exclude Unknown API entries

                  if (d.apiName === "Unknown API") return false;

                  return true;
                });
              }

              // Apply filtering first, then deduplicate

              const filteredDetails = filterOutSystemDefaults(logDetails);

              // Deduplicate each detail type to show only unique entries

              const uniqueApplications = deduplicateByKey(
                filteredDetails,

                (d) => d.application,
              );

              const uniqueApiNames = deduplicateByKey(
                filteredDetails,

                (d) => `${d.application}|${d.apiName}`,
              );

              const uniqueFileNames = deduplicateByKey(
                filteredDetails,

                (d) => `${d.application}|${d.fileName}`,
              );

              const uniqueErrorLocations = deduplicateByKey(
                filteredDetails,

                (d) => `${d.application}|${d.errorLocation}`,
              );

              const uniqueErrorMessages = deduplicateByKey(
                filteredDetails,

                (d) => `${d.application}|${d.errorMessage}`,
              );

              // Build consolidated HTML

              return `

              <div class="event-detail-item">

                <div class="event-detail-row">

                  <span class="detail-label">Affected Applications:</span>

                  <span class="detail-value">${escapeHtml(uniqueApplications.map((d) => d.application).join(", ")) || "N/A"}</span>

                </div>

                <div class="event-detail-row">

                  <span class="detail-label">API Names:</span>

                  <span class="detail-value">

                    ${
                      uniqueApiNames.length > 0
                        ? uniqueApiNames

                            .map(
                              (d, i) => `

                      <div class="detail-item-content">

                        <strong>${escapeHtml(d.application)}:</strong> ${escapeHtml(d.apiName)}

                      </div>

                    `,
                            )

                            .join("")
                        : '<span class="no-info">No API information available</span>'
                    }

                  </span>

                </div>

                <div class="event-detail-row">

                  <span class="detail-label">File Names:</span>

                  <span class="detail-value">

                    ${
                      uniqueFileNames.length > 0
                        ? uniqueFileNames

                            .map(
                              (d, i) => `

                      <div class="detail-item-content">

                        <strong>${escapeHtml(d.application)}:</strong> ${escapeHtml(d.fileName)}

                      </div>

                    `,
                            )

                            .join("")
                        : '<span class="no-info">No file information available</span>'
                    }

                  </span>

                </div>

                <div class="event-detail-row">

                  <span class="detail-label">Error Locations:</span>

                  <span class="detail-value">

                    ${
                      uniqueErrorLocations.length > 0
                        ? uniqueErrorLocations

                            .map(
                              (d, i) => `

                      <div class="detail-item-content">

                        <strong>${escapeHtml(d.application)}:</strong> ${escapeHtml(d.errorLocation)}

                      </div>

                    `,
                            )

                            .join("")
                        : '<span class="no-info">No location information available</span>'
                    }

                  </span>

                </div>

                <div class="event-detail-row">

                  <span class="detail-label">Error Descriptions:</span>

                  <span class="detail-value">

                    ${
                      uniqueErrorMessages.length > 0
                        ? uniqueErrorMessages

                            .map(
                              (d, i) => `

                      <div class="detail-item-content">

                        <strong>${escapeHtml(d.application)}:</strong> ${escapeHtml(d.errorMessage)}

                      </div>

                    `,
                            )

                            .join("")
                        : '<span class="no-info">No error description available</span>'
                    }

                  </span>

                </div>

                <div class="event-detail-actions" data-log-index="0" data-file-name="${escapeHtml((filteredDetails.length > 0 ? filteredDetails[0]?.fileName : logs[0]?.component) || "N/A")}"></div>

              </div>

            `;
            })()}

            <div class="event-details-footer" style="margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-color); display: flex; justify-content: center; align-items: center;">
              <div id="incidentActionContainer"></div>
            </div>

          </div>

        </div>

      </div>

    `;

    // Add modal to body

    document.body.insertAdjacentHTML("beforeend", modalHtml);

    // Debug: Log that modal was added

    console.log("Event details modal added to DOM");

    // Add event listeners immediately after DOM insertion

    const setupEventListeners = () => {
      const closeBtn = document.getElementById("closeEventDetails");

      const backdrop = document.querySelector(
        "#eventDetailsModal .event-details-backdrop",
      );

      const copyBtn = document.getElementById("copyLogContext");

      console.log("Setting up event listeners...");

      console.log("closeBtn found:", !!closeBtn);

      console.log("backdrop found:", !!backdrop);

      console.log("copyBtn found:", !!copyBtn);

      if (closeBtn) {
        closeBtn.addEventListener("click", (e) => {
          e.preventDefault();

          e.stopPropagation();

          console.log("Close button clicked!");

          closeEventDetailsModal();
        });

        console.log(
          "Event details close button listener attached successfully",
        );
      } else {
        console.error("closeEventDetails button not found - retrying...");

        // Retry after a short delay

        setTimeout(setupEventListeners, 50);

        return;
      }

      if (backdrop) {
        backdrop.addEventListener("click", (e) => {
          e.preventDefault();

          e.stopPropagation();

          console.log("Backdrop clicked!");

          closeEventDetailsModal();
        });
      }

      if (copyBtn) {
        copyBtn.addEventListener("click", copyLogContextToClipboard);
      }

      const refreshSummaryBtn = document.getElementById(
        "refreshAiErrorSummary",
      );

      if (refreshSummaryBtn) {
        refreshSummaryBtn.addEventListener("click", (e) => {
          e.preventDefault();

          e.stopPropagation();

          const ctx = window.__eventDetailsContext;

          if (!ctx || !ctx.logs || ctx.logs.length === 0) return;

          if (ctx.summaryRequestInFlight) return;

          if (ctx.summaryClarityLevel >= MAX_SUMMARY_CLARITY_LEVEL) return;

          if (!ctx.lastSummaryObservations && !ctx.lastSummaryRca) return;

          ctx.summaryClarityLevel += 1;

          let targetLog = null;

          for (let i = 0; i < ctx.logs.length; i++) {
            if (ctx.logs[i] && ctx.logs[i].exception) {
              targetLog = ctx.logs[i];

              break;
            }
          }

          targetLog = targetLog || ctx.logs[0];

          const appName = ctx.appName || "Unknown Application";

          generateErrorSummary(targetLog, 0, appName, {
            clarityLevel: ctx.summaryClarityLevel,

            previousObservations: ctx.lastSummaryObservations || "",

            previousRca: ctx.lastSummaryRca || "",
          });
        });
      }

      updateAiSummaryRefreshButtonState();

      // Add ESC key listener to close modal

      const escKeyHandler = (e) => {
        if (e.key === "Escape") {
          console.log("ESC key pressed - closing modal");

          closeEventDetailsModal();

          document.removeEventListener("keydown", escKeyHandler);
        }
      };

      document.addEventListener("keydown", escKeyHandler);
    };

    // Try to set up listeners immediately

    setupEventListeners();

    // Check for existing incident and populate incidentActionContainer

    populateIncidentActionContainer(eventId);

    document

      .getElementById("eventDetailsModal")

      .addEventListener("click", function handleFlowButtonClick(e) {
        const btn = e.target.closest("[data-action]");

        if (!btn) return;

        const action = btn.dataset.action;

        const ctx = window.__eventDetailsContext;

        if (!ctx) return;

        if (action === "upload-local") {
          openFileFromLocal();
        } else if (action === "upload-github") {
          const fileName = btn.dataset.fileName || "";
          const errorDescription = ctx.errorDescription || "";
          
          // Start multi-file analysis directly for GitHub files
          setEventDetailsFlowState("loading-github");
          startMultiFileAnalysisFromEventDetails(ctx, "github", fileName);
        } else if (action === "generate-changes") {
          const fileName = btn.dataset.fileName || "";

          const errorDescription = ctx.errorDescription || "";

          const appName = ctx.appName || "Unknown Application";

          // Check if we're in local mode or GitHub mode

          if (state.currentEnvId === "local") {
            // Local mode: use current log file content

            const errorText =
              ctx.logs?.[0]?.message ||
              ctx.errorDescription ||
              errorDescription;

            if (errorText) {
              // Create a file object that matches the expected structure
              const resolvedName =
                (fileName &&
                  fileName !== "N/A" &&
                  String(fileName).toLowerCase() !== "defaultexceptionlistener" &&
                  fileName) ||
                getErrorFileNameFromLog(ctx.logs?.[0]) ||
                "unknown-file.xml";

              const localFile = {
                name: resolvedName,

                content: errorText,

                path: resolvedName,

                owner: null,

                repo: null,
              };

              runGenerateCodeChanges(localFile);
            } else {
              alert("No error description available for code generation");
            }
          } else {
            // GitHub mode: use original GitHub flow
            const resolvedGithubName =
              (fileName &&
                fileName !== "N/A" &&
                String(fileName).toLowerCase() !== "defaultexceptionlistener" &&
                fileName) ||
              getErrorFileNameFromLog(ctx.logs?.[0]) ||
              fileName;

            openFileOnGithub(appName, resolvedGithubName, errorDescription);
          }
        } else if (action === "flow-cancel") {
          const ctx = window.__eventDetailsContext;
          if (ctx && ctx.eventId) {
            handleExpectedErrorToggle(ctx.eventId);
          } else {
            closeEventDetailsModal();
          }
        }
      });

    updateReferenceFileIndicator();

    updateEventDetailFlowButtons();

    // Generate AI summary for first log when modal opens

    if (logs.length > 0) {
      // Use setTimeout to ensure DOM is ready

      setTimeout(() => {
        // Find the first log that has an exception

        let logWithException = null;

        for (let i = 0; i < logs.length; i++) {
          if (logs[i] && logs[i].exception) {
            logWithException = logs[i];

            console.log(
              `[AutoSummary] Found log with exception at index ${i}:`,
              logs[i].exception,
            );

            break;
          }
        }

        // Use the log with exception, or fallback to first log

        const targetLog = logWithException || logs[0];

        console.log(`[AutoSummary] Using log for AI analysis:`, targetLog);

        // Always use index 0 since HTML is hardcoded to data-log-index="0"

        generateErrorSummary(targetLog, 0, appName, {
          clarityLevel: 0,
        });
      }, 100);
    }
  }

  function updateReferenceFileIndicator() {
    const indicator = document.getElementById("referenceFileIndicator");

    if (!indicator) return;

    const ctx = window.__eventDetailsContext;

    if (ctx?.referenceFile) {
      indicator.style.display = "flex";

      indicator.innerHTML = `<span>File attached: ${escapeHtml(ctx.referenceFile.name)}</span>

        <button type="button" class="btn-icon btn-icon-small" id="clearReferenceFile" title="Remove file">✕</button>`;

      const clearBtn = document.getElementById("clearReferenceFile");

      if (clearBtn)
        clearBtn.addEventListener("click", () => {
          if (ctx) {
            ctx.referenceFile = null;

            ctx.analysisFlowState = "attach";
          }

          updateReferenceFileIndicator();

          updateEventDetailFlowButtons();
        });
    } else {
      indicator.style.display = "none";

      indicator.innerHTML = "";
    }
  }

  function copyLogContextToClipboard() {
    const ctx = window.__eventDetailsContext;

    if (!ctx?.logs?.length) {
      alert("Nothing to copy.");

      return;
    }

    const appName = ctx.appName || "Unknown Application";

    const blocks = ctx.logs.map((log) => serializeErrorBlock(log, appName));

    const logContext = blocks.join("\n\n---\n\n");

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard

        .writeText(logContext)

        .then(() => {
          showCopyFeedback();
        })

        .catch(() => {
          fallbackCopyToClipboard(logContext);
        });
    } else {
      fallbackCopyToClipboard(logContext);
    }
  }

  function fallbackCopyToClipboard(text) {
    const ta = document.createElement("textarea");

    ta.value = text;

    ta.style.position = "fixed";

    ta.style.left = "-9999px";

    document.body.appendChild(ta);

    ta.select();

    try {
      document.execCommand("copy");

      showCopyFeedback();
    } catch (e) {
      alert("Copy failed. Please select and copy manually.");
    }

    document.body.removeChild(ta);
  }

  function showCopyFeedback() {
    const btn = document.getElementById("copyLogContext");

    if (!btn) return;

    const span = btn.querySelector("span");

    if (span) {
      const orig = span.textContent;

      span.textContent = "Copied!";

      setTimeout(() => {
        span.textContent = orig;
      }, 1500);
    }
  }

  function serializeErrorBlock(log, appName) {
    const parts = [
      `Application: ${appName}`,

      `Event ID: ${log.event_id || "N/A"}`,

      `Timestamp: ${log.timestamp || "N/A"}`,

      `Level: ${log.level || "N/A"}`,

      `Component: ${log.component || "N/A"}`,

      `Context: ${log.context || "N/A"}`,

      ``,

      `Log Message: ${log.message || "N/A"}`,

      ``,
    ];

    if (log.exception) {
      parts.push("Exception Details:");

      const exc = log.exception;

      for (const [k, v] of Object.entries(exc)) {
        if (k !== "raw" && v) parts.push(`  ${k}: ${v}`);
      }

      if (exc.raw && exc.raw.length) {
        parts.push("  Raw block:");

        exc.raw.forEach((l) => parts.push(`    ${l}`));
      }

      parts.push("");
    }

    if (log.details) parts.push(`Details:\n${log.details}`);

    return parts.join("\n");
  }

  function parseExpectedFileFromError(log) {
    const elementField = log.exception?.Element;

    const elementDslField = log.exception?.["Element DSL"];

    const fieldToUse = elementField || elementDslField;

    if (!fieldToUse) return "";

    const extracted = extractFilenameFromElement(fieldToUse);

    if (!extracted) return "";

    const afterAt = fieldToUse.includes("@")
      ? fieldToUse.split("@").pop().trim()
      : fieldToUse.trim();

    const lineMatch = afterAt.match(/:(\d+)\s*(?:\([^)]*\)\s*)?$/);

    return lineMatch ? `${extracted}:${lineMatch[1]}` : extracted;
  }

  function getErrorFileNameFromLog(log) {
    if (!log) return "";

    const elementField = log.exception?.Element;

    const elementDslField = log.exception?.["Element DSL"];

    const fieldToUse = elementField || elementDslField;

    if (fieldToUse) {
      const extracted = extractFilenameFromElement(fieldToUse);

      if (extracted) return extracted;

      const atMatch = fieldToUse.match(/@([^:]+):/);

      if (atMatch) return atMatch[1];

      const fileMatch = fieldToUse.match(/([^\/\\]+\.[a-zA-Z0-9]+)$/);

      if (fileMatch) return fileMatch[1];

      return fieldToUse;
    }

    // Mule often sets component to "DefaultExceptionListener" — that is NOT the source file.
    if (log.message) {
      const filePattern = /([^\/\s]+\.(xml|dwl|dw))/gi;
      const matches = log.message.match(filePattern);
      if (matches && matches.length > 0) {
        return matches[0].split("/").pop();
      }
    }

    const comp = (log.component || "").trim();
    if (
      comp &&
      comp !== "N/A" &&
      comp.toLowerCase() !== "defaultexceptionlistener"
    ) {
      return comp;
    }

    return "";
  }

  // Global functions for button clicks

  window.openFileFromLocal = function () {
    const input = document.getElementById("localFileInput");
    let expectedFiles = window.__eventDetailsContext?.expectedUploadFiles || [];

    if (!expectedFiles || expectedFiles.length <= 1) {
      const modal = document.getElementById("eventDetailsModal");
      const labels = modal
        ? Array.from(modal.querySelectorAll(".detail-label"))
        : [];
      const fileNamesLabel = labels.find(
        (label) => (label.textContent || "").trim() === "File Names:",
      );
      const row = fileNamesLabel ? fileNamesLabel.closest(".event-detail-row") : null;
      const valueContainer = row ? row.querySelector(".detail-value") : null;
      const itemNodes = valueContainer
        ? Array.from(valueContainer.querySelectorAll(".detail-item-content"))
        : [];

      const parsedNames = itemNodes
        .map((node) => {
          const clone = node.cloneNode(true);
          const strong = clone.querySelector("strong");
          if (strong) strong.remove();
          return String(clone.textContent || "")
            .split("\\")
            .pop()
            .split("/")
            .pop()
            .trim();
        })
        .filter((name) => name && name !== "N/A");

      const seen = new Set();
      expectedFiles = parsedNames.filter((name) => {
        const key = name.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });

      if (window.__eventDetailsContext) {
        window.__eventDetailsContext.expectedUploadFiles = expectedFiles;
      }
    }

    if (input) {
      input.multiple = expectedFiles.length > 1;
      input.value = "";
      input.click();
    }
  };

  window.openFileOnGithub = async function (
    appName,

    fileName,

    errorDescription,
  ) {
    if (!fileName) {
      alert("File name not available");

      return;
    }

    // Recheck session to get latest authentication state

    await checkSession();

    // Check if user is authenticated with GitHub

    if (!state.githubAuthenticated) {
      // Store the pending request to resume after login

      state.pendingGitHubFileRequest = {
        appName,

        fileName,

        errorDescription,
      };

      // Show GitHub login popup modal

      const modal = document.getElementById("githubLoginModal");

      if (modal) {
        modal.classList.remove("hidden");

        // Focus on username field

        setTimeout(() => {
          document.getElementById("popupGithubUsername").focus();
        }, 100);
      }

      return;
    }

    // Get GitHub username from state (loaded from backend session)

    const username = state.githubUsername || "MJPWC";

    // Call GitHub API to search for the file

    searchGitHubFile(fileName, username, errorDescription);
  };

  // Open file in GitHub tab (from Event Details Upload from GitHub)

  async function openFileInGitHubTab(fileInfo, content, owner, repo, filePath) {
    state.selectedRepo = {
      owner,

      repoName: repo,

      fullName: `${owner}/${repo}`,
    };

    state.selectedFile = {
      path: filePath,

      content,

      name: fileInfo.name,

      owner,

      repoName: repo,
    };

    state.currentPath = filePath.includes("/")
      ? filePath.split("/").slice(0, -1).join("/")
      : "";

    const ctx = window.__eventDetailsContext;

    if (ctx) {
      state.pendingGitHubErrorContext = {
        logs: ctx.logs,

        appName: ctx.appName,

        errorDescription: ctx.errorDescription,
      };

      // Persist correlation/log context for the PR->ServiceNow step
      state.ticketContextForPR = {
        eventId: ctx.eventId,
        logs: ctx.logs,
        appName: ctx.appName,
      };

      closeEventDetailsModal();
    }

    await switchTab("github");

    renderFileContent();
  }

  // Search GitHub file and show content in panel

  async function searchGitHubFile(filename, username, errorDescription) {
    try {
      showLoading();

      // Call backend API instead of direct GitHub API (to avoid CORS)

      const response = await api("POST", "/api/github/search", {
        filename: filename,

        username: username,
      });

      hideLoading();

      if (response.success) {
        // Parse GitHub URL to get owner, repo, and path

        const githubUrl = new URL(response.file.html_url);

        const pathParts = githubUrl.pathname.split("/");

        const owner = pathParts[1];

        const repo = pathParts[2];

        const filePath = pathParts.slice(5).join("/"); // Skip 'blob' and commit hash

        // Fetch file content using existing GitHub file API

        const fileResult = await api(
          "GET",

          `/api/github/file/${owner}/${repo}/${filePath}`,
        );

        if (fileResult.success) {
          openFileInGitHubTab(
            response.file,

            fileResult.content,

            owner,

            repo,

            filePath,
          );

          // Close the parent event details modal if it exists

          const eventDetailsModal =
            document.getElementById("eventDetailsModal");

          if (eventDetailsModal) {
            closeEventDetailsModal();
          }
        } else {
          console.error("Failed to load file content:", fileResult.error);
        }

        console.log("✅ GitHub file found:", response.file.name);
      } else {
        alert(`Failed to fetch from GitHub: ${response.error}`);
      }
    } catch (err) {
      hideLoading();

      alert(`GitHub search failed: ${err.message}`);
    }
  }

  // Analyze Error button - uses ruleset, immediately runs analysis

  window.analyzeErrorWithRuleset = async function (logIndex) {
    const ctx = window.__eventDetailsContext;

    if (!ctx) {
      alert(
        "Event details context not available. Please reopen the event details.",
      );

      return;
    }

    const log = ctx.logs[logIndex];

    if (!log) {
      alert("Log not found.");

      return;
    }

    const appName = ctx.appName || "Unknown Application";

    const errorMessage = log.exception?.Message || log.message || "N/A";

    let fileName = log.component || "N/A";

    // Debug: Log the entire exception object

    console.log("Debug - full exception object:", log.exception);

    // Try to extract file name from Element field first, then Element DSL field

    const elementField = log.exception?.Element;

    const elementDslField = log.exception?.["Element DSL"];

    const fieldToUse = elementField || elementDslField;

    console.log("Debug - elementField:", elementField); // Debug log

    console.log("Debug - elementDslField:", elementDslField); // Debug log

    console.log("Debug - fieldToUse:", fieldToUse); // Debug log

    if (fieldToUse) {
      // Handle different formats: @file.xml:line or just file.xml

      const atMatch = fieldToUse.match(/@([^:]+):/);

      if (atMatch) {
        fileName = atMatch[1];

        console.log("Debug - extracted from @match:", fileName); // Debug log
      } else {
        // Extract just the filename from path

        const fileMatch = fieldToUse.match(/([^\/\\]+\.[a-zA-Z0-9]+)$/);

        if (fileMatch) {
          fileName = fileMatch[1];

          console.log("Debug - extracted from fileMatch:", fileName); // Debug log
        } else {
          fileName = fieldToUse;

          console.log("Debug - using fieldToUse as fileName:", fileName); // Debug log
        }
      }
    }

    console.log("Debug - final fileName:", fileName); // Debug log

    // Create AI analysis modal with loading state
    window.AppModalUtils.ensureAiAnalysisModal();

    // Refresh button in AI Analysis Modal

    const btnRefreshAnalysis = document.getElementById("btnRefreshAnalysis");

    if (btnRefreshAnalysis) {
      btnRefreshAnalysis.addEventListener("click", async () => {
        const ctx = window.__eventDetailsContext;

        if (!ctx || !ctx.logs || ctx.logs.length === 0) {
          alert("No error context available for refresh");

          return;
        }

        // Get the original error details

        const fileName = ctx.logs[0]?.component || "unknown-file.xml";

        const errorText =
          ctx.logs[0]?.message || "No error description available";

        // Perform initial AI analysis (not re-run)

        const fullErrorBlock = serializeErrorBlock(
          ctx.logs[0],

          ctx.appName || "Unknown Application",
        );

        const resultDiv = document.getElementById("errorAnalysisResult");

        if (!resultDiv) return;

        resultDiv.innerHTML =
          '<div class="loading">Analyzing error with ruleset...</div>';

        try {
          const payload = {
            content: fullErrorBlock,
            prompt:
              "Analyze this MuleSoft error using the error-analysis ruleset. Output ALL required sections with bold section headers (e.g., **Summary**, **Quick Fix**, etc.). Do not omit any section even if values are N/A.",
            file_path: fileName,
            ruleset: "error-analysis-rules.txt",
          };

          // Use the regular analyze endpoint with error-analysis-rules.txt

          const result = await api("POST", "/api/error/analyze", payload);

          if (result.success) {
            const formattedAnalysis = formatAnalysis(result.analysis);
            renderAnalysisWithRefine(
              resultDiv,
              `<div class="analysis-text">${formattedAnalysis}</div>`,
              async function regenerateCallback(additionalInput) {
                const combinedPrompt = additionalInput
                  ? payload.prompt +
                    "\n\nAdditional context from user:\n" +
                    additionalInput
                  : payload.prompt;
                
                // Store user's additional context for code generation
                if (window.__eventDetailsContext) {
                  window.__eventDetailsContext.lastUserContext = additionalInput || "";
                }
                
                resultDiv.innerHTML =
                  '<div class="loading">Regenerating analysis...</div>';
                try {
                  const r2 = await api("POST", "/api/error/analyze", {
                    ...payload,
                    prompt: combinedPrompt,
                  });
                  if (r2.success) {
                    renderAnalysisWithRefine(
                      resultDiv,
                      `<div class="analysis-text">${formatAnalysis(r2.analysis)}</div>`,
                      regenerateCallback,
                    );
                  } else {
                    resultDiv.innerHTML = `<div class="error">Regeneration failed: ${r2.error}</div>`;
                  }
                } catch (e2) {
                  resultDiv.innerHTML = `<div class="error">Regeneration failed: ${e2.message}</div>`;
                }
              },
            );
          } else {
            resultDiv.innerHTML = `<div class="error">Analysis failed: ${result.error}</div>`;
          }
        } catch (err) {
          resultDiv.innerHTML = `<div class="error">Analysis failed: ${err.message}</div>`;
        }
      });
    }

    const fullErrorBlock = serializeErrorBlock(log, appName);

    const referenceFile = ctx.referenceFile;

    const prompt =
      "Analyze this MuleSoft error using the error-analysis ruleset. Output ALL required sections with bold section headers (e.g., **Additional Information**, **Summary**, **Quick Fix**, **Error Type**, **Severity**, **Root Cause**, **Impact**, **Immediate Actions**). Do not omit any section even if values are N/A.";

    const payload = {
      content: fullErrorBlock,

      prompt: prompt,

      file_path: fileName,
      ruleset: "error-analysis-rules.txt",
    };

    if (referenceFile) {
      const ext = (referenceFile.name.split(".").pop() || "").toLowerCase();

      payload.reference_file_content = referenceFile.content;

      payload.reference_file_name = referenceFile.name;

      payload.reference_file_extension = ext;

      payload.expected_file_from_error = parseExpectedFileFromError(log);
    }

    // Add AI error summary context if available
    if (ctx.lastSummaryObservations || ctx.lastSummaryRca) {
      payload.ai_error_observations = ctx.lastSummaryObservations || "";
      payload.ai_error_rca = ctx.lastSummaryRca || "";
    }

    // Add refined analysis and user context if available
    if (ctx.refinedAnalysis) {
      payload.refined_analysis = ctx.refinedAnalysis;
    }
    if (ctx.lastUserContext) {
      payload.user_context = ctx.lastUserContext;
    }

    const resultDiv = document.getElementById("errorAnalysisResult");

    try {
      const result = await api("POST", "/api/error/analyze", payload);

      if (result.success) {
        console.log("Raw analysis from LLM:", result.analysis);

        // Store Step 1 output so Step 2 (generate-code-changes) can use it as primary instruction
        if (window.__eventDetailsContext) {
          window.__eventDetailsContext.refinedAnalysis = result.analysis;
        }

        const formattedAnalysis = formatAnalysis(result.analysis);

        console.log("Formatted analysis length:", formattedAnalysis.length);

        console.log(
          "Formatted analysis preview:",

          formattedAnalysis.substring(0, 200),
        );
        renderAnalysisWithRefine(
          resultDiv,
          `<div class="analysis-text">${formattedAnalysis}</div>`,
          async function regenerateCallback(additionalInput) {
            // Regenerate: merge additionalInput into the prompt and re-call
            const ctx2 = window.__eventDetailsContext;
            const log2 = ctx2?.logs?.[logIndex];
            const errorBlock2 = log2
              ? serializeErrorBlock(log2, ctx2?.appName || appName)
              : fullErrorBlock;
            const combinedPrompt = additionalInput
              ? prompt + "\n\nAdditional context from user:\n" + additionalInput
              : prompt;
            const payload2 = { ...payload, prompt: combinedPrompt };
            try {
              const r2 = await api("POST", "/api/error/analyze", payload2);
              if (r2.success) {
                renderAnalysisWithRefine(
                  resultDiv,
                  `<div class="analysis-text">${formatAnalysis(r2.analysis)}</div>`,
                  regenerateCallback,
                );
              } else {
                resultDiv.innerHTML = `<div class="error">Regeneration failed: ${r2.error}</div>`;
              }
            } catch (e2) {
              resultDiv.innerHTML = `<div class="error">Regeneration failed: ${e2.message}</div>`;
            }
          },
        );
      } else {
        resultDiv.innerHTML = `<div class="error">Analysis failed: ${result.error}</div>`;
      }
    } catch (err) {
      resultDiv.innerHTML = `<div class="error">Analysis failed: ${err.message}</div>`;
    }
  };

  // Custom Prompt button - opens popup for user to enter their own prompt

  window.customPromptAnalysis = async function (logIndex) {
    const ctx = window.__eventDetailsContext;

    if (!ctx) {
      alert(
        "Event details context not available. Please reopen the event details.",
      );

      return;
    }

    const log = ctx.logs[logIndex];

    if (!log) {
      alert("Log not found.");

      return;
    }

    const appName = ctx.appName || "Unknown Application";

    const errorMessage = log.exception?.Message || log.message || "N/A";

    let fileName = log.component || "N/A";

    // Try to extract file name from Element field first, then Element DSL field

    const elementField = log.exception?.Element;

    const elementDslField = log.exception?.["Element DSL"];

    const fieldToUse = elementField || elementDslField;

    if (fieldToUse) {
      // Handle different formats: @file.xml:line or just file.xml

      const atMatch = fieldToUse.match(/@([^:]+):/);

      if (atMatch) {
        fileName = atMatch[1];
      } else {
        // Extract just the filename from path

        const fileMatch = fieldToUse.match(/([^\/\\]+\.[a-zA-Z0-9]+)$/);

        if (fileMatch) {
          fileName = fileMatch[1];
        } else {
          fileName = fieldToUse;
        }
      }
    }

    // Create custom prompt modal

    const customPromptModalHtml = `

      <div class="event-details-modal" id="customPromptModal">

        <div class="event-details-backdrop"></div>

        <div class="event-details-content">

          <div class="event-details-header">

            <h3>Custom AI Prompt</h3>

            <button class="btn-icon" id="closeCustomPrompt">✕</button>

          </div>

          <div class="event-details-body">

            <div class="analysis-input-section">

              <div class="analysis-form">
                <h5 style="margin: 0 0 10px 0; color: var(--text-primary); font-size: 13px; font-weight: 600;">User Input</h5>
                <div class="text-input-container">
                  <textarea id="customPromptInput" placeholder="Enter your custom prompt or input here..."></textarea>
                  <button class="btn-primary" id="runCustomPrompt">Send to AI</button>

                </div>

              </div>

            </div>
            <div class="analysis-result hidden" id="customPromptResult"></div>

          </div>

        </div>

      </div>

    `;

    // Add modal to body

    document.body.insertAdjacentHTML("beforeend", customPromptModalHtml);

    // Add event listeners

    document

      .getElementById("closeCustomPrompt")

      .addEventListener("click", closeCustomPromptModal);

    document

      .querySelector("#customPromptModal .event-details-backdrop")

      .addEventListener("click", closeCustomPromptModal);

    document

      .getElementById("runCustomPrompt")

      .addEventListener("click", async () => {
        const prompt = document

          .getElementById("customPromptInput")

          .value.trim();

        if (!prompt) {
          alert("Please enter a prompt");

          return;
        }

        const resultDiv = document.getElementById("customPromptResult");

        resultDiv.innerHTML =
          '<div class="loading">Processing your prompt...</div>';

        resultDiv.classList.remove("hidden");

        const ctx2 = window.__eventDetailsContext;

        const log2 = ctx2?.logs?.[logIndex];

        const fullErrorBlock = log2
          ? serializeErrorBlock(log2, ctx2?.appName || "Unknown Application")
          : errorMessage;

        const referenceFile = ctx2?.referenceFile;

        const payload = {
          content: fullErrorBlock,

          prompt: prompt,

          file_path: fileName,
        };

        if (referenceFile) {
          const ext = (referenceFile.name.split(".").pop() || "").toLowerCase();

          payload.reference_file_content = referenceFile.content;

          payload.reference_file_name = referenceFile.name;

          payload.reference_file_extension = ext;

          payload.expected_file_from_error = log2
            ? parseExpectedFileFromError(log2)
            : "";
        }

        try {
          const result = await api("POST", "/api/error/custom-prompt", payload);

          if (result.success) {
            resultDiv.innerHTML = `<div class="analysis-text">${formatAnalysis(result.analysis)}</div>`;
          } else {
            resultDiv.innerHTML = `<div class="error">Analysis failed: ${result.error}</div>`;
          }
        } catch (err) {
          resultDiv.innerHTML = `<div class="error">Analysis failed: ${err.message}</div>`;
        }
      });
  };

  function closeCustomPromptModal() {
    const modal = document.getElementById("customPromptModal");

    if (modal) {
      modal.remove();
    }
  }

  function closeAiAnalysisModal() {
    window.AppModalUtils.closeAiAnalysisModal();
  }

  // Time Range Filter Helpers

  function getTimeRangeEpoch() {
    const startDate = elements.startDate.value;

    const startTimeVal = elements.startTime.value;

    const endDate = elements.endDate.value;

    const endTimeVal = elements.endTime.value;

    let startEpoch = null;

    let endEpoch = null;

    if (startDate && startTimeVal) {
      const startDateTime = new Date(`${startDate}T${startTimeVal}:00`);

      startEpoch = startDateTime.getTime();
    }

    if (endDate && endTimeVal) {
      const endDateTime = new Date(`${endDate}T${endTimeVal}:00`);

      endEpoch = endDateTime.getTime();
    }

    return { startEpoch, endEpoch };
  }

  function setDefaultDateRange() {
    const today = new Date();

    const yesterday = new Date(today);

    yesterday.setDate(yesterday.getDate() - 1);

    // Format dates as YYYY-MM-DD

    const todayStr = today.toISOString().split("T")[0];

    const yesterdayStr = yesterday.toISOString().split("T")[0];

    elements.startDate.value = yesterdayStr;

    elements.endDate.value = todayStr;
  }

  function toggleFilterPanel() {
    elements.logsFilterPanel.classList.toggle("collapsed");

    elements.filterToggleBtn.classList.toggle("expanded");
  }

  function updateFilterVisibility() {
    // Show filter when an app is selected OR on Correlation tab

    if (elements.logsFilterContainer) {
      if (state.selectedAppId || state.currentTab === "correlation") {
        elements.logsFilterContainer.classList.remove("hidden");
      } else {
        elements.logsFilterContainer.classList.add("hidden");
      }
    }
  }

  function isLogInTimeRange(log) {
    // If no time filter is set, show all logs

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
    // Check if log has a valid (non-empty) event_id

    return log.event_id && log.event_id.trim() !== "";
  }

  function hasErrorDetails(log) {
    // Check if log has actual error details (exception with error type or error message)

    if (!log.exception) {
      return false;
    }

    const exception = log.exception;

    // Check if exception has error type or meaningful error message

    const hasErrorType = exception.ExceptionType || exception["Error type"];

    const hasErrorMessage =
      exception.Message && exception.Message.trim() !== "";

    // Also filter out logs that just say "successful" without actual errors

    const message = log.message || "";

    const isSuccessfulLog =
      message.toLowerCase().includes("successful") &&
      !hasErrorType &&
      !hasErrorMessage;

    return hasErrorType || hasErrorMessage;
  }

  function calculateFilteredErrorCount(appId) {
    // If time filter is active and we have logs for this app, count filtered logs

    if ((state.startTime || state.endTime) && state.appLogs[appId]) {
      return state.appLogs[appId]

        .filter((log) => isLogInTimeRange(log))

        .filter((log) => hasValidEventId(log))

        .filter((log) => hasErrorDetails(log)).length;
    }

    // Otherwise return total error count, filtering out logs without valid event_id or error details

    // to match the detail view display

    return (state.appLogs[appId] || [])

      .filter((log) => hasValidEventId(log))

      .filter((log) => hasErrorDetails(log)).length;
  }

  function applyTimeFilter() {
    const { startEpoch, endEpoch } = getTimeRangeEpoch();

    if (!startEpoch && !endEpoch) {
      alert("Please select a date range");

      return;
    }

    state.startTime = startEpoch;

    state.endTime = endEpoch;

    console.log(
      "Time filter applied - Start:",

      new Date(startEpoch).toISOString(),

      "End:",

      new Date(endEpoch).toISOString(),
    );

    // Close the filter panel after applying

    if (!elements.logsFilterPanel.classList.contains("collapsed")) {
      toggleFilterPanel();
    }

    // Update application list with filtered error counts

    renderApplications();

    // Reload data for active tab with new time range
    if (state.currentTab === "correlation") {
      loadCorrelationIds();
    } else if (state.selectedAppId) {
      loadLogs(state.selectedAppId);
    }
  }

  function clearTimeFilter() {
    // Clear time range state

    state.startTime = null;

    state.endTime = null;

    console.log("Time filter cleared - fetching all logs");

    // Reset filter input fields

    elements.startDate.value = "";

    elements.startTime.value = "00:00";

    elements.endDate.value = "";

    elements.endTime.value = "23:59";

    // Update application list with total error counts

    renderApplications();

    // Reload data without time range filters
    if (state.currentTab === "correlation") {
      loadCorrelationIds();
    } else if (state.selectedAppId) {
      loadLogs(state.selectedAppId);
    }
  }

  function resetTimeFilter() {
    // Clear time range state

    state.startTime = null;

    state.endTime = null;

    console.log("Time filter reset - showing all logs");

    // Reset filter input fields

    elements.startDate.value = "";

    elements.startTime.value = "";

    elements.endDate.value = "";

    elements.endTime.value = "";

    // Update filter visibility

    updateFilterVisibility();
  }

  // ── renderAnalysisWithRefine ────────────────────────────────────────────────
  // Renders formatted analysis HTML into resultDiv, then appends a textarea +
  // Regenerate button so the user can add context and re-run the analysis.
  //
  //   resultDiv   — the DOM element to write into
  //   html        — already-formatted analysis HTML string
  //   onRegenerate(additionalInput) — called with the textarea value when user clicks Regenerate
  // ─────────────────────────────────────────────────────────────────────────────
  function renderAnalysisWithRefine(resultDiv, html, onRegenerate) {
    const refineSection = `
      <div class="refine-section" style="margin-top:20px;padding:14px;border:1px solid var(--color-border-secondary);border-radius:8px;background:var(--color-background-secondary);">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <span style="font-size:13px;font-weight:500;color:var(--color-text-primary);">Not satisfied? Add more context and regenerate</span>
          </div>
          <button class="btn-refresh-analysis" id="btnRefreshAnalysis" title="Regenerate analysis (keeps all context)" style="background:transparent;border:1px solid var(--color-border-secondary);color:var(--color-text-secondary);padding:4px;border-radius:4px;cursor:pointer;transition:all 0.15s ease;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6a2 2 0 0 0 2 2h4a2 2 0 0 0 2 2v2a2 2 0 0 0 2 2h4a2 2 0 0 0 2 2v6a2 2 0 0 0 2 2h4a2 2 0 0 0 2 2v2a2 2 0 0 0 2 2h4a2 2 0 0 0 2 2z"/><path d="M23 4v6a2 2 0 0 1 2 2h4a2 2 0 0 1 2 2v2a2 2 0 0 1 2 2h4a2 2 0 0 1 2 2v6a2 2 0 0 1 2 2h4a2 2 0 0 1 2 2z"/></svg>
          </button>
        </div>
        <textarea id="refineInput" placeholder="e.g. The error also occurs when the payload is empty. Focus on null safety in the transform step..." style="width:100%;min-height:80px;padding:10px;border:1px solid var(--color-border-secondary);border-radius:6px;font-size:13px;line-height:1.5;resize:vertical;box-sizing:border-box;background:var(--color-background-primary);color:var(--color-text-primary);font-family:inherit;"></textarea>
        <div style="display:flex;gap:8px;margin-top:10px;">
          <button class="btn-primary" id="btnRegenerateAnalysis" style="font-size:13px;"> Regenerate analysis</button>
          <button class="btn-secondary" id="btnClearRefine" style="font-size:13px;">Clear</button>
        </div>
      </div>
    `;

    const codeChangesSection = `
      <div class="analysis-action-buttons" style="margin-top:16px;">
        <button class="btn-primary" id="btnGenerateCodeChanges">Generate Code Changes</button>
      </div>
    `;

    resultDiv.innerHTML = html + refineSection + codeChangesSection;

    resultDiv
      .querySelector("#btnRegenerateAnalysis")
      .addEventListener("click", function () {
        const input = resultDiv.querySelector("#refineInput").value.trim();
        resultDiv.innerHTML =
          '<div class="loading">Regenerating analysis...</div>';
        onRegenerate(input);
      });

    // Add event listener for Refresh Analysis button
    resultDiv
      .querySelector("#btnRefreshAnalysis")
      .addEventListener("click", function () {
        resultDiv.innerHTML =
          '<div class="loading">Regenerating analysis...</div>';
        onRegenerate(""); // Regenerate without additional context
      });

    resultDiv
      .querySelector("#btnClearRefine")
      .addEventListener("click", function () {
        resultDiv.querySelector("#refineInput").value = "";
        resultDiv.querySelector("#refineInput").focus();
      });

    // Add event listener for Generate Code Changes button
    const generateBtn = resultDiv.querySelector("#btnGenerateCodeChanges");
    if (generateBtn) {
      generateBtn.addEventListener("click", () => {
        // Check if we're in AI Analysis Modal (has eventDetailsContext) or GitHub panel (has selectedFile)
        const ctx = window.__eventDetailsContext;
        
        if (state.selectedFile) {
          // GitHub panel scenario
          runGenerateCodeChanges(state.selectedFile);
          return;
        }
        
        if (!ctx || !ctx.logs || ctx.logs.length === 0) {
          alert("No error context available for code generation");
          return;
        }

        // Get the current AI analysis result
        let analysisElement = resultDiv?.querySelector(".analysis-text");
        let analysisText = analysisElement?.textContent || "";
        
        // Fallback 1: try to get text from any code blocks or structured content
        if (!analysisText || analysisText.trim().length < 50) {
          const codeBlocks = resultDiv?.querySelectorAll(".analysis-code-block, .analysis-structured, .analysis-section-content");
          if (codeBlocks && codeBlocks.length > 0) {
            analysisText = Array.from(codeBlocks).map(block => block.textContent || "").join("\n\n").trim();
          }
        }
        
        // Fallback 2: try to get text content from resultDiv directly if .analysis-text not found
        if (!analysisText || analysisText.trim().length < 50) {
          analysisText = resultDiv.textContent || resultDiv.innerText || "";
          // Remove all UI text that might interfere
          analysisText = analysisText
            .replace(/Not satisfied\? Add more context and regenerate.*?Clear.*?$/s, '')
            .replace(/🔄 Regenerate analysis.*?Clear.*?$/s, '')
            .replace(/Generate Code Changes.*?$/s, '')
            .replace(/📝 Add more context.*?$/s, '')
            .replace(/Copy.*?Download.*?$/s, '')
            .trim();
        }
        
        // Debug logging
        console.log("Debug - Analysis element found:", !!analysisElement);
        console.log("Debug - Analysis text length:", analysisText.length);
        console.log("Debug - Analysis text preview:", analysisText.substring(0, 200));
        console.log("Debug - Full analysis text:", analysisText);

        // Store refined analysis and user context in eventDetailsContext for code generation
        if (ctx) {
          ctx.refinedAnalysis = analysisText;
          ctx.lastUserContext = ctx.lastUserContext || "";
        }

        // No validation checks - always proceed with whatever content is available
        console.log("Debug - Proceeding with code generation using available content");
        console.log("Debug - Analysis text length:", analysisText.length);
        console.log("Debug - Analysis text preview:", analysisText.substring(0, 200));

        // Serialize the full error log for the code-changes LLM
        const fullErrorBlock = serializeErrorBlock(
          ctx.logs[0],
          ctx.appName || "Unknown Application",
        );
        const log0 = ctx.logs[0];
        let baseName =
          getErrorFileNameFromLog(log0) ||
          (ctx.githubRepoPathByBasename &&
            Object.keys(ctx.githubRepoPathByBasename)[0]) ||
          "unknown-file.xml";
        baseName = String(baseName).split(/[\\/]/).pop() || "unknown-file.xml";

        const repoPath =
          (ctx.githubRepoPathByBasename && ctx.githubRepoPathByBasename[baseName]) ||
          baseName;
        const referenceSource =
          (ctx.githubSourceFileContentByBasename &&
            ctx.githubSourceFileContentByBasename[baseName]) ||
          "";

        // Check if we have GitHub context available
        const hasGitHubContext = ctx.githubRepoOwner && ctx.githubRepoName;
        
        // For AI Analysis context, create file object with GitHub context if available
        const analysisFile = {
          name: baseName,
          content: fullErrorBlock, // Raw error log — main LLM input when analysis prompt is empty
          path: repoPath, // repo-relative path for /api/github/apply-changes
          referenceSourceContent: referenceSource, // original XML (etc.) for codegen + PR baseline
          owner: hasGitHubContext ? ctx.githubRepoOwner : null,
          repo: hasGitHubContext ? ctx.githubRepoName : null,
          isLocalAnalysis: !hasGitHubContext, // Flag to indicate if this is local analysis
        };

        // Use runGenerateCodeChanges to generate actual code changes
        runGenerateCodeChanges(analysisFile);
      });
    }
  }

  // Event Handlers

  function setupEventListeners() {
    try {
      // Time range filter

      if (elements.filterToggleBtn) {
        elements.filterToggleBtn.addEventListener("click", toggleFilterPanel);
      }

      if (elements.applyFilterBtn) {
        elements.applyFilterBtn.addEventListener("click", applyTimeFilter);
      }

      if (elements.clearFilterBtn) {
        elements.clearFilterBtn.addEventListener("click", clearTimeFilter);
      }

      // Environment selector

      if (elements.envSelect) {
        elements.envSelect.addEventListener("change", async (e) => {
          state.currentEnvId = e.target.value;

          state.selectedAppId = null;

          state.logs = [];

          stopAutoRefresh(); // Stop auto-refresh when changing environment

          renderLogs();

          // Reset time filter when switching environments

          resetTimeFilter();

          // Update local file controls visibility

          if (elements.localFileControls) {
            const isLocalMode = state.currentEnvId === "local";

            elements.localFileControls.style.display = isLocalMode
              ? "block"
              : "none";
          }

          await loadApplications(state.currentEnvId);
        });
      }

      // Refresh button

      if (elements.refreshBtn) {
        elements.refreshBtn.addEventListener("click", refresh);
      }

      // Logs refresh button

      if (elements.logsRefreshBtn) {
        elements.logsRefreshBtn.addEventListener("click", async () => {
          if (state.selectedAppId) {
            elements.logsRefreshBtn.disabled = true;

            await loadLogs(state.selectedAppId);

            elements.logsRefreshBtn.disabled = false;
          }
        });
      }

      // API search

      if (elements.apiSearch) {
        elements.apiSearch.addEventListener("input", () => {
          renderApplications();
        });
      }

      // Auth indicator clicks - open login modals when not authenticated

      const anypointIndicator = document.getElementById("anypointIndicator");

      const githubIndicator = document.getElementById("githubIndicator");

      if (anypointIndicator) {
        anypointIndicator.addEventListener("click", () => {
          if (!state.authenticated && window.showAnypointLoginModal)
            window.showAnypointLoginModal();
        });

        anypointIndicator.style.cursor = "pointer";
      }

      if (githubIndicator) {
        githubIndicator.addEventListener("click", () => {
          if (!state.githubAuthenticated && window.showGithubLoginModal)
            window.showGithubLoginModal();
        });

        githubIndicator.style.cursor = "pointer";
      }

      // Tab navigation

      if (elements.tabBtns) {
        elements.tabBtns.forEach((btn) => {
          btn.addEventListener("click", () => {
            const tabName = btn.dataset.tab;

            switchTab(tabName);
          });
        });
      }

      // GitHub repository search

      if (elements.repoSearch) {
        elements.repoSearch.addEventListener("input", () => {
          renderRepositories();
        });
      }

      // GitHub file viewer - single delegated handler (avoids accumulation on each renderFileContent)

      if (elements.githubContent) {
        elements.githubContent.addEventListener("click", (e) => {
          const target = e.target;

          if (target.closest("#backBtn")) {
            if (state.selectedRepo) {
              loadRepositoryContents(
                state.selectedRepo.owner,

                state.selectedRepo.repoName,

                state.currentPath,
              );
            }

            return;
          }

          if (target.closest("#analyzeBtn")) {
            const section = document.getElementById("analysisSection");

            const inputSection = document.getElementById(
              "analysisInputSection",
            );

            const prompt = document.getElementById("analysisPrompt");

            const result = document.getElementById("analysisResult");

            if (section) section.classList.remove("hidden");

            if (result) result.innerHTML = "";

            if (inputSection) inputSection.classList.remove("hidden");

            if (prompt) prompt.focus();

            return;
          }

          if (target.closest("#closeAnalysis")) {
            const section = document.getElementById("analysisSection");

            const inputSection = document.getElementById(
              "analysisInputSection",
            );

            if (section) section.classList.add("hidden");

            if (inputSection) inputSection.classList.add("hidden");

            return;
          }

          if (target.closest("#toggleAnalysisMaximize")) {
            const section = document.getElementById("analysisSection");

            const btn = document.getElementById("toggleAnalysisMaximize");

            if (section && btn) {
              const isMax = section.classList.toggle("maximized");

              btn.textContent = isMax ? "⤡" : "⤢";
            }

            return;
          }

          if (target.closest("#runAnalysis")) {
            if (state.selectedFile) runRulesetAnalysis(state.selectedFile);

            return;
          }

          if (target.closest("#btnGenerateCodeChanges")) {
            if (state.selectedFile) {
              runGenerateCodeChanges(state.selectedFile);
            } else {
              // Show a user-friendly message instead of just console warning

              const resultDiv = document.getElementById("analysisResult");

              if (resultDiv) {
                resultDiv.innerHTML =
                  '<div class="error">Please select a file first from GitHub repository to generate code changes.</div>';
              }
            }

            return;
          }
        });
      }

      // Event ID click handler (using event delegation)

      document.addEventListener("click", async (e) => {
        if (e.target.classList.contains("event-id-clickable")) {
          const eventId = e.target.dataset.eventId;
          
          // Check if this correlation ID is already marked as expected error
          const envId = state.currentEnvId || "default";
          const statuses = getCorrelationStatuses(envId);
          const currentStatus = statuses[eventId];
          
          if (currentStatus === "expected") {
            // Ask user if they want to unmark the expected error
            const shouldUnmark = confirm(
              "This correlation ID is already marked as an expected error. Do you want to unmark it?"
            );
            
            if (shouldUnmark) {
              // Remove the expected status
              delete statuses[eventId];
              localStorage.setItem(`correlationStatuses_${envId}`, JSON.stringify(statuses));
              if (typeof window.syncStatusToBackend === "function") {
                window.syncStatusToBackend(envId, eventId, "");
              }
              
              // Update UI
              updateErrorCardStyling(eventId, false);
              
              // Refresh the current view to update styling
              refreshCurrentView();
              
              // Open the panel after unmarking
              await showEventDetails(eventId);
            }
            // If user says no, do nothing (don't open panel)
          } else {
            // Not marked as expected, open the panel normally
            await showEventDetails(eventId);
          }
        }
      });

      // Logout button handler

      const logoutBtn = document.getElementById("logoutBtn");

      if (logoutBtn) {
        logoutBtn.addEventListener("click", async () => {
          try {
            const result = await api("POST", "/api/logout");

            if (result.success) {
              // Redirect to login page

              window.location.href = "/login";
            }
          } catch (err) {
            console.error("Logout failed:", err);

            // Still redirect even if logout API fails

            window.location.href = "/login";
          }
        });
      }

      // Keyboard shortcuts

      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          // no-op
        }
      });

      // Change log file button

      if (elements.changeLogFileBtn) {
        console.log("Setting up changeLogFileBtn event listener");

        elements.changeLogFileBtn.addEventListener("click", () => {
          console.log("Change log file button clicked");

          if (elements.changeLogFileInput) {
            elements.changeLogFileInput.click();
          } else {
            console.error("changeLogFileInput element not found");
          }
        });
      } else {
        console.warn("changeLogFileBtn element not found during setup");
      }

      // Change log file input

      if (elements.changeLogFileInput) {
        elements.changeLogFileInput.addEventListener("change", async (e) => {
          const file = e.target.files[0];

          if (!file) return;

          var fileCheck = AuthApi.validateLocalLogFile(file);
          if (!fileCheck.ok) {
            alert(fileCheck.message);

            e.target.value = "";

            return;
          }

          // Clear frontend cache before uploading new file

          console.log("Clearing frontend cache before file change...");

          state.localLogs = [];

          state.localAppName = null;

          state.filteredLogs = [];

          state.currentFilter = "";

          state.currentLevel = "all";

          state.currentPage = 1;

          // Clear any displayed data

          if (elements.logContent) {
            elements.logContent.innerHTML = "";
          }

          if (elements.logCount) {
            elements.logCount.textContent = "0 logs";
          }

          // Confirm file change using custom modal

          const confirmMessage =
            "Are you sure you want to change the log file?\n\n" +
            `Current: ${state.localAppName || "Local Log File"}\n` +
            `New: ${file.name}\n\n` +
            "This will replace the current log file and all its data.";

          const confirmChange = await showConfirmModal(confirmMessage);

          if (!confirmChange) {
            e.target.value = "";

            return;
          }

          try {
            showLoading();

            // Create form data for file upload

            const formData = new FormData();

            formData.append("file", file);

            // Upload new file

            const uploadRes = await AuthApi.postLocalUpload(formData);

            const result = uploadRes.data;

            if (result.success) {
              // Reset time filter to show all logs from new file

              resetTimeFilter();

              // Clear the file input

              e.target.value = "";

              // Refresh session to update UI

              await checkSession();

              // Auto-select the first available application to show logs immediately

              if (state.applications && state.applications.length > 0) {
                await selectApplication(state.applications[0].id);
              } else {
                // Clear current selection and logs if no applications

                state.selectedAppId = null;

                state.logs = [];

                renderLogs();
              }
            } else {
              alert(
                "Failed to change log file: " +
                  (result.error || "Unknown error"),
              );
            }
          } catch (err) {
            console.error("Error changing log file:", err);

            alert("Error changing log file: " + err.message);
          } finally {
            hideLoading();
          }
        });
      }
    } catch (err) {
      console.error("Error in setupEventListeners:", err);
    }
  }

  // loginGithubFromPopup function is now in github.js

  // Initialize

  async function init() {
    // Initialize DOM elements
    elements = {
      envSelect: document.getElementById("envSelect"),
      refreshBtn: document.getElementById("refreshBtn"),
      lastRefreshDisplay: document.getElementById("lastRefreshDisplay"),
      apiSearch: document.getElementById("apiSearch"),
      apiList: document.getElementById("apiList"),
      logsContent: document.getElementById("logsContent"),
      logsFilterContainer: document.getElementById("filterBar"),
      loadingOverlay: document.getElementById("loadingOverlay"),
      filterToggleBtn: document.getElementById("filterToggleBtn"),

      logsFilterPanel: document.getElementById("logsFilterPanel"),

      startDate: document.getElementById("startDate"),

      startTime: document.getElementById("startTime"),

      endDate: document.getElementById("endDate"),

      endTime: document.getElementById("endTime"),

      applyFilterBtn: document.getElementById("applyFilterBtn"),

      clearFilterBtn: document.getElementById("clearFilterBtn"),

      // Tab navigation

      tabBtns: document.querySelectorAll(".tab-btn"),

      mulesoftTab: document.getElementById("mulesoftTab"),

      githubTab: document.getElementById("githubTab"),

      correlationTab: document.getElementById("correlationTab"),

      correlationContent: document.getElementById("correlationContent"),
      filterBar: document.getElementById("filterBar"),

      // GitHub elements

      repoSearch: document.getElementById("repoSearch"),

      repoList: document.getElementById("repoList"),

      githubContent: document.getElementById("githubContent"),

      // Local file elements

      localFileControls: document.getElementById("localFileControls"),
      changeLogFileBtn: document.getElementById("changeLogFileBtn"),
      changeLogFileInput: document.getElementById("changeLogFileInput"),
    };

    console.log("localFileControls:", !!elements.localFileControls);
    console.log("changeLogFileBtn:", !!elements.changeLogFileBtn);
    console.log("changeLogFileInput:", !!elements.changeLogFileInput);

    setupEventListeners();

    setDefaultDateRange();

    moveFilterBarToActiveTab(state.currentTab || "mulesoft");
    updateFilterVisibility();

    const urlParams = new URLSearchParams(window.location.search);

    const githubLoginSuccess = urlParams.get("github_login");

    const localUploadSuccess = urlParams.get("local_upload");

    if (githubLoginSuccess === "success") {
      // User just completed GitHub login, load GitHub content

      console.log(
        "User arrived from successful GitHub login, loading GitHub content",
      );

      await checkSession();

      if (state.githubAuthenticated) {
        // Switch to GitHub tab and load repositories

        await switchTab("github");

        if (state.githubRepos.length === 0) {
          loadGitHubRepos();
        }
      }
    }

    if (localUploadSuccess === "success") {
      // User just uploaded a local file, load local content and auto-select first app

      console.log(
        "User arrived from successful local file upload, loading local content",
      );

      // Reset time filter to show all logs from new file

      resetTimeFilter();

      // Check session and then auto-select first application

      checkSession().then(() => {
        if (state.applications && state.applications.length > 0) {
          // Auto-select the first application to show logs immediately

          selectApplication(state.applications[0].id);
        }
      });

      return;
    }

    checkSession();
  }

  // Run on DOM ready

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => init());
  } else {
    init();
  }

  // Expose button reset for manual testing
  window.verifyButtonStates = resetAllButtonStates;
  window.resetButtonStates = resetAllButtonStates;

  // Start multi-file analysis from event details
  async function startMultiFileAnalysisFromEventDetails(ctx, sourceType, primaryFileName) {
    try {
      showLoading();
      
      // Step 1: Create a list of file names from event details
      const uniqueFiles = new Set();
      const filesByApp = {};
      
      console.log("🔍 Step 1: Collecting file names from event details...");
      
      ctx.logs.forEach(log => {
        const appName = log.application_name || log.application || 'Unknown Application';
        
        // Enhanced file name extraction (same logic as in event details)
        let fileName = log.component || "N/A";
        const elementField = log.exception?.Element;
        const elementDslField = log.exception?.["Element DSL"];
        const fieldToUse = elementField || elementDslField;
        
        // Extract file name from multiple sources
        let extractedFileName = null;
        
        if (fieldToUse) {
          extractedFileName = extractFilenameFromElement(fieldToUse);
        }
        
        if (!extractedFileName && log.exception) {
          const fileFields = ['file', 'fileName', 'filename', 'File', 'FileName'];
          for (const field of fileFields) {
            if (log.exception[field]) {
              extractedFileName = log.exception[field];
              break;
            }
          }
        }
        
        if (!extractedFileName) {
          const directFileFields = ['fileName', 'filename', 'file', 'File'];
          for (const field of directFileFields) {
            if (log[field]) {
              extractedFileName = log[field];
              break;
            }
          }
        }
        
        if (!extractedFileName && log.message) {
          const filePattern = /(\w+\.(xml|dwl|dw|java|js|py))/gi;
          const matches = log.message.match(filePattern);
          if (matches && matches.length > 0) {
            extractedFileName = matches[0];
          }
        }
        
        if (extractedFileName) {
          fileName = extractedFileName;
        }
        
        if (fileName && fileName !== 'N/A') {
          uniqueFiles.add(fileName);
          
          if (!filesByApp[appName]) {
            filesByApp[appName] = {
              appName: appName,
              files: new Set()
            };
          }
          filesByApp[appName].files.add(fileName);
          
          console.log(`📁 Found file: ${fileName} from application: ${appName}`);
        }
      });
      
      const fileList = Array.from(uniqueFiles);
      console.log(`📋 Total unique files found: ${fileList.length}`, fileList);
      
      if (fileList.length === 0) {
        setEventDetailsFlowState("attach");
        hideLoading();
        alert("No files found in event details to analyze.");
        return;
      }
      
      if (sourceType === "github") {
        // Check GitHub authentication first
        if (!state.githubAuthenticated) {
          setEventDetailsFlowState("attach");
          hideLoading();
          alert("Please authenticate with GitHub first. Click on the GitHub tab and login.");
          return;
        }
        
        // Step 2: Fetch file contents from GitHub API
        console.log(" Step 2: Fetching file contents from GitHub...");
        
        const fileContents = {}; // Key-value pair: {fileName: content}
        
        // Get GitHub username from state
        const githubUsername = state.githubUsername || "MJPWC";
        console.log(` Using GitHub username: ${githubUsername}`);
        
        // Track repository information for context
        let repoOwner = githubUsername;
        let repoName = null;
        
        for (const fileName of fileList) {
          try {
            console.log(` Fetching file: ${fileName}`);
            
            // Call GitHub API to get file content
            const response = await api("POST", "/api/github/fetch-file-content", {
              username: githubUsername,
              file_name: fileName
            });
            
            console.log(` API Response for ${fileName}:`, response);
            
            if (response.success && response.content) {
              fileContents[fileName] = response.content;

              // Repo-relative path + source for later "Generate code" / PR (basename keys)
              if (!ctx.githubRepoPathByBasename) ctx.githubRepoPathByBasename = {};
              if (!ctx.githubSourceFileContentByBasename)
                ctx.githubSourceFileContentByBasename = {};
              if (response.file_path) {
                ctx.githubRepoPathByBasename[fileName] = response.file_path;
              }
              ctx.githubSourceFileContentByBasename[fileName] = response.content;
              
              // Extract repository information from the response
              if (response.found_in_repo && !repoName) {
                // Parse repository info from "owner/repo" format
                const repoParts = response.found_in_repo.split('/');
                if (repoParts.length === 2) {
                  repoOwner = repoParts[0];
                  repoName = repoParts[1];
                  console.log(` GitHub context detected - Owner: ${repoOwner}, Repo: ${repoName}`);
                }
              }
              
              console.log(` Successfully fetched content for: ${fileName} from ${response.found_in_repo || 'unknown repository'}`);
            } else {
              console.warn(` Could not fetch content for: ${fileName} - ${response.error || 'Unknown error'}`);
              if (response.details) {
                console.log(` Search details:`, response.details);
              }
              fileContents[fileName] = `// Could not fetch file content: ${response.error || 'File not found'}`;
            }
          } catch (error) {
            console.error(` Error fetching file ${fileName}:`, error);
            fileContents[fileName] = `// Error fetching file: ${error.message}`;
          }
        }
        
        // Check if any files were successfully fetched
        const successfulFetches = Object.entries(fileContents).filter(([fileName, content]) => 
          !content.startsWith('// Could not fetch file content') && !content.startsWith('// Error fetching file')
        );
        
        if (successfulFetches.length === 0) {
          setEventDetailsFlowState("attach");
          hideLoading();
          alert("No files available on GitHub. The referenced files could not be found in your repositories. Please try to upload file locally.");
          return;
        }
        
        console.log(` Successfully fetched ${successfulFetches.length} out of ${fileList.length} files`);
        
        // Set GitHub context in the event details context for code generation
        if (repoName) {
          ctx.githubRepoOwner = repoOwner;
          ctx.githubRepoName = repoName;
          console.log(` GitHub context set in ctx: ${repoOwner}/${repoName}`);
        }
        
        // Step 3: Prepare error content from logs
        console.log(" Step 4: Sending to unified analysis function...");
        
        // Directly call unified analysis function to avoid duplicate API calls
        if (typeof window.analyzeErrorWithRulesetUnified === "function") {
          await window.analyzeErrorWithRulesetUnified(0, fileList, fileContents);
        } else {
          throw new Error("Unified analysis function is not available");
        }
      } else {
        setEventDetailsFlowState("attach");
        hideLoading();
        alert("Local file multi-file analysis not implemented in this flow.");
      }
    } catch (error) {
      setEventDetailsFlowState("attach");
      hideLoading();
      console.error(" Error in multi-file analysis:", error);
      alert(`Multi-file analysis failed: ${error.message}`);
    } finally {
      // Ensure spinner always stops (success or failure).
      hideLoading();
    }
  }

// Unified AI Error Analysis - handles both single and multi-file scenarios
window.analyzeErrorWithRulesetUnified = async function(logIndex = 0, fileList = null, fileContents = null) {
  const ctx = window.__eventDetailsContext;
  
  // Determine if this is single or multi-file
  const isMultiFile = fileList && fileList.length > 1;
  
  // Prepare content (single file or multi-file)
  let content, filePath;
  if (isMultiFile && fileContents) {
    // Multi-file: combine all file contents
    const allFileContents = Object.entries(fileContents).map(([name, content]) => 
      `=== File: ${name} ===\n${content}`
    ).join('\n\n');
    
    // Check if this is from multi-file upload (ctx.errorDescription) or event details (ctx.logs)
    let errorContent;
    if (ctx.logs && ctx.logs.length > 0) {
      // Event details context (GitHub multi-file)
      if (ctx.logs.length > 1) {
        // Multiple logs: extract exception content from each log
        errorContent = ctx.logs.map((log, index) => {
          const appName = log.application_name || log.application || 'Unknown Application';
          let exceptionContent = '';
          
          if (log.exception) {
            // Convert exception object to readable string
            if (typeof log.exception === 'object') {
              exceptionContent = Object.entries(log.exception)
                .map(([key, value]) => `${key}: ${value}`)
                .join('\n');
            } else {
              exceptionContent = log.exception;
            }
          } else {
            exceptionContent = log.message || log.error_description || 'No exception details available';
          }
          
          return `=== Log ${index + 1} from ${appName} ===\n${exceptionContent}`;
        }).join('\n\n');
      } else {
        // Single log: use existing format
        errorContent = ctx.logs.map(log => 
          `${log.application_name || log.application}: ${log.message || log.error_description || 'No description'}`
        ).join('\n');
      }
    } else if (ctx.errorDescription) {
      // Multi-file upload context
      errorContent = ctx.errorDescription;
    } else {
      errorContent = "No error description available";
    }
    
    content = `${errorContent}\n\n=== Multi-File Context ===\n${allFileContents}`;
    filePath = fileList.join(', ');
  } else {
    // Single file: use existing logic
    const log = ctx.logs[logIndex];
    content = serializeErrorBlock(log, ctx.appName || "Unknown Application");
    filePath = log.component || "unknown-file.xml";
  }
  //console.log(`content send to llm :`, content);
  // Use a ruleset-aligned prompt so the UI can render consistent sections.
  const prompt =
    "Analyze this MuleSoft error using the error-analysis ruleset. Output ALL required sections with bold section headers (e.g., **Summary**, **Quick Fix**, etc.). Do not omit any section even if values are N/A.";
  
  let response;
  try {
    // Single API call to /api/error/analyze
    response = await api("POST", "/api/error/analyze", {
      content: content,
      prompt: prompt,
      file_path: filePath,
      ruleset: "error-analysis-rules.txt",
    });
  } catch (err) {
    // Stop spinner if the request fails before rendering.
    hideLoading();
    throw err;
  }
  
  // Use same renderAnalysisWithRefine for both
  const resultDiv = document.getElementById("errorAnalysisResult");
  if (!resultDiv) {
    window.AppModalUtils.ensureAiAnalysisModal();
  }
  
  const finalResultDiv = document.getElementById("errorAnalysisResult");
  renderAnalysisWithRefine(
    finalResultDiv,
    `<div class="analysis-text">${formatAnalysis(response.analysis)}</div>`,
    async function regenerateCallback(additionalInput) {
      // For both single and multi-file, re-run analysis with additional context
      const combinedContent = `${content}\n\n=== Additional Context ===\n${additionalInput}`;
      const regenerateResponse = await api("POST", "/api/error/analyze", {
        content: combinedContent,
        prompt: prompt,
        file_path: filePath,
        ruleset: "error-analysis-rules.txt",
      });
      
      if (regenerateResponse.success) {
        const modal = document.getElementById("aiAnalysisModal");
        const resultDiv = modal?.querySelector("#errorAnalysisResult");
        if (resultDiv) {
          const formattedAnalysis = formatAnalysis(regenerateResponse.analysis);
          renderAnalysisWithRefine(
            resultDiv,
            `<div class="analysis-text">${formattedAnalysis}</div>`,
            regenerateCallback
          );
        }
      } else {
        alert(`Regeneration failed: ${regenerateResponse.error}`);
      }
    }
  );

  // Stop spinner once the initial render is complete.
  hideLoading();
};

// Expose state, api, elements and functions to global scope for other scripts
window.state = state;
window.api = api;
window.elements = elements;
window.showLoading = showLoading;
window.hideLoading = hideLoading;
window.checkSession = checkSession;
window.stopAutoRefresh = stopAutoRefresh;
window.startAutoRefresh = startAutoRefresh;
window.renderLogs = renderLogs;
window.showEventDetails = showEventDetails;
window.loadLogs = loadLogs;
window.resetTimeFilter = resetTimeFilter;
window.loadApplications = loadApplications;
window.loadLocalApplications = loadLocalApplications;
window.fetchErrorCounts = fetchErrorCounts;
window.selectApplication = selectApplication;
window.displayMultiFileAnalysisResults = displayMultiFileAnalysisResults;
window.escapeHtml = escapeHtml;
window.formatTimestamp = formatTimestamp;
window.getFileIcon = getFileIcon;
window.formatFileSize = formatFileSize;
window.serializeErrorBlock = serializeErrorBlock;
window.renderErrorBanner = renderErrorBanner;
window.getErrorFileNameFromLog = getErrorFileNameFromLog;
window.extractApiAndFileFromFlowStack = extractApiAndFileFromFlowStack;
window.extractFilenameFromElement = extractFilenameFromElement;
window.extractApiNameFromElement = extractApiNameFromElement;
window.updateFilterVisibility = updateFilterVisibility;
window.isLogInTimeRange = isLogInTimeRange;
window.hasValidEventId = hasValidEventId;
window.hasErrorDetails = hasErrorDetails;
window.calculateFilteredErrorCount = calculateFilteredErrorCount;

})();