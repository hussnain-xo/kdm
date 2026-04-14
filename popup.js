// popup.js
document.addEventListener('DOMContentLoaded', function() {
  const toggleInterceptor = document.getElementById('toggleInterceptor');
  const statusText = document.getElementById('statusText');
  const connectionDot = document.getElementById('connectionDot');
  const connectionText = document.getElementById('connectionText');
  const urlInput = document.getElementById('urlInput');
  const quickDownloadBtn = document.getElementById('quickDownloadBtn');
  const currentPageBtn = document.getElementById('currentPageBtn');
  const scanPageBtn = document.getElementById('scanPageBtn');
  const downloadsBtn = document.getElementById('downloadsBtn');
  const settingsBtn = document.getElementById('settingsBtn');
  
  // Load current state
  chrome.storage.local.get(['kdmEnabled'], function(result) {
    const enabled = result.kdmEnabled !== false;
    toggleInterceptor.checked = enabled;
    updateStatus(enabled);
  });
  
  // Check KDM connection
  checkKDMConnection();
  
  // Toggle interceptor
  toggleInterceptor.addEventListener('change', function() {
    const enabled = this.checked;
    
    chrome.runtime.sendMessage({
      type: 'toggle_interceptor',
      enabled: enabled
    }, function(response) {
      if (response && response.ok) {
        updateStatus(enabled);
        showMessage(enabled ? 'Interceptor enabled' : 'Interceptor disabled');
      }
    });
  });
  
  // Quick download button
  quickDownloadBtn.addEventListener('click', function() {
    const url = urlInput.value.trim();
    
    if (url) {
      if (!isValidUrl(url)) {
        showMessage('Invalid URL format', true);
        return;
      }
      
      chrome.runtime.sendMessage({
        type: 'kdm_download',
        url: url,
        sourceType: 'popup_manual'
      }, function(response) {
        if (response && response.ok) {
          showMessage('Download sent to KDM');
          urlInput.value = '';
        } else {
          showMessage('Failed to send to KDM', true);
        }
      });
    } else {
      showMessage('Please enter a URL', true);
    }
  });
  
  // Current page button
  currentPageBtn.addEventListener('click', function() {
    chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
      if (tabs[0]) {
        chrome.runtime.sendMessage({
          type: 'kdm_download',
          url: tabs[0].url,
          sourceType: 'popup_current_page'
        }, function(response) {
          if (response && response.ok) {
            showMessage('Current page sent to KDM');
            window.close();
          }
        });
      }
    });
  });
  
  // Scan page button
  scanPageBtn.addEventListener('click', function() {
    chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
      if (tabs[0]) {
        chrome.runtime.sendMessage({
          type: 'scan_for_downloads'
        }, function(response) {
          if (response && response.ok) {
            showMessage(`Found ${response.links.length} downloadable links`);
          } else {
            showMessage('No downloadable links found', true);
          }
          window.close();
        });
      }
    });
  });
  
  // Open KDM button
  downloadsBtn.addEventListener('click', function() {
    // Try to focus existing KDM window or open new one
    chrome.runtime.sendMessage({
      type: 'focus_kdm_window'
    });
    window.close();
  });
  
  // Settings button
  settingsBtn.addEventListener('click', function() {
    // Open extension options page
    chrome.runtime.openOptionsPage();
    window.close();
  });
  
  // Populate URL input with current page URL
  chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
    if (tabs[0]) {
      urlInput.value = tabs[0].url;
      urlInput.select();
    }
  });
  
  // URL input enter key support
  urlInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      quickDownloadBtn.click();
    }
  });
  
  // Helper functions
  function updateStatus(enabled) {
    if (enabled) {
      statusText.textContent = 'Interceptor: ON';
      statusText.className = 'status on';
    } else {
      statusText.textContent = 'Interceptor: OFF';
      statusText.className = 'status off';
    }
  }
  
  function checkKDMConnection() {
    fetch('http://127.0.0.1:9669/jobs', { 
      method: 'GET',
      mode: 'no-cors'
    })
    .then(() => {
      connectionDot.className = 'connection-dot connected';
      connectionText.textContent = 'Connected to KDM';
    })
    .catch(() => {
      connectionDot.className = 'connection-dot disconnected';
      connectionText.textContent = 'KDM not running';
    });
  }
  
  function isValidUrl(string) {
    try {
      new URL(string);
      return true;
    } catch (_) {
      return false;
    }
  }
  
  function showMessage(message, isError = false) {
    // Create temporary message
    const messageEl = document.createElement('div');
    messageEl.textContent = message;
    messageEl.style.cssText = `
      position: fixed;
      top: 10px;
      right: 10px;
      background: ${isError ? '#EF4444' : '#10B981'};
      color: white;
      padding: 8px 12px;
      border-radius: 4px;
      font-size: 12px;
      z-index: 1000;
      animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(messageEl);
    
    setTimeout(() => {
      messageEl.style.animation = 'slideOut 0.3s ease';
      setTimeout(() => messageEl.remove(), 300);
    }, 3000);
  }
  
  // Add CSS animations
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideIn {
      from { transform: translateX(100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
      from { transform: translateX(0); opacity: 1; }
      to { transform: translateX(100%); opacity: 0; }
    }
  `;
  document.head.appendChild(style);
});