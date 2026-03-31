function switchTab(i) {
  [0, 1, 2].forEach(function (j) {
    document.getElementById("t" + j).classList.toggle("on", j === i);
    document.getElementById("p" + j).style.display = j === i ? "block" : "none";
  });
  // hide GitHub panel when switching tabs
  var ghPanel = document.getElementById("gh-panel");
  if (ghPanel) {
    ghPanel.style.display = "none";
    ghPanel.setAttribute("aria-hidden", "true");
  }
  // Clear any status messages
  hideStatus("anypointStatus");
  hideStatus("connectedAppStatus");
}

function showStatus(elementId, type, message) {
  var statusEl = document.getElementById(elementId);
  statusEl.className = "status-message " + type;
  statusEl.innerHTML = message;
  statusEl.style.display = "flex";
}

function hideStatus(elementId) {
  var statusEl = document.getElementById(elementId);
  statusEl.style.display = "none";
}

function setLoading(buttonId, loading) {
  var btn = document.getElementById(buttonId);
  var textEl = btn.querySelector(".btn-text");
  var loadingEl = btn.querySelector(".btn-loading");

  if (loading) {
    btn.disabled = true;
    textEl.style.display = "none";
    loadingEl.style.display = "inline";
  } else {
    btn.disabled = false;
    textEl.style.display = "inline";
    loadingEl.style.display = "none";
  }
}

// Anypoint Platform Login
async function loginAnypoint() {
  var username = document.getElementById("anypointUsername").value.trim();
  var password = document.getElementById("anypointPassword").value;

  // Clear previous status
  hideStatus("anypointStatus");

  // Validation
  if (!username || !password) {
    showStatus("anypointStatus", "error", "Please enter both username and password.");
    return;
  }

  // Set loading state
  setLoading("anypointLoginBtn", true);
  showStatus("anypointStatus", "info", "Authenticating with Anypoint Platform...");

  try {
    const res = await AuthApi.postAnypointLogin(username, password);
    const result = res.data;

    if (res.ok && result.success) {
      showStatus("anypointStatus", "success", "Connected to Anypoint Platform successfully!");

      // Show GitHub panel after successful authentication
      setTimeout(() => {
        authSuccess("Anypoint Platform");
      }, 1000);
    } else {
      showStatus(
        "anypointStatus",
        "error",
        result.error || "Authentication failed. Please check your credentials.",
      );
    }
  } catch (err) {
    showStatus("anypointStatus", "error", "Network error. Please try again.");
    console.error("Anypoint login error:", err);
  } finally {
    setLoading("anypointLoginBtn", false);
  }
}

// Connected App Login
async function loginConnectedApp() {
  var clientName = document.getElementById("clientName").value.trim();
  var clientId = document.getElementById("clientId").value.trim();
  var clientSecret = document.getElementById("clientSecret").value.trim();

  // Clear previous status
  hideStatus("connectedAppStatus");

  // Validation - clientName is always required
  if (!clientName) {
    showStatus("connectedAppStatus", "error", "Please enter a Client Name.");
    return;
  }

  // Set loading state
  setLoading("connectedAppLoginBtn", true);
  showStatus("connectedAppStatus", "info", "Authenticating with Connected App...");

  try {
    const res = await AuthApi.postConnectedAppLogin({
      clientName: clientName,
      clientId: clientId,
      clientSecret: clientSecret,
    });
    const result = res.data;

    if (res.ok && result.success) {
      showStatus("connectedAppStatus", "success", "Connected App authentication successful!");

      // Show GitHub panel after successful authentication
      setTimeout(() => {
        authSuccess("Connected App");
      }, 1000);
    } else {
      showStatus(
        "connectedAppStatus",
        "error",
        result.error || "Authentication failed. Please check your credentials.",
      );
    }
  } catch (err) {
    showStatus("connectedAppStatus", "error", "Network error. Please try again.");
    console.error("Connected App login error:", err);
  } finally {
    setLoading("connectedAppLoginBtn", false);
  }
}

// Toggle new client fields
function toggleNewClientFields() {
  var newFields = document.getElementById("newClientFields");
  var toggleText = document.getElementById("toggleText");

  if (newFields.style.display === "none") {
    newFields.style.display = "block";
    toggleText.textContent = "- Hide new client fields";
  } else {
    newFields.style.display = "none";
    toggleText.textContent = "+ Add new client";
  }
}

function fileChosen(input) {
  if (input.files && input.files[0]) {
    document.getElementById("fname").textContent = input.files[0].name;
    document.getElementById("file-chosen").style.display = "block";
    document.getElementById("dropzone").style.display = "none";
  }
}

function clearFile() {
  document.getElementById("file-chosen").style.display = "none";
  document.getElementById("dropzone").style.display = "block";
  document.getElementById("ffile").value = "";
}

// Local File Upload
async function uploadLocalFile() {
  var fileInput = document.getElementById("ffile");
  var file = fileInput.files[0];
  var appName = document.getElementById("appName")?.value?.trim() || file?.name;

  // Clear previous status
  hideStatus("anypointStatus");
  hideStatus("connectedAppStatus");

  var check = AuthApi.validateLocalLogFile(file);
  if (!check.ok) {
    alert(check.message);
    return;
  }

  // Set loading state
  setLoading("anypointLoginBtn", true); // Reuse the loading button
  showStatus("anypointStatus", "info", "Uploading and parsing log file...");

  try {
    const formData = new FormData();
    formData.append("file", file);
    if (appName) {
      formData.append("appName", appName);
    }

    const res = await AuthApi.postLocalUpload(formData);
    const result = res.data;

    if (res.ok && result.success) {
      showStatus("anypointStatus", "success", "Log file uploaded and analyzed successfully!");

      // Show GitHub panel after successful upload
      setTimeout(() => {
        authSuccess("Local File");
      }, 1000);
    } else {
      showStatus("anypointStatus", "error", result.error || "File upload failed. Please try again.");
    }
  } catch (err) {
    showStatus("anypointStatus", "error", "Network error during file upload. Please try again.");
    console.error("File upload error:", err);
  } finally {
    setLoading("anypointLoginBtn", false);
  }
}

// Handle Enter key for form submission
document.addEventListener("keydown", function (e) {
  if (e.key === "Enter") {
    var activeElement = document.activeElement;

    if (activeElement.id === "anypointUsername" || activeElement.id === "anypointPassword") {
      e.preventDefault();
      loginAnypoint();
    } else if (
      activeElement.id === "clientId" ||
      activeElement.id === "clientSecret" ||
      activeElement.id === "orgId"
    ) {
      e.preventDefault();
      loginConnectedApp();
    }
  }
});
