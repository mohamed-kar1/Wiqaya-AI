"""
app.py — WiqayaAI v1
Wiqaya AI — Surveillance HSE Intelligente — Système HSE Complet
"""

import os
import io
import json
import base64
import threading
import time
from datetime import datetime
from functools import wraps

import cv2
from flask import (Flask, render_template, Response, jsonify,
                   request, send_file, session, redirect, url_for, flash)
from flask_socketio import SocketIO

# ── Init Flask ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Imports locaux ────────────────────────────────────────────────────────────
from database import *
from detection_logic import DetectionEngine

# ── Modèle IA ─────────────────────────────────────────────────────────────────
MODEL_PATH = os.path.join(os.path.dirname(__file__), "ppe.pt")
model = None
engines = {}  # {camera_id: DetectionEngine}

def load_model():
    global model
    try:
        from ultralytics import YOLO
        if os.path.exists(MODEL_PATH):
            print(f"[MODEL] Chargement de {MODEL_PATH}...")
            model = YOLO(MODEL_PATH)
        else:
            print("[MODEL] ppe.pt introuvable — yolov8n.pt utilisé")
            model = YOLO("yolov8n.pt")
        print("[MODEL] Modèle chargé avec succès.")
    except Exception as e:
        print(f"[MODEL] Erreur : {e}")

# ── Gestion multi-caméras ─────────────────────────────────────────────────────
cameras_state = {}  # {camera_id: {running, thread, frame_jpg, cap}}
cameras_lock = threading.Lock()

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def save_snapshot(frame):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"violation_{ts}.jpg"
    path = os.path.join(SNAPSHOT_DIR, filename)
    cv2.imwrite(path, frame)
    return path


def make_violation_callback(cam_id, societe_id, chantier_id, zone):
    def _handle_violation(label, frame):
        """Traitement violation dans thread séparé — non bloquant."""
        try:
            snapshot_path = save_snapshot(frame)
            insert_violation(
                societe_id=societe_id,
                epi_type=label,
                chantier_id=chantier_id,
                camera_id=cam_id,
                zone=zone,
                snapshot_path=snapshot_path
            )
            hse = calculate_hse_score(societe_id)
            recent = get_violations(societe_id, days=1, limit=5)
            socketio.emit("violation", {
                "camera_id": cam_id,
                "label": label,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "zone": zone,
                "snapshot": f"/snapshot/{os.path.basename(snapshot_path)}" if snapshot_path else None,
                "hse": hse,
                "recent": recent,
            }, room=f"societe_{societe_id}")
            print(f"[ALERT] Cam {cam_id} — {label} — {zone}")
        except Exception as e:
            print(f"[ALERT ERROR] {e}")

    def on_violation(label, frame):
        """Callback appelé par le moteur IA — lance un thread et retourne immédiatement."""
        t = threading.Thread(
            target=_handle_violation,
            args=(label, frame.copy()),  # .copy() pour éviter les race conditions
            daemon=True
        )
        t.start()

    return on_violation


def camera_thread_func(cam_id, source, societe_id, chantier_id, zone):
    global cameras_state, model

    # Ouvrir la caméra
    if str(source).isdigit():
        cap = cv2.VideoCapture(int(source))
    else:
        cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        print(f"[CAM {cam_id}] Impossible d'ouvrir : {source}")
        with cameras_lock:
            cameras_state[cam_id]['running'] = False
        socketio.emit("camera_status", {"camera_id": cam_id, "running": False,
                                         "error": "Source introuvable"})
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Moteur de détection
    engine = DetectionEngine(model) if model else None
    if engine:
        engine.on_violation(make_violation_callback(cam_id, societe_id, chantier_id, zone))
    engines[cam_id] = engine

    socketio.emit("camera_status", {"camera_id": cam_id, "running": True})
    print(f"[CAM {cam_id}] Démarrée — source: {source}")

    while cameras_state.get(cam_id, {}).get('running', False):
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        if engine:
            annotated, violations, compliant = engine.process_frame(frame)
        else:
            annotated, violations, compliant = frame, [], True

        ret2, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ret2:
            with cameras_lock:
                if cam_id in cameras_state:
                    cameras_state[cam_id]['frame_jpg'] = buf.tobytes()

        socketio.emit("status_update", {
            "camera_id": cam_id,
            "is_compliant": compliant,
            "violations": violations,
            "hse": calculate_hse_score(societe_id),
        }, room=f"societe_{societe_id}")

        time.sleep(0.033)

    cap.release()
    with cameras_lock:
        if cam_id in cameras_state:
            cameras_state[cam_id]['frame_jpg'] = None
    if cam_id in engines:
        del engines[cam_id]
    socketio.emit("camera_status", {"camera_id": cam_id, "running": False})
    print(f"[CAM {cam_id}] Arrêtée")


def start_camera(cam_id, source, societe_id, chantier_id, zone):
    with cameras_lock:
        if cam_id in cameras_state and cameras_state[cam_id].get('running'):
            return
        cameras_state[cam_id] = {'running': True, 'frame_jpg': None}

    t = threading.Thread(
        target=camera_thread_func,
        args=(cam_id, source, societe_id, chantier_id, zone),
        daemon=True
    )
    t.start()


def stop_camera(cam_id):
    with cameras_lock:
        if cam_id in cameras_state:
            cameras_state[cam_id]['running'] = False


def gen_frames(cam_id):
    while True:
        frame = None
        with cameras_lock:
            if cam_id in cameras_state:
                frame = cameras_state[cam_id].get('frame_jpg')
        if frame:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        else:
            time.sleep(0.1)


# ── Auth decorators ───────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'superadmin':
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def get_current_societe_id():
    return session.get('societe_id')


# ── Routes Auth ───────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        if session.get('role') == 'superadmin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = get_user_by_email(email)

        if user and verify_password(user, password):
            session['user_id'] = user['id']
            session['user_nom'] = user['nom']
            session['role'] = user['role']
            session['societe_id'] = user['societe_id']
            update_last_login(user['id'])

            if user['role'] == 'superadmin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash('Email ou mot de passe incorrect', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Routes Admin HSE ──────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    if session.get('role') == 'superadmin':
        return redirect(url_for('admin_dashboard'))
    sid = get_current_societe_id()
    hse = calculate_hse_score(sid)
    recent = get_violations(sid, days=1, limit=5)
    cameras = get_cameras(sid)
    chantiers = get_chantiers(sid)
    return render_template('index.html', hse=hse, recent=recent,
                           cameras=cameras, chantiers=chantiers)


@app.route('/video_feed/<int:cam_id>')
@login_required
def video_feed(cam_id):
    return Response(gen_frames(cam_id),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route('/api/camera/start/<int:cam_id>', methods=['POST'])
@login_required
def api_start_camera(cam_id):
    sid = get_current_societe_id()
    cams = get_cameras(sid)
    cam = next((c for c in cams if c['id'] == cam_id), None)
    if not cam:
        return jsonify({"error": "Caméra introuvable"}), 404
    start_camera(cam_id, cam['source'], sid,
                 cam.get('chantier_id'), cam.get('zone', 'Zone principale'))
    return jsonify({"status": "started"})


@app.route('/api/camera/stop/<int:cam_id>', methods=['POST'])
@login_required
def api_stop_camera(cam_id):
    stop_camera(cam_id)
    return jsonify({"status": "stopped"})


@app.route('/api/status')
@login_required
def api_status():
    sid = get_current_societe_id()
    return jsonify({
        "hse": calculate_hse_score(sid),
        "cameras": {str(k): {"running": v.get('running', False)}
                    for k, v in cameras_state.items()},
    })


# ── Chantiers ─────────────────────────────────────────────────────────────────

@app.route('/chantiers')
@login_required
def chantiers_page():
    sid = get_current_societe_id()
    chantiers = get_chantiers(sid)
    return render_template('chantiers.html', chantiers=chantiers)


@app.route('/api/chantiers', methods=['POST'])
@login_required
def api_create_chantier():
    sid = get_current_societe_id()
    create_chantier(sid, request.get_json())
    return jsonify({"status": "ok"})


# ── Caméras ───────────────────────────────────────────────────────────────────

@app.route('/cameras')
@login_required
def cameras_page():
    sid = get_current_societe_id()
    cameras = get_cameras(sid)
    chantiers = get_chantiers(sid)
    return render_template('cameras.html', cameras=cameras, chantiers=chantiers)


@app.route('/api/cameras', methods=['POST'])
@login_required
def api_create_camera():
    sid = get_current_societe_id()
    create_camera(sid, request.get_json())
    return jsonify({"status": "ok"})


@app.route('/api/cameras/<int:cam_id>', methods=['DELETE'])
@login_required
def api_delete_camera(cam_id):
    sid = get_current_societe_id()
    stop_camera(cam_id)
    delete_camera(cam_id, sid)
    return jsonify({"status": "ok"})


# ── Ouvriers ──────────────────────────────────────────────────────────────────

@app.route('/ouvriers')
@login_required
def ouvriers_page():
    sid = get_current_societe_id()
    chantier_id = request.args.get('chantier_id', type=int)
    ouvriers = get_ouvriers(sid, chantier_id)
    chantiers = get_chantiers(sid)
    return render_template('ouvriers.html', ouvriers=ouvriers,
                           chantiers=chantiers, chantier_id=chantier_id)


@app.route('/api/ouvriers', methods=['POST'])
@login_required
def api_create_ouvrier():
    sid = get_current_societe_id()
    create_ouvrier(sid, request.get_json())
    return jsonify({"status": "ok"})


@app.route('/api/ouvriers/<int:ouvrier_id>', methods=['DELETE'])
@login_required
def api_delete_ouvrier(ouvrier_id):
    sid = get_current_societe_id()
    delete_ouvrier(ouvrier_id, sid)
    return jsonify({"status": "ok"})


# ── Stock EPI ─────────────────────────────────────────────────────────────────

@app.route('/stock')
@login_required
def stock_page():
    sid = get_current_societe_id()
    epi_types = get_epi_types(sid)
    attributions = get_attributions(sid)
    ouvriers = get_ouvriers(sid)
    return render_template('stock.html', epi_types=epi_types,
                           attributions=attributions, ouvriers=ouvriers)


@app.route('/api/epi_types', methods=['POST'])
@login_required
def api_create_epi_type():
    sid = get_current_societe_id()
    create_epi_type(sid, request.get_json())
    return jsonify({"status": "ok"})


@app.route('/api/epi_types/<int:epi_id>', methods=['DELETE'])
@login_required
def api_delete_epi_type(epi_id):
    sid = get_current_societe_id()
    delete_epi_type(epi_id, sid)
    return jsonify({"status": "ok"})


@app.route('/api/stock/ajout', methods=['POST'])
@login_required
def api_ajout_stock():
    sid = get_current_societe_id()
    data = request.get_json()
    update_stock(sid, data['epi_type_id'], int(data['quantite']))
    return jsonify({"status": "ok"})


@app.route('/api/attributions', methods=['POST'])
@login_required
def api_create_attribution():
    sid = get_current_societe_id()
    create_attribution(sid, request.get_json())
    return jsonify({"status": "ok"})


@app.route('/api/attributions/<int:attr_id>/retour', methods=['POST'])
@login_required
def api_retour_epi(attr_id):
    sid = get_current_societe_id()
    data = request.get_json()
    retour_epi(attr_id, sid, data.get('etat', 'bon'))
    return jsonify({"status": "ok"})


# ── Formations ────────────────────────────────────────────────────────────────

@app.route('/formations')
@login_required
def formations_page():
    sid = get_current_societe_id()
    categorie = request.args.get('categorie')
    formations = get_formations(sid, categorie)
    categories = ['EPI', 'Réglementation', 'Bonnes pratiques', 'Procédures']
    return render_template('formations.html', formations=formations,
                           categories=categories, categorie_active=categorie)


@app.route('/api/formations', methods=['POST'])
@login_required
def api_create_formation():
    sid = get_current_societe_id()
    create_formation(sid, request.get_json())
    return jsonify({"status": "ok"})


@app.route('/api/formations/<int:formation_id>', methods=['DELETE'])
@login_required
def api_delete_formation(formation_id):
    sid = get_current_societe_id()
    delete_formation(formation_id, sid)
    return jsonify({"status": "ok"})


# ── Historique ────────────────────────────────────────────────────────────────

@app.route('/historique')
@login_required
def historique_page():
    sid = get_current_societe_id()
    violations = get_violations(sid, days=30)
    stats = get_violations_by_type(sid)
    hse = calculate_hse_score(sid)
    return render_template('review.html', violations=violations, stats=stats, hse=hse)


# ── Rapport PDF ───────────────────────────────────────────────────────────────

@app.route('/rapport')
@login_required
def rapport():
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import cm

        sid = get_current_societe_id()
        societe = get_societe(sid)
        violations = get_violations(sid, days=7)
        hse = calculate_hse_score(sid)
        stats = get_violations_by_type(sid)
        today = datetime.now().strftime("%d/%m/%Y")

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(
            f"Rapport HSE — {societe['nom'] if societe else 'WiqayaAI'} — {today}",
            styles["Title"]
        ))
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph(
            f"Score HSE : {hse['score']}/100 — {hse['label']} — {hse['nb_violations']} violations sur 7 jours",
            styles["Normal"]
        ))
        story.append(Spacer(1, 0.4*cm))

        table_data = [["Date", "Heure", "EPI manquant", "Zone", "Chantier"]]
        for v in violations[:50]:
            ts = v.get("timestamp", "")
            table_data.append([
                ts[:10], ts[11:19],
                v.get("epi_type", ""),
                v.get("zone", ""),
                v.get("chantier_nom", "—"),
            ])
        if len(table_data) == 1:
            table_data.append(["—", "—", "Aucune violation", "—", "—"])

        t = Table(table_data)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#080C14")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4ff")]),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph(
            f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} par WiqayaAI",
            styles["Italic"]
        ))

        doc.build(story)
        buf.seek(0)
        filename = f"rapport_hse_{datetime.now().strftime('%Y%m%d')}.pdf"
        return send_file(buf, mimetype="application/pdf",
                         as_attachment=True, download_name=filename)
    except ImportError:
        return "ReportLab non installé. pip install reportlab", 500
    except Exception as e:
        return f"Erreur PDF : {e}", 500


# ── Paramètres ───────────────────────────────────────────────────────────────

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

def load_settings():
    default = {
        "required_ppe": ["Hardhat", "Safety Vest"],
        "alert_delay_sec": 3,
        "cooldown_sec": 30,
        "confidence_threshold": 0.55,
        "whatsapp_alerts": False,
        "whatsapp_number": "+212600000000",
        "twilio_account_sid": "",
        "twilio_auth_token": "",
        "twilio_from_number": "whatsapp:+14155238886",
    }
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH) as f:
            return {**default, **json.load(f)}
    return default

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    if request.method == 'POST':
        data = request.get_json()
        with open(SETTINGS_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        return jsonify({"status": "saved"})
    cfg = load_settings()
    return render_template('settings.html', config=cfg)


def send_whatsapp_alert(label, zone, chantier_nom, timestamp):
    """WhatsApp désactivé temporairement pour fluidité détection."""
    pass  # Réactiver quand nécessaire


# ── Snapshot ──────────────────────────────────────────────────────────────────

@app.route('/snapshot/<path:filename>')
@login_required
def snapshot(filename):
    basename = os.path.basename(filename)
    path = os.path.join(SNAPSHOT_DIR, basename)
    if os.path.exists(path):
        return send_file(path, mimetype="image/jpeg")
    return "Not found", 404


# ── Super Admin ───────────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
@superadmin_required
def admin_dashboard():
    societes = get_all_societes()
    stats = get_admin_stats()
    return render_template('admin.html', societes=societes, stats=stats)


@app.route('/api/admin/societes', methods=['POST'])
@login_required
@superadmin_required
def api_create_societe():
    create_societe(request.get_json())
    return jsonify({"status": "ok"})


@app.route('/api/admin/societes/<int:sid>/statut', methods=['POST'])
@login_required
@superadmin_required
def api_update_societe_statut(sid):
    data = request.get_json()
    update_societe_statut(sid, data['statut'])
    return jsonify({"status": "ok"})


# ── SocketIO ──────────────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    sid = session.get('societe_id')
    if sid:
        from flask_socketio import join_room
        join_room(f"societe_{sid}")


# ── Démarrage ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    load_model()
    print("=" * 55)
    print("  WiqayaAI v1 — Wiqaya AI — Surveillance HSE Intelligente")
    print("  http://localhost:5000")
    print("  Super Admin : admin@wiqayaai.ma / admin123")
    print("  Admin HSE   : hse@btpcasa.ma / hse123")
    print("=" * 55)
    socketio.run(app, host="0.0.0.0", port=5000,
                 debug=False, allow_unsafe_werkzeug=True)
