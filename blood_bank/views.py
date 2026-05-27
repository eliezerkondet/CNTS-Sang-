from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.mail import send_mail
from .models import PreEnregistrementDonneur


import json 
import qrcode
from io import BytesIO
import base64
from datetime import timedelta
from .models import Hopital
from .models import (
    Utilisateur, Donneur, PocheSang, DemandeTransfusion,
    Configuration, MessageIEC, AlerteStock, LogSMS,
    CarteDonneur, VisiteurCNTS, Hopital,
    TracabiliteEvenement, CandidatDon
)
from .forms import (
    LoginForm, DonneurForm, PocheSangForm, AnalysePocheForm,
    DemandeTransfusionForm, MessageIECForm, ConfigurationForm,
    UtilisateurForm
)
from .sms_service import (
    envoyer_sms, envoyer_sms_campagne, envoyer_notification_don,
    envoyer_alerte_stock, envoyer_confirmation_demande, handle_ussd
)


# ============================================================
# DÉCORATEUR RÔLES
# Règle simple : admin ne passe QUE là où 'admin' est listé
# ============================================================

def role_required(*roles):
    def decorator(view_func):
        @login_required
        def wrapper(request, *args, **kwargs):
            user_role = 'admin' if request.user.is_superuser else request.user.role
            if user_role in roles:
                return view_func(request, *args, **kwargs)
            messages.error(request, "Accès non autorisé pour votre rôle.")
            return redirect('dashboard')
        return wrapper
    return decorator


# ============================================================
# AUTHENTIFICATION
# ============================================================

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, f"Bienvenue, {user.get_full_name() or user.username}!")
        return redirect(request.GET.get('next', 'dashboard'))
    return render(request, 'blood_bank/login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


# ============================================================
# DASHBOARD — tous les rôles voient les chiffres globaux
# ============================================================

@login_required
def dashboard(request):
    today = timezone.now().date()
    config = Configuration.get_config()

    stats = {
        'total_donneurs': Donneur.objects.count(),
        'dons_mois': PocheSang.objects.filter(
            date_prelevement__month=today.month,
            date_prelevement__year=today.year
        ).count(),
        'poches_disponibles': PocheSang.objects.filter(statut='disponible').count(),
        'demandes_en_attente': DemandeTransfusion.objects.filter(
            statut_demande='en_attente'
        ).count(),
        'alertes_actives': AlerteStock.objects.filter(resolue=False).count(),
    }

    groupes = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
    stock_par_groupe = []
    for groupe in groupes:
        count = PocheSang.objects.filter(
            groupe_sanguin=groupe, statut='disponible'
        ).count()
        stock_par_groupe.append({
            'groupe': groupe, 'count': count,
            'critique': count <= config.seuil_alerte_stock,
        })

    stats_stock = {}
    for type_code, type_label in PocheSang.TYPE_PRODUIT_CHOICES:
        stats_stock[type_code] = PocheSang.objects.filter(
            type_produit=type_code, statut='disponible'
        ).count()

    dons_semaine = []
    for i in range(6, -1, -1):
        jour = today - timedelta(days=i)
        count = PocheSang.objects.filter(date_prelevement=jour).count()
        dons_semaine.append({'jour': jour.strftime('%d/%m'), 'count': count})

    demandes_recentes = DemandeTransfusion.objects.order_by('-date_demande')[:5]
    alertes = AlerteStock.objects.filter(resolue=False).order_by('-date_alerte')[:5]

    return render(request, 'blood_bank/dashboard.html', {
        'stats': stats,
        'stock_par_groupe': stock_par_groupe,
        'stats_stock': stats_stock,
        'demandes_recentes': demandes_recentes,
        'alertes': alertes,
        'dons_semaine': json.dumps(dons_semaine),
        'config': config,
        'user_role': request.user.role,
    })


# ============================================================
# DONNEURS
# Médecin : inscrit, examine, attribue résultats
# Directeur : voit seulement
# Admin : BLOQUÉ (confidentialité)
# ============================================================

@login_required
@role_required('medecin', 'infirmier', 'directeur', 'technicien', 'gestionnaire', 'responsable', 'prescripteur')
def donneur_list(request):
    q = request.GET.get('q', '')
    groupe = request.GET.get('groupe', '')
    donneurs = Donneur.objects.all()
    if q:
        donneurs = donneurs.filter(
            Q(nom_complet__icontains=q) |
            Q(code_unique__icontains=q) |
            Q(telephone__icontains=q)
        )
    if groupe:
        donneurs = donneurs.filter(groupe_sanguin=groupe)
    config = Configuration.get_config()
    return render(request, 'blood_bank/donneurs/list.html', {
        'donneurs': donneurs.order_by('-date_inscription'),
        'q': q, 'groupe': groupe,
        'groupes': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
        'is_directeur': request.user.role in ['directeur'],
        'config': config,
    })


@login_required
@role_required('medecin', 'infirmier', 'directeur', 'technicien', 'gestionnaire', 'responsable')
def donneur_detail(request, pk):
    donneur = get_object_or_404(Donneur, pk=pk)
    poches = PocheSang.objects.filter(donneur=donneur).order_by('-date_prelevement')
    carte = getattr(donneur, 'carte', None)
    return render(request, 'blood_bank/donneurs/detail.html', {
        'donneur': donneur, 'poches': poches, 'carte': carte,
        'peut_voir_examen': request.user.role in ['medecin', 'directeur'],
        'peut_modifier_examen': request.user.role == 'medecin',
        'is_directeur': request.user.role == 'directeur',
        'centre_lat': getattr(settings, 'CENTRE_LATITUDE', -4.2634),
        'centre_lon': getattr(settings, 'CENTRE_LONGITUDE', 15.2429),
    })


@login_required
@role_required( 'infirmier')
def donneur_create(request):
    form = DonneurForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        donneur = form.save(commit=False)
        donneur.enregistre_par = request.user
        donneur.save()
        try:
            envoyer_sms(donneur.telephone,
                f"Bienvenue {donneur.nom_complet.split()[0]} au CNTS! "
                f"Code: {donneur.code_unique}. Merci!")
        except Exception:
            pass
        messages.success(request, f"✅ Donneur {donneur.nom_complet} enregistré!")
        return redirect('donneur_detail', pk=donneur.pk)
    return render(request, 'blood_bank/donneurs/form.html', {
        'form': form, 'title': 'Nouveau Donneur'
    })


@login_required
@role_required('medecin', 'infirmier')
def donneur_edit(request, pk):
    donneur = get_object_or_404(Donneur, pk=pk)
    form = DonneurForm(request.POST or None, request.FILES or None, instance=donneur)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Informations mises à jour.")
        return redirect('donneur_detail', pk=pk)
    return render(request, 'blood_bank/donneurs/form.html', {
        'form': form, 'title': 'Modifier Donneur', 'donneur': donneur
    })


@login_required
@role_required('medecin', 'infirmier', 'directeur', 'gestionnaire')
def donneur_carte(request):
    donneurs = Donneur.objects.filter(
        latitude__isnull=False, longitude__isnull=False
    )
    data = []
    for d in donneurs:
        data.append({
            'id': d.pk, 'nom': d.nom_complet,
            'groupe': d.groupe_sanguin or '?',
            'lat': float(d.latitude), 'lon': float(d.longitude),
            'quartier': getattr(d, 'quartier', ''),
            'peut_donner': d.peut_donner(),
        })
    return render(request, 'blood_bank/donneurs/carte.html', {
        'donneurs_json': json.dumps(data),
        'centre_lat': getattr(settings, 'CENTRE_LATITUDE', -4.2634),
        'centre_lon': getattr(settings, 'CENTRE_LONGITUDE', 15.2429),
        'total_donneurs': len(data),
    })


# ============================================================
# RECHERCHE MÉDICALE — Médecin cherche donneur ou poche
# ============================================================

@login_required
@role_required('medecin', 'technicien')
def recherche_medicale(request):
    q = request.GET.get('q', '').strip()
    resultats_donneurs = []
    resultats_poches = []
    if q:
        resultats_donneurs = Donneur.objects.filter(
            Q(nom_complet__icontains=q) |
            Q(code_unique__icontains=q) |
            Q(telephone__icontains=q) |
            Q(groupe_sanguin__icontains=q)
        )[:10]
        resultats_poches = PocheSang.objects.filter(
            Q(code_barre__icontains=q) |
            Q(donneur__nom_complet__icontains=q) |
            Q(donneur__code_unique__icontains=q) |
            Q(groupe_sanguin__icontains=q)
        ).select_related('donneur')[:10]
    return render(request, 'blood_bank/donneurs/recherche_medicale.html', {
        'q': q,
        'resultats_donneurs': resultats_donneurs,
        'resultats_poches': resultats_poches,
    })


# ============================================================
# EXAMEN MÉDICAL — Médecin fait, Directeur voit
# ============================================================

@login_required
@role_required('medecin', 'directeur')
def examen_en_attente(request):
    """Liste des donneurs en attente d'examen médical"""
    
    # 1. Ceux qui n'ont pas encore d'examen médical du tout
    donneurs_sans_examen = Donneur.objects.filter(
        examen_medical__isnull=True
    ).order_by('-date_inscription')

    # 2. Ceux qui ont passé l'examen mais qui sont inactifs (inaptes)
    donneurs_inaptes = Donneur.objects.filter(
        examen_medical__isnull=False,
        actif=False
    ).order_by('-date_inscription')

    return render(request, 'blood_bank/donneurs/examens_attente.html', {
        'donneurs_sans_examen': donneurs_sans_examen,
        'donneurs_inaptes': donneurs_inaptes,
    })

@login_required
@role_required('medecin')
def examen_medical_create(request, pk):
    donneur = get_object_or_404(Donneur, pk=pk)
    
    # On crée un faux objet 'examen' juste pour que le HTML ne plante pas 
    # s'il cherche à afficher des valeurs existantes
    examen_existant = donneur 

    if request.method == 'POST':
        # 1. On lit les réponses du formulaire SANS les sauvegarder dans la table Donneur
        tension_ok = request.POST.get('tension_ok') == 'on'
        poids_ok = request.POST.get('poids_ok') == 'on'
        hemoglobine_ok = request.POST.get('hemoglobine_ok') == 'on'
        pas_fievre = request.POST.get('pas_fievre') == 'on'
        pas_de_maladie = request.POST.get('pas_de_maladie') == 'on'
        pas_de_medicament = request.POST.get('pas_de_medicament') == 'on'
        pas_tuberculose = request.POST.get('pas_tuberculose') == 'on'
        pas_antecedents_risque = request.POST.get('pas_antecedents_risque') == 'on'
        
        motif = request.POST.get('motif_inaptitude', '').strip()
        
        # 2. Le médecin peut pré-estimer le groupe sanguin (Ça oui, ça va dans la base)
        groupe_examen = request.POST.get('groupe_sanguin_examen', '').strip()
        if groupe_examen and not donneur.groupe_sanguin:
            donneur.groupe_sanguin = groupe_examen

        # 3. ÉVALUATION DIRECTE DANS LA VUE (Plus besoin de fonction dans le modèle !)
        apte = all([
            tension_ok, poids_ok, hemoglobine_ok, pas_fievre, 
            pas_de_maladie, pas_de_medicament, pas_tuberculose, pas_antecedents_risque
        ])

        # 4. On met à jour le statut officiel du donneur
        if apte:
            donneur.statut_inscription = 'apte' # Le bon champ de ta table Donneur
            messages.success(request, f"✅ {donneur.nom_complet} est APTE. Passez au prélèvement.")
            # Le SMS si tu as la connexion
            try:
                envoyer_sms(donneur.telephone, f"Bonjour {donneur.nom_complet}, vous êtes apte au don. Merci!")
            except Exception:
                pass
        else:
            donneur.statut_inscription = 'inapte'
            messages.warning(request, f"⚠ {donneur.nom_complet} est INAPTE. Motif: {motif or 'Non précisé'}")
            
        donneur.save()
        return redirect('donneur_detail', pk=pk)

    # L'affichage du formulaire HTML
    return render(request, 'blood_bank/donneurs/examen_medical.html', {
        'donneur': donneur,
        'examen': examen_existant, 
        'groupe_choices': [('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'), ('O+', 'O+'), ('O-', 'O-'), ('AB+', 'AB+'), ('AB-', 'AB-')],
        'is_new': True,
    })



# POCHES DE SANG
# Seul le médecin prélève le SANG TOTAL
# Seul le technicien analyse
# Technicien fractionne
# ============================================================

@login_required
@role_required('medecin', 'technicien', 'gestionnaire', 'directeur', 'responsable')
def poche_list(request):
    statut = request.GET.get('statut', '')
    groupe = request.GET.get('groupe', '')
    type_produit = request.GET.get('type_produit', '')
    q = request.GET.get('q', '')
    today = timezone.now().date()

    poches = PocheSang.objects.select_related('donneur').all()
    
    # Technicien : voit uniquement les poches à analyser
    if request.user.role == 'Technicien de Laboratoire':
        poches = poches.filter(statut__in=['collectee', 'en_analyse'])
    
    if statut:
        poches = poches.filter(statut=statut)
    if groupe:
        poches = poches.filter(groupe_sanguin=groupe)
    if type_produit:
        poches = poches.filter(type_produit=type_produit)
    if q:
        poches = poches.filter(
            Q(code_barre__icontains=q) |
            Q(donneur__nom_complet__icontains=q)
        )
    
    # Marquer les expirées automatiquement
    for p in poches.filter(statut='disponible'):
        if p.est_expiree:
            p.statut = 'expiree'
            p.save()

    # ===== COMPTEURS =====
    total_collectees = PocheSang.objects.filter(statut='collectee').count()
    total_en_analyse = PocheSang.objects.filter(statut='en_analyse').count()
    total_disponibles = PocheSang.objects.filter(statut='disponible').count()
    total_rejetees = PocheSang.objects.filter(statut='rejetee').count()
    total_attribuees = PocheSang.objects.filter(statut='attribuee').count()
    # ====================

    return render(request, 'blood_bank/poches/list.html', {
        'poches': poches.order_by('-date_prelevement'),
        'statut': statut, 'groupe': groupe,
        'type_produit': type_produit, 'q': q,
        'statuts': PocheSang.STATUT_CHOICES,
        'groupes': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
        'types_produit': PocheSang.TYPE_PRODUIT_CHOICES,
        'total_collectees': total_collectees,
        'total_en_analyse': total_en_analyse,
        'total_disponibles': total_disponibles,
        'total_rejetees': total_rejetees,
        'total_attribuees': total_attribuees,
        'total_expirant': PocheSang.objects.filter(
            statut='disponible',
            date_expiration__lte=today + timedelta(days=7)
        ).count(),
    })

@login_required
@role_required('medecin', 'technicien', 'gestionnaire', 'directeur', 'responsable')
def poche_detail(request, pk):
    poche = get_object_or_404(PocheSang, pk=pk)
    return render(request, 'blood_bank/poches/detail.html', {
        'poche': poche,
        'peut_fractionner': (
            request.user.role == 'technicien' and
            poche.type_produit == 'sang_total' and
            poche.statut == 'disponible'
        ),
    })


@login_required
@role_required('infirmier')
def poche_create(request):
    """
    Seul l'infirmier prélève. Type forcé = sang_total uniquement.
    Le fractionnement se fait après en labo par le technicien.
    """
    if request.method == 'POST':
        form = PocheSangForm(request.POST)
        if form.is_valid():
            poche = form.save(commit=False)
            poche.creee_par = request.user
            poche.statut = 'collectee'
            # IMPORTANT : on prélève UNIQUEMENT du sang total
            poche.type_produit = 'sang_total'
            
            if not poche.date_prelevement:
                poche.date_prelevement = timezone.now().date()

            # ===== LIEU DE COLLECTE =====
            lieu = request.POST.get('lieu_collecte')
            if lieu == 'autre':
                lieu = request.POST.get('autre_lieu', 'Autre')
            poche.lieu_collecte = lieu
            # ============================

            # --- VÉRIFICATION DE L'EXAMEN MÉDICAL DU DONNEUR ---
            donneur = poche.donneur
            if donneur and hasattr(donneur, 'examen_medical') and donneur.examen_medical and donneur.examen_medical.resultat != 'apte':
                messages.error(request, "Ce donneur n'est pas apte (examen médical non validé).")
                return redirect('donneur_detail', pk=donneur.pk)
            # -------------------------------------------------

            if poche.donneur and poche.donneur.groupe_sanguin:
                poche.groupe_sanguin = poche.donneur.groupe_sanguin
            poche.save()

            # Incrémenter le donneur
            if donneur:
                donneur.date_dernier_don = poche.date_prelevement
                donneur.credit_solidaire = getattr(donneur, 'credit_solidaire', 0) + 1
                donneur.save(update_fields=['date_dernier_don', 'credit_solidaire'])
                try:
                    envoyer_notification_don(donneur)
                except Exception:
                    pass
                CarteDonneur.generer_si_eligible(donneur)

            # Traçabilité
            TracabiliteEvenement.objects.create(
                poche=poche, etape='prelevement',
                effectue_par=request.user,
                notes='Prélèvement sang total enregistré'
            )

            messages.success(request, f"✅ Poche {poche.code_barre} enregistrée avec succès!")
            return redirect('poche_analyser', pk=poche.pk)
    else:
        form = PocheSangForm()
    
    return render(request, 'blood_bank/poches/form.html', {
        'form': form,
        'title': 'Nouveau prélèvement'
    })


@login_required
@role_required('technicien')
def poche_analyser(request, pk):
    print("=== Vue poche_analyser appelée ===")
    """
    Technicien analyse la poche — 5 tests obligatoires.
    Enregistrement obligatoire même si rejetée (cause enregistrée).
    Groupe sanguin déterminé ici si inconnu.
    """
    poche = get_object_or_404(PocheSang, pk=pk)
    form = AnalysePocheForm(request.POST or None, instance=poche)

    donneur_sans_groupe = (
        not poche.donneur or not poche.donneur.groupe_sanguin
    )

    if request.method == 'POST' and form.is_valid():
        print("=== MÉTHODE POST DÉTECTÉE ===") 
        poche = form.save(commit=False)
        poche.date_analyse = timezone.now()
        poche.biologiste = request.user

        # Groupe sanguin déterminé lors de l'analyse
        groupe_determine = request.POST.get('groupe_sanguin_donneur', '').strip()
        if groupe_determine:
            poche.groupe_sanguin = groupe_determine
            if poche.donneur and not poche.donneur.groupe_sanguin:
                poche.donneur.groupe_sanguin = groupe_determine
                poche.donneur.save()
                messages.info(request,
                    f"🩸 Groupe {groupe_determine} attribué au donneur "
                    f"{poche.donneur.nom_complet}")

        # Vérification des 5 tests
        # False = positif (rejet) | None = pas encore fait | True = négatif (ok)
        tests_echoues = []
        if poche.test_vih is False:
            tests_echoues.append("VIH 1&2")
        if poche.test_hepatite_b is False:
            tests_echoues.append("Hépatite B (HBsAg)")
        if poche.test_hepatite_c is False:
            tests_echoues.append("Hépatite C (Anti-HCV)")
        if poche.test_syphilis is False:
            tests_echoues.append("Syphilis (TPHA/VDRL)")
        if poche.test_paludisme is False:
            tests_echoues.append("Paludisme")
            # ===== GESTION SUSPENSION DONNEUR POUR PALUDISME =====
            messages.warning(request, "⚠️ Test paludisme positif : poche rejetée, donneur suspendu temporairement.")
            if poche.donneur:
                from datetime import timedelta
                poche.donneur.date_suspension_paludisme = timezone.now().date()
                poche.donneur.date_retour_autorise = timezone.now().date() + timedelta(days=180)  # 6 mois
                poche.donneur.actif = False
                poche.donneur.classification = 'suspendu'
                poche.donneur.save()
            else:
                messages.info(request, "Test paludisme positif : informer la personne.")
            # ====================================================

        if tests_echoues:
            # REJET — enregistrement obligatoire avec cause
            poche.statut = 'rejetee'
            poche.save()
            # Supprimer doublons traçabilité puis créer
            TracabiliteEvenement.objects.filter(
                poche=poche, etape='rejet'
            ).delete()
            TracabiliteEvenement.objects.create(
                poche=poche, etape='rejet',
                effectue_par=request.user,
                notes=f"REJET — Tests positifs: {', '.join(tests_echoues)}"
            )
            messages.error(request,
                f"❌ Poche {poche.code_barre} REJETÉE. "
                f"Cause enregistrée: {', '.join(tests_echoues)}")
        else:
            # VALIDATION — tous les tests négatifs
            poche.statut = 'disponible'
            poche.save()
            TracabiliteEvenement.objects.filter(
                poche=poche, etape='validation_stock'
            ).delete()
            TracabiliteEvenement.objects.create(
                poche=poche, etape='validation_stock',
                effectue_par=request.user,
                notes='5 tests négatifs — poche validée et disponible'
            )
            messages.success(request,
                f"✅ Poche {poche.code_barre} DISPONIBLE! "
                f"Tous les 5 tests négatifs.")

        verifier_alertes_stock()
        return redirect('poche_list')

    return render(request, 'blood_bank/poches/analyser.html', {
        'form': form, 'poche': poche,
        'donneur_sans_groupe': donneur_sans_groupe,
        'groupes_sanguins': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
    })


def verifier_alertes_stock():
    try:
        config = Configuration.get_config()
        seuil = config.seuil_alerte_stock
    except:
        seuil = 5

    for type_produit, _ in PocheSang.TYPE_PRODUIT_CHOICES:
        for groupe in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
            count = PocheSang.objects.filter(
                type_produit=type_produit,
                groupe_sanguin=groupe,
                statut='disponible'
            ).count()
            if count <= seuil:
                niveau = 'critical' if count == 0 else 'warning'
                # Utilise update_or_create avec des critères uniques
                alerte, created = AlerteStock.objects.update_or_create(
                    type_produit=type_produit,
                    groupe_sanguin=groupe,
                    resolue=False,
                    defaults={
                        'niveau': niveau,
                        'message': f"Stock {type_produit} {groupe}: {count} poche(s). Seuil: {seuil}",
                        'stock_actuel': count,
                        'seuil': seuil,
                    }
                )
                if created:
                    try:
                        envoyer_alerte_stock(groupe, count, seuil)
                    except:
                        pass
# ============================================================
# FRACTIONNEMENT — Technicien uniquement
# Sang total → culot érythrocytaire + plasma/cryoprécipité
# Plaquettes → pooling de 4-5 poches sang total
# ============================================================



@login_required
@role_required('technicien')
def fractionner_poche(request, pk):
    """
    Le technicien fractionne une poche de sang total disponible.
    La poche source est marquée utilisée.
    Les produits dérivés héritent des tests de la source.
    """
    poche_source = get_object_or_404(PocheSang, pk=pk)

    if poche_source.type_produit != 'sang_total':
        messages.error(request, "❌ Seul le sang total peut être fractionné!")
        return redirect('poche_detail', pk=pk)

    if poche_source.statut != 'disponible':
        messages.error(request, "❌ La poche doit être disponible (tests validés) pour être fractionnée!")
        return redirect('poche_detail', pk=pk)

    if request.method == 'POST':
        types_selectionnes = request.POST.getlist('types_fractionnement')
        if not types_selectionnes:
            messages.error(request, "❌ Sélectionnez au moins un produit à créer.")
            return redirect('fractionner_poche', pk=pk)

        poches_creees = []
        
        # Les volumes exacts
        volumes = {
            'culot_erythrocytaire': 280,
            'plasma_frais_congele': 200,
            'cryoprecipite': 15,
        }
        
        # Les jours de conservation exacts
        conservation = {
            'culot_erythrocytaire': 42,
            'plasma_frais_congele': 365,
            'cryoprecipite': 365,
        }

        for type_produit in types_selectionnes:
            if type_produit == 'sang_total':
                continue
            
            # Bloquer les plaquettes ici (ça se fait dans la vue Pooling)
            if type_produit == 'culot_plaquettaire':
                continue

            # Calcul de la nouvelle date d'expiration
            duree = conservation.get(type_produit, 42)
            nouvelle_date_exp = poche_source.date_prelevement + timedelta(days=duree)

            # Création de la poche dérivée (on copie tous les tests de la mère !)
            poche_derivee = PocheSang.objects.create(
                donneur=poche_source.donneur,
                type_produit=type_produit,
                groupe_sanguin=poche_source.groupe_sanguin,
                date_prelevement=poche_source.date_prelevement,
                date_expiration=nouvelle_date_exp, # La bonne date !
                volume_ml=volumes.get(type_produit, 200), # Le bon volume !
                statut='disponible',
                
                # Héritage obligatoire des tests
                test_vih=poche_source.test_vih,
                test_hepatite_b=poche_source.test_hepatite_b,
                test_hepatite_c=poche_source.test_hepatite_c,
                test_syphilis=poche_source.test_syphilis,
                test_paludisme=poche_source.test_paludisme,
                
                creee_par=request.user,
                notes=f"Fractionnée depuis {poche_source.code_barre}"
            )
            
            # Traçabilité
            TracabiliteEvenement.objects.create(
                poche=poche_derivee,
                etape='validation_stock',
                effectue_par=request.user,
                notes=f"Issue du fractionnement de {poche_source.code_barre}"
            )
            poches_creees.append(poche_derivee.get_type_produit_display())

        if poches_creees:
            # La poche mère est détruite
            poche_source.statut = 'utilisee'
            poche_source.save()
            TracabiliteEvenement.objects.create(
                poche=poche_source,
                etape='livraison',
                effectue_par=request.user,
                notes=f"Fractionnée → {', '.join(poches_creees)}"
            )
            messages.success(request, f"✅ Fractionnement réussi! Produits créés : {', '.join(poches_creees)}")
            verifier_alertes_stock()

        return redirect('poche_list')

    # LE VRAI DICTIONNAIRE MÉDICAL POUR TON HTML
    return render(request, 'blood_bank/poches/fractionner.html', {
        'poche': poche_source,
        'types_disponibles': [
            ('culot_erythrocytaire', '🔴 Culot érythrocytaire (Globules rouges) — 280 mL — 42 jours'),
            ('plasma_frais_congele', '💧 Plasma Frais Congelé (PFC) — 200 mL — 1 an'),
            ('cryoprecipite', '❄️ Cryoprécipité (Facteur VIII) — 15 mL — 1 an'),
        ]
    })
@login_required
@role_required('technicien', 'medecin')
def pooling_plaquettes(request):
    """
    Pooling: 4-5 poches de Sang Total du même groupe → 1 concentré plaquettaire (MCP).
    Expire en 5 jours. Les poches sources sont détruites.
    """
    groupes = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']

    if request.method == 'POST':
        poches_ids = request.POST.getlist('poches_sources')
        
        if len(poches_ids) < 4:
            messages.error(request, "❌ Minimum 4 poches de sang total nécessaires pour le pooling!")
            return redirect('pooling_plaquettes')

        poches = PocheSang.objects.filter(
            pk__in=poches_ids,
            type_produit='sang_total',
            statut='disponible'
        )
        
        if poches.count() < 4:
            messages.error(request, "❌ Poches insuffisantes ou non disponibles!")
            return redirect('pooling_plaquettes')

        groupes_poches = set(poches.values_list('groupe_sanguin', flat=True))
        if len(groupes_poches) > 1:
            messages.error(request, "❌ Toutes les poches doivent avoir le même groupe sanguin!")
            return redirect('pooling_plaquettes')

        groupe = list(groupes_poches)[0]

        # Création du concentré plaquettaire
        from datetime import timedelta
        poche_pool = PocheSang.objects.create(
            # On attribue arbitrairement au premier donneur (règle CNTS classique)
            donneur=poches.first().donneur, 
            type_produit='culot_plaquettaire',
            groupe_sanguin=groupe,
            date_prelevement=timezone.now().date(),
            date_expiration=timezone.now().date() + timedelta(days=5), # Expire très vite (5 jours)
            volume_ml=50 * poches.count(), # Approx 50mL par poche source
            statut='disponible',
            
            # Les tests sont validés car toutes les sources étaient 'disponibles'
            test_vih=True,
            test_hepatite_b=True,
            test_hepatite_c=True,
            test_syphilis=True,
            test_paludisme=True,
            
            creee_par=request.user,
            notes=f"Concentré plaquettaire (MCP) — Pool de {poches.count()} poches sources : {', '.join([p.code_barre for p in poches])}"
        )
        
        # Traçabilité de la nouvelle poche
        TracabiliteEvenement.objects.create(
            poche=poche_pool,
            etape='validation_stock',
            effectue_par=request.user,
            notes=f"Pooling plaquettaire généré à partir de {poches.count()} poches."
        )
        
        # Destruction (utilisation) des poches sources
        for poche in poches:
            poche.statut = 'utilisee'
            poche.save()
            TracabiliteEvenement.objects.create(
                poche=poche,
                etape='livraison', # Ou une étape 'transformation' si tu en as une
                effectue_par=request.user,
                notes=f"Utilisée pour le pooling du MCP : {poche_pool.code_barre}"
            )

        messages.success(request, f"✅ Concentré plaquettaire {poche_pool.code_barre} créé ({groupe}) — Attention, il expire dans 5 jours.")
        verifier_alertes_stock()
        return redirect('poche_list')

    # Affichage du formulaire (GET) : On trie les poches par groupe
    poches_par_groupe = {}
    for groupe in groupes:
        poches_dispo = PocheSang.objects.filter(
            groupe_sanguin=groupe,
            type_produit='sang_total',
            statut='disponible'
        )
        # On n'affiche le groupe que s'il y a assez de poches pour faire un pool
        if poches_dispo.count() >= 4:
            poches_par_groupe[groupe] = poches_dispo

    return render(request, 'blood_bank/poches/pooling.html', {
        'poches_par_groupe': poches_par_groupe,
    })


# ============================================================
# DEMANDES DE TRANSFUSION
# Prescripteur soumet, Responsable/Gestionnaire valide et livre
# Stock décrémente quand poche passe à 'utilisee'
# ============================================================

@login_required
@role_required('prescripteur', 'medecin', 'responsable', 'gestionnaire', 'directeur')
def demande_list(request):
    statut = request.GET.get('statut', '')
    groupe = request.GET.get('groupe', '')
    demandes = DemandeTransfusion.objects.all()
    if statut:
        demandes = demandes.filter(statut_demande=statut)
    if groupe:
        demandes = demandes.filter(groupe_requis=groupe)
    return render(request, 'blood_bank/demandes/list.html', {
        'demandes': demandes.order_by('-date_demande'),
        'statut': statut, 'groupe': groupe,
        'statuts': DemandeTransfusion.STATUT_CHOICES,
        'groupes': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
        'is_directeur': request.user.role == 'directeur',
    })


@login_required
@role_required('prescripteur', 'medecin', 'directeur')
def demande_create(request):
    form = DemandeTransfusionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        demande = form.save(commit=False)
        demande.prescripteur = request.user
        demande.prix_final = demande.calculer_prix()
        demande.save()
        groupes_ok = PocheSang.groupes_donneurs_compatibles(demande.groupe_requis)
        stock = PocheSang.objects.filter(
            type_produit=demande.type_produit,
            groupe_sanguin__in=groupes_ok,
            statut='disponible'
        ).count()
        if stock == 0:
            messages.warning(request,
                f"⚠ Aucun {demande.groupe_requis} disponible en stock!")
        else:
            messages.success(request,
                f"✅ Demande #{demande.pk} enregistrée. "
                f"{stock} poche(s) compatible(s) disponible(s).")
        try:
            envoyer_confirmation_demande(demande)
        except Exception:
            pass
        return redirect('demande_detail', pk=demande.pk)
    return render(request, 'blood_bank/demandes/form.html', {
        'form': form, 'title': 'Nouvelle demande de transfusion',
        'config': Configuration.get_config(),
    })


@login_required
@role_required( 'responsable')
               
def demande_detail(request, pk):
    demande = get_object_or_404(DemandeTransfusion, pk=pk)
    groupes_ok = PocheSang.groupes_donneurs_compatibles(demande.groupe_requis)
    poches_compatibles = []
    if demande.statut_demande in ['en_attente', 'validee']:
        poches_compatibles = PocheSang.objects.filter(
            groupe_sanguin__in=groupes_ok,
            type_produit=demande.type_produit,
            statut='disponible'
        )
    return render(request, 'blood_bank/demandes/detail.html', {
        'demande': demande,
        'poches_compatibles': poches_compatibles,
        'groupe_choices': DemandeTransfusion.GROUPE_CHOICES, 
        'is_directeur': request.user.role == 'directeur',
    })

@login_required
@role_required('gestionnaire', 'responsable', 'directeur')
def demande_traiter(request, pk):
    """
    Responsable/Gestionnaire valide et attribue les poches.
    Le stock décrémente quand les poches passent à 'attribuee' puis 'utilisee'.
    """
    demande = get_object_or_404(DemandeTransfusion, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'valider':
            poches_ids = request.POST.getlist('poches')
            groupe_patient = request.POST.get('groupe_patient_verifie', '').strip()
            if not groupe_patient:
                messages.error(request,
                    "❌ Groupe sanguin du patient obligatoire avant délivrance!")
                return redirect('demande_detail', pk=pk)

            demande.groupe_patient_verifie = groupe_patient
            demande.verification_groupe_ok = True
            groupes_ok = PocheSang.groupes_donneurs_compatibles(demande.groupe_requis)
            poches = PocheSang.objects.filter(
                pk__in=poches_ids,
                statut='disponible',
                groupe_sanguin__in=groupes_ok
            )[:demande.quantite]

            # INTERDIRE LA VALIDATION SANS POCHE
            if not poches.exists():
                messages.error(request, "❌ Vous devez sélectionner au moins une poche pour valider la demande.")
                return redirect('demande_detail', pk=pk)

            for poche in poches:
                poche.statut = 'attribuee'
                poche.save()
                demande.poches_attribuees.add(poche)
                TracabiliteEvenement.objects.get_or_create(
                    poche=poche, etape='reservation',
                    defaults={
                        'effectue_par': request.user,
                        'notes': f"Réservée — Demande #{demande.pk}"
                    }
                )
            demande.statut_demande = 'preparee'
            demande.date_traitement = timezone.now()
            demande.save()
            messages.success(request,
                f"✅ Demande #{pk} validée. "
                f"{poches.count()} poche(s) attribuée(s).")

        elif action == 'livrer':
            # INTERDIRE LA LIVRAISON SANS POCHE ATTRIBUÉE
            if demande.poches_attribuees.count() == 0:
                messages.error(request, "❌ Aucune poche attribuée à cette demande. Impossible de livrer.")
                return redirect('demande_detail', pk=pk)

            # Convertir le nom de l'hôpital en instance de Hopital
            from .models import Hopital
            hopital_obj = None
            if demande.hopital:
                hopital_obj = Hopital.objects.filter(nom__iexact=demande.hopital.strip()).first()
                if not hopital_obj:
                    # Création automatique si l'hôpital n'existe pas
                    hopital_obj = Hopital.objects.create(
                        nom=demande.hopital.strip(),
                        actif=True
                    )
                    messages.info(request, f"Hôpital '{hopital_obj.nom}' ajouté automatiquement.")

            for poche in demande.poches_attribuees.all():
                poche.statut = 'utilisee'  # ← Stock décrémente ici
                poche.save()
                TracabiliteEvenement.objects.get_or_create(
                    poche=poche, etape='livraison',
                    defaults={
                        'effectue_par': request.user,
                        'hopital': hopital_obj,  # ← Maintenant c'est une instance ou None
                        'notes': (
                            f"Livré à {demande.hopital} — "
                            f"Patient: {demande.patient_nom}"
                        )
                    }
                )
            demande.statut_demande = 'livree'
            demande.date_traitement = timezone.now()
            demande.save()
            verifier_alertes_stock()
            messages.success(request,
                f"✅ Demande #{pk} livrée à {demande.hopital}.")

    return redirect('demande_detail', pk=pk)



@login_required
@role_required('responsable')
def demandes_a_livrer(request):
    demandes = DemandeTransfusion.objects.filter(
        statut_demande='preparee'
    ).order_by('-date_traitement')
    return render(request, 'blood_bank/demandes/a_livrer.html', {
        'demandes': demandes,
        'title': 'Demandes à livrer',
        'is_directeur': request.user.role == 'directeur',
        'statuts': DemandeTransfusion.STATUT_CHOICES,
        'groupes': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
    })


@login_required
@role_required('responsable')
def demande_livrer(request, pk):
    """Livraison finale d'une demande préparée"""
    demande = get_object_or_404(DemandeTransfusion, pk=pk)
    if request.method == 'POST':
        if demande.statut_demande != 'preparee':
            messages.error(request, "Demande non prête pour la livraison.")
            return redirect('demande_detail', pk=pk)
        notes = request.POST.get('notes_livraison', '')
        nb = 0
        for poche in demande.poches_attribuees.filter(statut='attribuee'):
            poche.statut = 'utilisee'  # ← Stock décrémente
            poche.save()
            nb += 1
            TracabiliteEvenement.objects.get_or_create(
                poche=poche, etape='livraison',
                defaults={
                    'effectue_par': request.user,
                    'hopital': demande.hopital,
                    'notes': (
                        f"Livré — #{demande.pk} — "
                        f"{demande.patient_nom} — {notes}"
                    )
                }
            )
        demande.statut_demande = 'livree'
        demande.date_traitement = timezone.now()
        demande.save()
        if demande.telephone_contact:
            try:
                envoyer_sms(
                    demande.telephone_contact,
                    f"CNTS — Livraison #{demande.pk} effectuée. "
                    f"{nb} poche(s) {demande.groupe_requis}. "
                    f"Patient: {demande.patient_nom}."
                )
            except Exception:
                pass
        verifier_alertes_stock()
        messages.success(request,
            f"✅ Demande #{pk} livrée — {nb} poche(s).")
    return redirect('demande_detail', pk=pk)


@login_required
@role_required('directeur', 'admin')
def approuver_prix_solidaire(request, pk):
    demande = get_object_or_404(DemandeTransfusion, pk=pk)
    if request.method == 'POST':
        annuler = request.POST.get('annuler_solidaire') == '1'
        if annuler:
            demande.prix_solidaire_approuve = False
            demande.approuve_par = None
            demande.motif_solidaire = ''
            demande.prix_final = demande.calculer_prix()
        else:
            nouveau_prix = request.POST.get('prix_personnalise', '').strip()
            demande.prix_solidaire_approuve = True
            demande.approuve_par = request.user
            demande.motif_solidaire = (
                request.POST.get('motif_solidaire', '') or
                "Approuvé par le Directeur"
            )
            demande.prix_final = (
                int(nouveau_prix) if nouveau_prix else demande.calculer_prix()
            )
        demande.save()
        messages.success(request,
            f"✅ Prix mis à jour: {demande.prix_final} FCFA.")
    return redirect('demande_detail', pk=pk)


# ============================================================
# STOCK & ALERTES
# Gestionnaire, Responsable, Directeur voient le stock détaillé
# Admin : BLOQUÉ sur stock détaillé
# ============================================================

@login_required
@role_required('gestionnaire', 'directeur', 'responsable')
def stock_view(request):
    groupes = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
    config = Configuration.get_config()

    # Marquer automatiquement les expirées
    PocheSang.objects.filter(
        statut='disponible',
        date_expiration__lt=timezone.now().date()
    ).update(statut='expiree')

    stock_detail = []
    for groupe in groupes:
        for type_code, type_label in PocheSang.TYPE_PRODUIT_CHOICES:
            disponibles = PocheSang.objects.filter(
                groupe_sanguin=groupe,
                type_produit=type_code,
                statut='disponible'
            ).count()
            expirant = PocheSang.objects.filter(
                groupe_sanguin=groupe,
                type_produit=type_code,
                statut='disponible',
                date_expiration__lte=timezone.now().date() + timedelta(days=7)
            ).count()
            stock_detail.append({
                'groupe': groupe,
                'type_produit': type_label,
                'type_code': type_code,
                'disponibles': disponibles,
                'expirant': expirant,
                'critique': disponibles <= config.seuil_alerte_stock,
            })

    alertes = AlerteStock.objects.filter(resolue=False).order_by('-date_alerte')
    return render(request, 'blood_bank/stock/view.html', {
        'stock_detail': stock_detail,
        'alertes': alertes,
        'config': config,
        'stats_stock': {
            'sang_total': PocheSang.objects.filter(
                type_produit='sang_total', statut='disponible'
            ).count(),
            'plaquettes': PocheSang.objects.filter(
                type_produit='culot_plaquettaire', statut='disponible'
            ).count(),
            'globules': PocheSang.objects.filter(
                type_produit='culot_erythrocytaire', statut='disponible'
            ).count(),
            'cryo': PocheSang.objects.filter(
                type_produit='cryoprecipite', statut='disponible'
            ).count(),
        }
    })


@login_required
@role_required('gestionnaire', 'directeur', 'responsable')
def resoudre_alerte(request, pk):
    alerte = get_object_or_404(AlerteStock, pk=pk)
    alerte.resolue = True
    alerte.date_resolution = timezone.now()
    alerte.save()
    messages.success(request, "Alerte résolue.")
    return redirect('stock_view')


# ============================================================
# IA PRÉDICTION J+3 — bouton interface
# ============================================================

@login_required
@role_required('directeur', 'gestionnaire')
def lancer_prediction_ia(request):
    if request.method == 'POST':
        try:
            alertes = AlerteStock.predire_rupture_j3()
            expirations = AlerteStock.verifier_expirations()
            messages.success(request,
                f"🤖 IA J+3: {len(alertes)} prédiction(s), "
                f"{len(expirations)} expiration(s) détectée(s).")
        except Exception as e:
            messages.error(request, f"Erreur IA: {e}")
    return redirect('statistiques')


# ============================================================
# MESSAGES IEC / SMS
# Admin voit et envoie les SMS
# ============================================================

@login_required
@role_required('admin', 'directeur', 'gestionnaire')
def message_list(request):
    messages_iec = MessageIEC.objects.order_by('-date_creation')
    logs_sms = LogSMS.objects.order_by('-date_envoi')[:20]
    return render(request, 'blood_bank/messages/list.html', {
        'messages_iec': messages_iec, 'logs_sms': logs_sms,
    })


@login_required
@role_required('admin', 'directeur', 'gestionnaire')
def message_create(request):
    form = MessageIECForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        msg = form.save(commit=False)
        msg.cree_par = request.user
        msg.save()
        messages.success(request, "Message IEC créé.")
        return redirect('message_list')
    return render(request, 'blood_bank/messages/form.html', {
        'form': form, 'title': 'Nouveau message IEC'
    })


@login_required
@role_required('admin', 'directeur', 'gestionnaire')
def message_envoyer(request, pk):
    msg_iec = get_object_or_404(MessageIEC, pk=pk)
    if request.method == 'POST':
        try:
            success, fail = envoyer_sms_campagne(msg_iec)
            messages.success(request,
                f"Campagne envoyée! ✅ {success} succès, ❌ {fail} échecs.")
        except Exception as e:
            messages.error(request, f"Erreur envoi: {e}")
    return redirect('message_list')


# ============================================================
# CONFIGURATION — Admin + Directeur
# ============================================================

@login_required
@role_required('admin', 'directeur')
def configuration_view(request):
    config = Configuration.get_config()
    form = ConfigurationForm(request.POST or None, instance=config)
    if request.method == 'POST' and form.is_valid():
        c = form.save(commit=False)
        c.modifie_par = request.user
        c.save()
        messages.success(request, "Configuration mise à jour.")
        return redirect('configuration')
    return render(request, 'blood_bank/config/view.html', {
        'form': form, 'config': config
    })


# ============================================================
# UTILISATEURS — Admin uniquement
# ============================================================

@login_required
@role_required('admin')
def utilisateur_list(request):
    utilisateurs = Utilisateur.objects.all().order_by('role', 'username')
    return render(request, 'blood_bank/utilisateurs/list.html', {
        'utilisateurs': utilisateurs
    })


@login_required
@role_required('admin')
def utilisateur_create(request):
    form = UtilisateurForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        mdp = form.cleaned_data.get('password')
        if mdp:
            user.set_password(mdp)
        user.save()
        messages.success(request, f"Utilisateur {user.username} créé!")
        return redirect('utilisateur_list')
    return render(request, 'blood_bank/utilisateurs/form.html', {
        'form': form, 'title': 'Nouvel utilisateur'
    })


@login_required
@role_required('admin')
def utilisateur_edit(request, pk):
    user = get_object_or_404(Utilisateur, pk=pk)
    form = UtilisateurForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Utilisateur mis à jour.")
        return redirect('utilisateur_list')
    return render(request, 'blood_bank/utilisateurs/form.html', {
        'form': form, 'title': 'Modifier utilisateur', 'obj': user
    })


# ============================================================
# STATISTIQUES COMPLÈTES
# ============================================================

@login_required
@role_required('directeur', 'admin', 'gestionnaire')
def statistiques(request):
    today = timezone.now().date()

    # 1. Poches collectées
    total_poches = PocheSang.objects.count()
    poches_ce_mois = PocheSang.objects.filter(
        date_prelevement__month=today.month,
        date_prelevement__year=today.year
    ).count()
    poches_disponibles = PocheSang.objects.filter(statut='disponible').count()
    poches_rejetees = PocheSang.objects.filter(statut='rejetee').count()

    # 2. Demandes
    total_demandes = DemandeTransfusion.objects.count()
    demandes_livrees = DemandeTransfusion.objects.filter(
        statut_demande='livree'
    ).count()
    demandes_en_attente = DemandeTransfusion.objects.filter(
        statut_demande='en_attente'
    ).count()

    # 3. Taux de satisfaction
    taux = round(demandes_livrees / total_demandes * 100) if total_demandes > 0 else 0

    # 4. Groupes les plus demandés
    groupes_demandes = []
    for groupe in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
        nb = DemandeTransfusion.objects.filter(groupe_requis=groupe).count()
        groupes_demandes.append({
            'groupe': groupe,
            'total': nb,
            'pourcentage': round(nb / total_demandes * 100) if total_demandes > 0 else 0
        })
    groupes_demandes.sort(key=lambda x: x['total'], reverse=True)

    # 5. Stock par groupe
    stock_par_groupe = []
    for groupe in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
        nb = PocheSang.objects.filter(
            groupe_sanguin=groupe, statut='disponible'
        ).count()
        stock_par_groupe.append({'groupe': groupe, 'total': nb})

    # 6. Stock par type
    stock_par_type = {}
    for type_code, type_label in PocheSang.TYPE_PRODUIT_CHOICES:
        stock_par_type[type_code] = {
            'label': type_label,
            'total': PocheSang.objects.filter(
                type_produit=type_code, statut='disponible'
            ).count()
        }

    alertes_stock = AlerteStock.objects.filter(
        resolue=False
    ).order_by('-date_alerte')[:8]

    return render(request, 'blood_bank/stats/view.html', {
        'stats': {
            'total_poches': total_poches,
            'poches_ce_mois': poches_ce_mois,
            'poches_disponibles': poches_disponibles,
            'poches_rejetees': poches_rejetees,
            'total_demandes': total_demandes,
            'demandes_livrees': demandes_livrees,
            'demandes_en_attente': demandes_en_attente,
            'taux_satisfaction': taux,
            'total_donneurs': Donneur.objects.count(),
            'nouveaux_donneurs': Donneur.objects.filter(
                date_inscription__month=today.month,
                date_inscription__year=today.year
            ).count(),
            'groupes_demandes': groupes_demandes,
            'stock_par_groupe': stock_par_groupe,
            'stock_par_type': stock_par_type,
        },
        'alertes_stock': alertes_stock,
    })


# ============================================================
# ACCUEIL CANDIDAT
# ============================================================

@login_required
@role_required('infirmier', 'medecin', 'accueil')
def accueil_candidat(request):
    if request.method == 'POST':
        nom = request.POST.get('nom_complet', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        type_visite = request.POST.get('type_visite', 'campagne')
        age_ok = request.POST.get('age_ok') == 'on'
        bonne_sante = request.POST.get('bonne_sante') == 'on'
        pas_don_recent = request.POST.get('pas_don_recent') == 'on'
        notes = request.POST.get('notes', '')
        date_naissance_str = request.POST.get('date_naissance', '').strip()
        poids_str = request.POST.get('poids', '').strip()

        if not nom or not telephone:
            messages.error(request, "Nom et téléphone obligatoires.")
            return redirect('accueil_candidat')

        # --- Date de naissance ---
        if not date_naissance_str:
            messages.error(request, "La date de naissance est obligatoire.")
            return redirect('accueil_candidat')
        try:
            from datetime import datetime
            date_naissance = datetime.strptime(date_naissance_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Format de date invalide. Utilisez AAAA-MM-JJ.")
            return redirect('accueil_candidat')

        # --- Poids ---
        if not poids_str:
            messages.error(request, "Le poids est obligatoire.")
            return redirect('accueil_candidat')
        try:
            from decimal import Decimal
            poids = Decimal(poids_str)
        except ValueError:
            messages.error(request, "Le poids doit être un nombre.")
            return redirect('accueil_candidat')

        # --- Création du candidat ---
        candidat = CandidatDon(
            nom_complet=nom,
            telephone=telephone,
            date_naissance=date_naissance,
            poids=poids,
            type_visite=type_visite,
            age_ok=age_ok,
            bonne_sante=bonne_sante,
            pas_don_recent=pas_don_recent,
            notes=notes,
            accueilli_par=request.user,
        )
        candidat.evaluer_eligibilite()
        candidat.save()

        if candidat.eligible_don:
            messages.success(request, f"✅ {nom} est éligible! Orientez vers l'entretien médical.")
        else:
            messages.warning(request, f"⚠ {nom} n'est pas éligible pour le moment.")
        return redirect('accueil_candidat')

    # GET : afficher le formulaire
    candidats_jour = CandidatDon.objects.filter(
        date_visite__date=timezone.now().date()
    ).order_by('-date_visite')
    return render(request, 'blood_bank/accueil/candidat.html', {
        'type_choices': CandidatDon.TYPE_VISITE,
        'candidats_jour': candidats_jour,
        'criteres': [
            ('age_ok', '🎂 Âge entre 18 et 65 ans'),
            ('poids', '⚖️ Poids ≥ 50 kg'),
            ('bonne_sante', '💪 En bonne santé — pas de fièvre'),
            ('pas_don_recent', '📅 Pas de don dans les 56 derniers jours'),
        ],
    })


# ============================================================
# VISITEURS CNTS
# ============================================================

@login_required
@role_required('infirmier', 'accueil', 'medecin')
def visiteur_list(request):
    q = request.GET.get('q', '')
    visiteurs = VisiteurCNTS.objects.all()
    if q:
        visiteurs = visiteurs.filter(
            Q(nom_complet__icontains=q) | Q(telephone__icontains=q)
        )
    return render(request, 'blood_bank/visiteurs/list.html', {
        'visiteurs': visiteurs.order_by('-date_visite'), 'q': q,
    })


@login_required
@role_required('infirmier', 'accueil', 'medecin')
def visiteur_create(request):
    if request.method == 'POST':
        nom_complet = request.POST.get('nom_complet', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        nom_patient = request.POST.get('nom_patient', '').strip()
        prenom_patient = request.POST.get('prenom_patient', '').strip()
        telephone_patient = request.POST.get('telephone_patient', '').strip()
        groupe_patient = request.POST.get('groupe_patient', '').strip()
        hopital_input = request.POST.get('hopital_patient', '').strip()
        demande_id = request.POST.get('demande_associee', '').strip()

        if not nom_complet or not telephone or not nom_patient:
            messages.error(request, "Nom du donneur, téléphone et nom du patient sont obligatoires.")
            return redirect('visiteur_create')

        # ===== GESTION DE L'HÔPITAL (avec option "Autre") =====
        hopital_patient = hopital_input
        if hopital_input == 'autre':
            hopital_patient = request.POST.get('hopital_patient_autre', '').strip()
        # =====================================================

        # Si une demande est associée
        demande = None
        if demande_id:
            try:
                demande = DemandeTransfusion.objects.get(pk=demande_id)
            except DemandeTransfusion.DoesNotExist:
                pass

        visiteur = VisiteurCNTS.objects.create(
            nom_complet=nom_complet,
            telephone=telephone,
            nom_patient=nom_patient,
            prenom_patient=prenom_patient,
            telephone_patient=telephone_patient,
            groupe_patient=groupe_patient,
            hopital_patient=hopital_patient,
            date_naissance=request.POST.get('date_naissance') or None,
            poids=request.POST.get('poids') or None,
            type_visite='don_familial',
            demande_associee=demande,
            enregistre_par=request.user,
            statut_don='en_attente'
        )

        messages.success(request, f"✅ Visiteur {nom_complet} enregistré pour le patient {nom_patient}.")
        return redirect('visiteur_prelever', pk=visiteur.pk)

    # GET : afficher le formulaire
    hopitaux = Hopital.objects.filter(actif=True)
    demandes_en_attente = DemandeTransfusion.objects.filter(
        statut_demande='en_attente'
    ).order_by('-date_demande')

    return render(request, 'blood_bank/visiteurs/form.html', {
        'hopitaux': hopitaux,
        'demandes': demandes_en_attente,
        'groupes': Donneur.GROUPE_CHOICES,
    })
@login_required
def visiteur_detail(request, pk):
    visiteur = get_object_or_404(VisiteurCNTS, pk=pk)
    return render(request, 'blood_bank/visiteurs/detail.html', {
        'visiteur': visiteur,
    })


@login_required
@role_required('medecin', 'infirmier', 'accueil')
def visiteur_prelever(request, pk):
    visiteur = get_object_or_404(VisiteurCNTS, pk=pk)
    if request.method == 'POST':
        donneur, _ = Donneur.objects.get_or_create(
            telephone=visiteur.telephone,
            defaults={
                'nom_complet': visiteur.nom_complet,
                'groupe_sanguin': '',
                'date_naissance': timezone.now().date()  - timedelta(days=25*365),
                'sexe': 'M',
                'poids': 70,
            }
        )
        poche = PocheSang.objects.create(
            donneur=donneur,
            type_produit='sang_total',
            statut='collectee',
            date_prelevement=timezone.now().date(),
            volume_ml=450,
            lieu_collecte='CNTS Brazzaville',
            creee_par=request.user,
            notes=f"Don familial — Patient: {visiteur.nom_patient}"
        )
        TracabiliteEvenement.objects.create(
            poche=poche, etape='prelevement',
            effectue_par=request.user,
            notes=f"Don familial — {visiteur.nom_complet} pour {visiteur.nom_patient}"
        )
        messages.success(request,
            f"🩸 Poche {poche.code_barre} créée. Envoyez au labo.")
        return redirect('poche_analyser', pk=poche.pk)
    return render(request, 'blood_bank/visiteurs/prelevement.html', {
        'visiteur': visiteur,
        'title': f"Prélèvement — {visiteur.nom_complet}"
    })


# ============================================================
# CANDIDATS À PRÉLEVER
# ============================================================

@login_required
@role_required('medecin', 'infirmier', 'accueil')
def candidats_a_prelever(request):
    candidats = CandidatDon.objects.filter(
        eligible_don=True,
        examen_medical_valide=True, 
        poches_prelevees__isnull=True   # ← Seulement ceux sans poche prélevée
    ).order_by('-date_visite')
    return render(request, 'blood_bank/prelevement/candidats_list.html', {'candidats': candidats})

@login_required
@role_required('medecin', 'infirmier')
def prelever_candidat(request, pk):
    candidat = get_object_or_404(CandidatDon, pk=pk)
    if request.method == 'POST':
        if not candidat.examen_medical_valide:
            messages.error(request, "Ce candidat n'a pas encore été examiné par le médecin.")
            return redirect('candidats_a_prelever')
        donneur, _ = Donneur.objects.get_or_create(
            telephone=candidat.telephone,
            defaults={
                'nom_complet': candidat.nom_complet,
                'groupe_sanguin': '',
                'date_naissance': timezone.now().date(),
                'sexe': 'M',
                
            }
        )
        poche = PocheSang.objects.create(
            donneur=donneur,
            candidat_source=candidat, 
            type_produit='sang_total',
            statut='collectee',
            date_prelevement=timezone.now().date(),
            volume_ml=450,
            lieu_collecte='CNTS Brazzaville',
            creee_par=request.user,
            notes=f"Candidat: {candidat.nom_complet}"
        )
        TracabiliteEvenement.objects.create(
            poche=poche, etape='prelevement',
            effectue_par=request.user,
            notes=f"Prélèvement candidat {candidat.nom_complet}"
        )
        messages.success(request, f"✅ Poche {poche.code_barre} créée.")
        return redirect('poche_analyser', pk=poche.pk)
    # GET : afficher le formulaire de confirmation
    return render(request, 'blood_bank/prelevement/prelever_candidat.html', {'candidat': candidat})
@login_required
@role_required('medecin', 'directeur')
def examen_medical_candidat(request, pk):
    candidat = get_object_or_404(CandidatDon, pk=pk)
    if request.method == 'POST':
        # Récupérer tous les critères
        candidat.tension = request.POST.get('tension', '')
        candidat.poids_ok = request.POST.get('poids_ok') == 'on'
        candidat.tension_ok = request.POST.get('tension_ok') == 'on'
        candidat.hemoglobine_ok = request.POST.get('hemoglobine_ok') == 'on'
        candidat.pas_de_maladie = request.POST.get('pas_de_maladie') == 'on'
        candidat.pas_de_medicament = request.POST.get('pas_de_medicament') == 'on'
        candidat.pas_tuberculose = request.POST.get('pas_tuberculose') == 'on'
        candidat.pas_fievre = request.POST.get('pas_fievre') == 'on'
        candidat.pas_antecedents_risque = request.POST.get('pas_antecedents_risque') == 'on'
        candidat.motif_inaptitude = request.POST.get('motif_inaptitude', '')
        
        # Groupe sanguin si déterminé
        groupe_examen = request.POST.get('groupe_sanguin_examen', '').strip()
        if groupe_examen and not candidat.groupe_sanguin:
            candidat.groupe_sanguin = groupe_examen
        
        # Évaluation automatique de l'aptitude
        apte = all([
            candidat.poids_ok,
            candidat.tension_ok,
            candidat.hemoglobine_ok,
            candidat.pas_de_maladie,
            candidat.pas_de_medicament,
            candidat.pas_tuberculose,
            candidat.pas_fievre,
            candidat.pas_antecedents_risque,
        ])
        
        if apte:
            candidat.examen_medical_valide = True
            candidat.date_examen = timezone.now()
            messages.success(request, f"✅ {candidat.nom_complet} est APTE au don.")
            # Envoyer SMS au candidat
            try:
                envoyer_sms(candidat.telephone, f"Bonjour {candidat.nom_complet}, vous êtes apte au don. Merci!")
            except:
                pass
        else:
            candidat.examen_medical_valide = False
            messages.warning(request, f"⚠ {candidat.nom_complet} est INAPTE. Motif: {candidat.motif_inaptitude or 'Non précisé'}")
        
        candidat.save()
        return redirect('examen_candidats')
    
    return render(request, 'blood_bank/donneurs/examen_medical_candidat.html', {
        'candidat': candidat,
        'groupe_choices': Donneur.GROUPE_CHOICES,
    })
# ============================================================
# HÔPITAUX GÉOLOCALISÉS
# ============================================================

@login_required
def hopital_list(request):
    return render(request, 'blood_bank/hopitaux/list.html', {
        'hopitaux': Hopital.objects.filter(actif=True)
    })


@login_required
@role_required('admin', 'directeur', 'gestionnaire')
def hopital_create(request):
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        if nom:
            lat = request.POST.get('latitude', '')
            lng = request.POST.get('longitude', '')
            Hopital.objects.create(
                nom=nom,
                adresse=request.POST.get('adresse', ''),
                telephone=request.POST.get('telephone', ''),
                quartier=request.POST.get('quartier', ''),
                latitude=float(lat) if lat else None,
                longitude=float(lng) if lng else None,
            )
            messages.success(request, f"✅ Hôpital {nom} ajouté.")
            return redirect('hopital_list')
    return render(request, 'blood_bank/hopitaux/form.html')


# ============================================================
# TRAÇABILITÉ
# ============================================================

@login_required
def tracabilite_view(request, pk):
    poche = get_object_or_404(PocheSang, pk=pk)
    if request.method == 'POST':
        etape = request.POST.get('etape')
        temperature = request.POST.get('temperature', '')
        hopital_id = request.POST.get('hopital_id', '')
        evt = TracabiliteEvenement(
            poche=poche, etape=etape,
            effectue_par=request.user,
            notes=request.POST.get('notes', ''),
            temperature=float(temperature) if temperature else None,
        )
        if hopital_id:
            try:
                evt.hopital_id = int(hopital_id)
            except Exception:
                pass
        evt.save()
        if etape == 'livraison':
            poche.statut = 'utilisee'
            poche.save()
        elif etape == 'rejet':
            poche.statut = 'rejetee'
            poche.save()
        messages.success(request, "✅ Étape enregistrée.")
        return redirect('tracabilite_view', pk=pk)

    return render(request, 'blood_bank/poches/tracabilite.html', {
        'poche': poche,
        'evenements': poche.tracabilite.all().order_by('date_heure'),
        'hopitaux': Hopital.objects.filter(actif=True),
        'etapes': TracabiliteEvenement.ETAPE_CHOICES,
    })


# ============================================================
# CARTE DONNEUR — Directeur uniquement émet
# ============================================================

@login_required
@role_required('directeur', 'admin')
def carte_donneur_view(request, pk):
    donneur = get_object_or_404(Donneur, pk=pk)
    config = Configuration.get_config()
    nb_dons = PocheSang.objects.filter(
        donneur=donneur,
        statut__in=['disponible', 'attribuee', 'utilisee']
    ).count()
    eligible = nb_dons >= config.seuil_credits
    carte = getattr(donneur, 'carte', None)

    if request.method == 'POST' and eligible and not carte:
        carte = CarteDonneur(donneur=donneur, emise_par=request.user)
        carte.save()
        carte.generer_qr_code()
        messages.success(request, f"🎉 Carte {carte.numero_carte} générée!")
        try:
            envoyer_sms(donneur.telephone,
                f"Félicitations {donneur.nom_complet}! "
                f"Carte CNTS émise. N°{carte.numero_carte}.")
        except Exception:
            pass

    return render(request, 'blood_bank/donneurs/carte_donneur.html', {
        'donneur': donneur, 'carte': carte,
        'nb_dons': nb_dons, 'eligible': eligible,
        'seuil': config.seuil_credits,
        'is_directeur': request.user.role == 'directeur',
    })


# ============================================================
# RÉSULTATS — Donneur et Visiteur consultent leurs résultats
# ============================================================

def resultats_donneur(request, code_unique):
    """Page publique — le donneur consulte avec son code unique"""
    donneur = get_object_or_404(Donneur, code_unique=code_unique)
    poches = PocheSang.objects.filter(
        donneur=donneur
    ).order_by('-date_prelevement')
    return render(request, 'blood_bank/donneurs/resultats_donneur.html', {
        'donneur': donneur,
        'poches': poches,
        'nb_dons': poches.filter(
            statut__in=['disponible', 'attribuee', 'utilisee']
        ).count(),
        'apte': donneur.apte_au_don,
    })


def resultats_visiteur(request, telephone):
    """Page publique — visiteur consulte avec son téléphone"""
    visiteur = get_object_or_404(VisiteurCNTS, telephone=telephone)
    return render(request, 'blood_bank/visiteurs/resultats.html', {
        'visiteur': visiteur,
    })


def candidat_resultats(request, code_acces):
    """Page résultats candidat — accès par téléphone"""
    candidat = get_object_or_404(CandidatDon, telephone=code_acces)
    return render(request, 'blood_bank/accueil/candidat.html', {
        'candidat': candidat,
        'type_choices': CandidatDon.TYPE_VISITE,
        'candidats_jour': CandidatDon.objects.none(),
        'criteres': [],
    })


# ============================================================
# API JSON
# ============================================================

@login_required
def api_donneurs_geo(request):
    donneurs = Donneur.objects.filter(
        latitude__isnull=False, longitude__isnull=False
    )
    return JsonResponse({
        'donneurs': [{
            'id': d.pk, 'nom': d.nom_complet,
            'groupe': d.groupe_sanguin or '?',
            'lat': d.latitude, 'lon': d.longitude,
            'peut_donner': d.peut_donner(),
        } for d in donneurs],
        'total': donneurs.count()
    })


@login_required
def api_hopitaux_geo(request):
    hopitaux = Hopital.objects.filter(actif=True, latitude__isnull=False)
    return JsonResponse({
        'hopitaux': [{
            'id': h.pk, 'nom': h.nom,
            'lat': h.latitude, 'lng': h.longitude,
            'telephone': h.telephone,
        } for h in hopitaux],
        'total': hopitaux.count()
    })


@login_required
def api_stock(request):
    data = {}
    for type_code, _ in PocheSang.TYPE_PRODUIT_CHOICES:
        data[type_code] = {}
        for g in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
            data[type_code][g] = PocheSang.objects.filter(
                groupe_sanguin=g,
                type_produit=type_code,
                statut='disponible'
            ).count()
    return JsonResponse(data)


@login_required
def api_statistiques(request, type_stat):
    today = timezone.now().date()
    if type_stat == 'dons_par_periode':
        jours = 7 if request.GET.get('periode') == 'semaine' else 30
        data = []
        for i in range(jours - 1, -1, -1):
            jour = today - timedelta(days=i)
            data.append({
                'date': jour.strftime('%d/%m'),
                'count': PocheSang.objects.filter(date_prelevement=jour).count()
            })
        return JsonResponse({'data': data})
    elif type_stat == 'repartition_groupes':
        return JsonResponse({'data': [
            {'groupe': g, 'count': Donneur.objects.filter(groupe_sanguin=g).count()}
            for g in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
        ]})
    elif type_stat == 'stock_par_groupe':
        return JsonResponse({'data': [
            {'groupe': g, 'count': PocheSang.objects.filter(
                groupe_sanguin=g, statut='disponible'
            ).count()}
            for g in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
        ]})
    return JsonResponse({'error': 'Type invalide'}, status=400)


# ============================================================
# USSD ENDPOINT — Africa's Talking
# ============================================================

@csrf_exempt
def ussd_endpoint(request):
    if request.method == 'POST':
        response = handle_ussd(
            request.POST.get('sessionId', ''),
            request.POST.get('serviceCode', ''),
            request.POST.get('phoneNumber', ''),
            request.POST.get('text', '')
        )
        return HttpResponse(response, content_type='text/plain')
    return HttpResponse("Méthode non autorisée", status=405)


# ============================================================
# PROFIL
# ============================================================

@login_required
def profil(request):
    return render(request, 'blood_bank/profil.html', {'user': request.user})


@login_required
def profil_edit(request):
    form = UtilisateurForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Profil mis à jour.")
        return redirect('profil')
    return render(request, 'blood_bank/utilisateurs/form.html', {
        'form': form, 'title': 'Mon profil'
    })
@login_required
@role_required('medecin', 'directeur')
def recherche_medicale(request):
    q = request.GET.get('q', '')
    donneurs = []
    poches = []
    if q:
        donneurs = Donneur.objects.filter(
            Q(nom_complet__icontains=q) |
            Q(code_unique__icontains=q) |
            Q(telephone__icontains=q)
        )
        poches = PocheSang.objects.filter(
            Q(code_barre__icontains=q) |
            Q(donneur__nom_complet__icontains=q) |
            Q(groupe_sanguin__icontains=q)
        )
    return render(request, 'blood_bank/donneurs/recherche_medical.html', {
        'q': q,
        'donneurs': donneurs,
        'poches': poches,
    })

# ============================================================
# RÉSULTATS DONNEUR (consultation publique par code unique)
# ============================================================

def resultats_donneur(request, code):
    donneur = get_object_or_404(Donneur, code_unique=code)
    poches = PocheSang.objects.filter(donneur=donneur).order_by('-date_prelevement')
    return render(request, 'blood_bank/donneurs/resultats_donneur.html', {'donneur': donneur, 'poches': poches})
@login_required
@role_required('medecin', 'directeur')
def examen_candidats(request):
    candidats = CandidatDon.objects.filter(
        eligible_don=True,
        examen_medical_valide=False,
        type_visite__in=['campagne', 'deviendra_donneur']
    ).order_by('-date_visite')
    return render(request, 'blood_bank/donneurs/examen_candidats.html', {'candidats': candidats})
@login_required
@role_required('medecin', 'directeur')
def readmettre_donneur(request, pk):
    donneur = get_object_or_404(Donneur, pk=pk)
    if donneur.date_suspension_paludisme:
        donneur.date_suspension_paludisme = None
        donneur.date_retour_autorise = None
        donneur.actif = True
        donneur.classification = 'donneur'
        donneur.save()
        messages.success(request, f"{donneur.nom_complet} a été réadmis.")
    return redirect('donneur_detail', pk=pk) 
@login_required
@role_required('medecin', 'directeur')
def readmettre_donneur(request, pk):
    donneur = get_object_or_404(Donneur, pk=pk)
    if donneur.date_suspension_paludisme:
        donneur.date_suspension_paludisme = None
        donneur.date_retour_autorise = None
        donneur.actif = True
        donneur.classification = 'donneur'
        donneur.save()
        messages.success(request, f"{donneur.nom_complet} a été réadmis.")
    return redirect('donneur_detail', pk=pk)
def pre_enregistrement_donneur(request):
    if request.method == 'POST':
        nom = request.POST.get('nom_complet', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        email = request.POST.get('email', '').strip()
        if nom and telephone:
            PreEnregistrementDonneur.objects.create(
                nom_complet=nom,
                telephone=telephone,
                email=email
            )
            # Envoyer un email à l'infirmier (à adapter)
            send_mail(
                'Nouvelle demande de pré‑enregistrement donneur',
                f"Nom: {nom}\nTéléphone: {telephone}\nEmail: {email}",
                settings.DEFAULT_FROM_EMAIL,
                ['cntscongobrazzaville@gmail.com'],  # ← à remplacer par l'email réel de l'infirmier
                fail_silently=False,
            )
            return JsonResponse({'success': True, 'message': 'Votre demande a été envoyée. Vous serez contacté.'})
        else:
            return JsonResponse({'success': False, 'message': 'Le nom et le téléphone sont obligatoires.'})
    return JsonResponse({'success': False, 'message': 'Méthode non autorisée.'})

# Vue pour lister les pré‑enregistrements (infirmier uniquement)
@login_required
@role_required('infirmier', 'admin')
def liste_pre_enregistrements(request):
    demandes = PreEnregistrementDonneur.objects.filter(traite=False).order_by('-date_demande')
    return render(request, 'blood_bank/liste_pre_enregistrements.html', {'demandes': demandes})

# Vue pour marquer une demande comme traitée
@login_required
@role_required('infirmier', 'admin')
def traiter_pre_enregistrement(request, pk):
    demande = get_object_or_404(PreEnregistrementDonneur, pk=pk)
    demande.traite = True
    demande.save()
    messages.success(request, f"Demande de {demande.nom_complet} marquée comme traitée.")
    return redirect('liste_pre_enregistrements')
