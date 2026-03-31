(function (global) {
  "use strict";

  function renderErrorBanner(elements, message) {
    const root = elements.logsContent || elements.correlationContent;
    if (!root) {
      return;
    }
    root.innerHTML = `<div class="error-banner">${global.escapeHtml ? global.escapeHtml(message) : message}</div>`;
  }

  function startAutoRefresh(state, refresh) {
    if (state.autoRefreshInterval) {
      clearInterval(state.autoRefreshInterval);
    }
    state.autoRefreshInterval = setInterval(async () => {
      if (state.authenticated && state.currentEnvId) {
        await refresh();
      }
    }, 300000);
  }

  function stopAutoRefresh(state) {
    if (state.autoRefreshInterval) {
      clearInterval(state.autoRefreshInterval);
      state.autoRefreshInterval = null;
    }
  }

  function updateLastRefreshDisplay(state, elements) {
    const now = new Date();
    let displayText = "Now";

    if (state.lastRefreshTime) {
      const diffSeconds = Math.floor((now - state.lastRefreshTime) / 1000);
      if (diffSeconds < 5) {
        displayText = "Now";
      } else if (diffSeconds < 60) {
        displayText = `${diffSeconds}s ago`;
      } else {
        const diffMinutes = Math.floor(diffSeconds / 60);
        displayText = `${diffMinutes}m ago`;
      }
    }

    const target = elements.lastRefreshTime;
    if (target) {
      target.textContent = displayText;
    }
  }

  global.AppRefreshUtils = {
    renderErrorBanner: renderErrorBanner,
    startAutoRefresh: startAutoRefresh,
    stopAutoRefresh: stopAutoRefresh,
    updateLastRefreshDisplay: updateLastRefreshDisplay,
  };
})(typeof window !== "undefined" ? window : this);
