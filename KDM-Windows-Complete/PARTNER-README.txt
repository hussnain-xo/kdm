KDM — Windows partner checklist (read this on a Windows 64-bit PC)
===================================================================

What this package is
--------------------
Full **source and build files** to run Kalupura Download Manager (KDM) on Windows
and to produce a portable `KDM.exe` folder, optional Inno EXE, optional WiX MSI.
This is not a pre-built KDM.exe unless you run the build steps below.

Quick run from source (developer test)
--------------------------------------
1) Install **Python 3.10+** (64-bit) for Windows, and **Git** (optional).
2) Unzip this archive so the folder `KDM-Windows-Complete` (or the inner folder) sits where you like.
3) Open **cmd** or **PowerShell** in that **project root** (folder containing `kdm.py`).
4) `python -m venv .venv`  then  `.venv\Scripts\activate`
5) `pip install -r requirements-app.txt`
6) `python kdm.py`  
   If the GUI starts, the environment is OK. (Chromium/Playwright may need
   `playwright install chromium` per your policy.)

Build Windows EXE (PyInstaller)
---------------------------------
1) `pip install -r requirements-build.txt`
2) `pyinstaller packaging\kdm.spec`  
3) Output: `dist\KDM\KDM.exe` and supporting files. Zip the whole `dist\KDM` folder to ship “portable”.

Optional: Inno Setup EXE
-------------------------
Install **Inno Setup 6** (ISCC), then from repo root:
`powershell -ExecutionPolicy Bypass -File scripts\build_windows_installer.ps1`
(Prerequisite: `dist\KDM\KDM.exe` from PyInstaller step.)

Optional: WiX MSI
-------------------
See `packaging\wix\` and `scripts\build_windows_msi.ps1` (WiX 3+ required).

Files worth knowing
-------------------
- `kdm.py`          Main application
- `kdm\`            Python package (licensing, download helpers)
- `packaging\kdm.spec`  PyInstaller definition
- `packaging\windows\`  Inno script
- `packaging\wix\`      MSI
- `extension-for-users\KDM-Browser-Extension\`  Bundled with the frozen app

Support
-------
This drop is a **code snapshot** for review/build, not a store-signed installer.
