"""
database.py — WiqayaAI v1
Base de données complète : sociétés, users, chantiers, caméras, ouvriers, EPI, formations, violations
"""

import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "wiqayaai_v1.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # ── Sociétés ──────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS societes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nom             TEXT NOT NULL,
            secteur         TEXT DEFAULT 'BTP',
            ville           TEXT,
            telephone       TEXT,
            email           TEXT,
            abonnement      TEXT DEFAULT 'starter',
            statut          TEXT DEFAULT 'actif',
            date_creation   TEXT DEFAULT (datetime('now')),
            nb_cameras_max  INTEGER DEFAULT 3
        )
    """)

    # ── Utilisateurs ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nom             TEXT NOT NULL,
            prenom          TEXT,
            email           TEXT UNIQUE NOT NULL,
            password_hash   TEXT NOT NULL,
            role            TEXT DEFAULT 'admin_hse',
            societe_id      INTEGER REFERENCES societes(id),
            actif           INTEGER DEFAULT 1,
            date_creation   TEXT DEFAULT (datetime('now')),
            derniere_connexion TEXT
        )
    """)

    # ── Chantiers ─────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chantiers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            societe_id      INTEGER NOT NULL REFERENCES societes(id),
            nom             TEXT NOT NULL,
            adresse         TEXT,
            ville           TEXT,
            responsable     TEXT,
            date_debut      TEXT,
            date_fin        TEXT,
            statut          TEXT DEFAULT 'actif',
            date_creation   TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Caméras ───────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            societe_id      INTEGER NOT NULL REFERENCES societes(id),
            chantier_id     INTEGER REFERENCES chantiers(id),
            nom             TEXT NOT NULL,
            zone            TEXT,
            type_camera     TEXT DEFAULT 'usb',
            source          TEXT DEFAULT '0',
            actif           INTEGER DEFAULT 1,
            date_creation   TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Types EPI (configurables par société) ─────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS epi_types (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            societe_id      INTEGER NOT NULL REFERENCES societes(id),
            nom             TEXT NOT NULL,
            icone           TEXT DEFAULT '🦺',
            seuil_alerte    INTEGER DEFAULT 5,
            duree_vie_mois  INTEGER DEFAULT 24,
            actif           INTEGER DEFAULT 1
        )
    """)

    # ── Stock EPI ─────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_epi (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            societe_id      INTEGER NOT NULL REFERENCES societes(id),
            epi_type_id     INTEGER NOT NULL REFERENCES epi_types(id),
            quantite_total  INTEGER DEFAULT 0,
            quantite_dispo  INTEGER DEFAULT 0,
            date_maj        TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Ouvriers ──────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ouvriers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            societe_id      INTEGER NOT NULL REFERENCES societes(id),
            chantier_id     INTEGER REFERENCES chantiers(id),
            nom             TEXT NOT NULL,
            prenom          TEXT,
            poste           TEXT,
            telephone       TEXT,
            date_embauche   TEXT,
            statut          TEXT DEFAULT 'actif',
            date_creation   TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Attributions EPI ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attributions_epi (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            societe_id      INTEGER NOT NULL REFERENCES societes(id),
            ouvrier_id      INTEGER NOT NULL REFERENCES ouvriers(id),
            epi_type_id     INTEGER NOT NULL REFERENCES epi_types(id),
            reference       TEXT,
            date_attribution TEXT DEFAULT (datetime('now')),
            date_expiration TEXT,
            etat            TEXT DEFAULT 'neuf',
            statut          TEXT DEFAULT 'actif',
            date_retour     TEXT,
            notes           TEXT
        )
    """)

    # ── Violations ───────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            societe_id      INTEGER NOT NULL REFERENCES societes(id),
            chantier_id     INTEGER REFERENCES chantiers(id),
            camera_id       INTEGER REFERENCES cameras(id),
            timestamp       TEXT NOT NULL,
            epi_type        TEXT NOT NULL,
            zone            TEXT DEFAULT 'Zone principale',
            snapshot        TEXT,
            duree_sec       INTEGER DEFAULT 0,
            resolved        INTEGER DEFAULT 0
        )
    """)

    # ── Bibliothèque Formation ────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS formations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            societe_id      INTEGER REFERENCES societes(id),
            titre           TEXT NOT NULL,
            description     TEXT,
            type_contenu    TEXT DEFAULT 'video',
            url_contenu     TEXT,
            categorie       TEXT DEFAULT 'EPI',
            source          TEXT DEFAULT 'interne',
            obligatoire     INTEGER DEFAULT 0,
            date_creation   TEXT DEFAULT (datetime('now')),
            actif           INTEGER DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()

    # Créer super admin et données démo si vide
    _seed_data()
    print("[DB] Base de données WiqayaAI v1 initialisée.")


def _seed_data():
    """Crée le super admin et une société démo si la BDD est vide."""
    conn = get_connection()
    cur = conn.cursor()

    # Super Admin
    existing = cur.execute("SELECT id FROM users WHERE role='superadmin'").fetchone()
    if not existing:
        cur.execute("""
            INSERT INTO users (nom, prenom, email, password_hash, role, societe_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("WiqayaAI", "Admin", "admin@wiqayaai.ma",
              generate_password_hash("admin123"), "superadmin", None))

        # Société démo
        cur.execute("""
            INSERT INTO societes (nom, secteur, ville, email, abonnement)
            VALUES (?, ?, ?, ?, ?)
        """, ("BTP Casablanca Demo", "BTP", "Casablanca", "demo@btpcasa.ma", "pro"))
        societe_id = cur.lastrowid

        # Admin HSE démo
        cur.execute("""
            INSERT INTO users (nom, prenom, email, password_hash, role, societe_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("Responsable", "HSE", "hse@btpcasa.ma",
              generate_password_hash("hse123"), "admin_hse", societe_id))

        # Chantier démo
        cur.execute("""
            INSERT INTO chantiers (societe_id, nom, adresse, ville, responsable)
            VALUES (?, ?, ?, ?, ?)
        """, (societe_id, "Chantier Centre Ville", "Rue Hassan II", "Casablanca", "M. Alami"))
        chantier_id = cur.lastrowid

        # Caméra démo
        cur.execute("""
            INSERT INTO cameras (societe_id, chantier_id, nom, zone, type_camera, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (societe_id, chantier_id, "Caméra 1", "Entrée principale", "usb", "0"))

        # EPI types démo
        epis = [
            ("Casque de chantier", "👷", 5, 36),
            ("Gilet haute visibilité", "🦺", 5, 12),
            ("Lunettes de protection", "👓", 10, 6),
            ("Chaussures de sécurité", "🥾", 3, 24),
            ("Gants de protection", "🧤", 10, 6),
            ("Masque anti-poussière", "😷", 20, 1),
        ]
        for nom, icone, seuil, duree in epis:
            cur.execute("""
                INSERT INTO epi_types (societe_id, nom, icone, seuil_alerte, duree_vie_mois)
                VALUES (?, ?, ?, ?, ?)
            """, (societe_id, nom, icone, seuil, duree))
            epi_id = cur.lastrowid
            cur.execute("""
                INSERT INTO stock_epi (societe_id, epi_type_id, quantite_total, quantite_dispo)
                VALUES (?, ?, ?, ?)
            """, (societe_id, epi_id, 20, 15))

        # Ouvriers démo
        ouvriers = [
            ("Alami", "Khalid", "Maçon"),
            ("Benali", "Youssef", "Chef équipe"),
            ("Tazi", "Rachid", "Électricien"),
            ("Ouali", "Samir", "Plombier"),
            ("Karimi", "Mohamed", "Manœuvre"),
        ]
        for nom, prenom, poste in ouvriers:
            cur.execute("""
                INSERT INTO ouvriers (societe_id, chantier_id, nom, prenom, poste)
                VALUES (?, ?, ?, ?, ?)
            """, (societe_id, chantier_id, nom, prenom, poste))

        # Formations démo
        formations = [
            ("Port correct du casque de chantier", "video", "https://www.youtube.com/embed/hL3I4YMJkBs", "EPI"),
            ("Utilisation des gilets haute visibilité", "video", "https://www.youtube.com/embed/TKCMw0utiak", "EPI"),
            ("ISO 45001 — Santé et sécurité au travail", "document", "https://www.iso.org/iso-45001-occupational-health-and-safety.html", "Réglementation"),
            ("Code du travail marocain — HSE", "document", "https://www.emploi.gov.ma/index.php/fr/code-du-travail", "Réglementation"),
            ("Bonnes pratiques sécurité chantier", "video", "https://www.youtube.com/embed/nT3e5K9iFSA", "Bonnes pratiques"),
        ]
        for titre, type_c, url, cat in formations:
            cur.execute("""
                INSERT INTO formations (societe_id, titre, type_contenu, url_contenu, categorie)
                VALUES (?, ?, ?, ?, ?)
            """, (societe_id, titre, type_c, url, cat))

        conn.commit()
        print("[DB] Données démo créées.")
        print("[DB] Super Admin : admin@wiqayaai.ma / admin123")
        print("[DB] Admin HSE   : hse@btpcasa.ma / hse123")

    conn.close()


# ── Authentification ──────────────────────────────────────────────────────────

def get_user_by_email(email):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE email=? AND actif=1", (email,)).fetchone()
    conn.close()
    return dict(user) if user else None


def verify_password(user, password):
    return check_password_hash(user['password_hash'], password)


def update_last_login(user_id):
    conn = get_connection()
    conn.execute("UPDATE users SET derniere_connexion=? WHERE id=?",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()


# ── Sociétés ──────────────────────────────────────────────────────────────────

def get_all_societes():
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.*, 
               COUNT(DISTINCT c.id) as nb_cameras,
               COUNT(DISTINCT ch.id) as nb_chantiers,
               COUNT(DISTINCT o.id) as nb_ouvriers
        FROM societes s
        LEFT JOIN cameras c ON c.societe_id = s.id
        LEFT JOIN chantiers ch ON ch.societe_id = s.id
        LEFT JOIN ouvriers o ON o.societe_id = s.id
        GROUP BY s.id ORDER BY s.date_creation DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_societe(data):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO societes (nom, secteur, ville, telephone, email, abonnement)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (data['nom'], data.get('secteur', 'BTP'), data.get('ville', ''),
          data.get('telephone', ''), data.get('email', ''), data.get('abonnement', 'starter')))
    sid = cur.lastrowid

    # Créer admin HSE pour cette société
    cur.execute("""
        INSERT INTO users (nom, email, password_hash, role, societe_id)
        VALUES (?, ?, ?, ?, ?)
    """, (data['nom'], data['email_admin'],
          generate_password_hash(data['password_admin']), 'admin_hse', sid))

    conn.commit()
    conn.close()
    return sid


def get_societe(societe_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM societes WHERE id=?", (societe_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_societe_statut(societe_id, statut):
    conn = get_connection()
    conn.execute("UPDATE societes SET statut=? WHERE id=?", (statut, societe_id))
    conn.commit()
    conn.close()


# ── Chantiers ─────────────────────────────────────────────────────────────────

def get_chantiers(societe_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT ch.*, COUNT(DISTINCT c.id) as nb_cameras, COUNT(DISTINCT o.id) as nb_ouvriers
        FROM chantiers ch
        LEFT JOIN cameras c ON c.chantier_id = ch.id
        LEFT JOIN ouvriers o ON o.chantier_id = ch.id
        WHERE ch.societe_id=? GROUP BY ch.id ORDER BY ch.date_creation DESC
    """, (societe_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_chantier(societe_id, data):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO chantiers (societe_id, nom, adresse, ville, responsable, date_debut, date_fin)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (societe_id, data['nom'], data.get('adresse', ''), data.get('ville', ''),
          data.get('responsable', ''), data.get('date_debut', ''), data.get('date_fin', '')))
    conn.commit()
    conn.close()


# ── Caméras ───────────────────────────────────────────────────────────────────

def get_cameras(societe_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT c.*, ch.nom as chantier_nom
        FROM cameras c
        LEFT JOIN chantiers ch ON ch.id = c.chantier_id
        WHERE c.societe_id=? ORDER BY c.id
    """, (societe_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_camera(societe_id, data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO cameras (societe_id, chantier_id, nom, zone, type_camera, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (societe_id, data.get('chantier_id'), data['nom'],
          data.get('zone', ''), data.get('type_camera', 'usb'), data.get('source', '0')))
    conn.commit()
    conn.close()


def delete_camera(camera_id, societe_id):
    conn = get_connection()
    conn.execute("DELETE FROM cameras WHERE id=? AND societe_id=?", (camera_id, societe_id))
    conn.commit()
    conn.close()


def toggle_camera(camera_id, societe_id):
    conn = get_connection()
    conn.execute("""
        UPDATE cameras SET actif = CASE WHEN actif=1 THEN 0 ELSE 1 END
        WHERE id=? AND societe_id=?
    """, (camera_id, societe_id))
    conn.commit()
    conn.close()


# ── Ouvriers ──────────────────────────────────────────────────────────────────

def get_ouvriers(societe_id, chantier_id=None):
    conn = get_connection()
    if chantier_id:
        rows = conn.execute("""
            SELECT o.*, ch.nom as chantier_nom,
                   COUNT(DISTINCT v.id) as nb_violations
            FROM ouvriers o
            LEFT JOIN chantiers ch ON ch.id = o.chantier_id
            LEFT JOIN violations v ON v.chantier_id = o.chantier_id
                AND v.timestamp >= datetime('now', '-30 days')
            WHERE o.societe_id=? AND o.chantier_id=?
            GROUP BY o.id ORDER BY o.nom
        """, (societe_id, chantier_id)).fetchall()
    else:
        rows = conn.execute("""
            SELECT o.*, ch.nom as chantier_nom,
                   COUNT(DISTINCT v.id) as nb_violations
            FROM ouvriers o
            LEFT JOIN chantiers ch ON ch.id = o.chantier_id
            LEFT JOIN violations v ON v.chantier_id = o.chantier_id
                AND v.timestamp >= datetime('now', '-30 days')
            WHERE o.societe_id=?
            GROUP BY o.id ORDER BY o.nom
        """, (societe_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_ouvrier(societe_id, data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO ouvriers (societe_id, chantier_id, nom, prenom, poste, telephone, date_embauche)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (societe_id, data.get('chantier_id'), data['nom'], data.get('prenom', ''),
          data.get('poste', ''), data.get('telephone', ''), data.get('date_embauche', '')))
    conn.commit()
    conn.close()


def delete_ouvrier(ouvrier_id, societe_id):
    conn = get_connection()
    conn.execute("DELETE FROM ouvriers WHERE id=? AND societe_id=?", (ouvrier_id, societe_id))
    conn.commit()
    conn.close()


# ── EPI Types ─────────────────────────────────────────────────────────────────

def get_epi_types(societe_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT e.*, s.quantite_total, s.quantite_dispo,
               s.quantite_total - s.quantite_dispo as en_utilisation
        FROM epi_types e
        LEFT JOIN stock_epi s ON s.epi_type_id = e.id AND s.societe_id = e.societe_id
        WHERE e.societe_id=? AND e.actif=1 ORDER BY e.nom
    """, (societe_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_epi_type(societe_id, data):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO epi_types (societe_id, nom, icone, seuil_alerte, duree_vie_mois)
        VALUES (?, ?, ?, ?, ?)
    """, (societe_id, data['nom'], data.get('icone', '🦺'),
          int(data.get('seuil_alerte', 5)), int(data.get('duree_vie_mois', 24))))
    epi_id = cur.lastrowid
    cur.execute("""
        INSERT INTO stock_epi (societe_id, epi_type_id, quantite_total, quantite_dispo)
        VALUES (?, ?, 0, 0)
    """, (societe_id, epi_id))
    conn.commit()
    conn.close()


def update_stock(societe_id, epi_type_id, quantite_ajout):
    conn = get_connection()
    conn.execute("""
        UPDATE stock_epi
        SET quantite_total = quantite_total + ?,
            quantite_dispo = quantite_dispo + ?,
            date_maj = datetime('now')
        WHERE societe_id=? AND epi_type_id=?
    """, (quantite_ajout, quantite_ajout, societe_id, epi_type_id))
    conn.commit()
    conn.close()


def delete_epi_type(epi_id, societe_id):
    conn = get_connection()
    conn.execute("UPDATE epi_types SET actif=0 WHERE id=? AND societe_id=?", (epi_id, societe_id))
    conn.commit()
    conn.close()


# ── Attributions EPI ──────────────────────────────────────────────────────────

def get_attributions(societe_id, ouvrier_id=None):
    conn = get_connection()
    query = """
        SELECT a.*, o.nom || ' ' || o.prenom as ouvrier_nom,
               e.nom as epi_nom, e.icone as epi_icone,
               ch.nom as chantier_nom
        FROM attributions_epi a
        JOIN ouvriers o ON o.id = a.ouvrier_id
        JOIN epi_types e ON e.id = a.epi_type_id
        LEFT JOIN chantiers ch ON ch.id = o.chantier_id
        WHERE a.societe_id=?
    """
    params = [societe_id]
    if ouvrier_id:
        query += " AND a.ouvrier_id=?"
        params.append(ouvrier_id)
    query += " ORDER BY a.date_attribution DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_attribution(societe_id, data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO attributions_epi
        (societe_id, ouvrier_id, epi_type_id, reference, date_expiration, etat, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (societe_id, data['ouvrier_id'], data['epi_type_id'],
          data.get('reference', ''), data.get('date_expiration', ''),
          data.get('etat', 'neuf'), data.get('notes', '')))
    # Décrémenter stock disponible
    conn.execute("""
        UPDATE stock_epi SET quantite_dispo = quantite_dispo - 1
        WHERE societe_id=? AND epi_type_id=? AND quantite_dispo > 0
    """, (societe_id, data['epi_type_id']))
    conn.commit()
    conn.close()


def retour_epi(attribution_id, societe_id, etat):
    conn = get_connection()
    attr = conn.execute("SELECT * FROM attributions_epi WHERE id=?", (attribution_id,)).fetchone()
    if attr:
        conn.execute("""
            UPDATE attributions_epi SET statut='retourné', date_retour=datetime('now'), etat=?
            WHERE id=? AND societe_id=?
        """, (etat, attribution_id, societe_id))
        # Remettre en stock si bon état
        if etat in ('neuf', 'bon'):
            conn.execute("""
                UPDATE stock_epi SET quantite_dispo = quantite_dispo + 1
                WHERE societe_id=? AND epi_type_id=?
            """, (societe_id, attr['epi_type_id']))
        else:
            # Retiré du total si cassé/perdu
            conn.execute("""
                UPDATE stock_epi SET quantite_total = quantite_total - 1
                WHERE societe_id=? AND epi_type_id=?
            """, (societe_id, attr['epi_type_id']))
    conn.commit()
    conn.close()


# ── Violations ────────────────────────────────────────────────────────────────

def insert_violation(societe_id, epi_type, chantier_id=None, camera_id=None,
                     zone="Zone principale", snapshot_path=None):
    conn = get_connection()
    cur = conn.cursor()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Stocker uniquement le nom du fichier (pas le chemin complet)
    snap_name = os.path.basename(snapshot_path) if snapshot_path else None
    cur.execute("""
        INSERT INTO violations (societe_id, chantier_id, camera_id, timestamp, epi_type, zone, snapshot)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (societe_id, chantier_id, camera_id, ts, epi_type, zone, snap_name))
    vid = cur.lastrowid
    conn.commit()
    conn.close()
    return vid


def get_violations(societe_id, days=30, limit=None):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    query = """
        SELECT v.*, ch.nom as chantier_nom, c.nom as camera_nom
        FROM violations v
        LEFT JOIN chantiers ch ON ch.id = v.chantier_id
        LEFT JOIN cameras c ON c.id = v.camera_id
        WHERE v.societe_id=? AND v.timestamp >= ?
        ORDER BY v.id DESC
    """
    params = [societe_id, since]
    if limit:
        query += f" LIMIT {limit}"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def calculate_hse_score(societe_id):
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    nb = conn.execute(
        "SELECT COUNT(*) FROM violations WHERE societe_id=? AND timestamp>=?",
        (societe_id, since)
    ).fetchone()[0]
    conn.close()
    score = max(0, 100 - nb * 2)
    if score > 75:
        color, label = "success", "BON"
    elif score >= 50:
        color, label = "warning", "MOYEN"
    else:
        color, label = "danger", "CRITIQUE"
    return {"score": score, "nb_violations": nb, "color": color, "label": label}


def get_violations_by_type(societe_id, days=7):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    rows = conn.execute("""
        SELECT epi_type, COUNT(*) as cnt FROM violations
        WHERE societe_id=? AND timestamp>=?
        GROUP BY epi_type ORDER BY cnt DESC
    """, (societe_id, since)).fetchall()
    conn.close()
    return {r['epi_type']: r['cnt'] for r in rows}


# ── Formations ────────────────────────────────────────────────────────────────

def get_formations(societe_id, categorie=None):
    conn = get_connection()
    if categorie:
        rows = conn.execute("""
            SELECT * FROM formations WHERE (societe_id=? OR societe_id IS NULL)
            AND categorie=? AND actif=1 ORDER BY date_creation DESC
        """, (societe_id, categorie)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM formations WHERE (societe_id=? OR societe_id IS NULL)
            AND actif=1 ORDER BY categorie, date_creation DESC
        """, (societe_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _convert_youtube_url(url: str) -> str:
    """Convertit une URL YouTube normale en URL embed."""
    if not url:
        return url
    # https://www.youtube.com/watch?v=ID
    if 'youtube.com/watch?v=' in url:
        vid_id = url.split('watch?v=')[1].split('&')[0]
        return f'https://www.youtube.com/embed/{vid_id}'
    # https://youtu.be/ID
    if 'youtu.be/' in url:
        vid_id = url.split('youtu.be/')[1].split('?')[0]
        return f'https://www.youtube.com/embed/{vid_id}'
    # Déjà en format embed ou autre URL
    return url


def create_formation(societe_id, data):
    url = _convert_youtube_url(data.get('url_contenu', ''))
    conn = get_connection()
    conn.execute("""
        INSERT INTO formations (societe_id, titre, description, type_contenu, url_contenu, categorie, obligatoire)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (societe_id, data['titre'], data.get('description', ''),
          data.get('type_contenu', 'video'), url,
          data.get('categorie', 'EPI'), int(data.get('obligatoire', 0))))
    conn.commit()
    conn.close()


def delete_formation(formation_id, societe_id):
    conn = get_connection()
    conn.execute("UPDATE formations SET actif=0 WHERE id=? AND societe_id=?",
                 (formation_id, societe_id))
    conn.commit()
    conn.close()


# ── Stats Super Admin ─────────────────────────────────────────────────────────

def get_admin_stats():
    conn = get_connection()
    stats = {
        "nb_societes": conn.execute("SELECT COUNT(*) FROM societes WHERE statut='actif'").fetchone()[0],
        "nb_societes_total": conn.execute("SELECT COUNT(*) FROM societes").fetchone()[0],
        "nb_cameras": conn.execute("SELECT COUNT(*) FROM cameras WHERE actif=1").fetchone()[0],
        "nb_violations_today": conn.execute(
            "SELECT COUNT(*) FROM violations WHERE timestamp >= date('now')"
        ).fetchone()[0],
    }
    conn.close()
    return stats


# Init automatique
init_db()
