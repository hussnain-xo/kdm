// background.js — Enhanced Player URL Support with Cookie Handling
// Updated with new download windows support

// Safari: use browser if chrome is not defined (service worker has no window)
if (typeof chrome === "undefined" && typeof browser !== "undefined") {
  self.chrome = browser;
}

const KDM_BASE = "http://127.0.0.1:9669";
const KDM_ALT = "http://localhost:9669";

// Timeout in ms (Safari may be slower)
const KDM_TIMEOUT_MS = 20000;

// Capture streams: prefer real .m3u8; never overwrite with JW Player / analytics URLs (those break yt-dlp)
var capturedStreams = {}; // tabId -> { m3u8, pl, ts }
var CAPTURE_TTL_MS = 10 * 60 * 1000; // 10 min
function isBadStreamUrl(u) {
  if (!u) return true;
  var l = u.toLowerCase();
  return l.indexOf("jwpltx.com") !== -1 ||
    (l.indexOf("jwplayer") !== -1 && l.indexOf(".m3u8") === -1) ||
    l.indexOf("analytics") !== -1 || l.indexOf("doubleclick") !== -1 || l.indexOf("googletagmanager") !== -1;
}

try {
  chrome.webRequest.onBeforeRequest.addListener(
    function(details) {
      var u = details.url || "";
      if (isBadStreamUrl(u)) return;
      var isM3u8 = u.indexOf(".m3u8") !== -1 && u.indexOf(".m3u8.js") === -1;
      var isPlStream = u.indexOf("/pl/") !== -1 && (/neonhorizonworkshops|vidoza|streamtape|vidplay/i.test(u));
      if (!isM3u8 && !isPlStream) return;
      var tabId = details.tabId;
      if (tabId > 0) {
        var cap = capturedStreams[tabId] || { m3u8: null, pl: null, ts: 0 };
        var now = Date.now();
        if (isM3u8) {
          cap.m3u8 = u;
          cap.ts = now;
        } else if (isPlStream && !cap.m3u8) {
          cap.pl = u;
          cap.ts = now;
        }
        capturedStreams[tabId] = cap;
        var keys = Object.keys(capturedStreams);
        if (keys.length > 50) {
          for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            if (capturedStreams[k] && (now - capturedStreams[k].ts) > CAPTURE_TTL_MS) delete capturedStreams[k];
          }
        }
      }
    },
    { urls: ["<all_urls>"] }
  );
} catch (e) {}

function safeApiCall(url, payload, sendResponse) {
  var responseSent = false;
  function send(result) {
    if (responseSent) return;
    try {
      sendResponse(result);
      responseSent = true;
    } catch (e) {}
  }
  var controller = new AbortController();
  var t = setTimeout(function() { controller.abort(); }, KDM_TIMEOUT_MS);
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: controller.signal
  }).then(function(res) {
    clearTimeout(t);
    if (!res || !res.ok) {
      send({ ok: false, error: "KDM server is not running" });
      return null;
    }
    return res.json().catch(function() { return null; });
  }).then(function(data) {
    if (data && !responseSent) send({ ok: true, data: data });
    else if (!responseSent) send({ ok: false, error: "KDM server is not running" });
  }).catch(function(err) {
    clearTimeout(t);
    if (!responseSent) {
      var msg = (err && err.name === "AbortError") ? "KDM timed out. Start: python3 kdm.py" : "KDM server not running";
      send({ ok: false, error: msg });
    }
  });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // New message type for download with info (triggers download windows)
  if (msg.type === "kdm_download_with_info") {
    var urlToSend = msg.url;

    if (sender.tab && sender.tab.id) {
      var cap = capturedStreams[sender.tab.id];
      if (cap && (Date.now() - cap.ts) < CAPTURE_TTL_MS) {
        var picked = cap.m3u8 || cap.pl;
        if (picked && !isBadStreamUrl(picked)) {
          urlToSend = picked;
          if (!msg.referer && sender.tab && sender.tab.url) {
            msg.referer = sender.tab.url;
          }
        }
      }
    }

    const payload = {
      url: urlToSend,
      quality: msg.quality || "1080p",
      title: msg.title || "video"
    };
    if (msg.sourceType) payload.sourceType = msg.sourceType;
    if (msg.enhanced) payload.enhanced = true;
    payload.isPlayerUrl = msg.isPlayerUrl !== undefined ? msg.isPlayerUrl : (urlToSend.includes('strp2p.live') || urlToSend.includes('#'));
    if (msg.referer) payload.referer = msg.referer;

    var isStream = /neonhorizonworkshops|vidoza|streamtape|vidplay|strp2p|mistwolf|filemoon|doodstream|streamwish|lulustream|\.m3u8|\/pl\//i.test(urlToSend || '');
    if (isStream && !payload.referer) {
      payload.referer = sender.tab ? sender.tab.url : '';
    }
    if (isStream && urlToSend.indexOf('.m3u8') !== -1) {
      payload.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
    }

    function mergeCookieUrlsIntoPayload(done) {
      var origins = [];
      try {
        var o1 = new URL(urlToSend).origin + '/';
        if (origins.indexOf(o1) === -1) origins.push(o1);
      } catch (e) {}
      var ref = payload.referer || (sender.tab && sender.tab.url) || '';
      if (ref && /^https?:\/\//i.test(ref)) {
        try {
          var o2 = new URL(ref).origin + '/';
          if (origins.indexOf(o2) === -1) origins.push(o2);
        } catch (e2) {}
      }
      if (!chrome.cookies || !chrome.cookies.getAll || origins.length === 0) {
        done();
        return;
      }
      var merged = {};
      var left = origins.length;
      function finishOne(items) {
        if (items && items.length) {
          for (var i = 0; i < items.length; i++) {
            var c = items[i];
            if (c && c.name != null && c.value != null) merged[c.name] = c.value;
          }
        }
        left--;
        if (left <= 0) {
          var names = Object.keys(merged);
          if (names.length) {
            var parts = [];
            for (var j = 0; j < names.length; j++) parts.push(names[j] + '=' + merged[names[j]]);
            payload.cookie = parts.join('; ');
          }
          done();
        }
      }
      for (var k = 0; k < origins.length; k++) {
        chrome.cookies.getAll({ url: origins[k] }, finishOne);
      }
    }
    if (isStream) {
      try {
        mergeCookieUrlsIntoPayload(function() {
          safeApiCall(KDM_BASE + "/enqueue_with_info", payload, sendResponse);
        });
      } catch (e) {
        safeApiCall(KDM_BASE + "/enqueue_with_info", payload, sendResponse);
      }
    } else {
      safeApiCall(KDM_BASE + "/enqueue_with_info", payload, sendResponse);
    }
    return true;
  }
  
  // Original message type (backward compatibility)
  if (msg.type === "kdm_download") {
    // Enhanced payload with player URL detection
    const payload = {
      url: msg.url,
      quality: msg.quality || "1080p"
    };
    
    // Add enhanced options for player URLs
    if (msg.sourceType) {
      payload.sourceType = msg.sourceType;
    }
    
    if (msg.enhanced) {
      payload.enhanced = true;
    }
    
    // Detect player URLs automatically
    if (msg.isPlayerUrl !== undefined) {
      payload.isPlayerUrl = msg.isPlayerUrl;
    } else {
      // Auto-detect player URLs
      payload.isPlayerUrl = msg.url.includes('strp2p.live') || msg.url.includes('#');
    }
    
    // Add referer and user-agent for protected streams
    if (msg.url.includes('strp2p.live') || msg.url.includes('.m3u8')) {
      payload.referer = sender.tab ? sender.tab.url : '';
      payload.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
    }
    
    // Use safe API call wrapper
    safeApiCall(KDM_BASE + "/enqueue", payload, sendResponse);
    return true;
  }
});

// Add context menu (remove first to avoid duplicate id errors)
function createContextMenu() {
  chrome.contextMenus.removeAll(function() {
    try {
      chrome.contextMenus.create({
        id: "kdm-download-video",
        title: "Download with KDM",
        contexts: ["video", "link", "page"]
      });
      chrome.contextMenus.create({
        id: "kdm-download-torrent",
        title: "Download torrent with KDM",
        contexts: ["link"]
      });
    } catch (e) {}
  });
}
chrome.runtime.onInstalled.addListener(createContextMenu);
createContextMenu();

function isTorrentUrl(url) {
  if (!url || typeof url !== "string") return false;
  var u = url.toLowerCase();
  return u.indexOf(".torrent") !== -1 || u.indexOf("magnet:") === 0;
}

// Collect Cookie header for a given URL (needs \"cookies\" permission)
function getCookiesForUrl(url, cb) {
  if (!chrome.cookies || !chrome.cookies.getAll) {
    cb("");
    return;
  }
  try {
    chrome.cookies.getAll({ url: url }, function(items) {
      if (!items || !items.length) {
        cb("");
        return;
      }
      var parts = [];
      for (var i = 0; i < items.length; i++) {
        var c = items[i];
        if (c && c.name != null && c.value != null) {
          parts.push(c.name + "=" + c.value);
        }
      }
      cb(parts.join("; "));
    });
  } catch (e) {
    cb("");
  }
}

chrome.contextMenus.onClicked.addListener(function(info, tab) {
  var url = info.srcUrl || info.linkUrl || info.pageUrl;
  if (!url) return;
  var title = (tab && tab.title) ? String(tab.title).substring(0, 120) : "download";
  var sourceType = "generic";
  if (info.menuItemId === "kdm-download-torrent" || isTorrentUrl(url)) {
    sourceType = "torrent";
  }
  getCookiesForUrl(url, function(cookieHeader) {
    var payload = {
      url: url,
      title: title,
      quality: "best",
      sourceType: sourceType
    };
    if (tab && tab.url) {
      payload.referer = tab.url;
    }
    if (cookieHeader) {
      payload.cookie = cookieHeader;
    }
    safeApiCall(KDM_BASE + "/enqueue_with_info", payload, function() {});
  });
});

// Intercept all Chrome downloads and send to KDM (use fetch – service worker has no XMLHttpRequest)
chrome.downloads.onCreated.addListener(function(downloadItem) {
  var url = downloadItem.url || downloadItem.finalUrl;
  if (!url || url.startsWith("blob:") || url.startsWith("data:")) return;
  chrome.downloads.cancel(downloadItem.id);
  var rawName = downloadItem.filename ? downloadItem.filename.replace(/^.*[/\\]/, "") : "";
  var title = rawName || "download";
  var sourceType = isTorrentUrl(url) || rawName === "torfile.bin" || /\.torrent$/i.test(rawName) ? "torrent" : "generic";
  var referer = "";
  try { referer = new URL(url).origin + "/"; } catch (e) {}
  getCookiesForUrl(url, function(cookieHeader) {
    var payload = { url: url, title: title, quality: "best", sourceType: sourceType, referer: referer };
    if (cookieHeader) {
      payload.cookie = cookieHeader;
    }
    fetch(KDM_BASE + "/enqueue_with_info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).catch(function() {});
    try {
      var msg = sourceType === "torrent" ? "Torrent sent to KDM" : "Download sent to KDM";
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/48.png",
        title: "KDM",
        message: msg
      });
    } catch (e) {}
  });
});
