# Safari Extension – Ab kya karna hai (step by step)

## Step 1: Xcode mein manifest fix karo

Jo **manifest** file Xcode mein open hai (Shared (Extension) > Resources > **manifest**), usme ye changes karo:

### 1.1 `content_scripts` ke andar `matches` badlo

**Pehle (galat):**
```json
"matches": [ "*://example.com/*" ]
```

**KDM ke liye (sahi):**  
Har content_scripts entry ke andar `matches` ko is tarah set karo. Agar ek hi content_scripts entry hai to use ye replace karo:

```json
"content_scripts": [
  {
    "js": [ "content.js" ],
    "matches": [
      "https://www.youtube.com/*",
      "https://m.youtube.com/*",
      "https://*.youtube.com/*",
      "https://youtu.be/*",
      "https://www.dailymotion.com/*",
      "https://*.dailymotion.com/*",
      "http://www.dailymotion.com/*",
      "http://*.dailymotion.com/*",
      "https://www.watchfilmy.to/*",
      "https://*.watchfilmy.to/*",
      "https://*.watchfilmy.lat/*",
      "http://*.watchfilmy.to/*",
      "http://*.watchfilmy.lat/*",
      "https://*/*",
      "http://*/*"
    ],
    "run_at": "document_end"
  }
]
```

(Last wale `"https://*/*"` aur `"http://*/*"` se context menu / “Download with KDM” har site pe kaam karega.)

### 1.2 `permissions` add karo

**Pehle (galat):**
```json
"permissions": []
```

**KDM ke liye (sahi):**
```json
"permissions": [
  "activeTab",
  "scripting",
  "downloads",
  "storage",
  "notifications",
  "contextMenus"
],
"host_permissions": [
  "http://127.0.0.1:9669/*",
  "http://localhost:9669/*",
  "https://*/*",
  "http://*/*"
]
```

Manifest v3 mein `host_permissions` alag array hota hai; agar tumhare manifest mein nahi hai to `permissions` ke baad ye block add kar dena.

Save karo: **Cmd + S**.

---

## Step 2: Extension build karo

1. Xcode ke top-left mein **scheme** select karo: **macOS (App)** ya **kdm (macOS)**.
2. Menu: **Product → Build** (ya **Cmd + B**).
3. Build successful hone tak koi error fix karo.

---

## Step 3: Safari mein extension chalana / enable karna

1. Xcode se app **run** karo: **Product → Run** (ya **Cmd + R**).  
   Ye ek chhoti “helper” app start karegi jo Safari ko batati hai ke extension available hai.
2. **Safari** kholo.
3. **Safari → Settings** (ya Preferences) → **Extensions** tab.
4. List mein **kdm** (ya jo name dikhe) enable karo.  
   Agar nahi dikh raha to pehle Xcode se **Run** kiya hua ho (Step 3.1).
5. Permission mangne par **Turn On** / **Allow** kar do.

Ab KDM backend (Python app) start karo. Safari mein kisi bhi page pe right-click karke “Download with KDM” ya extension icon se download bhej sakte ho.

---

## Short summary

| Step | Kya karna hai |
|------|----------------|
| 1    | Xcode mein manifest ki `matches` aur `permissions` / `host_permissions` fix karo (upar diye gaye hisse copy karo). |
| 2    | **Product → Build** se build karo. |
| 3    | **Product → Run** se extension wali app chalao, phir Safari → Settings → Extensions mein jaa kar extension **enable** karo. |

“Browse Extensions” wala button App Store ke liye hai; apna Xcode wala extension **Run** se hi Safari ke Extensions list mein aayega.
