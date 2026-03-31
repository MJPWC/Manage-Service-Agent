/**
 * Anypoint Platform integration: business groups and environment selectors
 */

(function() {
  "use strict";

  // Render environments dropdown
  function renderEnvironments() {
    console.log(`[Business Group] renderEnvironments called, state.environments:`, window.state?.environments);
    const envSelect = document.getElementById("envSelect");
    if (!envSelect) {
      console.log(`[Business Group] envSelect element not found in DOM`);
      return;
    }

    envSelect.innerHTML = '<option value="">Select Environment</option>';

    if (!window.state?.environments || window.state.environments.length === 0) {
      console.log(`[Business Group] No environments to render, environments:`, window.state?.environments);
      envSelect.disabled = true;
      envSelect.title = "Log in to Anypoint (click on circle icon) to select an environment";
      return;
    }

    console.log(`[Business Group] Rendering ${window.state.environments.length} environments`);
    window.state.environments.forEach((env) => {
      const option = document.createElement("option");
      option.value = env.id;
      option.textContent = env.name;
      envSelect.appendChild(option);
      console.log(`[Business Group] Added environment option: ${env.name} (${env.id})`);
    });

    envSelect.disabled = false;
    envSelect.title = "";

    if (window.state?.currentEnvId) {
      envSelect.value = window.state.currentEnvId;
    }
    
    console.log(`[Business Group] Environment dropdown updated successfully`);
    console.log(`[Business Group] Final envSelect options count:`, envSelect.options.length);
    console.log(`[Business Group] Final envSelect HTML:`, envSelect.innerHTML);
  }

  // Fetch environments for selected business group
  async function fetchEnvironmentsForBusinessGroup(businessGroupId) {
    try {
      console.log(`[Business Group] Fetching environments for: ${businessGroupId}`);
      
      const result = await window.api("GET", `/api/organizations/${businessGroupId}/environments`);
      console.log(`[Business Group] API response:`, result);
      
      if (result.success && result.environments) {
        window.state.environments = result.environments;
        console.log(`[Business Group] Loaded ${result.environments.length} environments:`, result.environments);
        
        // Store selected business group ID in session via API
        await window.api("POST", "/api/session/update", {
          selected_business_group_id: businessGroupId
        });
        
        // Enable environment selector when business group is selected
        const envSelect = document.getElementById("envSelect");
        if (envSelect) {
          envSelect.disabled = false;
          envSelect.style.pointerEvents = "auto";
          envSelect.style.opacity = "1";
          
          // Rebind environment change event if needed
          if (!envSelect.hasAttribute('data-event-bound')) {
            envSelect.addEventListener("change", async (e) => {
              window.state.currentEnvId = e.target.value;
              window.state.selectedAppId = null;
              window.state.logs = [];
              if (window.stopAutoRefresh) window.stopAutoRefresh();
              if (window.renderLogs) window.renderLogs();
              if (window.resetTimeFilter) window.resetTimeFilter();
              if (window.loadApplications) await window.loadApplications(window.state.currentEnvId);
            });
            envSelect.setAttribute('data-event-bound', 'true');
          }
        }     
        // Render environments
        renderEnvironments();
      } else {
        console.error(`[Business Group] Failed to load environments: ${result.error}`);
        window.state.environments = [];
        renderEnvironments();
      }
    } catch (err) {
      console.error(`[Business Group] Error fetching environments:`, err);
      window.state.environments = [];
      renderEnvironments();
    }
  }

  // Update business group display
  function updateBusinessGroupDisplay(businessGroups) {
    console.log(`[Business Group] updateBusinessGroupDisplay called with:`, businessGroups);
    const bgSelector = document.getElementById("businessGroupSelector");
    const bgSelect = document.getElementById("businessGroupSelect");
    const envSelect = document.getElementById("envSelect");
    
    console.log(`[Business Group] DOM elements found:`, {
      bgSelector: !!bgSelector,
      bgSelect: !!bgSelect,
      envSelect: !!envSelect
    });
    
    // Always ensure environment selector is completely disabled and hidden when no business group selected
    if (envSelect) {
      envSelect.disabled = true;
      envSelect.style.pointerEvents = "none";
      envSelect.style.opacity = "0.3";
      envSelect.value = "";
    }
    
    if (businessGroups && businessGroups.length > 0 && bgSelector && bgSelect) {
      // Clear existing options
      bgSelect.innerHTML = '<option value="">Select Business Group</option>';
      
      // Add business group options
      businessGroups.forEach(bg => {
        const option = document.createElement("option");
        option.value = bg.id;
        option.textContent = bg.name;
        bgSelect.appendChild(option);
      });
      
      // Show and enable selector
      bgSelector.style.display = "flex";
      bgSelect.disabled = false;
      
      console.log(`[Business Groups] Loaded ${businessGroups.length} business groups`);
    } else if (bgSelector) {
      bgSelector.style.display = "none";
    }
  }

  // Setup business group and environment event handlers
  function setupBusinessGroupAndEnvironmentHandlers() {
    // Ensure environment change event is properly bound
    const envSelect = document.getElementById("envSelect");
    if (envSelect && !envSelect.hasAttribute("data-event-bound")) {
      envSelect.addEventListener("change", async (e) => {
        window.state.currentEnvId = e.target.value;
        window.state.selectedAppId = null;
        window.state.logs = [];
        if (window.stopAutoRefresh) window.stopAutoRefresh();
        if (window.renderLogs) window.renderLogs();
        if (window.resetTimeFilter) window.resetTimeFilter();
        await window.loadApplications(window.state.currentEnvId);
      });

      envSelect.setAttribute("data-event-bound", "true");
    }

    // Ensure business group change event is properly bound
    const bgSelect = document.getElementById("businessGroupSelect");
    if (bgSelect && !bgSelect.hasAttribute('data-event-bound')) {
      bgSelect.addEventListener("change", async (e) => {
        const selectedBgId = e.target.value;
        const selectedBgName = e.target.options[e.target.selectedIndex].textContent;
        
        if (selectedBgId) {
          console.log(`[Business Group] Selected: ${selectedBgName} (${selectedBgId})`);
          
          // Store selected business group in state
          window.state.selectedBusinessGroup = {
            id: selectedBgId,
            name: selectedBgName
          };
          
          // Fetch environments for this business group
          await fetchEnvironmentsForBusinessGroup(selectedBgId);
          
        } else {
          // Disable environment selector if no business group selected
          const envSelect = document.getElementById("envSelect");
          if (envSelect) {
            envSelect.disabled = true;
            envSelect.value = "";
          }
          
          window.state.selectedBusinessGroup = null;
          window.state.currentEnvId = null;
          window.state.environments = [];
          renderEnvironments();
        }
      });

      bgSelect.setAttribute('data-event-bound', 'true');
    }
  }

  // Expose functions to global scope
  window.renderEnvironments = renderEnvironments;
  window.fetchEnvironmentsForBusinessGroup = fetchEnvironmentsForBusinessGroup;
  window.updateBusinessGroupDisplay = updateBusinessGroupDisplay;
  window.setupBusinessGroupAndEnvironmentHandlers = setupBusinessGroupAndEnvironmentHandlers;

})();