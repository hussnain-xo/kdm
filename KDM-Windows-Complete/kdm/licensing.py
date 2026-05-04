"""
KDM trial (30 days) + offline license keys (HMAC).

Change LICENSE_HMAC_SECRET and optionally set env KDM_LICENSE_SECRET for releases.
Generate keys: python3 scripts/gen_license.py you@email.com perpetual
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

TRIAL_DAYS = 30

# Override in production; must match scripts/gen_license.py
LICENSE_HMAC_SECRET = os.environ.get(
    "KDM_LICENSE_SECRET",
    "kdm-dev-only-change-before-selling-32chars!",
).encode("utf-8")


def _data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        return base / "KalupuraDM"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "KalupuraDM"
    return Path.home() / ".local" / "share" / "KalupuraDM"


def _state_path() -> Path:
    d = _data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "license_state.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_payload(data: bytes) -> Tuple[bool, str]:
    """Returns (ok, reason)."""
    try:
        s = data.decode("utf-8").strip()
    except Exception:
        return False, "invalid encoding"
    parts = s.split("|", 1)
    if len(parts) != 2:
        return False, "bad format"
    _email, exp = parts[0].strip(), parts[1].strip().lower()
    if exp == "perpetual":
        return True, ""
    try:
        # YYYY-MM-DD
        exp_dt = datetime.strptime(exp, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if _utc_now().date() > exp_dt.date():
            return False, "license expired"
    except ValueError:
        return False, "bad expiry"
    return True, ""


def verify_license_key(key: str) -> Tuple[bool, str]:
    key = (key or "").strip().replace(" ", "")
    if not key or "--" not in key:
        return False, "invalid key shape"
    try:
        data_b64, sig = key.rsplit("--", 1)
        pad = (4 - len(data_b64) % 4) % 4
        data = base64.urlsafe_b64decode(data_b64 + ("=" * pad))
    except Exception:
        return False, "could not decode key"
    expected = hmac.new(LICENSE_HMAC_SECRET, data, hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(expected, sig.lower()):
        return False, "key not valid"
    ok, reason = _parse_payload(data)
    if not ok:
        return False, reason or "invalid"
    return True, ""


class LicenseGate:
    def __init__(self) -> None:
        self._state: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        p = _state_path()
        if not p.is_file():
            self._state = {}
            return
        try:
            self._state = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            self._state = {}

    def reload(self) -> None:
        """Re-read license state from disk (e.g. after midnight or external activation)."""
        self._load()

    def _save(self) -> None:
        p = _state_path()
        p.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def _ensure_trial_started(self) -> None:
        if self._state.get("trial_started_at"):
            return
        self._state["trial_started_at"] = _utc_now().isoformat()
        self._save()

    def trial_started_at(self) -> Optional[datetime]:
        raw = self._state.get("trial_started_at")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None

    def saved_license_key(self) -> str:
        return str(self._state.get("license_key") or "").strip()

    def has_valid_saved_license(self) -> bool:
        k = self.saved_license_key()
        if not k:
            return False
        ok, _ = verify_license_key(k)
        return ok

    def apply_license_key(self, key: str) -> Tuple[bool, str]:
        ok, err = verify_license_key(key)
        if not ok:
            return False, err
        self._state["license_key"] = key.strip()
        self._save()
        return True, ""

    def trial_days_remaining(self) -> Optional[int]:
        """None if no trial clock or licensed."""
        if self.has_valid_saved_license():
            return None
        self._ensure_trial_started()
        start = self.trial_started_at()
        if not start:
            return None
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        elapsed = (_utc_now() - start).days
        left = TRIAL_DAYS - elapsed
        return max(0, left)

    def is_trial_expired(self) -> bool:
        if self.has_valid_saved_license():
            return False
        self._ensure_trial_started()
        left = self.trial_days_remaining()
        return left is not None and left <= 0

    def is_allowed(self) -> bool:
        if self.has_valid_saved_license():
            return True
        self._ensure_trial_started()
        left = self.trial_days_remaining()
        return left is not None and left > 0

    def status_line(self) -> str:
        if self.has_valid_saved_license():
            return "Licensed"
        left = self.trial_days_remaining()
        if left is None:
            return ""
        if left <= 0:
            return "Trial expired — license required"
        return f"Free trial: {left} day(s) left"


def show_license_blocking_dialog(app, gate: LicenseGate, purchase_url: str) -> bool:
    """
    IDM-style gate: trial over → prominent Buy Now (opens website), then key + Activate.
    Blocks until user activates or quits. Returns True if app should continue.
    """
    from PyQt6.QtCore import Qt, QUrl
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import (
        QDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
    )

    while not gate.is_allowed():
        dlg = QDialog()
        dlg.setWindowTitle("Kalupura Download Manager — Trial ended")
        dlg.setMinimumWidth(480)
        dlg.setStyleSheet("""
            QDialog { background:#111; color:white; font-family:'Segoe UI'; }
            QLabel { color:#ddd; }
            QLineEdit { background:#1a1a1a; color:#eee; border:1px solid #444; padding:8px; border-radius:4px; }
            QPushButton { background:#1a1a1a; color:white; border:1px solid #444; padding:8px 16px; border-radius:4px; }
            QPushButton:hover { background:#003366; border:1px solid #4da6ff; }
        """)
        v = QVBoxLayout(dlg)
        v.setSpacing(12)
        intro = QLabel(
            "<p style='font-size:11pt;'><b>Your 30-day free trial is over.</b></p>"
            "<p>Thank you for trying KDM. To continue, purchase a license on our website — "
            "you will sign in or enter your <b>email</b>, pay, and receive your "
            "<b>license key</b> (for example by email).</p>"
            "<p>Click <b>Buy Now</b> to open the purchase page in your browser, then paste your key below.</p>"
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(intro)

        buy = (purchase_url or "").strip()
        b_buy_now = QPushButton("Buy Now — open website")
        b_buy_now.setMinimumHeight(46)
        b_buy_now.setCursor(Qt.CursorShape.PointingHandCursor)
        b_buy_now.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3cb371, stop:1 #2e8b57);
                color: white; font-weight: bold; font-size: 11pt;
                border: 1px solid #5acd8c; border-radius: 6px; padding: 10px 20px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4ddb82, stop:1 #3cb371);
                border: 1px solid #7dffc0;
            }
            QPushButton:pressed { background: #256d45; }
            QPushButton:disabled {
                background: #2a2a2a; color: #777; border: 1px solid #444;
            }
        """)

        def do_buy_now():
            if buy:
                QDesktopServices.openUrl(QUrl(buy))

        b_buy_now.clicked.connect(do_buy_now)
        if not buy:
            b_buy_now.setEnabled(False)
            v.addWidget(
                QLabel(
                    "<i>Buy Now will work after your team adds <code>purchase_url</code> "
                    "(or <code>distribution_page</code>) in <b>kdm_config.json</b> next to the app.</i>"
                )
            )
        else:
            hint = QLabel(f"<span style='color:#888; font-size:9pt;'>{buy}</span>")
            hint.setWordWrap(True)
            hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.addWidget(hint)

        v.addWidget(b_buy_now)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setFixedHeight(2)
        v.addWidget(line)

        v.addWidget(QLabel("Already purchased? Paste your license key:"))
        le = QLineEdit()
        le.setPlaceholderText("License key from email / your account")
        v.addWidget(le)

        row = QHBoxLayout()
        b_act = QPushButton("Activate")
        b_quit = QPushButton("Quit")
        row.addWidget(b_act)
        row.addStretch()
        row.addWidget(b_quit)
        v.addLayout(row)

        def do_activate():
            k = le.text().strip()
            if not k:
                QMessageBox.warning(dlg, "License", "Enter your license key.")
                return
            ok, err = gate.apply_license_key(k)
            if ok:
                QMessageBox.information(dlg, "License", "KDM is activated. Thank you!")
                dlg.accept()
            else:
                QMessageBox.warning(dlg, "License", f"Could not activate:\n{err}")

        b_act.clicked.connect(do_activate)
        b_quit.clicked.connect(dlg.reject)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        if gate.is_allowed():
            return True
    return True


def _config_paths_for_purchase_url() -> list:
    paths: list = []
    try:
        if getattr(sys, "frozen", False):
            paths.append(Path(sys.executable).resolve().parent / "kdm_config.json")
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                paths.append(Path(meipass) / "kdm_config.json")
        paths.append(Path.cwd() / "kdm_config.json")
        paths.append(Path(__file__).resolve().parent.parent / "kdm_config.json")
    except Exception:
        paths.append(Path.cwd() / "kdm_config.json")
    return paths


def run_startup_license_check(app) -> bool:
    """Load config purchase URL; if trial expired and no license, block. Returns False to exit."""
    gate = LicenseGate()
    if gate.is_allowed():
        return True

    purchase_url = ""
    try:
        for cfg in _config_paths_for_purchase_url():
            if cfg.is_file():
                data = json.loads(cfg.read_text(encoding="utf-8"))
                purchase_url = (
                    data.get("purchase_url") or data.get("distribution_page") or ""
                ).strip()
                if purchase_url:
                    break
    except Exception:
        pass

    return show_license_blocking_dialog(app, gate, purchase_url)
