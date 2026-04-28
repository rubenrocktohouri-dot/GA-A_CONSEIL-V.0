# 🚁 Guide d'Intégration Drones - Protocole RELYAS

Ce document explique comment intégrer des drones et des capteurs au système RELYAS ADMIN.

---

## 🔌 API d'Enregistrement des Drones

### **1. Enregistrer un Drone**

**Endpoint :** `POST /register_drone`

```json
{
  "drone_id": "DRONE-001",
  "farmer_username": "paul",
  "location": "Zone A - Plantations Nord"
}
```

**Réponse (succès):**
```json
{
  "success": true,
  "drone_id": "DRONE-001"
}
```

**Réponse (erreur):**
```json
{
  "success": false,
  "message": "Données manquantes"
}
```

---

## 📡 API de Télémétrie

### **2. Envoyer les Données des Capteurs**

**Endpoint :** `POST /post_sensor_data`

```json
{
  "drone_id": "DRONE-001",
  "farmer_username": "paul",
  "humidity": 65.5,
  "temperature": 28.4,
  "soil_ph": 6.8,
  "soil_moisture": 45.2,
  "nitrogen_level": 42.0
}
```

**Réponse (succès):**
```json
{
  "success": true,
  "message": "Données enregistrées"
}
```

**Réponse (erreur):**
```json
{
  "success": false,
  "message": "Données manquantes"
}
```

---

## 📊 Récupérer les Données

### **3. Récupérer la Télémétrie**

**Endpoint :** `GET /get_telemetry_data?farmer_username=paul`

**Réponse:**
```json
{
  "drone_id": "DRONE-001",
  "humidity": 65.5,
  "temperature": 28.4,
  "soil_ph": 6.8,
  "soil_moisture": 45.2,
  "nitrogen_level": 42.0,
  "timestamp": "2026-04-28 14:30:00"
}
```

### **4. Récupérer l'État de la Flotte**

**Endpoint :** `GET /get_fleet_status`

**Réponse:**
```json
[
  {
    "drone_id": "DRONE-001",
    "farmer_username": "paul",
    "status": "online",
    "battery_level": 95.0,
    "location": "Zone A - Plantations Nord",
    "last_connection": "2026-04-28 14:30:00"
  },
  {
    "drone_id": "DRONE-002",
    "farmer_username": "alice",
    "status": "offline",
    "battery_level": 20.0,
    "location": "Zone B - Plantations Sud",
    "last_connection": "2026-04-28 12:15:00"
  }
]
```

---

## 🚨 API des Alertes

### **5. Créer une Alerte Manuelle**

**Endpoint :** `POST /create_alert`
**Accès :** Admin uniquement

```json
{
  "farmer_username": "paul",
  "alert_type": "drought",
  "severity": "critical",
  "message": "Attention ! Humidité du sol très basse, irrigation urgente recommandée."
}
```

**Réponse (succès):**
```json
{
  "success": true,
  "alert_id": 1
}
```

**Réponse (erreur):**
```json
{
  "success": false,
  "message": "Niveau de sévérité invalide"
}
```

### **6. Récupérer les Alertes Actives**

**Endpoint :** `GET /get_alerts?severity=critical`
**Accès :** Admin uniquement

**Réponse:**
```json
[
  {
    "id": 1,
    "alert_type": "drought",
    "severity": "critical",
    "farmer_username": "paul",
    "message": "Attention ! Humidité du sol très basse...",
    "created_at": "2026-04-28 14:30:00"
  }
]
```

---

## 💡 API Recommandations (SAD)

### **7. Envoyer une Recommandation**

**Endpoint :** `POST /send_recommendation`
**Accès :** Admin uniquement

```json
{
  "farmer_username": "paul",
  "content": "Selon les données actuelles : humidité 45%, augmenter irrigation de 20% pour 2 heures. Vérifier drainage après."
}
```

**Réponse (succès):**
```json
{
  "success": true
}
```

**Réponse (erreur):**
```json
{
  "success": false,
  "message": "Planteur introuvable"
}
```

---

## 💬 API Recommandations pour Planteurs

### **8. Récupérer ses Recommandations**

**Endpoint :** `GET /get_farmer_recommendations`
**Accès :** Planteur uniquement (session required)

**Réponse:**
```json
[
  {
    "id": 1,
    "admin_username": "admin",
    "content": "Selon les données actuelles : humidité 45%...",
    "created_at": "2026-04-28 14:30:00"
  }
]
```

---

## 📱 Exemple d'Intégration Python (Pour Drones)

```python
import requests
import time
import random
from datetime import datetime

BASE_URL = "http://localhost:5000"

# Configuration du drone
DRONE_ID = "DRONE-PROTOTYPE-001"
FARMER_USERNAME = "paul"
LOCATION = "Zone Test - Parcelle 1"

def register_drone():
    """Enregistrer le drone auprès de RELYAS"""
    response = requests.post(f"{BASE_URL}/register_drone", json={
        "drone_id": DRONE_ID,
        "farmer_username": FARMER_USERNAME,
        "location": LOCATION
    })
    return response.json()

def send_sensor_data():
    """Envoyer les données des capteurs"""
    data = {
        "drone_id": DRONE_ID,
        "farmer_username": FARMER_USERNAME,
        "humidity": random.uniform(50, 80),
        "temperature": random.uniform(25, 35),
        "soil_ph": random.uniform(6.5, 7.5),
        "soil_moisture": random.uniform(30, 70),
        "nitrogen_level": random.uniform(30, 60)
    }
    response = requests.post(f"{BASE_URL}/post_sensor_data", json=data)
    return response.json()

def main():
    print(f"🚁 Drone {DRONE_ID} - Initialisation RELYAS")
    
    # Enregistrement
    result = register_drone()
    print(f"✓ Enregistrement: {result}")
    
    # Boucle d'envoi de données
    print("\n📡 Envoi des données capteurs...")
    for i in range(5):
        result = send_sensor_data()
        print(f"  {i+1}. {result}")
        time.sleep(5)

if __name__ == "__main__":
    main()
```

---

## 🔄 Flux Complet : Exemple Scénario

### **1. Initialisation**
```bash
POST /register_drone
→ Drone DRONE-001 enregistré
```

### **2. Collecte de Données**
```bash
POST /post_sensor_data (répété)
→ Toutes les 5-10 minutes
```

### **3. Admin Supervise**
```bash
GET /get_telemetry_data?farmer_username=paul
→ Données en temps réel affichées
```

### **4. Alerte Détectée**
```bash
GET /get_alerts
→ Admin voit sécheresse critique
```

### **5. Admin Intervient**
```bash
POST /send_recommendation
→ Planteur reçoit recommandation < 3 secondes
```

### **6. Planteur Répond**
```bash
POST /send_message
→ Admin voit réponse immédiatement
```

---

## ⚙️ Configuration Recommandée

### **Intervalle d'Envoi des Données**

| Situation | Intervalle |
|-----------|-----------|
| Normal | 10 minutes |
| Alerte Moyenne | 2 minutes |
| Alerte Critique | 30 secondes |
| Batterie < 20% | 30 minutes |

### **Authentification API**

Toutes les routes sont sécurisées :
- Routes admin : Nécessitent une session admin valide
- Routes publiques : `/register_drone`, `/post_sensor_data`, `/get_farmer_recommendations`
- Routes privées : Toutes les autres

---

## 🛡️ Bonnes Pratiques

1. ✅ **Valider les données** avant envoi
2. ✅ **Gérer les erreurs réseau** avec retry logic
3. ✅ **Respecter les limites** de fréquence d'envoi
4. ✅ **Logger les erreurs** pour debugging
5. ✅ **Utiliser HTTPS** en production
6. ✅ **Implémenter des tokens** d'authentification

---

## 🐛 Troubleshooting

### **"Planteur introuvable"**
- Vérifier que `farmer_username` existe dans la base de données
- Planteur doit être enregistré dans le système d'abord

### **"Données enregistrées" mais rien n'apparaît**
- Vérifier que le drone_id est correct
- Vérifier les permissions d'accès
- Consulter les logs du serveur Flask

### **Latence > 3 secondes**
- Vérifier la connexion réseau
- Réduire la fréquence de polling
- Vérifier les performances du serveur

---

## 📞 Endpoints Résumé

| Méthode | Endpoint | Accès | Description |
|---------|----------|-------|-------------|
| POST | `/register_drone` | Public | Enregistrer drone |
| POST | `/post_sensor_data` | Public | Envoyer télémétrie |
| GET | `/get_telemetry_data` | Admin | Récupérer données |
| GET | `/get_fleet_status` | Admin | État flotte |
| POST | `/create_alert` | Admin | Créer alerte |
| GET | `/get_alerts` | Admin | Récupérer alertes |
| POST | `/send_recommendation` | Admin | Recommandation |
| GET | `/get_farmer_recommendations` | Planteur | Récupérer recommandations |

---

**Version API:** 1.0
**Date:** 28 Avril 2026
**Status:** Production Ready ✅
