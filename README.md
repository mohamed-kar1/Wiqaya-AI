# WiqayaAI — Surveillance HSE intelligente

Application web de contrôle du port des EPI (équipements de protection individuelle) sur chantier, basée sur la détection d'objets **YOLOv8** en temps réel. Elle détecte l'absence de casque, de gilet ou de masque via des caméras (USB ou IP/RTSP), déclenche des alertes et centralise la gestion HSE d'une ou plusieurs sociétés.

## Fonctionnalités

- Détection en temps réel des EPI manquants (casque, gilet, masque) avec seuil de confiance, délai d'alerte et anti-spam (cooldown) configurables
- Flux vidéo multi-caméras (USB, RTSP) et notifications en direct via Socket.IO
- Gestion des chantiers, caméras et ouvriers
- Stock d'EPI, attributions et retours
- Suivi des formations
- Historique des violations avec captures, et rapport PDF
- Paramètres de détection modifiables depuis l'interface
- Multi-sociétés avec un espace Super Admin (création et activation/suspension des sociétés)
- Alertes WhatsApp via Twilio (optionnelles, désactivées par défaut)

## Stack technique

Python · Flask · Flask-SocketIO · SQLite · OpenCV · Ultralytics YOLOv8 · ReportLab

## Structure

```
.
├── app.py                  # Application Flask, routes et gestion des caméras
├── database.py             # Schéma SQLite et accès aux données
├── detection_logic.py      # Moteur de détection YOLOv8 et règles d'alerte
├── ppe.pt                  # Poids du modèle de détection d'EPI
├── requirements.txt
└── templates/              # Pages HTML (Jinja2)
```

## Installation

Prérequis : Python 3.9 ou plus.

```bash
git clone https://github.com/mohamed-kar1/wiqayaai.git
cd wiqayaai

python -m venv .venv
# Windows : .venv\Scripts\activate
# Linux/macOS : source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

L'application est disponible sur http://localhost:5000. La base SQLite (`wiqayaai_v1.db`) est créée automatiquement au premier lancement, avec des données de démonstration.

## Comptes de démonstration

Créés automatiquement dans une base vide :

| Rôle | E-mail | Mot de passe |
|---|---|---|
| Super Admin | `admin@wiqayaai.ma` | `admin123` |
| Admin HSE | `hse@btpcasa.ma` | `hse123` |

> Ces identifiants sont uniquement destinés à la démonstration. Change-les avant tout déploiement réel.

## Configuration

Les paramètres se modifient depuis la page **Paramètres** de l'application (ils sont enregistrés dans `settings.json`, créé automatiquement) :

| Clé | Rôle |
|---|---|
| `required_ppe` | EPI obligatoires (`Hardhat`, `Safety Vest`, `Mask`) |
| `confidence_threshold` | Seuil de confiance de la détection |
| `alert_delay_sec` | Durée de la violation avant alerte |
| `cooldown_sec` | Délai minimum entre deux alertes du même type |
| `whatsapp_alerts` | Active les alertes WhatsApp |
| `twilio_*` | Identifiants Twilio (optionnel) |

Sources de caméra : index USB (`0`, `1`…) ou URL RTSP, par exemple `rtsp://utilisateur:motdepasse@192.168.1.10:554/stream1`.

## Remarques de sécurité

- `settings.json`, la base `wiqayaai_v1.db` et le dossier `snapshots/` sont générés à l'exécution : ne les commite pas. Les URL RTSP et identifiants Twilio non plus.
- Le serveur écoute sur `0.0.0.0` et le CORS Socket.IO est ouvert (`*`) : à restreindre en production, derrière un serveur WSGI et HTTPS.

## Classes détectées

`Hardhat`, `Mask`, `NO-Hardhat`, `NO-Mask`, `NO-Safety Vest`, `Person`, `Safety Cone`, `Safety Vest`, `Machinery`, `Vehicle`.

## Auteur

Mohamed Amine Karany — Master Data Science & Big Data, Faculté des Sciences Ben M'Sik, Université Hassan II de Casablanca.

## Licence

MIT — voir [LICENSE](LICENSE).
