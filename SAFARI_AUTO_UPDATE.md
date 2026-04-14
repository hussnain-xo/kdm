# Safari extension ko auto-update kaise karein (copy-paste na karna pare)

## Option 1: Xcode ko main folder se files refer karo (sabse acha)

Jab bhi hum `content.js` ya `background.js` update karte hain, Safari extension bhi wahi files use kare — iske liye Xcode mein **file reference** use karo (copy mat karo).

### Steps (sirf ek baar):

1. **Xcode** mein apna KDM extension project kholo (e.g. `kdm.xcodeproj`).
2. Left sidebar se **Shared (Extension)** → **Resources** expand karo.
3. Resources ke andar jo **content.js**, **background.js**, **manifest** (ya manifest.json) hain, unhe **select karke Delete** karo (Move to Trash ya Remove Reference — project se hatao, file delete optional).
4. Ab main kdm folder ki files **reference** se add karo:
   - Menu: **File** → **Add Files to "kdm"...**
   - Navigate karo: **/Users/hussnainasif/kdm** (jahan `kdm.py` hai).
   - **content.js**, **background.js**, **manifest.json**, **watchfilmy-capture.js** select karo (Cmd+click se multiple).
   - Neeche **"Copy items if needed"** ko **uncheck** karo (taake copy na ho, sirf reference add ho).
   - **"Create groups"** select rakho. **Add** dabao.
   - Agar Xcode puche "Add to targets?" to **Extension target** (e.g. "kdm Extension") ko check karo.
5. **manifest.json:** Agar Xcode project mein file ka naam sirf **manifest** hai (bina .json), to pehle wahi purani file delete karo, phir **manifest.json** add karo (same tarah, reference, copy unchecked).

Iske baad jab bhi hum yahan `content.js` / `background.js` edit karenge, Xcode wala build **automatically** wahi updated files use karega — aapko kuch copy-paste nahi karna hoga.

---

## Option 2: Sync script chalana

Agar Option 1 nahi karna chahte to ek script se files copy ho sakti hain:

```bash
cd /Users/hussnainasif/kdm
chmod +x sync_safari_extension.sh
./sync_safari_extension.sh
```

Ye **SafariExtensionFiles** folder ko hamesha latest `content.js`, `background.js`, `manifest.json`, `watchfilmy-capture.js` se update kar dega.

Agar aap apna Xcode project path dein to script wahan bhi copy kar sakti hai (ek hi command se):

```bash
./sync_safari_extension.sh "/Users/hussnainasif/Downloads/kdm/Shared (Extension)/Resources"
```

Path wahi use karo jahan Xcode project ke andar **Shared (Extension) → Resources** wala folder hai.

---

## Short

- **Best:** Option 1 — Xcode mein main kdm folder ki files **reference** se add karo (Copy items **uncheck**). Phir koi bhi update yahan se auto reflect.
- **Alternative:** Option 2 — `./sync_safari_extension.sh` (aur agar chaho to script ke saath Resources path) chala kar files sync karo.
