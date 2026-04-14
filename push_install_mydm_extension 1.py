#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kalupura Download Manager (KDM)
Extension install helper — formerly MyDM
"""

import webbrowser
import time
import platform

print("Opening Extensions page for Kalupura Download Manager (KDM)...")
time.sleep(1)

# Open both Edge and Chrome extensions pages
if platform.system() == "Windows":
    webbrowser.open("edge://extensions")
    webbrowser.open("chrome://extensions")

print("""
=========================================================
 Kalupura Download Manager (KDM) — Extension Installation
=========================================================
 1) Enable Developer Mode in the Extensions page.
 2) Click "Load unpacked".
 3) Select the folder containing 'manifest.json'.
 4) Keep KDM running (you should see:
        Ready — API: http://127.0.0.1:9669 )
=========================================================
""")
