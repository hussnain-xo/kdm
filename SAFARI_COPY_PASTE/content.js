// content.js — Kalupura Download Manager (KDM)
// Updated with new download windows system

// Safari: use browser if chrome is not defined
if (typeof chrome === "undefined" && typeof browser !== "undefined") {
  window.chrome = browser;
}

// Safe sendMessage: avoids "Extension context invalidated" and undefined chrome.runtime
function safeSendMessage(payload, callback) {
  function safeCall(opt) {
    try {
      if (typeof callback === "function") callback(opt || { ok: false, error: "Extension context invalidated" });
    } catch (e) { /* swallow */ }
  }
  try {
    var runtime = (typeof chrome !== "undefined" && chrome && chrome.runtime) ? chrome.runtime : null;
    if (!runtime || !runtime.id) {
      safeCall({ ok: false, error: "Extension context invalidated" });
      return;
    }
    try {
      runtime.sendMessage(payload, function (res) {
        var hasError = false;
        try {
          hasError = !!(chrome && chrome.runtime && chrome.runtime.lastError);
        } catch (e) {
          hasError = true;
        }
        if (hasError) {
          safeCall({ ok: false, error: "Extension context invalidated" });
          return;
        }
        safeCall(res || { ok: false });
      });
    } catch (sendErr) {
      safeCall({ ok: false, error: "Extension context invalidated" });
    }
  } catch (e) {
    safeCall({ ok: false, error: "Extension context invalidated" });
  }
}

function showContextInvalidMessage() {
  try {
    alert("KDM was updated or reloaded.\n\nPlease refresh this page (F5) and try again.");
  } catch (e) { /* swallow */ }
}

// YouTube injection function
function injectKDM() {
  const player = document.querySelector(".html5-video-player") || document.querySelector("#movie_player") || document.querySelector("ytd-watch-flexy");
  if (!player || document.getElementById("kdm-btn")) {
    if (!player) console.log("KDM: YouTube player not found");
    if (document.getElementById("kdm-btn")) console.log("KDM: YouTube button already exists");
    return;
  }
  
  console.log("KDM: Injecting YouTube download button");

  const wrap = document.createElement("div");
  wrap.id = "kdm-btn";
  wrap.style.cssText =
    "position:absolute;top:10px;right:30px;z-index:999999;font-family:sans-serif;pointer-events:auto;";

  const main = document.createElement("button");
  main.textContent = "Download This Video";
  main.type = "button";
  main.style.cssText =
    "background:#2563EB;color:#fff;border:none;border-radius:6px;padding:8px 16px;cursor:pointer;font-size:14px;font-weight:500;box-shadow:0 2px 5px rgba(0,0,0,.2);height:36px;line-height:1;display:flex;align-items:center;justify-content:center;font-family:'YouTube Noto',Roboto,Arial,sans-serif;min-width:140px;pointer-events:auto;";

  wrap.appendChild(main);

  const menu = document.createElement("div");
  menu.id = "kdm-btn-menu";
  menu.style.cssText =
    "display:none;position:fixed;background:#1f2937;color:#fff;border-radius:6px;box-shadow:0 4px 20px rgba(0,0,0,.5);min-width:180px;font-size:13px;overflow:visible;opacity:0;transition:opacity .15s;z-index:2147483647;pointer-events:auto;";
  menu.setAttribute("aria-hidden", "true");
  const qualities = [
    ["Best available", "adaptive/best"],
    ["1080p (MP4)", "1080p"],
    ["720p (MP4)", "720p"],
    ["480p (MP4)", "480p"],
    ["360p (MP4)", "360p"],
    ["240p (MP4)", "240p"]
  ];
  qualities.forEach(([label, q]) => {
    const opt = document.createElement("div");
    opt.textContent = label;
    opt.style.cssText = "padding:8px 12px;cursor:pointer";
    opt.onmouseenter = () => (opt.style.background = "#374151");
    opt.onmouseleave = () => (opt.style.background = "transparent");
    opt.onclick = (e) => {
      e.stopPropagation();
      e.preventDefault();
      hideMenu();
      
      var origText = main.textContent;
      main.textContent = "Sending to KDM...";
      main.disabled = true;
      main.style.opacity = "0.8";
      
      var titleElYt = document.querySelector('h1.ytd-watch-metadata, ytd-video-primary-info-renderer h1, #info-contents h1');
      var videoTitle = (titleElYt && titleElYt.textContent && titleElYt.textContent.trim()) || document.title.replace(' - YouTube', '') || "video";
      
      var responded = false;
      var timeoutId = setTimeout(function() {
        if (responded) return;
        responded = true;
        main.textContent = origText;
        main.disabled = false;
        main.style.opacity = "1";
        alert("⚠️ KDM did not respond.\n\n1. Start KDM first: Terminal → cd /Users/hussnainasif/kdm && python3 kdm.py\n2. Wait for the KDM window to open.\n3. Reload this page (Cmd+R) and try Download again.");
      }, 10000);
      
      safeSendMessage(
          { type: "kdm_download_with_info", url: location.href, quality: q, title: videoTitle.substring(0, 100), sourceType: "youtube" },
          function(res) {
            if (responded) return;
            responded = true;
            clearTimeout(timeoutId);
            if (!res || !res.ok) {
              if (res && res.error === "Extension context invalidated") {
                showContextInvalidMessage();
              }
              main.textContent = origText;
              main.disabled = false;
              main.style.opacity = "1";
              if (!(res && res.error === "Extension context invalidated")) {
                var errorMsg = (res && res.error) ? res.error : "KDM server is not running";
                if (errorMsg.indexOf("KDM server") !== -1 || errorMsg.indexOf("timed out") !== -1) {
                  alert("⚠️ KDM Server Not Running\n\nPlease start KDM:\n1. Open Terminal\n2. Run: cd /Users/hussnainasif/kdm && python3 kdm.py\n\nThen try the download again.");
                } else {
                  alert("⚠️ Kalupura Download Manager (KDM) API not reachable.\n\nMake sure KDM server is running.");
                }
              }
              return;
            }
            main.textContent = "✓ Added to KDM!";
            main.style.background = "#059669";
            setTimeout(function () {
              main.textContent = origText;
              main.style.background = "#2563EB";
              main.disabled = false;
              main.style.opacity = "1";
            }, 2500);
          }
      );
    };
    menu.appendChild(opt);
  });
  wrap.appendChild(menu);

  function positionMenu() {
    const r = wrap.getBoundingClientRect();
    menu.style.left = r.left + "px";
    menu.style.top = (r.bottom + 4) + "px";
  }

  function toggleMenu(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
    }
    const show = menu.style.display !== "block";
    if (show) {
      positionMenu();
      document.body.appendChild(menu);
      menu.style.display = "block";
      menu.style.opacity = "1";
      menu.setAttribute("aria-hidden", "false");
    } else {
      menu.style.display = "none";
      menu.style.opacity = "0";
      menu.setAttribute("aria-hidden", "true");
      wrap.appendChild(menu);
    }
  }

  function hideMenu() {
    menu.style.display = "none";
    menu.style.opacity = "0";
    menu.setAttribute("aria-hidden", "true");
    if (menu.parentNode === document.body) {
      wrap.appendChild(menu);
    }
  }

  main.addEventListener("click", toggleMenu, true);
  main.addEventListener("mousedown", (e) => {
    e.stopPropagation();
    e.preventDefault();
  }, true);
  document.addEventListener("click", (e) => {
    if (!wrap.contains(e.target) && !menu.contains(e.target)) hideMenu();
  });

  player.style.position = "relative";
  player.appendChild(wrap);
  console.log("KDM: ✅ YouTube download button injected");
}


// Dailymotion: fixed-position, draggable button (move anywhere, e.g. onto video)
function createDailymotionFixedButton() {
    if (document.getElementById("kdm-dailymotion-fixed")) return;
    const isVideoPage = /\/video\/|\/embed\//.test(window.location.pathname) || !!document.querySelector('video');
    if (!isVideoPage) return;
    const wrap = document.createElement("div");
    wrap.id = "kdm-dailymotion-fixed";
    wrap.style.cssText = "position:fixed;top:80px;right:20px;z-index:2147483646;font-family:sans-serif;pointer-events:auto;cursor:grab;";
    wrap.title = "Drag to move • Click to download";
    const main = document.createElement("button");
    main.type = "button";
    main.textContent = "⬇ Download with KDM";
    main.style.cssText = "background:linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);color:#fff;border:none;border-radius:8px;padding:10px 18px;cursor:pointer;font-size:14px;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,0.3);height:40px;line-height:1;display:flex;align-items:center;justify-content:center;min-width:160px;pointer-events:auto;";
    main.onclick = function(e) {
        e.preventDefault();
        e.stopPropagation();
        var origDm = main.textContent;
        main.textContent = "Sending to KDM...";
        main.disabled = true;
        var title = (document.querySelector('h1[data-testid="video-title"], .dmp_VideoTitle, h1.title, h1') && document.querySelector('h1[data-testid="video-title"], .dmp_VideoTitle, h1.title, h1').textContent) ? document.querySelector('h1[data-testid="video-title"], .dmp_VideoTitle, h1.title, h1').textContent.trim() : (document.title.replace(/\s*\|\s*Dailymotion/i, '').trim() || "video");
        var responded = false;
        var toId = setTimeout(function() {
            if (responded) return;
            responded = true;
            main.textContent = origDm;
            main.disabled = false;
            alert("⚠️ KDM did not respond. Start KDM first: Terminal → cd /Users/hussnainasif/kdm && python3 kdm.py");
        }, 12000);
        safeSendMessage({ type: "kdm_download_with_info", url: location.href, quality: "1080p", title: title.substring(0, 100), sourceType: "dailymotion" }, function(res) {
            if (responded) return;
            responded = true;
            clearTimeout(toId);
            main.disabled = false;
            if (res && res.ok) { main.textContent = "✓ Added to KDM!"; main.style.background = "linear-gradient(135deg, #059669 0%, #047857 100%)"; setTimeout(function() { main.textContent = origDm; main.style.background = "linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)"; }, 2500); }
            else { if (res && res.error === "Extension context invalidated") showContextInvalidMessage(); else alert("⚠️ KDM server not running. Start it: cd /Users/hussnainasif/kdm && python3 kdm.py"); main.textContent = origDm; }
        });
    };
    wrap.appendChild(main);
    document.body.appendChild(wrap);

    (function makeDraggable(el) {
        let startX, startY, startLeft, startTop, moved;
        el.addEventListener("mousedown", function(e) {
            if (e.button !== 0) return;
            startX = e.clientX;
            startY = e.clientY;
            moved = false;
            el.setAttribute("data-kdm-dragged", "0");
            const r = el.getBoundingClientRect();
            startLeft = r.left;
            startTop = r.top;
            el.style.cursor = "grabbing";
            function move(e) {
                const dx = e.clientX - startX;
                const dy = e.clientY - startY;
                if (Math.abs(dx) > 4 || Math.abs(dy) > 4) moved = true;
                el.setAttribute("data-kdm-dragged", moved ? "1" : "0");
                el.style.left = (startLeft + dx) + "px";
                el.style.top = (startTop + dy) + "px";
                el.style.right = "auto";
            }
            function up() {
                el.style.cursor = "grab";
                document.removeEventListener("mousemove", move);
                document.removeEventListener("mouseup", up);
            }
            document.addEventListener("mousemove", move);
            document.addEventListener("mouseup", up);
        });
    })(wrap);
    main.addEventListener("click", function(e) {
        if (wrap.getAttribute("data-kdm-dragged") === "1") {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            wrap.setAttribute("data-kdm-dragged", "0");
        }
    }, true);

    console.log("KDM: ✅ Dailymotion download button added (drag to move)");
}

// Dailymotion injection (on-video button + fixed fallback)
function injectDailymotion() {
    if (document.getElementById("kdm-dailymotion-btn")) {
        console.log("KDM: Dailymotion button already exists");
        return;
    }
    
    console.log("KDM: Attempting to inject Dailymotion button");
    
    const video = document.querySelector('video');
    
    const tryInject = () => {
        if (document.getElementById("kdm-dailymotion-btn")) return;
        if (!video) {
            createDailymotionFixedButton();
            return;
        }
        const videoRect = video.getBoundingClientRect();
        if (videoRect.width < 50 || videoRect.height < 50) {
            createDailymotionFixedButton();
            return;
        }
        
        let container = video.parentElement;
        let bestContainer = container;
        let depth = 0;
        let bestArea = Infinity;
        
        while (container && depth < 8) {
            const containerRect = container.getBoundingClientRect();
            const area = containerRect.width * containerRect.height;
            
            if (containerRect.width >= videoRect.width * 0.98 &&
                containerRect.height >= videoRect.height * 0.98 &&
                containerRect.width <= videoRect.width * 1.2) {
                if (area < bestArea) {
                    bestContainer = container;
                    bestArea = area;
                }
            }
            container = container.parentElement;
            depth++;
        }
        
        container = bestContainer || video.parentElement;
        const containerPosition = window.getComputedStyle(container).position;
        if (containerPosition === 'static' || !containerPosition || containerPosition === '') {
            container.style.position = 'relative';
        }
        
        const wrap = document.createElement("div");
        wrap.id = "kdm-dailymotion-btn";
        wrap.style.cssText = "position:absolute;top:10px;right:30px;z-index:999999;font-family:sans-serif;pointer-events:auto;";
        
        const main = document.createElement("button");
        main.type = "button";
        main.textContent = "⬇ Download This Video";
        main.style.cssText = "background:linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);color:#fff;border:none;border-radius:8px;padding:10px 18px;cursor:pointer;font-size:14px;font-weight:600;box-shadow:0 4px 12px rgba(37,99,235,0.4);height:40px;line-height:1;display:flex;align-items:center;justify-content:center;font-family:'Segoe UI',Roboto,Arial,sans-serif;min-width:160px;transition:all 0.2s ease;text-transform:uppercase;letter-spacing:0.5px;pointer-events:auto;";
        
        main.addEventListener("mouseenter", function() {
            this.style.background = "linear-gradient(135deg, #1D4ED8 0%, #1E40AF 100%)";
            this.style.transform = "translateY(-2px)";
            this.style.boxShadow = "0 6px 16px rgba(37,99,235,0.5)";
        });
        
        main.addEventListener("mouseleave", function() {
            this.style.background = "linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)";
            this.style.transform = "translateY(0)";
            this.style.boxShadow = "0 4px 12px rgba(37,99,235,0.4)";
        });
        
        wrap.appendChild(main);
        
        const menu = document.createElement("div");
        menu.id = "kdm-dailymotion-menu";
        menu.style.cssText = "display:none;position:fixed;background:linear-gradient(180deg, #1f2937 0%, #111827 100%);color:#fff;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,0.5);min-width:200px;font-size:13px;overflow:visible;opacity:0;transition:all 0.2s ease;border:1px solid rgba(255,255,255,0.1);z-index:2147483647;pointer-events:auto;";
        
        const qualities = [
            ["⭐ Best available", "adaptive/best"],
            ["🎬 1080p (MP4)", "1080p"],
            ["🎥 720p (MP4)", "720p"],
            ["📺 480p (MP4)", "480p"],
            ["📱 360p (MP4)", "360p"],
            ["💾 240p (MP4)", "240p"]
        ];
        
        qualities.forEach(([label, q]) => {
            const opt = document.createElement("div");
            opt.textContent = label;
            opt.style.cssText = "padding:12px 16px;cursor:pointer;transition:all 0.15s ease;border-bottom:1px solid rgba(255,255,255,0.05);display:flex;align-items:center;";
            opt.onmouseenter = function() {
                this.style.background = "linear-gradient(90deg, #374151 0%, #4B5563 100%)";
                this.style.paddingLeft = "20px";
            };
            opt.onmouseleave = function() {
                this.style.background = "transparent";
                this.style.paddingLeft = "16px";
            };
            opt.onclick = (e) => {
                e.stopPropagation();
                e.preventDefault();
                hideMenu();
                
                var origText = main.textContent;
                main.textContent = "Sending to KDM...";
                main.disabled = true;
                main.style.opacity = "0.8";
                
                var titleSelectors = ['h1[data-testid="video-title"]', 'h1.dmp_VideoTitle', '.dmp_VideoTitle', 'h1.title', '.video-title', 'h1', '.dm-title', '[data-testid="title"]'];
                var videoTitle = "video";
                for (var si = 0; si < titleSelectors.length; si++) {
                    var titleEl = document.querySelector(titleSelectors[si]);
                    if (titleEl && titleEl.textContent.trim()) { videoTitle = titleEl.textContent.trim(); break; }
                }
                if (videoTitle === "video") {
                    videoTitle = document.title.replace(' | Dailymotion', '').replace(' - Dailymotion', '').trim() || "video";
                }
                
                var responded = false;
                var dmTimeoutId = setTimeout(function() {
                    if (responded) return;
                    responded = true;
                    main.textContent = origText;
                    main.disabled = false;
                    main.style.opacity = "1";
                    alert("⚠️ KDM did not respond. Start KDM first: Terminal → cd /Users/hussnainasif/kdm && python3 kdm.py");
                }, 12000);
                
                safeSendMessage(
                    { type: "kdm_download_with_info", url: location.href, quality: q, title: videoTitle.substring(0, 100), sourceType: "dailymotion" },
                    function(res) {
                        if (responded) return;
                        responded = true;
                        clearTimeout(dmTimeoutId);
                        if (!res || !res.ok) {
                            main.textContent = origText;
                            main.disabled = false;
                            main.style.opacity = "1";
                            if (res && res.error === "Extension context invalidated") showContextInvalidMessage();
                            else alert("⚠️ KDM server not running. Start it: cd /Users/hussnainasif/kdm && python3 kdm.py");
                            return;
                        }
                        main.textContent = "✓ Added to KDM!";
                        main.style.background = "linear-gradient(135deg, #059669 0%, #047857 100%)";
                        setTimeout(function() {
                            main.textContent = origText;
                            main.style.background = "linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)";
                            main.disabled = false;
                            main.style.opacity = "1";
                        }, 2500);
                    }
                );
            };
            menu.appendChild(opt);
        });
        
        wrap.appendChild(menu);
        
        function positionMenu() {
            const r = wrap.getBoundingClientRect();
            menu.style.left = r.left + "px";
            menu.style.top = (r.bottom + 4) + "px";
        }
        
        function toggleMenu(e) {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
            }
            const show = menu.style.display !== "block";
            if (show) {
                positionMenu();
                document.body.appendChild(menu);
                menu.style.display = "block";
                menu.style.opacity = "1";
            } else {
                menu.style.display = "none";
                menu.style.opacity = "0";
                if (menu.parentNode === document.body) wrap.appendChild(menu);
            }
        }
        
        function hideMenu() {
            menu.style.display = "none";
            menu.style.opacity = "0";
            if (menu.parentNode === document.body) wrap.appendChild(menu);
        }
        
        main.addEventListener("click", toggleMenu, true);
        main.addEventListener("mousedown", (e) => { e.stopPropagation(); e.preventDefault(); }, true);
        document.addEventListener("click", (e) => {
            if (!wrap.contains(e.target) && !menu.contains(e.target)) hideMenu();
        });
        
        container.appendChild(wrap);
        console.log("KDM: ✅ Dailymotion download button injected on video");
    };
    
    tryInject();
    setTimeout(tryInject, 300);
    setTimeout(tryInject, 800);
    setTimeout(tryInject, 2000);
    setTimeout(() => {
        if (!document.getElementById("kdm-dailymotion-btn") && !document.getElementById("kdm-dailymotion-fixed")) {
            createDailymotionFixedButton();
        }
    }, 3500);
    
    if (video) {
        if (video.readyState >= 1) setTimeout(tryInject, 100);
        video.addEventListener('loadedmetadata', tryInject, { once: true });
        video.addEventListener('loadeddata', tryInject, { once: true });
        video.addEventListener('play', tryInject, { once: true });
        video.addEventListener('canplay', tryInject, { once: true });
        const observer = new MutationObserver(() => {
            if (!document.getElementById("kdm-dailymotion-btn")) tryInject();
        });
        observer.observe(video, { attributes: true, childList: false });
    } else {
        createDailymotionFixedButton();
    }
}

// Torrent sites (Nyaa, Pirate Bay, YTS, Torrent Galaxy, 1337x): intercept .torrent/magnet link clicks → send to KDM
function isTorrentLink(href) {
    if (!href || typeof href !== 'string') return false;
    var h = href.trim().toLowerCase();
    return h.indexOf('.torrent') !== -1 || h.indexOf('magnet:') === 0;
}
function injectTorrentSiteHandler() {
    if (document.documentElement.getAttribute('data-kdm-torrent-handler')) return;
    document.documentElement.setAttribute('data-kdm-torrent-handler', '1');
    document.addEventListener('click', function(e) {
        var a = e.target && (e.target.closest ? e.target.closest('a') : (function(n){ while(n){ if(n.tagName==='A') return n; n=n.parentElement; } return null; })(e.target));
        if (!a || !a.href) return;
        if (!isTorrentLink(a.href)) return;
        e.preventDefault();
        e.stopPropagation();
        var url = a.href;
        var title = (a.textContent && a.textContent.trim()) ? a.textContent.trim().substring(0, 120) : (a.download || 'torrent');
        if (title === 'torfile.bin' || /\.torrent$/i.test(title)) title = title;
        var referer = window.location.origin + '/';
        safeSendMessage({
            type: 'kdm_download_with_info',
            url: url,
            title: title,
            quality: 'best',
            sourceType: 'torrent',
            referer: referer
        }, function(res) {
            if (res && res.ok) {
                try {
                    var notif = document.createElement('div');
                    notif.textContent = 'Sent to KDM';
                    notif.style.cssText = 'position:fixed;top:16px;right:16px;z-index:2147483647;background:#059669;color:#fff;padding:10px 16px;border-radius:8px;font-family:sans-serif;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,0.3);';
                    document.body.appendChild(notif);
                    setTimeout(function() { try { notif.remove(); } catch(e){} }, 2500);
                } catch (e) {}
            } else if (res && res.error && res.error.indexOf('not running') !== -1) {
                alert('KDM is not running. Start it first: Terminal → python3 kdm.py');
            }
        });
        return false;
    }, true);
    console.log('KDM: Torrent site – click any .torrent/magnet link to send to KDM');
}


function injectAll() {
    var hostname = window.location.hostname || '';
    try {
        if (hostname.indexOf('youtube.com') !== -1 || hostname.indexOf('youtu.be') !== -1) {
            injectKDM();
        } else if (hostname.indexOf('dailymotion.com') !== -1) {
            injectDailymotion();
        } else if (/nyaa\.si|thepiratebay|piratebay|yts\.|yts-official|torrentgalaxy|1337x\.to/i.test(hostname)) {
            injectTorrentSiteHandler();
        }
    } catch (e) { /* swallow so retries can run */ }
}

// Start injection
function startInjection() {
    try {
        injectAll();
    } catch (e) { /* prevent one site from breaking others */ }
    setTimeout(function() { try { injectAll(); } catch (e) {} }, 1500);
    setTimeout(function() { try { injectAll(); } catch (e) {} }, 4000);
}

// YouTube navigation
if (window.location.hostname.indexOf('youtube.com') !== -1 || window.location.hostname.indexOf('youtu.be') !== -1) {
    window.addEventListener("yt-navigate-finish", function() { setTimeout(injectAll, 1000); });
}

// Dailymotion monitoring
if (window.location.hostname.indexOf('dailymotion.com') !== -1) {
    function startDailymotionObserver() {
        if (!document.body) { setTimeout(startDailymotionObserver, 100); return; }
        try {
            var obs = new MutationObserver(function() {
                if (!document.getElementById("kdm-dailymotion-btn")) setTimeout(injectDailymotion, 500);
            });
            obs.observe(document.body, { childList: true, subtree: true });
        } catch (e) {}
    }
    startDailymotionObserver();
}

// Start
function runStart() {
    try { startInjection(); } catch (e) {}
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', runStart);
} else {
    runStart();
}
window.addEventListener('load', function() { try { startInjection(); } catch (e) {} });