# CNTS Banque de Sang - Système de Gestion

Système complet de gestion de banque de sang pour le Centre National de Transfusion Sanguine (CNTS) de Brazzaville, Congo.

## 🩸 Fonctionnalités

### Gestion des donneurs
- Enregistrement des donneurs avec géolocalisation
- Classification donneur/non-donneur
- Identification des donneurs à risque
- Examen médical complet (10 critères)
- Génération de carte donneur avec QR code (réservé au Directeur)

### Gestion des poches de sang
- 4 types de produits sanguins (Sang total, Culot érythrocytaire, Culot plaquettaire, Cryoprécipité)
- Tests médicaux complets (10 tests)
- Suivi des dates d'expiration
- Alertes automatiques de stock
- Gestion du stock en temps réel

### Demandes de transfusion
- Compatibilité sanguine stricte (groupe identique)
- Gestion des prix (standard, solidaire, personnalisé)
- Traçabilité complète (du prélèvement à la livraison)
- Système d'urgence (normal/urgent/critique)

### Communication
- Envoi de SMS avec Africa's Talking
- Interface USSD pour les donneurs
- Campagnes d'information IEC

### Géolocalisation
- Carte interactive des donneurs
- Localisation des hôpitaux partenaires
- Itinéraires et distances

## 📋 Prérequis

- Python 3.10+
- Django 6.0+
- SQLite3 (par défaut)
- Compte Africa's Talking (pour les SMS)

## 🚀 Installation

1. **Cloner le dépôt**
```bash
git clone https://github.com/YOUR_USERNAME/banque-sang-cnts.git
cd banque-sang-cnts