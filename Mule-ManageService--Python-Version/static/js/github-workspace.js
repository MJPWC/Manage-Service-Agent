(function (global) {
  "use strict";

  function getState() {
    return global.state || {};
  }

  function getElements() {
    const shared = global.elements || {};

    return {
      ...shared,
      repoSearch: shared.repoSearch || document.getElementById("repoSearch"),
      repoList: shared.repoList || document.getElementById("repoList"),
      githubContent:
        shared.githubContent || document.getElementById("githubContent"),
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

  function getFileIcon(name) {
    if (typeof global.getFileIcon === "function") {
      return global.getFileIcon(name);
    }

    return "📄";
  }

  function formatFileSize(size) {
    if (typeof global.formatFileSize === "function") {
      return global.formatFileSize(size);
    }

    if (!size && size !== 0) return "Unknown";
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  function serializeErrorBlock(log, appName) {
    if (typeof global.serializeErrorBlock === "function") {
      return global.serializeErrorBlock(log, appName);
    }

    return `${appName || "Unknown Application"}\n${JSON.stringify(log || {}, null, 2)}`;
  }

  async function loadGitHubRepos() {
    const state = getState();

    console.log("loadGitHubRepos called - current state:", {
      loading: state.loadingGitHubRepos,
      authenticated: state.githubAuthenticated,
      reposCount: state.githubRepos.length,
    });

    if (state.loadingGitHubRepos) {
      console.log("GitHub repos already loading, skipping duplicate call");
      return;
    }

    if (!state.githubAuthenticated) {
      console.log("User not authenticated with GitHub, skipping repo load");
      return;
    }

    if (state.githubRepos.length > 0) {
      console.log("GitHub repos already loaded, skipping API call");
      renderRepositories();
      return;
    }

    try {
      state.loadingGitHubRepos = true;
      console.log("Starting GitHub repos API call");

      if (typeof global.showLoading === "function") {
        global.showLoading();
      }

      const result = await global.api("GET", "/api/github/repos");

      if (result.success) {
        state.githubRepos = result.repos;
        console.log("Successfully loaded", result.repos.length, "GitHub repos");
        renderRepositories();
      } else {
        console.error("Failed to load GitHub repos:", result.error);
      }
    } catch (error) {
      console.error("Error loading GitHub repos:", error);
    } finally {
      state.loadingGitHubRepos = false;

      if (typeof global.hideLoading === "function") {
        global.hideLoading();
      }
    }
  }

  function renderRepositories() {
    const state = getState();
    const elements = getElements();
    const searchTerm = (elements.repoSearch?.value || "").toLowerCase();

    const filteredRepos = state.githubRepos.filter(
      (repo) =>
        repo.name.toLowerCase().includes(searchTerm) ||
        (repo.description &&
          repo.description.toLowerCase().includes(searchTerm)) ||
        (repo.language && repo.language.toLowerCase().includes(searchTerm)),
    );

    if (!elements.repoList) return;

    if (filteredRepos.length === 0) {
      elements.repoList.innerHTML = `
        <div class="empty-state">
          <p>${searchTerm ? "No repositories found matching your search" : "No repositories available"}</p>
        </div>
      `;
      return;
    }

    elements.repoList.innerHTML = filteredRepos
      .map(
        (repo) => `
      <div class="api-item" data-repo="${repo.full_name}">
        <div class="api-item-header">
          <h3 class="api-item-name">${repo.name}</h3>
          <span class="api-item-status ${repo.private ? "private" : "public"}">
            ${repo.private ? "Private" : "Public"}
          </span>
        </div>
        <div class="api-item-details">
          <p class="api-item-description">${repo.description || "No description"}</p>
          <div class="api-item-meta">
            <span class="repo-language">${repo.language || "Unknown"}</span>
            <span class="repo-stars">⭐ ${repo.stargazers_count}</span>
            <span class="repo-forks">🔀 ${repo.forks_count}</span>
          </div>
        </div>
      </div>
    `,
      )
      .join("");

    elements.repoList.querySelectorAll(".api-item").forEach((item) => {
      item.addEventListener("click", () => {
        const repoFullName = item.dataset.repo;
        selectRepository(repoFullName);
      });
    });
  }

  async function selectRepository(repoFullName) {
    const [owner, repoName] = repoFullName.split("/");
    const state = getState();

    state.selectedRepo = { owner, repoName, fullName: repoFullName };

    await loadRepositoryContents(owner, repoName);
  }

  async function loadRepositoryContents(owner, repoName, path = "") {
    const state = getState();

    if (typeof global.checkSession === "function") {
      await global.checkSession();
    }

    if (!state.githubAuthenticated) {
      if (typeof global.showGithubLoginModal === "function") {
        global.showGithubLoginModal();
      } else {
        const modal = document.getElementById("githubLoginModal");
        if (modal) {
          modal.classList.remove("hidden");
          setTimeout(() => {
            const input = document.getElementById("popupGithubUsername");
            if (input) input.focus();
          }, 100);
        }
      }
      return;
    }

    try {
      if (typeof global.showLoading === "function") {
        global.showLoading();
      }

      const endpoint = path
        ? `/api/github/repo/${owner}/${repoName}/${path}`
        : `/api/github/repo/${owner}/${repoName}`;

      const result = await global.api("GET", endpoint);

      if (result.success) {
        state.githubFiles = result.contents;
        state.currentPath = path;
        renderGitHubFiles();
      } else {
        console.error("Failed to load repository contents:", result.error);
      }
    } catch (error) {
      console.error("Error loading repository contents:", error);
    } finally {
      if (typeof global.hideLoading === "function") {
        global.hideLoading();
      }
    }
  }

  function renderGitHubFiles() {
    const state = getState();
    const elements = getElements();

    if (!elements.githubContent) return;

    if (state.githubFiles.length === 0) {
      elements.githubContent.innerHTML = `
        <div class="empty-state">
          <p>This directory is empty</p>
        </div>
      `;
      return;
    }

    const breadcrumb = state.currentPath
      ? `
      <div class="breadcrumb">
        <a href="#" class="breadcrumb-item" data-path="">${state.selectedRepo.fullName}</a>
        ${state.currentPath
          .split("/")
          .map((part, index, arr) => {
            const path = arr.slice(0, index + 1).join("/");
            return `<span class="breadcrumb-separator">/</span><a href="#" class="breadcrumb-item" data-path="${path}">${part}</a>`;
          })
          .join("")}
      </div>
    `
      : `<div class="breadcrumb"><a href="#" class="breadcrumb-item" data-path="">${state.selectedRepo.fullName}</a></div>`;

    const filesHtml = state.githubFiles
      .map((file) => {
        if (file.type === "dir") {
          return `
          <div class="file-item directory" data-path="${file.path}">
            <div class="file-icon">📁</div>
            <div class="file-info">
              <div class="file-name">${file.name}</div>
              <div class="file-meta">Directory</div>
            </div>
          </div>
        `;
        }

        return `
          <div class="file-item file" data-path="${file.path}" data-type="${file.type}">
            <div class="file-icon">${getFileIcon(file.name)}</div>
            <div class="file-info">
              <div class="file-name">${file.name}</div>
              <div class="file-meta">${formatFileSize(file.size)}</div>
            </div>
          </div>
        `;
      })
      .join("");

    elements.githubContent.innerHTML = `
      ${breadcrumb}
      <div class="file-list">
        ${filesHtml}
      </div>
    `;

    elements.githubContent.querySelectorAll(".directory").forEach((item) => {
      item.addEventListener("click", () => {
        loadRepositoryContents(
          state.selectedRepo.owner,
          state.selectedRepo.repoName,
          item.dataset.path,
        );
      });
    });

    elements.githubContent.querySelectorAll(".file").forEach((item) => {
      item.addEventListener("click", () => {
        loadFileContent(
          state.selectedRepo.owner,
          state.selectedRepo.repoName,
          item.dataset.path,
        );
      });
    });

    elements.githubContent.querySelectorAll(".breadcrumb-item").forEach((item) => {
      item.addEventListener("click", (event) => {
        event.preventDefault();
        loadRepositoryContents(
          state.selectedRepo.owner,
          state.selectedRepo.repoName,
          item.dataset.path,
        );
      });
    });
  }

  async function loadFileContent(owner, repoName, filePath) {
    const state = getState();

    try {
      if (typeof global.showLoading === "function") {
        global.showLoading();
      }

      const result = await global.api(
        "GET",
        `/api/github/file/${owner}/${repoName}/${filePath}`,
      );

      if (result.success) {
        state.selectedFile = {
          path: filePath,
          content: result.content,
          name: filePath.split("/").pop(),
          owner,
          repoName,
        };

        renderFileContent();
      } else {
        console.error("Failed to load file content:", result.error);
      }
    } catch (error) {
      console.error("Error loading file content:", error);
    } finally {
      if (typeof global.hideLoading === "function") {
        global.hideLoading();
      }
    }
  }

  function renderFileContent() {
    const state = getState();
    const elements = getElements();
    const file = state.selectedFile;

    if (!file || !elements.githubContent) return;

    elements.githubContent.innerHTML = `
      <div class="file-viewer">
        <div class="file-header">
          <button class="btn-secondary" id="backBtn">← Back to ${state.selectedRepo.fullName}</button>
          <div class="file-info">
            <h3>${file.name}</h3>
            <span class="file-path">${file.path}</span>
          </div>
          <button class="btn-primary" id="analyzeBtn">Analyze with AI</button>
        </div>
        <div class="file-content-wrapper">
          <div class="file-content">
            <pre><code>${escapeHtml(file.content)}</code></pre>
          </div>
          <div class="analysis-section hidden" id="analysisSection">
            <div class="analysis-header">
              <h4>AI Analysis</h4>
              <div class="analysis-header-actions">
                <button class="btn-icon" id="toggleAnalysisMaximize" title="Maximize">⛶</button>
                <button class="btn-icon" id="closeAnalysis">✕</button>
              </div>
            </div>
            <div class="analysis-input-section" id="analysisInputSection">
              <div class="analysis-form">
                <h5 style="margin: 0 0 10px 0; color: var(--text-primary); font-size: 13px; font-weight: 600;">User Input</h5>
                <div class="text-input-container" id="textInputContainer">
                  <textarea id="analysisPrompt" placeholder="Provide your input or paste error logs here regarding the analysis..."></textarea>
                  <button class="btn-primary" id="runAnalysis">Submit</button>
                </div>
              </div>
            </div>
            <div class="analysis-result" id="analysisResult"></div>
          </div>
        </div>
      </div>
    `;

    if (state.pendingGitHubErrorContext) {
      const ctx = state.pendingGitHubErrorContext;
      const blocks = (ctx.logs || []).map((log) =>
        serializeErrorBlock(log, ctx.appName || "Unknown Application"),
      );
      const serialized = blocks.join("\n\n---\n\n");
      const errorDescription = ctx.errorDescription || "";
      const fullPrompt = errorDescription
        ? `${errorDescription}\n\n---\n\n${serialized}`
        : serialized;

      const analysisSection = document.getElementById("analysisSection");
      const analysisInputSection = document.getElementById("analysisInputSection");
      const analysisPrompt = document.getElementById("analysisPrompt");

      if (analysisSection && analysisInputSection && analysisPrompt) {
        analysisSection.classList.remove("hidden");
        analysisInputSection.classList.remove("hidden");
        analysisPrompt.value = fullPrompt;
        analysisPrompt.focus();
      }

      state.pendingGitHubErrorContext = null;
    }
  }

  global.GitHubWorkspace = {
    loadGitHubRepos,
    renderRepositories,
    selectRepository,
    loadRepositoryContents,
    renderGitHubFiles,
    loadFileContent,
    renderFileContent,
  };

  global.loadGitHubRepos = loadGitHubRepos;
  global.renderRepositories = renderRepositories;
  global.selectRepository = selectRepository;
  global.loadRepositoryContents = loadRepositoryContents;
  global.renderGitHubFiles = renderGitHubFiles;
  global.loadFileContent = loadFileContent;
  global.renderFileContent = renderFileContent;
})(typeof window !== "undefined" ? window : this);
