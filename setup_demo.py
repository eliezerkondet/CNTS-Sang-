#!/usr/bin/env python
"""
Script de configuration initiale de la base de données CNTS Brazzaville
Lance ce script avec: python setup_demo.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'banque_sang.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.contrib.auth import get_user_model
from blood_bank.models import (
    Utilisateur, Donneur, PocheSang, Configuration,
    DemandeTransfusion, MessageIEC
)
from datetime import date, timedelta
import random

User = get_user_model()

def create_users():
    print("👤 Création des utilisateurs...")
    users_data = [
        {'username': 'admin', 'password': 'admin123', 'role': 'admin',
         'first_name': 'Admin', 'last_name': 'CNTS', 'is_superuser': True, 'is_staff': True},
        {'username': 'medecin1', 'password': 'medecin123', 'role': 'medecin',
         'first_name': 'Dr. Pierre', 'last_name': 'MOUKASSA', 'telephone': '+242068001111'},
        {'username': 'infirmier1', 'password': 'infirmier123', 'role': 'infirmier',
         'first_name': 'Marie', 'last_name': 'LOEMBA', 'telephone': '+242068002222'},
        {'username': 'technicien1', 'password': 'technicien123', 'role': 'technicien',
         'first_name': 'Jean', 'last_name': 'BOUANGA', 'telephone': '+242068003333'},
        {'username': 'gestionnaire1', 'password': 'gestionnaire123', 'role': 'gestionnaire',
         'first_name': 'Cécile', 'last_name': 'NZINGA', 'telephone': '+242068004444'},
        {'username': 'prescripteur1', 'password': 'prescripteur123', 'role': 'prescripteur',
         'first_name': 'Dr. Samuel', 'last_name': 'MBEMBA', 'telephone': '+242068005555'},
    ]
    for data in users_data:
        if not User.objects.filter(username=data['username']).exists():
            is_super = data.pop('is_superuser', False)
            is_staff = data.pop('is_staff', False)
            password = data.pop('password')
            user = User(**data)
            user.set_password(password)
            user.is_superuser = is_super
            user.is_staff = is_staff
            user.centre_ref = "Centre National de Transfusion Sanguine"
            user.save()
            print(f"  ✓ {user.username} ({user.get_role_display()})")

def create_config():
    print("⚙️ Configuration du système...")
    config, created = Configuration.objects.get_or_create(pk=1)
    config.prix_standard = 25000
    config.prix_reduit = 0
    config.seuil_credits = 3
    config.seuil_alerte_stock = 10
    config.save()
    print("  ✓ Config: 25 000 FCFA standard, seuil 10 poches")

def create_donneurs():
    print("🩸 Création des donneurs de démonstration...")
    donneurs_data = [
        {'nom': 'Alain MABIALA', 'sexe': 'M', 'naissance': date(1990, 3, 15),
         'tel': '+242068100001', 'groupe': 'O+', 'type': 'benevole',
         'lat': -4.2634, 'lon': 15.2429, 'quartier': 'Centre-ville'},
        {'nom': 'Pauline NGOMA', 'sexe': 'F', 'naissance': date(1995, 7, 22),
         'tel': '+242068100002', 'groupe': 'A+', 'type': 'benevole',
         'lat': -4.2800, 'lon': 15.2600, 'quartier': 'Bacongo'},
        {'nom': 'Robert MOUKOURI', 'sexe': 'M', 'naissance': date(1985, 11, 8),
         'tel': '+242068100003', 'groupe': 'B+', 'type': 'familial',
         'lat': -4.2450, 'lon': 15.2200, 'quartier': 'Poto-Poto'},
        {'nom': 'Christelle BATOU', 'sexe': 'F', 'naissance': date(1992, 1, 30),
         'tel': '+242068100004', 'groupe': 'AB+', 'type': 'benevole',
         'lat': -4.3100, 'lon': 15.2700, 'quartier': 'Makélékélé'},
        {'nom': 'Emmanuel LOUBAKI', 'sexe': 'M', 'naissance': date(1988, 6, 12),
         'tel': '+242068100005', 'groupe': 'O-', 'type': 'benevole',
         'lat': -4.2900, 'lon': 15.2400, 'quartier': 'Moungali'},
        {'nom': 'Nadège KIMPOUNI', 'sexe': 'F', 'naissance': date(1998, 9, 5),
         'tel': '+242068100006', 'groupe': 'A-', 'type': 'benevole',
         'lat': -4.2700, 'lon': 15.2800, 'quartier': 'Ouenzé'},
        {'nom': 'Gilles MABANZA', 'sexe': 'M', 'naissance': date(1983, 4, 18),
         'tel': '+242068100007', 'groupe': 'B-', 'type': 'familial',
         'lat': -4.2550, 'lon': 15.2350, 'quartier': 'Talangaï'},
        {'nom': 'Flore NKODIA', 'sexe': 'F', 'naissance': date(1993, 12, 25),
         'tel': '+242068100008', 'groupe': 'AB-', 'type': 'benevole',
         'lat': -4.3200, 'lon': 15.2550, 'quartier': 'Mfilou'},
        {'nom': 'Patrick TATY', 'sexe': 'M', 'naissance': date(1975, 8, 10),
         'tel': '+242068100009', 'groupe': 'O+', 'type': 'benevole',
         'lat': -4.2350, 'lon': 15.2650, 'quartier': 'Djiri'},
        {'nom': 'Sylvie BITSIEKI', 'sexe': 'F', 'naissance': date(1987, 2, 14),
         'tel': '+242068100010', 'groupe': 'A+', 'type': 'benevole',
         'lat': -4.2650, 'lon': 15.2500, 'quartier': 'Centre-ville'},
    ]

    for d in donneurs_data:
        if not Donneur.objects.filter(telephone=d['tel']).exists():
            donneur = Donneur(
                nom_complet=d['nom'], sexe=d['sexe'],
                date_naissance=d['naissance'], poids=random.randint(55, 90),
                telephone=d['tel'], groupe_sanguin=d['groupe'],
                type_donneur=d['type'], actif=True,
                latitude=d['lat'] + random.uniform(-0.02, 0.02),
                longitude=d['lon'] + random.uniform(-0.02, 0.02),
                quartier=d['quartier'],
                credit_solidaire=random.randint(0, 8),
            )
            donneur.save()
            print(f"  ✓ {donneur.nom_complet} ({donneur.groupe_sanguin})")

def create_poches():
    print("💉 Création de poches de sang de démonstration...")
    donneurs = list(Donneur.objects.all())
    statuts = ['disponible', 'disponible', 'disponible', 'en_analyse', 'utilisee']

    for i in range(30):
        donneur = random.choice(donneurs)
        date_prel = date.today() - timedelta(days=random.randint(1, 30))
        statut = random.choice(statuts)

        if not PocheSang.objects.filter(donneur=donneur, date_prelevement=date_prel).exists():
            poche = PocheSang(
                donneur=donneur,
                date_prelevement=date_prel,
                date_expiration=date_prel + timedelta(days=42),
                groupe_sanguin=donneur.groupe_sanguin,
                statut=statut,
                volume_ml=450,
            )
            if statut != 'en_analyse':
                poche.test_vih = True
                poche.test_hepatite = True
                poche.test_syphilis = True
            poche.save()

    print(f"  ✓ {PocheSang.objects.count()} poches créées")

def create_demandes():
    print("📋 Création de demandes de transfusion...")
    hopitaux = [
        "CHU de Brazzaville", "Hôpital Général de Loandjili",
        "Clinique Ngaliema", "Centre Hospitalier de Base de Makélékélé",
        "Hôpital de la Base Navale",
    ]
    groupes = ['O+', 'A+', 'B+', 'AB+', 'O-']
    prescripteur = Utilisateur.objects.filter(role='prescripteur').first()

    for i in range(5):
        DemandeTransfusion.objects.create(
            hopital=random.choice(hopitaux),
            medecin=f"Dr. Médecin {i+1}",
            groupe_requis=random.choice(groupes),
            quantite=random.randint(1, 4),
            urgence=random.choice(['normal', 'urgent', 'critique']),
            prix_final=25000 * random.randint(1, 4),
            statut_demande=random.choice(['en_attente', 'preparee', 'livree']),
            prescripteur=prescripteur,
            compatibilite_verifiee=True,
            disponibilite_verifiee=True,
        )
    print(f"  ✓ {DemandeTransfusion.objects.count()} demandes créées")

def create_messages():
    print("📱 Création de messages IEC...")
    admin = Utilisateur.objects.filter(role='admin').first()
    messages_data = [
        {
            'titre': 'Campagne Don de Sang Brazzaville',
            'contenu': 'Donnez votre sang, sauvez des vies! Le CNTS Brazzaville a besoin de vous. Venez donner ce samedi, Ave. des 3 Martyrs. Groupe O- et A- urgents!',
            'cible': 'tous',
        },
        {
            'titre': 'Rappel donneurs inactifs',
            'contenu': 'Vous n\'avez pas donné depuis 6 mois. Votre don peut sauver jusqu\'à 3 vies! CNTS Brazzaville vous attend. Tel: +242 06 XXX XXXX',
            'cible': 'inactifs',
        },
    ]
    for m in messages_data:
        if not MessageIEC.objects.filter(titre=m['titre']).exists():
            MessageIEC.objects.create(
                titre=m['titre'],
                contenu=m['contenu'],
                cible=m['cible'],
                type_message='sms',
                createur=admin,
            )
    print(f"  ✓ {MessageIEC.objects.count()} messages créés")

if __name__ == '__main__':
    print("\n🩸 === CNTS Brazzaville - Setup Base de Données ===\n")
    create_config()
    create_users()
    create_donneurs()
    create_poches()
    create_demandes()
    create_messages()
    print("\n✅ Setup terminé!")
    print("\n🔑 Connexions:")
    print("   Admin:        admin / admin123")
    print("   Médecin:      medecin1 / medecin123")
    print("   Infirmier:    infirmier1 / infirmier123")
    print("   Technicien:   technicien1 / technicien123")
    print("   Gestionnaire: gestionnaire1 / gestionnaire123")
    print("\n🌍 Serveur: python manage.py runserver")
    print("   URL:     http://127.0.0.1:8000/\n")