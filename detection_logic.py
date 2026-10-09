"""
detection_logic.py — Logique de détection YOLOv8 pour WiqayaAI v1
Corrections :
  - Cooldown par violation (évite les multiples détections)
  - Score HSE supprimé de l'overlay
"""

import time
import json
import os
import cv2
from datetime import datetime

# Mapping classes du modèle PPE
CLASS_NAMES = {
    0: "Hardhat",
    1: "Mask",
    2: "NO-Hardhat",
    3: "NO-Mask",
    4: "NO-Safety Vest",
    5: "Person",
    6: "Safety Cone",
    7: "Safety Vest",
    8: "Machinery",
    9: "Vehicle",
}

PPE_MISSING  = {"NO-Hardhat", "NO-Mask", "NO-Safety Vest"}
PPE_PRESENT  = {"Hardhat", "Mask", "Safety Vest"}

COLORS = {
    "Person":          (200, 200, 200),
    "Hardhat":         (0, 200, 0),
    "Mask":            (0, 200, 0),
    "Safety Vest":     (0, 200, 0),
    "NO-Hardhat":      (0, 0, 255),
    "NO-Mask":         (0, 0, 255),
    "NO-Safety Vest":  (0, 0, 255),
    "Safety Cone":     (0, 165, 255),
    "Machinery":       (255, 165, 0),
    "Vehicle":         (255, 200, 0),
}

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")


def load_settings() -> dict:
    default = {
        "required_ppe":          ["Hardhat", "Safety Vest"],
        "alert_delay_sec":       3,
        "cooldown_sec":          30,   # ← délai minimum entre 2 alertes du même type
        "confidence_threshold":  0.55, # ← seuil relevé pour éviter fausses détections
    }
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH) as f:
            return {**default, **json.load(f)}
    return default


class DetectionEngine:
    """Moteur YOLOv8 avec anti-spam des violations."""

    def __init__(self, model):
        self.model               = model
        self.violation_callbacks = []
        self.frame_violations    = []
        self.is_compliant        = True

        # {label: timestamp} — quand la violation a été détectée pour la 1ère fois
        self._first_seen = {}
        # {label: timestamp} — quand la dernière alerte a été envoyée
        self._last_fired = {}

    def on_violation(self, callback):
        self.violation_callbacks.append(callback)

    def _fire(self, label: str, frame):
        for cb in self.violation_callbacks:
            cb(label, frame)

    def process_frame(self, frame):
        settings    = load_settings()
        conf_thresh = settings.get("confidence_threshold", 0.55)
        delay       = settings.get("alert_delay_sec",      3)
        cooldown    = settings.get("cooldown_sec",         30)

        results    = self.model(frame, conf=conf_thresh, verbose=False)
        violations = []
        detections = []

        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf   = float(box.conf[0])
                label  = CLASS_NAMES.get(cls_id, f"Class{cls_id}")
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append((label, conf, x1, y1, x2, y2))
                if label in PPE_MISSING:
                    violations.append(label)

        annotated             = self._draw_boxes(frame.copy(), detections)
        self.frame_violations = violations
        self.is_compliant     = len(violations) == 0

        now = time.time()

        # ── Logique anti-spam ──────────────────────────────────────────
        current_labels = set(violations)

        for label in current_labels:
            # 1. Première apparition → noter l'heure
            if label not in self._first_seen:
                self._first_seen[label] = now

            # 2. La violation persiste depuis "delay" secondes ?
            persists = (now - self._first_seen[label]) >= delay

            # 3. Cooldown : assez de temps depuis la dernière alerte ?
            last = self._last_fired.get(label, 0)
            cooled = (now - last) >= cooldown

            # 4. Déclencher l'alerte seulement si les deux conditions sont remplies
            if persists and cooled:
                self._fire(label, frame)
                self._last_fired[label] = now

        # Nettoyer les violations qui ont disparu
        for label in list(self._first_seen):
            if label not in current_labels:
                del self._first_seen[label]

        annotated = self._draw_status(annotated)
        return annotated, violations, self.is_compliant

    def _draw_boxes(self, frame, detections):
        for label, conf, x1, y1, x2, y2 in detections:
            color = COLORS.get(label, (128, 128, 128))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            text = f"{label} {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(frame, text, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        return frame

    def _draw_status(self, frame):
        """Overlay minimaliste — statut + heure uniquement, sans score."""
        h, w = frame.shape[:2]

        # Statut CONFORME / VIOLATION
        txt   = "CONFORME" if self.is_compliant else "VIOLATION"
        color = (0, 180, 0) if self.is_compliant else (0, 0, 220)
        cv2.rectangle(frame, (0, 0), (200, 34), (0, 0, 0), -1)
        cv2.putText(frame, txt, (8, 23),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

        # Heure
        ts = datetime.now().strftime("%H:%M:%S")
        cv2.putText(frame, ts, (w - 85, 23),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        return frame

    def get_status(self) -> dict:
        return {
            "is_compliant": self.is_compliant,
            "violations":   self.frame_violations,
        }
