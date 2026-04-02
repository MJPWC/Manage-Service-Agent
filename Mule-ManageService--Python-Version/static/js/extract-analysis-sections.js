// Helper function to extract specific sections from AI analysis
function extractAnalysisSections(analysisText) {
  if (!analysisText || typeof analysisText !== 'string') {
    return {
      immediate_actions: '',
      change_summary: '',
      full_analysis: analysisText || ''
    };
  }

  let immediate_actions = '';
  let change_summary = '';

  // Extract Immediate Actions section
  const immediateActionsMatch = analysisText.match(
    /(?:\*\*Immediate Actions\*\*|### Immediate Actions|## Immediate Actions)([\s\S]*?)(?=\*\*[^*]+\*\*|### [^#]+|## [^#]+|\Z)/i
  );
  
  if (immediateActionsMatch && immediateActionsMatch[1]) {
    immediate_actions = immediateActionsMatch[1].trim();
  }

  // Extract Change Summary section
  const changeSummaryMatch = analysisText.match(
    /(?:\*\*Change Summary\*\*|### Change Summary|## Change Summary)([\s\S]*?)(?=\*\*[^*]+\*\*|### [^#]+|## [^#]+|\Z)/i
  );
  
  if (changeSummaryMatch && changeSummaryMatch[1]) {
    change_summary = changeSummaryMatch[1].trim();
  }

  return {
    immediate_actions,
    change_summary,
    full_analysis: analysisText
  };
}

// Export for use in app.js
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { extractAnalysisSections };
} else {
  window.extractAnalysisSections = extractAnalysisSections;
}
