// Multi-file upload functionality - Clean implementation

// Global functions for file selection modal
window.closeFileSelectionModal = function() {
  const modal = document.getElementById('fileSelectionModal');
  if (modal) {
    modal.remove();
  }
};

window.addMoreFiles = function() {
  const input = document.createElement('input');
  input.type = 'file';
  input.multiple = true;
  input.onchange = function(e) {
    const newFiles = Array.from(e.target.files);
    if (newFiles.length > 0) {
      window.__selectedFiles = [...window.__selectedFiles, ...newFiles];
      updateFileList();
    }
  };
  input.click();
};

window.removeFile = function(fileName) {
  window.__selectedFiles = window.__selectedFiles.filter(file => file.name !== fileName);
  updateFileList();
};

window.updateFileList = function() {
  const fileList = document.getElementById('selectedFilesList');
  const fileCount = document.getElementById('fileCount');
  
  fileList.innerHTML = window.__selectedFiles.map(file => `
    <div class="file-item">
      <span class="file-name">${file.name}</span>
      <button class="btn-remove-file" onclick="removeFile('${file.name}')">✕</button>
    </div>
  `).join('');
  
  fileCount.textContent = window.__selectedFiles.length;
};

window.submitFilesForAnalysis = function() {
  const files = window.__selectedFiles;
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
            <p>You can add more files or proceed with analysis.</p>
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
}

// Function to upload multiple local files
function uploadMultipleLocalFiles(files) {
  console.log(`📁 Uploading ${files.length} files for multi-file analysis`);
  
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
      console.error('❌ Upload failed:', data.error);
      alert(`Upload failed: ${data.error}`);
    }
  })
  .catch(error => {
    console.error('❌ Upload error:', error);
    alert(`Upload error: ${error.message}`);
  });
}

// Function to start multi-file analysis from local files
function startMultiFileAnalysisFromLocalFiles(fileNames) {
  console.log(`🔍 Starting multi-file analysis for local files: ${fileNames.join(', ')}`);
  
  const ctx = window.__eventDetailsContext;
  if (!ctx) {
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
    console.error('❌ Error reading files:', error);
    alert(`Error reading files: ${error.message}`);
  });
}

// Function to upload single local file
function uploadSingleLocalFile(file) {
  const ctx = window.__eventDetailsContext;
  
  if (ctx && ctx.logs && ctx.logs.length > 0) {
    const expectedFile = parseExpectedFileFromError(ctx.logs[0]);
    
    if (expectedFile) {
      // Extract filename from expected file (remove line numbers)
      const expectedFileName = expectedFile.split(":")[0].trim();
      const uploadedFileName = file.name
        .split("\\")
        .pop()
        .split("/")
        .pop(); // Extract just the filename
      
      if (uploadedFileName.toLowerCase() !== expectedFileName.toLowerCase()) {
        alert(
          `File name mismatch!\n\nUploaded file: "${uploadedFileName}"\nExpected file: "${expectedFileName}"\n\nPlease upload the correct file.`
        );
        document.getElementById("localFileInput").value = "";
        return;
      }
    }
  }

  const reader = new FileReader();
  reader.onload = function () {
    if (window.__eventDetailsContext) {
      window.__eventDetailsContext.referenceFile = {
        name: file.name,
        content: reader.result,
      };
      window.__eventDetailsContext.analysisFlowState = "attached";
      updateReferenceFileIndicator();
      updateEventDetailFlowButtons();
      // Automatically trigger analysis with first log
      analyzeErrorWithRuleset(0);
    }
  };
  reader.readAsText(file);
  document.getElementById("localFileInput").value = "";
}
