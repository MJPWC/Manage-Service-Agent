// Multi-file upload functionality - Clean implementation

function normalizeSelectedFileName(fileName) {
  return String(fileName || "")
    .split("\\")
    .pop()
    .split("/")
    .pop()
    .trim();
}

function getExpectedFilesFromEventDetails() {
  const ctx = window.__eventDetailsContext;
  const fromContext = Array.from(ctx?.expectedUploadFiles || [])
    .map(name => normalizeSelectedFileName(name))
    .filter(Boolean);

  if (fromContext.length > 1) {
    return fromContext;
  }

  const modal = document.getElementById("eventDetailsModal");
  if (!modal) {
    return fromContext;
  }

  const labels = Array.from(modal.querySelectorAll(".detail-label"));
  const fileNamesLabel = labels.find(
    (label) => (label.textContent || "").trim() === "File Names:"
  );

  if (!fileNamesLabel) {
    return fromContext;
  }

  const row = fileNamesLabel.closest(".event-detail-row");
  const valueContainer = row ? row.querySelector(".detail-value") : null;
  if (!valueContainer) {
    return fromContext;
  }

  const itemNodes = Array.from(valueContainer.querySelectorAll(".detail-item-content"));
  const parsed = itemNodes
    .map((node) => {
      const clone = node.cloneNode(true);
      const strong = clone.querySelector("strong");
      if (strong) {
        strong.remove();
      }
      return normalizeSelectedFileName(clone.textContent || "");
    })
    .filter((name) => name && name !== "N/A");

  const uniqueParsed = [];
  const seen = new Set();
  parsed.forEach((name) => {
    const key = name.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    uniqueParsed.push(name);
  });

  if (uniqueParsed.length > 0 && ctx) {
    ctx.expectedUploadFiles = uniqueParsed;
  }

  return uniqueParsed.length > 0 ? uniqueParsed : fromContext;
}

function updateReferenceFileIndicatorLocal() {
  const indicator = document.getElementById("referenceFileIndicator");
  if (!indicator) return;

  const ctx = window.__eventDetailsContext;
  const selectedFiles = Array.from(window.__selectedFiles || []);

  if (selectedFiles.length > 0) {
    indicator.style.display = "flex";

    const label =
      selectedFiles.length === 1
        ? `File attached: ${selectedFiles[0].name}`
        : `${selectedFiles.length} files attached: ${selectedFiles.map((file) => file.name).join(", ")}`;

    indicator.innerHTML = `<span>${label}</span>
      <button type="button" class="btn-icon btn-icon-small" id="clearReferenceFile" title="Remove file(s)">✕</button>`;

    const clearBtn = document.getElementById("clearReferenceFile");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        window.__selectedFiles = [];
        if (ctx) {
          ctx.referenceFile = null;
          ctx.referenceFiles = [];
          ctx.analysisFlowState = "attach";
        }
        updateReferenceFileIndicatorLocal();
        if (window.updateEventDetailFlowButtons) {
          window.updateEventDetailFlowButtons();
        }
      });
    }
    return;
  }

  if (ctx?.referenceFile) {
    indicator.style.display = "flex";
    indicator.innerHTML = `<span>File attached: ${ctx.referenceFile.name}</span>
      <button type="button" class="btn-icon btn-icon-small" id="clearReferenceFile" title="Remove file">✕</button>`;

    const clearBtn = document.getElementById("clearReferenceFile");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        if (ctx) {
          ctx.referenceFile = null;
          ctx.referenceFiles = [];
          ctx.analysisFlowState = "attach";
        }
        updateReferenceFileIndicatorLocal();
        if (window.updateEventDetailFlowButtons) {
          window.updateEventDetailFlowButtons();
        }
      });
    }
  } else {
    indicator.style.display = "none";
    indicator.innerHTML = "";
  }
}

function validateFilesAgainstEventDetails(files, options = {}) {
  const { allowPartial = false } = options;
  const ctx = window.__eventDetailsContext;
  const expectedFiles = getExpectedFilesFromEventDetails().map(name => String(name).trim());
  const expectedMap = new Map(expectedFiles.map(name => [name.toLowerCase(), name]));
  const selectedFiles = Array.from(files || []);
  const selectedNames = selectedFiles.map(file => normalizeSelectedFileName(file.name));

  if (expectedFiles.length === 0) {
    return { valid: true, expectedFiles, selectedNames };
  }

  if (expectedFiles.length === 1) {
    if (selectedNames.length !== 1) {
      return {
        valid: false,
        message: `Please upload exactly one file: "${expectedFiles[0]}".`
      };
    }

    if (selectedNames[0].toLowerCase() !== expectedFiles[0].toLowerCase()) {
      return {
        valid: false,
        message: `Wrong file passed.\n\nUploaded file: "${selectedNames[0]}"\nExpected file: "${expectedFiles[0]}"`
      };
    }

    return { valid: true, expectedFiles, selectedNames };
  }

  if (!allowPartial && selectedNames.length < 2) {
    return {
      valid: false,
      message: `Please upload multiple files from the Event Details list.\n\nExpected file names: ${expectedFiles.join(", ")}`
    };
  }

  const seenSelected = new Set();
  const duplicateFiles = selectedNames.filter(name => {
    const key = name.toLowerCase();
    if (seenSelected.has(key)) return true;
    seenSelected.add(key);
    return false;
  });
  if (duplicateFiles.length > 0) {
    return {
      valid: false,
      message: `Duplicate file selected.\n\nDuplicate file(s): ${duplicateFiles.join(", ")}`
    };
  }

  const invalidFiles = selectedNames.filter(name => !expectedMap.has(name.toLowerCase()));
  if (invalidFiles.length > 0) {
    return {
      valid: false,
      message:
        `Wrong file passed.\n\nInvalid file(s): ${invalidFiles.join(", ")}\nExpected file names: ${expectedFiles.join(", ")}`
    };
  }

  if (!allowPartial) {
    const missingFiles = expectedFiles.filter(
      name => !selectedNames.some(selected => selected.toLowerCase() === name.toLowerCase())
    );
    if (missingFiles.length > 0) {
      return {
        valid: false,
        message:
          `Please upload all required files.\n\nMissing file(s): ${missingFiles.join(", ")}\nExpected file names: ${expectedFiles.join(", ")}`
      };
    }
  }

  return { valid: true, expectedFiles, selectedNames };
}

// Global functions for file selection modal
window.closeFileSelectionModal = function() {
  const modal = document.getElementById('fileSelectionModal');
  if (modal) {
    modal.remove();
  }
};

window.addMoreFiles = function() {
  const expectedFiles = getExpectedFilesFromEventDetails().map(name => String(name).trim());

  const input = document.createElement('input');
  input.type = 'file';
  input.multiple = expectedFiles.length > 1;
  input.onchange = function(e) {
    const newFiles = Array.from(e.target.files);
    if (newFiles.length > 0) {
      const combinedFiles = [...(window.__selectedFiles || []), ...newFiles];
      const validation = validateFilesAgainstEventDetails(combinedFiles, { allowPartial: true });
      if (!validation.valid) {
        alert(validation.message);
        return;
      }
      window.__selectedFiles = combinedFiles;
      updateFileList();
      updateReferenceFileIndicatorLocal();

      const missingFiles = expectedFiles.filter(
        name => !window.__selectedFiles.some(file => normalizeSelectedFileName(file.name).toLowerCase() === name.toLowerCase())
      );

      if (missingFiles.length > 0) {
        const shouldContinue = confirm(
          `Please select the remaining file(s): ${missingFiles.join(", ")}`
        );
        if (shouldContinue) {
          window.addMoreFiles();
        }
      }
    }
  };
  input.click();
};

window.removeFile = function(fileName) {
  window.__selectedFiles = window.__selectedFiles.filter(file => file.name !== fileName);
  updateFileList();
  updateReferenceFileIndicatorLocal();
};

window.updateFileList = function() {
  const fileList = document.getElementById('selectedFilesList');
  const fileCount = document.getElementById('fileCount');
  const helperText = document.getElementById('remainingFilesHint');
  const expectedFiles = getExpectedFilesFromEventDetails().map(name => String(name).trim());
  const missingFiles = expectedFiles.filter(
    name => !(window.__selectedFiles || []).some(file => normalizeSelectedFileName(file.name).toLowerCase() === name.toLowerCase())
  );

  if (!fileList || !fileCount) return;
  
  fileList.innerHTML = window.__selectedFiles.map(file => `
    <div class="file-item">
      <span class="file-name">${file.name}</span>
      <button class="btn-remove-file" onclick="removeFile('${file.name}')">✕</button>
    </div>
  `).join('');
  
  fileCount.textContent = window.__selectedFiles.length;

  if (helperText) {
    if (missingFiles.length > 0) {
      helperText.textContent = `Please add the remaining file(s): ${missingFiles.join(", ")}`;
      helperText.style.display = "block";
    } else {
      helperText.textContent = "All required files selected. You can proceed with analysis.";
      helperText.style.display = "block";
    }
  }
};

window.submitFilesForAnalysis = function() {
  const files = window.__selectedFiles;
  const validation = validateFilesAgainstEventDetails(files, { allowPartial: false });
  if (!validation.valid) {
    alert(validation.message);
    return;
  }
  console.log(`🔍 Submitting ${files.length} files for analysis`);
  
  closeFileSelectionModal();
  
  if (files.length > 1) {
    uploadMultipleLocalFiles(files);
  } else {
    uploadSingleLocalFile(files[0]);
  }
};

// Function to show file selection interface
function showFileSelectionInterface(initialFiles) {
  console.log(`📁 Showing file selection interface with ${initialFiles.length} files`);
  
  // Store selected files globally
  window.__selectedFiles = initialFiles;
  updateReferenceFileIndicatorLocal();
  
  // Create file selection modal
  const modalHtml = `
    <div class="file-selection-modal" id="fileSelectionModal">
      <div class="file-selection-backdrop"></div>
      <div class="file-selection-content">
        <div class="file-selection-header">
          <h3>📁 Select Files for Analysis</h3>
          <button class="btn-icon" onclick="closeFileSelectionModal()">✕</button>
        </div>
        <div class="file-selection-body">
          <div class="file-selection-info">
            <p>Selected <span id="fileCount">${initialFiles.length}</span> file(s)</p>
            <p id="remainingFilesHint">You can add more files or proceed with analysis.</p>
          </div>
          <div class="file-list" id="selectedFilesList">
            ${initialFiles.map(file => `
              <div class="file-item">
                <span class="file-name">${file.name}</span>
                <button class="btn-remove-file" onclick="removeFile('${file.name}')">✕</button>
              </div>
            `).join('')}
          </div>
          <div class="file-selection-actions">
            <button class="btn-secondary" onclick="addMoreFiles()">
              <span>➕ Add More Files</span>
            </button>
            <button class="btn-primary" onclick="submitFilesForAnalysis()">
              <span>🔍 Analyze Files</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  `;
  
  // Add modal to page
  document.body.insertAdjacentHTML('beforeend', modalHtml);
  updateFileList();
}

// Function to upload multiple local files
function uploadMultipleLocalFiles(files) {
  console.log(`📁 Uploading ${files.length} files for multi-file analysis`);
  const validation = validateFilesAgainstEventDetails(files, { allowPartial: false });
  if (!validation.valid) {
    if (window.setEventDetailsFlowState) {
      window.setEventDetailsFlowState('attach');
    }
    alert(validation.message);
    const input = document.getElementById("localFileInput");
    if (input) {
      input.value = "";
    }
    return;
  }

  if (window.setEventDetailsFlowState) {
    window.setEventDetailsFlowState('loading-local-multiple');
  }
  
  const formData = new FormData();
  files.forEach(file => {
    formData.append('files', file);
  });
  
  // Add application name if available
  const ctx = window.__eventDetailsContext;
  if (ctx && ctx.appName) {
    formData.append('appName', ctx.appName);
  }
  
  fetch('/api/local/upload-multiple', {
    method: 'POST',
    body: formData
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      console.log(`✅ Successfully uploaded ${data.files.length} files`);
      
      // Trigger multi-file analysis
      startMultiFileAnalysisFromLocalFiles(data.files);
    } else {
      if (window.setEventDetailsFlowState) {
        window.setEventDetailsFlowState('attach');
      }
      console.error('❌ Upload failed:', data.error);
      alert(`Upload failed: ${data.error}`);
    }
  })
  .catch(error => {
    if (window.setEventDetailsFlowState) {
      window.setEventDetailsFlowState('attach');
    }
    console.error('❌ Upload error:', error);
    alert(`Upload error: ${error.message}`);
  });
}

// Function to start multi-file analysis from local files
function startMultiFileAnalysisFromLocalFiles(fileNames) {
  console.log(`🔍 Starting multi-file analysis for local files: ${fileNames.join(', ')}`);
  
  const ctx = window.__eventDetailsContext;
  if (!ctx) {
    if (window.setEventDetailsFlowState) {
      window.setEventDetailsFlowState('attach');
    }
    console.error('❌ No event details context available');
    alert('No error context available for analysis');
    return;
  }
  
  // Read actual file contents from the uploaded files
  const fileContents = {};
  const filePromises = window.__selectedFiles.map(file => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = function(e) {
        fileContents[file.name] = e.target.result;
        console.log(`✅ Read content for ${file.name}: ${e.target.result.length} chars`);
        resolve();
      };
      reader.onerror = function(e) {
        console.error(`❌ Error reading file ${file.name}:`, e);
        reject(e);
      };
      reader.readAsText(file);
    });
  });
  
  Promise.all(filePromises).then(() => {
    console.log(`📋 All files read, starting analysis...`);
    
    // Directly call unified analysis function to avoid duplicate API calls
    window.analyzeErrorWithRulesetUnified(0, fileNames, fileContents);
  })
  .catch(error => {
    if (window.setEventDetailsFlowState) {
      window.setEventDetailsFlowState('attach');
    }
    console.error('❌ Error reading files:', error);
    alert(`Error reading files: ${error.message}`);
  });
}

// Function to upload single local file
function uploadSingleLocalFile(file) {
  const ctx = window.__eventDetailsContext;
  const expectedFiles = getExpectedFilesFromEventDetails().map(name => String(name).trim());
  const incomingFiles = [file];
  const combinedFiles = [...(window.__selectedFiles || []), ...incomingFiles];
  const validation = validateFilesAgainstEventDetails(
    expectedFiles.length > 1 ? combinedFiles : incomingFiles,
    { allowPartial: expectedFiles.length > 1 }
  );
  if (!validation.valid) {
    if (window.setEventDetailsFlowState) {
      window.setEventDetailsFlowState('attach');
    }
    alert(validation.message);
    document.getElementById("localFileInput").value = "";
    return;
  }

  if (expectedFiles.length > 1) {
    window.__selectedFiles = combinedFiles;
    if (ctx) {
      ctx.referenceFiles = combinedFiles.map(selectedFile => ({
        name: selectedFile.name,
      }));
      ctx.analysisFlowState = "attach";
    }
    updateReferenceFileIndicatorLocal();
    if (window.updateEventDetailFlowButtons) {
      window.updateEventDetailFlowButtons();
    }

    const missingFiles = expectedFiles.filter(
      name => !combinedFiles.some(selectedFile => normalizeSelectedFileName(selectedFile.name).toLowerCase() === name.toLowerCase())
    );

    if (missingFiles.length > 0) {
      showFileSelectionInterface(combinedFiles);
      setTimeout(() => {
        window.addMoreFiles();
      }, 0);
      document.getElementById("localFileInput").value = "";
      return;
    }

    showFileSelectionInterface(combinedFiles);
    document.getElementById("localFileInput").value = "";
    return;
  }

  if (window.setEventDetailsFlowState) {
    window.setEventDetailsFlowState('loading-local');
  }

  const reader = new FileReader();
  reader.onload = function () {
    if (window.__eventDetailsContext) {
      window.__eventDetailsContext.referenceFile = {
        name: file.name,
        content: reader.result,
      };
      window.__eventDetailsContext.referenceFiles = [
        {
          name: file.name,
          content: reader.result,
        },
      ];
      window.__eventDetailsContext.analysisFlowState = "attached";
      window.__selectedFiles = [file];
      updateReferenceFileIndicatorLocal();
      if (window.updateEventDetailFlowButtons) {
        window.updateEventDetailFlowButtons();
      }
      // Automatically trigger analysis with first log
      analyzeErrorWithRuleset(0);
    }
  };
  reader.onerror = function (error) {
    if (window.setEventDetailsFlowState) {
      window.setEventDetailsFlowState('attach');
    }
    console.error('❌ Error reading local file:', error);
    alert('Error reading local file.');
  };
  reader.readAsText(file);
  document.getElementById("localFileInput").value = "";
}
