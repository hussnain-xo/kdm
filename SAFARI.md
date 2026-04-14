# KDM Extension – Safari mein add karna

## Option 1: Bina extension (simple)
1. KDM start karo (`python3 kdm.py` ya `./start_kdm.sh`).
2. Safari se download link copy karo.
3. KDM mein **Add URL** par click karo, URL paste karo, Start Download.

---

## Option 2: Safari Web Extension (Chrome jaisa “Download with KDM”)

Safari Web Extension banane ke liye Apple ka converter use hota hai. Steps:

### 1. Extension folder ready karo
Chrome extension wale files same folder mein hon: `manifest.json`, `background.js`, `content.js`, etc. (jo abhi `kdm` project folder mein hain.)

### 2. Safari Web Extension Converter chalao
Terminal mein KDM project folder mein jao, phir:

```bash
cd /Users/hussnainasif/kdm
xcrun safari-web-extension-converter .
```

Ye command ek **Xcode project** bana degi (`.xcodeproj`) isi folder ke andar.  
**Zaroori:** Xcode 12+ install hona chahiye (Mac App Store se Xcode).

### 3. Xcode se build karo
1. Double‑click se naya bana **`.xcodeproj`** open karo (Xcode khul jayega).
2. Menu: **Product → Build** (ya `Cmd + B`).
3. Build successful hone tak errors fix karo (agar koi aaye).

### 4. Safari mein extension enable karo
1. **Safari** kholo.
2. Menu: **Safari → Settings** (ya **Preferences** purane macOS pe).
3. **Extensions** tab pe jao.
4. List mein **KDM** (ya jo name converter ne diya) dikhega – usko **enable** karo.
5. Pehli bar enable karoge to Safari permission maangega – **Turn On** / **Allow** kar do.

Ab Safari mein bhi “Download with KDM” / context menu se download KDM ko bhej sakte ho (jab KDM app chal rahi ho aur backend same port pe ho).

---

## Agar converter error de
- **“xcrun: error”** – Xcode install karo ya `xcode-select -s` se path sahi karo.
- **“No such file”** – Terminal ka current directory wahi hona chahiye jahan `manifest.json` hai (`cd /Users/hussnainasif/kdm`).

## Note
Safari extension ka code Chrome wala hi hai; converter use karke Safari‑compatible wrapper banta hai. KDM backend (Python) dono browsers ke liye same rehta hai.
