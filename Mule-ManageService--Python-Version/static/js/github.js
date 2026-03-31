/**
 * Login page: optional GitHub connect (after Anypoint / Connected App / local file).
 */
(function () {
  "use strict";

  var PANEL_HTML =
    '<div class="auth-success-badge">' +
    '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/></svg>' +
    '<span id="auth-label">Connected to Anypoint Platform</span>' +
    "</div>" +
    '<div class="gh-card">' +
    '<div class="gh-card-header">' +
    '<div class="gh-icon">' +
    '<svg width="20" height="20" viewBox="0 0 16 16" fill="#e6edf3"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>' +
    "</div>" +
    "<div>" +
    '<div class="gh-card-title">Connect GitHub <span class="gh-optional">optional</span></div>' +
    '<div class="gh-card-sub">Enable code analysis, AI fix generation and branch push</div>' +
    "</div>" +
    "</div>" +
    '<div class="gh-features">' +
    '<div class="gh-feat"><div class="gh-feat-dot" style="background:#2563EB"></div>Auto-find source file by filename from error logs</div>' +
    '<div class="gh-feat"><div class="gh-feat-dot" style="background:#16a34a"></div>Send code + error to LLM, get a targeted fix back</div>' +
    '<div class="gh-feat"><div class="gh-feat-dot" style="background:#7c3aed"></div>Review fix and push directly to a new branch</div>' +
    "</div>" +
    '<div class="gh-actions">' +
    '<div class="gh-field">' +
    '<label class="fl gh-label" for="githubUsername">GitHub Username</label>' +
    '<input class="fi gh-input" id="githubUsername" placeholder="your-username" autocomplete="username">' +
    "</div>" +
    '<div class="gh-field">' +
    '<label class="fl gh-label" for="githubToken">Personal Access Token</label>' +
    '<input class="fi gh-input" type="password" id="githubToken" placeholder="ghp_..." autocomplete="current-password">' +
    "</div>" +
    '<button type="button" class="btn gh full" id="githubConnectBtn">' +
    '<svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>' +
    "Connect GitHub" +
    "</button>" +
    '<button type="button" class="btn full btn-gh-skip" id="githubSkipBtn">Skip for now — go to workspace</button>' +
    '<div class="gh-hint">Without GitHub: error summary and SN tickets still work.<br>Code analysis and branch push require GitHub.</div>' +
    "</div>" +
    "</div>";

  function injectGithubLoginPanel() {
    var el = document.getElementById("gh-panel");
    if (!el || el.getAttribute("data-github-injected") === "1") {
      return;
    }
    el.innerHTML = PANEL_HTML;
    el.setAttribute("data-github-injected", "1");
    document.getElementById("githubConnectBtn").addEventListener("click", connectGitHub);
    document.getElementById("githubSkipBtn").addEventListener("click", skipGitHub);
  }

  /** Called after Anypoint / Connected App / local file success */
  function authSuccess(source) {
    injectGithubLoginPanel();
    var tabsSection = document.querySelector(".tabs");
    var panes = document.querySelectorAll('[id^="p"]');

    if (tabsSection) tabsSection.style.display = "none";
    panes.forEach(function (pane) {
      pane.style.display = "none";
    });

    var panel = document.getElementById("gh-panel");
    var label = document.getElementById("auth-label");
    if (label) label.textContent = "Connected to " + source;
    if (panel) {
      panel.style.display = "block";
      panel.setAttribute("aria-hidden", "false");
    }
  }

  function connectGitHub() {
    var tokenEl = document.getElementById("githubToken");
    var userEl = document.getElementById("githubUsername");
    var token = tokenEl && tokenEl.value.trim();
    var username = userEl && userEl.value.trim();

    if (!token || !username) {
      alert("Please enter both GitHub token and username.");
      return;
    }

    var connectBtn = document.getElementById("githubConnectBtn");
    var labelHtml = connectBtn ? connectBtn.innerHTML : "";
    if (connectBtn) {
      connectBtn.disabled = true;
      connectBtn.textContent = "Connecting...";
    }

    AuthApi.postGithubLogin(username, token)
      .then(function (res) {
        if (res.data.success) {
          window.location.href = "/?github_login=success";
        } else {
          alert("GitHub login failed: " + (res.data.error || "Unknown error"));
          if (connectBtn) {
            connectBtn.disabled = false;
            connectBtn.innerHTML = labelHtml;
          }
        }
      })
      .catch(function (err) {
        console.error("GitHub login error:", err);
        alert("GitHub login failed: " + err.message);
        if (connectBtn) {
          connectBtn.disabled = false;
          connectBtn.innerHTML = labelHtml;
        }
      });
  }

  function skipGitHub() {
    window.location.href = "/";
  }

  injectGithubLoginPanel();

  window.authSuccess = authSuccess;
  window.connectGitHub = connectGitHub;
  window.skipGitHub = skipGitHub;

  // GitHub Login Popup Functions
  window.showGithubLoginModal = function () {
    const modal = document.getElementById("githubLoginModal");
    if (modal) {
      modal.classList.remove("hidden");
      // Focus on username field
      const usernameField = document.getElementById("popupGithubUsername");
      if (usernameField) {
        usernameField.focus();
      }
    }
  };

  window.closeGithubLoginModal = function () {
    const modal = document.getElementById("githubLoginModal");
    if (modal) {
      modal.classList.add("hidden");
      // Clear form fields
      document.getElementById("popupGithubUsername").value = "";
      document.getElementById("popupGithubToken").value = "";
    }
  };

  window.loginGithubFromPopup = async function () {
    const username = document
      .getElementById("popupGithubUsername")
      .value.trim();
    const token = document.getElementById("popupGithubToken").value.trim();

    if (!username || !token) {
      alert("Please enter both username and token");
      return;
    }

    try {
      const res = await AuthApi.postGithubLogin(username, token);
      const result = res.data;

      if (result.success) {
        // Close modal
        window.closeGithubLoginModal();

        // Update authentication indicators
        if (window.updateAuthIndicators) {
          window.updateAuthIndicators(window.state?.authenticated || false, true);
        }

        // Refresh session from backend
        if (window.checkSession) {
          await window.checkSession();
        }

        // Load GitHub repositories if available
        if (window.loadGitHubRepos && window.state?.githubRepos?.length === 0) {
          await window.loadGitHubRepos();
        }

        // Switch to GitHub tab if available
        if (window.switchTab) {
          await window.switchTab("github");
        }

        // Show success message
        alert("GitHub login successful!");
      } else {
        alert("GitHub login failed: " + (result.error || "Unknown error"));
      }
    } catch (err) {
      alert("GitHub login failed: " + err.message);
    }
  };
})();
