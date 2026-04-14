# Safari extension – manually update (copy-paste)

Xcode mein **Shared (Extension) → Resources** kholo. Neeche diye **3 steps** follow karo.

---

## Step 1: manifest

- Xcode Resources mein **manifest** ya **manifest.json** kholo.
- Saara purana content **delete** karo.
- Ye folder kholo: **kdm/SAFARI_COPY_PASTE/**  
  → **manifest.json** kholo, **Cmd+A** (select all), **Cmd+C** (copy).
- Xcode wali manifest file mein **Cmd+V** (paste) karo. **Cmd+S** se save.

---

## Step 2: background.js

- Xcode Resources mein **background.js** kholo.
- Purana saara **delete** karo.
- **kdm/SAFARI_COPY_PASTE/background.js** kholo → **Cmd+A** → **Cmd+C**.
- Xcode wali **background.js** mein **Cmd+V** → **Cmd+S**.

---

## Step 3: content.js

- Xcode Resources mein **content.js** kholo.
- Purana saara **delete** karo.
- **kdm/SAFARI_COPY_PASTE/content.js** kholo → **Cmd+A** → **Cmd+C**.
- Xcode wali **content.js** mein **Cmd+V** → **Cmd+S**.

---

## Step 4 (optional): watchfilmy-capture.js

- Agar Xcode Resources mein **watchfilmy-capture.js** hai to usko bhi replace karo.
- **kdm/SAFARI_COPY_PASTE/watchfilmy-capture.js** se copy karke paste karo.

---

## Path (Finder mein)

Copy-paste wali files yahan hain:

```
/Users/hussnainasif/kdm/SAFARI_COPY_PASTE/
├── manifest.json
├── background.js
├── content.js
└── watchfilmy-capture.js
```

Inhi 4 files ko Xcode ke **Shared (Extension) → Resources** wale folder ki same-name files mein paste karo (purana content replace).

---

## Uske baad

- Xcode: **Cmd+B** (Build), phir **Cmd+R** (Run).
- Safari → Settings → Extensions → **KDM** enable.
- Download try karne se pehle **Terminal** se KDM chalao: `cd /Users/hussnainasif/kdm && python3 kdm.py`
