@echo off
setlocal
cd /d "%~dp0.."

python -m pip install -r requirements-build.txt
python -m PyInstaller packaging\kdm.spec --noconfirm

echo.
echo Output: dist\KDM\KDM.exe  (folder dist\KDM — zip this folder for users)
echo After install, users may run: playwright install chromium
pause