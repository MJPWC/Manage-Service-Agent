(function (global) {
  "use strict";

  function acquire(state, overlay) {
    state.loadingRequests = (state.loadingRequests || 0) + 1;
    if (overlay) {
      overlay.classList.remove("hidden");
    }
  }

  function release(state, overlay) {
    state.loadingRequests = Math.max(0, (state.loadingRequests || 0) - 1);
    if (overlay && state.loadingRequests === 0) {
      overlay.classList.add("hidden");
    }
  }

  global.AppLoadingUtils = {
    acquire: acquire,
    release: release,
  };
})(typeof window !== "undefined" ? window : this);
