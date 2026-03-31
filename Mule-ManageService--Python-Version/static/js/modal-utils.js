(function (global) {
  "use strict";

  function removeModalById(id) {
    const modal = document.getElementById(id);
    if (modal) {
      modal.remove();
    }
  }

  function closeEventDetailsModal() {
    removeModalById("eventDetailsModal");
    removeModalById("aiAnalysisModal");
    removeModalById("customPromptModal");
    if (global.__eventDetailsContext) {
      delete global.__eventDetailsContext;
    }
  }

  function closeAiAnalysisModal() {
    removeModalById("aiAnalysisModal");
  }

  function ensureAiAnalysisModal() {
    let modal = document.getElementById("aiAnalysisModal");
    if (modal) {
      return modal;
    }

    const analysisModalHtml = `
      <div class="event-details-modal" id="aiAnalysisModal">
        <div class="event-details-backdrop"></div>
        <div class="event-details-content">
          <div class="event-details-header">
            <h3>AI Error Analysis</h3>
            <button class="btn-icon" id="closeAiAnalysis">✕</button>
          </div>
          <div class="event-details-body">
            <div class="analysis-result" id="errorAnalysisResult">
              <div class="loading">Analyzing error with ruleset...</div>
            </div>
            <div class="analysis-actions" id="aiAnalysisActions"></div>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML("beforeend", analysisModalHtml);
    modal = document.getElementById("aiAnalysisModal");

    document
      .getElementById("closeAiAnalysis")
      .addEventListener("click", closeAiAnalysisModal);
    document
      .querySelector("#aiAnalysisModal .event-details-backdrop")
      .addEventListener("click", closeAiAnalysisModal);

    return modal;
  }

  global.AppModalUtils = {
    removeModalById: removeModalById,
    closeEventDetailsModal: closeEventDetailsModal,
    closeAiAnalysisModal: closeAiAnalysisModal,
    ensureAiAnalysisModal: ensureAiAnalysisModal,
  };

  global.closeEventDetailsModal = closeEventDetailsModal;
  global.closeAiAnalysisModal = closeAiAnalysisModal;
})(typeof window !== "undefined" ? window : this);
