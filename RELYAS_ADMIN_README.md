# 🌍 RELYAS ADMIN - SOC Agricole GAÏA-CI

## 📋 Vue d'ensemble

**RELYAS ADMIN** est le cerveau opérationnel de GAÏA-CI. Conçu comme un **Security Operations Center (SOC) agricole**, ce système permet aux experts agronomes de superviser, analyser et intervenir sur les plantations en temps réel.

---

## 🎯 Fonctionnalités Principales

### 1️⃣ **Supervision de Télémétrie en Temps Réel**
- Réception automatique des données des capteurs embarqués sur les drones
- **Données suivies** :
  - Humidité relative (%)
  - Température ambiante (°C)
  - pH du sol
  - Humidité du sol (%)
  - Composition azotée du sol (mg/kg)
- Mise à jour automatique toutes les **3 secondes**
- Interface dédiée au dashboard central

### 2️⃣ **Gestion des Alertes Critiques**
- **Types d'alertes** : épidémie, sécheresse, maladie, gel, autres
- **Niveaux de sévérité** : critical, high, medium, low
- Visualisation des alertes par ordre de sévérité
- Mode "Urgence" activable sur l'interface planteur
- Historique complet des alertes

### 3️⃣ **Système d'Aide à la Décision (SAD)**
- Interface dédiée pour rédiger des recommandations personnalisées
- Basées sur les données télémétriques en temps réel
- Envoi immédiat au planteur via canal de communication direct
- Traçabilité complète (Admin, Date, Contenu)

### 4️⃣ **Gestion de Flotte & Utilisateurs**
- Enregistrement des drones avec ID unique
- Suivi de l'état de connexion (online/offline/maintenance)
- Niveau de batterie en temps réel
- Localisation GPS de chaque drone
- Gestion des planteurs associés

### 5️⃣ **Système de Communication Multimédia**
- Chat direct avec les planteurs
- Polling optimisé (< 3 secondes)
- Support des messages structurés
- Historique complet des conversations
- Recherche rapide des planteurs

---

## 🖥️ Architecture de l'Interface (3 Colonnes)

### **Colonne Gauche : État Système**
```
┌─────────────────────────┐
│ 📊 État du Système      │
├─────────────────────────┤
│ Total Planteurs: X      │
│ Drones En Ligne: X/Y    │
│ Alertes CRITIQUES: Z 🚨 │
├─────────────────────────┤
│ 📋 Alertes Actives:     │
│  • Alerte 1             │
│  • Alerte 2             │
└─────────────────────────┘
```

### **Colonne Centrale : Dashboard Opérationnel**
```
┌───────────────────────┬───────────────────────┐
│ 📡 Télémétrie         │ 💡 SAD                │
│ ├─ Humidité: 65%      │ ├─ Planteur [Select]  │
│ ├─ Temp: 28.4°C       │ ├─ Texte [Textarea]   │
│ ├─ pH: 6.8            │ └─ Envoyer [Btn]      │
│ └─ Azote: 45 mg/kg    │                       │
└───────────────────────┴───────────────────────┘
┌──────────────────────────────────────────────┐
│ 🚁 État de la Flotte                         │
│ ├─ DRONE-001 (paul) → 🟢 Online 95%         │
│ ├─ DRONE-002 (alice) → 🔴 Offline          │
│ └─ DRONE-003 (bob) → 🟡 Maintenance        │
└──────────────────────────────────────────────┘
```

### **Colonne Droite : Communications**
```
┌─────────────────────────┐
│ 💬 Communications       │
├─────────────────────────┤
│ [Recherche planteur 🔍] │
├─────────────────────────┤
│ ✓ paul - Paul Yao       │
│   admin: Bonjour...     │
│                         │
│ □ alice - Alice M.      │
│ □ bob - Bob S.          │
├─────────────────────────┤
│ [Chat Messages...]      │
├─────────────────────────┤
│ [Message Input........] │
└─────────────────────────┘
```

---

## 🔐 Sécurité Implémentée

### **Authentification**
- ✅ Décorateur `@admin_required` sur toutes les routes SOC
- ✅ Tokens SHA-256 pour sessions sécurisées
- ✅ Isolation des flux de données administrateurs (Protocole RELYAS)

### **Validation des Données**
- ✅ Vérification des droits utilisateur
- ✅ Sanitisation des entrées HTML
- ✅ Validation des formats de données

---

## 📡 Routes API Disponibles

### **Routes Statistiques**
```
GET /get_dashboard_stats
└─ Retourne: total_farmers, total_drones, online_drones, 
              active_alerts, critical_alerts
```

### **Routes Télémétrie**
```
GET /get_telemetry_data?farmer_username=paul
└─ Retourne: données capteurs en temps réel

POST /post_sensor_data
└─ Reçoit: données des drones
```

### **Routes Alertes**
```
GET /get_alerts?severity=critical
└─ Retourne: liste des alertes actives

POST /create_alert
└─ Crée: alerte manuelle avec type et sévérité
```

### **Routes Recommandations (SAD)**
```
POST /send_recommendation
└─ Envoie: recommandation au planteur + message
```

### **Routes Flotte**
```
GET /get_fleet_status
└─ Retourne: état de tous les drones

POST /register_drone
└─ Enregistre: nouveau drone
```

### **Routes Communication**
```
GET /admin_get_users
└─ Retourne: liste des planteurs avec dernier message

POST /admin_send_message
└─ Envoie: message direct au planteur
```

---

## 📊 Modèles de Données

### **SensorData** (Télémétrie)
```python
- id (PK)
- drone_id: String
- farmer_username: String (FK)
- humidity: Float
- temperature: Float
- soil_ph: Float
- soil_moisture: Float
- nitrogen_level: Float
- timestamp: DateTime
```

### **Alert** (Alertes)
```python
- id (PK)
- alert_type: String (epidemic, drought, disease, frost)
- severity: String (critical, high, medium, low)
- farmer_username: String (FK)
- message: Text
- activated: Boolean
- created_at: DateTime
```

### **AdminRecommendation** (SAD)
```python
- id (PK)
- admin_username: String (FK)
- farmer_username: String (FK)
- content: Text
- based_on_sensor_data: Boolean
- created_at: DateTime
- read: Boolean
```

### **DroneFleet** (Gestion Flotte)
```python
- id (PK)
- drone_id: String (unique)
- farmer_username: String (FK)
- status: String (online, offline, maintenance)
- battery_level: Float
- location: String
- last_connection: DateTime
```

---

## 🚀 Démarrer l'Application

```bash
# Depuis le terminal
cd "c:\Users\Asnam.Ba\Desktop\GAÏA_CONSEIL V.0"
python app.py

# Accéder à RELYAS ADMIN
# 1. Aller sur http://localhost:5000
# 2. Cliquer "Se connecter"
# 3. Entrer les identifiants admin: admin / 123
# 4. Accès automatique à RELYAS ADMIN
```

---

## 📱 Flux de Communication (Polling Optimisé)

**Temps de réponse cible : < 3 secondes**

```
Admin (RELYAS)          Planteur (Interface)
    │                           │
    ├─ Envoie recommandation    │
    ├──────────────────────────>│
    │                           ├─ Reçoit (< 1s)
    │                           │
    │                    Planteur chérifie
    │                           │
    │      Planteur répond       │
    │<──────────────────────────┤
    │                           │
    ├─ Reçoit (< 3s)            │
    │                           │
```

---

## ✨ Valeur Ajoutée

1. **Centralisation** : Un seul expert pour superviser des centaines d'hectares
2. **Réactivité** : Du diagnostic à l'action en quelques minutes
3. **Traçabilité** : Historique complet de toutes les interactions
4. **Intelligence** : Recommandations basées sur des données réelles
5. **Scalabilité** : Architecture prête pour des milliers de capteurs

---

## 📝 Exemple d'Utilisation

### **Scénario : Alerte Sécheresse**

1. **Détection** : Capteur détecte humidité sol < 30%
2. **Alerte** : Admin reçoit notification CRITIQUE
3. **Analyse** : Admin consulte télémétrie + historique
4. **Décision** : Admin rédige recommandation (« Augmenter irrigation »)
5. **Action** : Planteur reçoit recommandation en < 3 secondes
6. **Suivi** : Historique complet enregistré dans la base de données

---

## 🔄 Synchronisation Automatique

- Stats: mise à jour toutes les **3 secondes**
- Alertes: vérification continu
- Télémétrie: mise à jour à chaque envoi de drone
- Messages: polling continu

---

## 📞 Support

Pour des questions sur RELYAS ADMIN ou des améliorations, consultez les fichiers:
- `app.py` : Backend Flask
- `templates/admin_dashboard.html` : Interface SOC
- `static/` : Assets statiques

**Status**: ✅ Production Ready
**Version**: 1.0
**Dernière mise à jour**: 28 Avril 2026
