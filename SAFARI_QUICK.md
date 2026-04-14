# Safari extension – code auto-update (bina pehle wale steps)

Pehle wale Xcode “reference” wale steps ki zaroorat nahi. Sirf ye karo:

---

## 1. Sirf ek baar – Safari project ka path set karo

Terminal kholo, kdm folder mein jao, aur ye command chalao (apna **sahi** path likho):

```bash
cd /Users/hussnainasif/kdm
./sync_safari_extension.sh "/Users/hussnainasif/Downloads/kdm/Shared (Extension)/Resources"
```

- Agar tumhara **kdm** Xcode project **Downloads** mein nahi, to `"/Users/hussnainasif/Downloads/kdm/..."` ki jagah woh path do jahan **Shared (Extension) → Resources** wala folder hai.
- Is se path save ho jayega. Ab har baar jab bhi code update ho, sirf step 2 karna hai.

---

## 2. Jab bhi code update ho (auto-update ke liye)

Jab bhi hum yahan `content.js` / `background.js` / `manifest.json` change karein, tum ye chalao:

```bash
cd /Users/hussnainasif/kdm
./sync_safari_extension.sh
```

- Ye script latest files **SafariExtensionFiles** aur tumhare saved Safari Xcode **Resources** dono jagah copy kar degi.
- Phir **Xcode** kholo → **Cmd+B** (build) → **Cmd+R** (run).
- **Safari** mein extension enable karke use karo.

Isse code automatically Safari extension mein update ho jayega; pehle wale “reference” wale steps follow karne ki zaroorat nahi.
