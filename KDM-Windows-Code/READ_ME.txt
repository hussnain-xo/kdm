KDM — Windows develop bundle (yahan se Windows build / EXE / MSI)
================================================================
Ye folder aapke repo se sirf WSL / Windows / CI wali cheezain utha kar banaya gaya hai
(macOS: packaging/mac_*, Linux: packaging/linux/ — woh is zip mein NAHI hain).

Kya andar hai
-------------
packaging/kdm.spec         PyInstaller: KDM.exe bundle banane ke liye (source repo root se kdm.py, etc. manta hai)
packaging/windows/         Inno Setup 6: KDM-Setup-*-x64.exe
packaging/wix/             WiX: MSI (Welcome / EULA / install dir)
packaging/BUILD.txt        Build notes (sab OS; Windows bhi)
packaging/USER_QUICK_START.txt
packaging/INSTALL.template.txt
packaging/VERSION
requirements-build.txt     PyInstaller / build pip deps (build scripts yeh repo root se expect)
scripts/build_windows.ps1, .bat, build_windows_installer.ps1, build_windows_msi.ps1
.github/workflows/         GitHub Actions: Windows job (artifact EXE/zip) ke sath

Application source (GUI + backend) is bundle mein NAHI
-------------------------------------------------------
Poora chalne wala code repo root pe:
  kdm.py, kdm/, extensions, translations.json, requirements-app.txt, ...
Windows bundle sirf *build + installer* scripts hain. Build se pehle woh source wahi
repo root se copy/clone karke rakhna.

Typical on Windows (repo root)
--------------------------------
  scripts\build_windows_installer.ps1
  (pehle PyInstaller se dist\KDM\KDM.exe, phir ISCC for Inno, optional MSI script)

Yeh path (absolute aapke machine par):
  (repo)/KDM-Windows-Code/

Pura zip: KDM-Windows-Code.zip (repo root, agar bana chuka ho)
