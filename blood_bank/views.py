from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json
import qrcode
from io import BytesIO
import base64
from datetime import timedelta
from PIL import Image

from .models import (
    Utilisateur, Donneur, PocheSang, DemandeTransfusion,
    Configuration, MessageIEC, AlerteStock, LogSMS,
    ExamenMedical, CarteDonneur, VisiteurCNTS, Hopital,
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


def role_required(*roles):
    """Décorateur pour restreindre l'accès par rôle"""

    def decorator(view_func):
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role in roles or request.user.is_superuser:
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
    messages.info(request, "Déconnexion réussie.")
    return redirect('login')


# ============================================================
# DASHBOARD AVEC ACCÈS RAPIDE
# ============================================================

@login_required
def dashboard(request):
    today = timezone.now().date()

    # Statistiques générales
    stats = {
        'total_donneurs': Donneur.objects.filter(actif=True).count(),
        'dons_mois': PocheSang.objects.filter(
            date_prelevement__month=today.month,
            date_prelevement__year=today.year
        ).count(),
        'poches_disponibles': PocheSang.objects.filter(statut='disponible').count(),
        'demandes_en_attente': DemandeTransfusion.objects.filter(statut_demande='en_attente').count(),
        'alertes_actives': AlerteStock.objects.filter(resolue=False).count(),
        'sms_envoyes': LogSMS.objects.filter(
            date_envoi__date=today
        ).count(),
    }

    # Stock par groupe sanguin
    groupes = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
    stock_par_groupe = []
    config = Configuration.get_config()

    # Calcul du stock par type de produit
    stock_par_type = {}
    for type_code, type_label in PocheSang.TYPE_PRODUIT_CHOICES:
        stock_par_type[type_code] = {
            'label': type_label,
            'total': PocheSang.objects.filter(
                type_produit=type_code,
                statut='disponible'
            ).count()
        }

    for groupe in groupes:
        count = PocheSang.objects.filter(groupe_sanguin=groupe, statut='disponible').count()
        stock_par_groupe.append({
            'groupe': groupe,
            'count': count,
            'critique': count <= config.seuil_alerte_stock,
        })

    # Dernières demandes
    demandes_recentes = DemandeTransfusion.objects.select_related('prescripteur').order_by('-date_demande')[:5]

    # Donneurs récents
    donneurs_recents = Donneur.objects.order_by('-date_inscription')[:5]

    # Alertes stock
    alertes = AlerteStock.objects.filter(resolue=False).order_by('-date_alerte')[:5]

    # Données pour graphique (7 derniers jours)
    dons_semaine = []
    for i in range(6, -1, -1):
        jour = today - timedelta(days=i)
        count = PocheSang.objects.filter(date_prelevement=jour).count()
        dons_semaine.append({'jour': jour.strftime('%d/%m'), 'count': count})

    # Géolocalisation centre
    centre_info = {
        'nom': settings.CENTRE_NOM,
        'adresse': settings.CENTRE_ADRESSE,
        'latitude': settings.CENTRE_LATITUDE,
        'longitude': settings.CENTRE_LONGITUDE,
        'telephone': settings.CENTRE_TELEPHONE,
    }

    # Accès rapide selon rôle
    acces_rapide = []
    if request.user.role in ['directeur', 'admin']:
        acces_rapide = [
            {'nom': 'Générer carte', 'url': 'donneur_list', 'icon': 'card', 'color': 'primary'},
            {'nom': 'Fixer prix', 'url': 'configuration', 'icon': 'price', 'color': 'success'},
            {'nom': 'Approuver réductions', 'url': 'demande_list', 'icon': 'discount', 'color': 'warning'},
        ]
    elif request.user.role in ['medecin', 'infirmier']:
        acces_rapide = [
            {'nom': 'Examen médical', 'url': 'examen_en_attente', 'icon': 'medical', 'color': 'info'},
            {'nom': 'Prélèvement', 'url': 'poche_create', 'icon': 'blood', 'color': 'danger'},
        ]
    elif request.user.role in ['gestionnaire', 'responsable']:
        acces_rapide = [
            {'nom': 'Stock', 'url': 'stock_view', 'icon': 'stock', 'color': 'primary'},
            {'nom': 'Délivrance', 'url': 'demande_list', 'icon': 'delivery', 'color': 'success'},
        ]

    context = {
        'stats': stats,
        'stock_par_groupe': stock_par_groupe,
        'stock_par_type': stock_par_type,
        'demandes_recentes': demandes_recentes,
        'donneurs_recents': donneurs_recents,
        'alertes': alertes,
        'dons_semaine': json.dumps(dons_semaine),
        'centre_info': centre_info,
        'config': config,
        'acces_rapide': acces_rapide,
        'user_role': request.user.role,
    }
    return render(request, 'blood_bank/dashboard.html', context)


# ============================================================
# DONNEURS
# ============================================================
from django.db.models import Q
@login_required
def donneur_list(request):
    q = request.GET.get('q', '')
    groupe = request.GET.get('groupe', '')
    type_d = request.GET.get('type', '')
    risque = request.GET.get('risque', '')

    donneurs = Donneur.objects.filter(actif=True)
    if q:
        donneurs = donneurs.filter(
            Q(nom_complet__icontains=q) |
            Q(code_unique__icontains=q) |
            Q(telephone__icontains=q)
        )
    if groupe:
        donneurs = donneurs.filter(groupe_sanguin=groupe)
    if type_d:
        donneurs = donneurs.filter(type_donneur=type_d)
    if risque:
        if risque == 'oui':
            donneurs = donneurs.filter(est_donneur_risque=True)
        elif risque == 'non':
            donneurs = donneurs.filter(est_donneur_risque=False)

    donneurs = donneurs.order_by('-date_inscription')

    # Récupérer la configuration pour le seuil de dons
    config = Configuration.get_config()

    # Ajouter le nombre de dons pour chaque donneur
    from django.db.models import Count, Q as Q_count
    donneurs = donneurs.annotate(
        nb_dons=Count('pochesang', filter=Q_count(pochesang__statut__in=['disponible', 'attribuee', 'utilisee']))
    )

    context = {
        'donneurs': donneurs,
        'q': q,
        'groupe': groupe,
        'type_d': type_d,
        'risque': risque,
        'groupes': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
        'is_directeur': request.user.role in ['directeur', 'admin'],
        'config': config,  # Ajout de la configuration
    }
    return render(request, 'blood_bank/donneurs/list.html', context)


@login_required
def donneur_create(request):
    form = DonneurForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        donneur = form.save()
        # SMS de bienvenue
        msg = (
            f"Bienvenue {donneur.nom_complet.split()[0]} au CNTS!\n"
            f"Code: {donneur.code_unique}\n"
            f"Groupe: {donneur.groupe_sanguin}\n"
            f"Merci pour votre engagement!"
        )
        envoyer_sms(donneur.telephone, msg, donneur=donneur)
        messages.success(request, f"Donneur {donneur.nom_complet} enregistré avec succès!")
        return redirect('donneur_detail', pk=donneur.pk)

    return render(request, 'blood_bank/donneurs/form.html', {
        'form': form, 'title': 'Nouveau Donneur'
    })


@login_required
def donneur_detail(request, pk):
    donneur = get_object_or_404(Donneur, pk=pk)
    poches = PocheSang.objects.filter(donneur=donneur).order_by('-date_prelevement')
    examen = getattr(donneur, 'examen_medical', None)
    carte = getattr(donneur, 'carte', None)

    return render(request, 'blood_bank/donneurs/detail.html', {
        'donneur': donneur,
        'poches': poches,
        'examen': examen,
        'carte': carte,
        'centre_lat': settings.CENTRE_LATITUDE,
        'centre_lon': settings.CENTRE_LONGITUDE,
        'is_directeur': request.user.role in ['directeur', 'admin'],
    })


@login_required
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
def donneur_carte(request):
    """Carte géolocalisée de tous les donneurs"""
    from django.conf import settings
    import json

    # Récupérer les donneurs avec des coordonnées
    donneurs = Donneur.objects.filter(actif=True, latitude__isnull=False, longitude__isnull=False)

    donneurs_data = []
    for d in donneurs:
        donneurs_data.append({
            'id': d.pk,
            'nom': d.nom_complet,
            'groupe': d.groupe_sanguin if d.groupe_sanguin else '?',
            'lat': float(d.latitude),
            'lon': float(d.longitude),
            'quartier': d.quartier,
            'peut_donner': d.peut_donner(),
            'est_risque': d.est_donneur_risque,
        })

    context = {
        'donneurs_json': json.dumps(donneurs_data),
        'centre_lat': getattr(settings, 'CENTRE_LATITUDE', -4.2634),
        'centre_lon': getattr(settings, 'CENTRE_LONGITUDE', 15.2429),
        'centre_nom': getattr(settings, 'CENTRE_NOM', 'CNTS Brazzaville'),
        'groupes_liste': ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-'],
        'total_donneurs': len(donneurs_data),
    }

    # CORRECTION ICI : utiliser carte.html au lieu de carte_donneur.html
    return render(request, 'blood_bank/donneurs/carte.html', context)

# ============================================================
# POCHES DE SANG AVEC GESTION STOCK TEMPS RÉEL
# ============================================================

@login_required
def poche_list(request):
    statut = request.GET.get('statut', '')
    groupe = request.GET.get('groupe', '')
    type_produit = request.GET.get('type_produit', '')
    q = request.GET.get('q', '')

    poches = PocheSang.objects.select_related('donneur').all()
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

    poches_list = list(poches.order_by('-date_prelevement'))
    today = timezone.now().date()

    # Vérifier et marquer les poches expirées
    for poche in poches_list:
        if poche.est_expiree and poche.statut == 'disponible':
            poche.statut = 'expiree'
            poche.save()
            verifier_alertes_stock()

    return render(request, 'blood_bank/poches/list.html', {
        'poches': poches_list,
        'statut': statut,
        'groupe': groupe,
        'type_produit': type_produit,
        'q': q,
        'statuts': PocheSang.STATUT_CHOICES,
        'groupes': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
        'types_produit': PocheSang.TYPE_PRODUIT_CHOICES,
        # Compteurs pour les stat-cards
        'total_poches': PocheSang.objects.count(),
        'total_disponibles': PocheSang.objects.filter(statut='disponible').count(),
        'total_en_analyse': PocheSang.objects.filter(statut='en_analyse').count(),
        'total_attribuees': PocheSang.objects.filter(statut='attribuee').count(),
        'total_expirant': PocheSang.objects.filter(
            statut='disponible',
            date_expiration__lte=today + timedelta(days=7)
        ).count(),
    })


@login_required
def poche_detail(request, pk):
    poche = get_object_or_404(PocheSang, pk=pk)
    return render(request, 'blood_bank/poches/detail.html', {'poche': poche})


def verifier_alertes_stock():
    """Vérifie et crée des alertes si stock insuffisant"""
    from .models import Configuration, PocheSang, AlerteStock, Utilisateur
    import logging

    try:
        config = Configuration.get_config()
    except:
        # Si la configuration n'existe pas, utiliser des valeurs par défaut
        class DefaultConfig:
            seuil_alerte_stock = 5

        config = DefaultConfig()

    alertes_creees = []

    for type_produit, type_label in PocheSang.TYPE_PRODUIT_CHOICES:
        for groupe in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
            count = PocheSang.objects.filter(
                groupe_sanguin=groupe,
                type_produit=type_produit,
                statut='disponible'
            ).count()

            if count <= config.seuil_alerte_stock:
                niveau = 'critical' if count == 0 else 'warning'

                alerte, created = AlerteStock.objects.get_or_create(
                    groupe_sanguin=groupe,
                    type_produit=type_produit,
                    resolue=False,
                    defaults={
                        'niveau': niveau,
                        'message': f"Stock {type_label} {groupe}: {count} poche(s) disponible(s). Seuil: {config.seuil_alerte_stock}",
                        'stock_actuel': count,
                        'seuil': config.seuil_alerte_stock,
                    }
                )

                if created:
                    alertes_creees.append({
                        'groupe': groupe,
                        'type': type_label,
                        'count': count
                    })

                    # Appeler la fonction d'alerte avec 3 arguments
                    try:
                        from .sms_service import envoyer_alerte_stock
                        envoyer_alerte_stock(groupe, count, config.seuil_alerte_stock)
                    except Exception as e:
                        print(f"Erreur envoi alerte SMS: {e}")

                    # Logger l'alerte au lieu de créer une notification
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"ALERTE STOCK - {type_label} {groupe}: {count} poches (seuil: {config.seuil_alerte_stock})")

                    # Optionnel: Utiliser messages Django si vous avez un request
                    # from django.contrib import messages
                    # messages.warning(request, f"⚠️ ALERTE STOCK - {type_label} {groupe}: {count} poche(s) restante(s)")

    if alertes_creees:
        print(f"Nouvelles alertes créées: {len(alertes_creees)}")

    return alertes_creees


@login_required
@role_required('infirmier', 'medecin', 'admin')
def poche_create(request):
    form = PocheSangForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        poche = form.save(commit=False)
        poche.creee_par = request.user

        # Vérifier si le donneur est à risque
        if poche.donneur.est_donneur_risque:
            messages.warning(request, f"⚠ Attention: {poche.donneur.nom_complet} est identifié comme donneur à risque!")

        poche.save()

        # Mettre à jour le date du dernier don
        donneur = poche.donneur
        donneur.date_dernier_don = poche.date_prelevement
        donneur.credit_solidaire += 1
        donneur.save(update_fields=['date_dernier_don', 'credit_solidaire'])

        # Notification SMS
        envoyer_notification_don(donneur)

        # Vérifier si le donneur est éligible pour la carte
        CarteDonneur.generer_si_eligible(donneur)

        messages.success(request, f"Poche {poche.code_barre} enregistrée!")
        return redirect('poche_analyser', pk=poche.pk)

    return render(request, 'blood_bank/poches/form.html', {
        'form': form, 'title': 'Enregistrer un prélèvement'
    })



@login_required
@role_required('technicien', 'admin')
def poche_analyser(request, pk):
    poche = get_object_or_404(PocheSang, pk=pk)
    form = AnalysePocheForm(request.POST or None, instance=poche)

    if request.method == 'POST' and form.is_valid():
        poche = form.save(commit=False)
        poche.date_analyse = timezone.now()
        poche.analysee_par = request.user

        # Vérifier tous les tests médicaux
        tests_echoues = []
        if not poche.test_vih:
            tests_echoues.append("VIH")
        if not poche.test_hepatite_b:
            tests_echoues.append("Hépatite B")
        if not poche.test_hepatite_c:
            tests_echoues.append("Hépatite C")
        if not poche.test_syphilis:
            tests_echoues.append("Syphilis")
        if not poche.test_paludisme:
            tests_echoues.append("Paludisme")
        if not poche.test_chagas:
            tests_echoues.append("Maladie de Chagas")
        if not poche.test_htlv:
            tests_echoues.append("HTLV")
        if not poche.test_cytomegalovirus:
            tests_echoues.append("Cytomégalovirus")
        if not poche.test_ebv:
            tests_echoues.append("Virus d'Epstein-Barr")
        if not poche.test_parvovirus:
            tests_echoues.append("Parvovirus B19")

        if len(tests_echoues) == 0:
            poche.statut = 'disponible'
            poche.tests_ok = True
            messages.success(
                request,
                f"✅ Tous les tests sont négatifs — "
                f"Poche {poche.code_barre} disponible pour transfusion !"
            )
        else:
            poche.statut = 'rejetee'
            poche.tests_ok = False
            poche.donneur.est_donneur_risque = True
            poche.donneur.save()
            raison = ", ".join(tests_echoues)
            messages.warning(
                request,
                f"❌ Poche {poche.code_barre} REJETÉE — "
                f"Tests positifs : {raison}. Donneur marqué comme à risque."
            )

        poche.save()
        verifier_alertes_stock()
        return redirect('poche_list')

    return render(request, 'blood_bank/poches/analyser.html', {
        'form': form, 'poche': poche
    })


# ============================================================
# DEMANDES DE TRANSFUSION AVEC COMPATIBILITÉ SANGUINE CORRIGÉE
# ============================================================

@login_required
def demande_list(request):
    statut = request.GET.get('statut', '')
    urgence = request.GET.get('urgence', '')
    groupe = request.GET.get('groupe', '')

    demandes = DemandeTransfusion.objects.select_related('prescripteur', 'donneur_parrain').all()
    if statut:
        demandes = demandes.filter(statut_demande=statut)
    if urgence:
        demandes = demandes.filter(urgence=urgence)
    if groupe:
        demandes = demandes.filter(groupe_requis=groupe)

    return render(request, 'blood_bank/demandes/list.html', {
        'demandes': demandes,
        'statut': statut,
        'urgence': urgence,
        'groupe': groupe,
        'statuts': DemandeTransfusion.STATUT_CHOICES,
        'groupes': DemandeTransfusion.GROUPE_CHOICES,
        'is_directeur': request.user.role in ['directeur', 'admin'],
    })


@login_required
def demande_create(request):
    form = DemandeTransfusionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        demande = form.save(commit=False)
        demande.prescripteur = request.user

        # Vérification stricte de compatibilité sanguine
        groupes_compatibles = PocheSang.groupes_donneurs_compatibles(demande.groupe_requis)

        # Vérifier stock disponible par type ET groupe compatible
        stock_dispo = PocheSang.objects.filter(
            type_produit=demande.type_produit,
            groupe_sanguin__in=groupes_compatibles,
            statut='disponible'
        ).count()

        demande.disponibilite_verifiee = True
        demande.compatibilite_verifiee = True

        # Calcul du prix (peut être modifié par le directeur)
        demande.prix_final = demande.calculer_prix()
        demande.save()

        if stock_dispo == 0:
            messages.warning(
                request,
                f"⚠ Aucun {demande.get_type_produit_display()} "
                f"compatible {demande.groupe_requis} disponible en stock !"
            )
        elif stock_dispo < demande.quantite:
            messages.warning(
                request,
                f"⚠ Stock insuffisant : {stock_dispo} poche(s) disponible(s) "
                f"sur {demande.quantite} demandée(s)."
            )
        else:
            messages.success(
                request,
                f"✓ Demande #{demande.pk} créée. "
                f"{stock_dispo} {demande.get_type_produit_display()} "
                f"compatible(s) disponible(s)."
            )

        if demande.telephone_contact:
            envoyer_confirmation_demande(demande)

        return redirect('demande_detail', pk=demande.pk)

    # Stock disponible par type pour affichage dans le formulaire
    stock_par_type = {}
    for type_code, type_label in DemandeTransfusion.TYPE_PRODUIT_CHOICES:
        stock_par_type[type_code] = {
            'label': type_label,
            'total': PocheSang.objects.filter(
                type_produit=type_code,
                statut='disponible'
            ).count()
        }

    return render(request, 'blood_bank/demandes/form.html', {
        'form': form,
        'title': 'Nouvelle demande de transfusion',
        'config': Configuration.get_config(),
        'stock_par_type': stock_par_type,
    })


@login_required
def demande_detail(request, pk):
    demande = get_object_or_404(DemandeTransfusion, pk=pk)
    groupes_compatibles = PocheSang.groupes_donneurs_compatibles(demande.groupe_requis)
    poches_compatibles = PocheSang.objects.filter(
        groupe_sanguin__in=groupes_compatibles,
        type_produit=demande.type_produit,
        statut='disponible'
    ) if demande.statut_demande in ['en_attente', 'en_cours'] else []

    return render(request, 'blood_bank/demandes/detail.html', {
        'demande': demande,
        'poches_compatibles': poches_compatibles,
        'groupe_choices': DemandeTransfusion.GROUPE_CHOICES,
        'is_directeur': request.user.role in ['directeur', 'admin'],
    })


@login_required
@role_required('gestionnaire', 'responsable', 'admin', 'directeur')
def demande_traiter(request, pk):
    demande = get_object_or_404(DemandeTransfusion, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')
        poches_ids = request.POST.getlist('poches')
        groupe_patient = request.POST.get('groupe_patient_verifie', '').strip()

        if action == 'valider' and poches_ids:

            # ── VÉRIFICATION OBLIGATOIRE DU GROUPE PATIENT ──
            if not groupe_patient:
                messages.error(
                    request,
                    "❌ Impossible de délivrer : le groupe sanguin du patient "
                    "doit être vérifié par le laboratoire avant toute délivrance !"
                )
                return redirect('demande_detail', pk=pk)

            # Vérification stricte de compatibilité
            if not PocheSang.verifier_compatibilite_patient(groupe_patient, demande.groupe_requis):
                messages.error(
                    request,
                    f"❌ INCOMPATIBILITÉ DÉTECTÉE : Le groupe du patient "
                    f"({groupe_patient}) ne correspond pas au groupe requis "
                    f"({demande.groupe_requis}). Délivrance REFUSÉE pour sécurité !"
                )
                return redirect('demande_detail', pk=pk)

            # Groupe vérifié et concordant → on peut délivrer
            demande.groupe_patient_verifie = groupe_patient
            demande.verification_groupe_ok = True

            # Récupérer les poches compatibles
            groupes_compatibles = PocheSang.groupes_donneurs_compatibles(demande.groupe_requis)
            poches = PocheSang.objects.filter(
                pk__in=poches_ids,
                statut='disponible',
                groupe_sanguin__in=groupes_compatibles,
                type_produit=demande.type_produit,
            )[:demande.quantite]

            if not poches:
                messages.error(
                    request,
                    "❌ Aucune poche compatible disponible !"
                )
                return redirect('demande_detail', pk=pk)

            for poche in poches:
                poche.statut = 'attribuee'
                poche.save()
                demande.poches_attribuees.add(poche)

                # Enregistrer dans la traçabilité
                TracabiliteEvenement.objects.create(
                    poche=poche,
                    etape='attribution',
                    effectue_par=request.user,
                    notes=f"Attribuée à la demande #{demande.pk} - {demande.hopital}"
                )

            demande.statut_demande = 'preparee'
            demande.tracabilite_verifiee = True
            demande.date_traitement = timezone.now()
            demande.save()

            messages.success(
                request,
                f"✅ Demande #{pk} validée. Groupe patient {groupe_patient} "
                f"vérifié et concordant. {poches.count()} poche(s) attribuée(s)."
            )
            envoyer_confirmation_demande(demande)

        elif action == 'livrer':
            for poche in demande.poches_attribuees.all():
                poche.statut = 'utilisee'
                poche.save()

                # Enregistrer dans la traçabilité
                TracabiliteEvenement.objects.create(
                    poche=poche,
                    etape='livraison',
                    effectue_par=request.user,
                    hopital=demande.hopital,
                    notes=f"Livrée à {demande.hopital} pour patient {demande.patient_nom}"
                )

            demande.statut_demande = 'livree'
            demande.date_livraison = timezone.now()
            demande.save()
            messages.success(request, f"✅ Demande #{pk} livrée à {demande.hopital}.")
            envoyer_confirmation_demande(demande)

        elif action == 'refuser':
            demande.statut_demande = 'refusee'
            demande.notes += f"\nRefusé le {timezone.now().strftime('%d/%m/%Y à %H:%M')}"
            demande.save()
            messages.warning(request, f"Demande #{pk} refusée.")
            envoyer_confirmation_demande(demande)

        return redirect('demande_detail', pk=pk)

    return redirect('demande_detail', pk=pk)


# ============================================================
# MESSAGES IEC / SMS
# ============================================================

@login_required
@role_required('admin')
def message_list(request):
    messages_iec = MessageIEC.objects.select_related('createur').all()
    logs_sms = LogSMS.objects.select_related('donneur').order_by('-date_envoi')[:20]

    return render(request, 'blood_bank/messages/list.html', {
        'messages_iec': messages_iec,
        'logs_sms': logs_sms,
    })


@login_required
@role_required('admin')
def message_create(request):
    form = MessageIECForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        msg = form.save(commit=False)
        msg.createur = request.user
        msg.save()
        messages.success(request, "Message créé. Cliquez sur 'Envoyer' pour le diffuser.")
        return redirect('message_list')

    return render(request, 'blood_bank/messages/form.html', {
        'form': form, 'title': 'Nouveau message IEC'
    })


@login_required
@role_required('admin')
def message_envoyer(request, pk):
    msg_iec = get_object_or_404(MessageIEC, pk=pk)

    if request.method == 'POST':
        success, fail = envoyer_sms_campagne(msg_iec)
        messages.success(
            request,
            f"Campagne envoyée! Succès: {success}, Échecs: {fail}"
        )

    return redirect('message_list')


# ============================================================
# STOCK & ALERTES AVEC GESTION TEMPS RÉEL
# ============================================================

@login_required
def stock_view(request):
    groupes = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
    config = Configuration.get_config()
    stock_detail = []

    # Vérifier et marquer les poches expirées
    poches_expirees = PocheSang.objects.filter(
        statut='disponible',
        date_expiration__lt=timezone.now().date()
    )
    for poche in poches_expirees:
        poche.statut = 'expiree'
        poche.save()

    for groupe in groupes:
        for type_produit, type_label in PocheSang.TYPE_PRODUIT_CHOICES:
            disponibles = PocheSang.objects.filter(
                groupe_sanguin=groupe,
                type_produit=type_produit,
                statut='disponible'
            )
            expirant_bientot = disponibles.filter(
                date_expiration__lte=timezone.now().date() + timedelta(days=7)
            )

            stock_detail.append({
                'groupe': groupe,
                'type_produit': type_label,
                'type_code': type_produit,
                'disponibles': disponibles.count(),
                'expirant': expirant_bientot.count(),
                'critique': disponibles.count() <= config.seuil_alerte_stock,
            })

    alertes = AlerteStock.objects.filter(resolue=False).order_by('-date_alerte')

    # Statistiques de stock global
    stats_stock = {
        'total_sang_total': PocheSang.objects.filter(type_produit='sang_total', statut='disponible').count(),
        'total_plaquettes': PocheSang.objects.filter(type_produit='culot_plaquettaire', statut='disponible').count(),
        'total_globules_rouges': PocheSang.objects.filter(type_produit='culot_erythrocytaire',
                                                          statut='disponible').count(),
        'total_plasma': PocheSang.objects.filter(type_produit='cryoprecipite', statut='disponible').count(),
    }

    return render(request, 'blood_bank/stock/view.html', {
        'stock_detail': stock_detail,
        'alertes': alertes,
        'config': config,
        'stats_stock': stats_stock,
        'types_produit': PocheSang.TYPE_PRODUIT_CHOICES,
    })


@login_required
@role_required('gestionnaire', 'admin')
def resoudre_alerte(request, pk):
    alerte = get_object_or_404(AlerteStock, pk=pk)
    alerte.resolue = True
    alerte.date_resolution = timezone.now()
    alerte.save()
    messages.success(request, "Alerte marquée comme résolue.")
    return redirect('stock_view')


# ============================================================
# CONFIGURATION AVEC GESTION DES PRIX PAR LE DIRECTEUR
# ============================================================

@login_required
@role_required('admin', 'directeur')
def configuration_view(request):
    config = Configuration.get_config()
    form = ConfigurationForm(request.POST or None, instance=config)

    if request.method == 'POST' and form.is_valid():
        config = form.save(commit=False)
        config.modifie_par = request.user
        config.save()
        messages.success(request, "Configuration mise à jour.")
        return redirect('configuration')

    return render(request, 'blood_bank/config/view.html', {
        'form': form, 'config': config
    })


# ============================================================
# UTILISATEURS
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
        user = form.save()
        messages.success(request, f"Utilisateur {user.username} créé.")
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
# STATISTIQUES & RAPPORTS AVEC BOUTONS INTERACTIFS
# ============================================================

@login_required
def statistiques(request):
    today = timezone.now().date()

    # Périodes pour les rapports
    periodes = {
        'aujourdhui': today,
        'semaine': today - timedelta(days=7),
        'mois': today - timedelta(days=30),
        'trimestre': today - timedelta(days=90),
        'annee': today - timedelta(days=365),
    }

    periode = request.GET.get('periode', 'mois')
    date_debut = periodes.get(periode, periodes['mois'])

    # Dons par mois (12 derniers mois)
    dons_par_mois = []
    for i in range(11, -1, -1):
        mois = today.month - i
        annee = today.year
        while mois <= 0:
            mois += 12
            annee -= 1
        count = PocheSang.objects.filter(
            date_prelevement__month=mois,
            date_prelevement__year=annee
        ).count()
        dons_par_mois.append({
            'mois': f"{mois:02d}/{annee}",
            'count': count
        })

    # Répartition par groupe sanguin
    repartition_groupes = []
    for groupe in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
        count = Donneur.objects.filter(groupe_sanguin=groupe, actif=True).count()
        repartition_groupes.append({'groupe': groupe, 'count': count})

    # Répartition par type de produit
    repartition_produits = []
    for type_code, type_label in PocheSang.TYPE_PRODUIT_CHOICES:
        count = PocheSang.objects.filter(type_produit=type_code).count()
        repartition_produits.append({'type': type_label, 'count': count})

    # Répartition par type de donneur
    types_donneurs = Donneur.objects.values('type_donneur').annotate(
        count=Count('id')
    ).order_by('-count')

    # Demandes par statut
    demandes_statut = DemandeTransfusion.objects.values('statut_demande').annotate(
        count=Count('id')
    )

    # Donneurs à risque
    donneurs_risque = Donneur.objects.filter(est_donneur_risque=True).count()

    # Taux d'utilisation des poches
    total_poches = PocheSang.objects.count()
    poches_utilisees = PocheSang.objects.filter(statut='utilisee').count()
    taux_utilisation = (poches_utilisees / total_poches * 100) if total_poches > 0 else 0

    context = {
        'dons_par_mois': json.dumps(dons_par_mois),
        'repartition_groupes': json.dumps(repartition_groupes),
        'repartition_produits': json.dumps(repartition_produits),
        'types_donneurs': list(types_donneurs),
        'demandes_statut': list(demandes_statut),
        'total_donneurs': Donneur.objects.filter(actif=True).count(),
        'total_poches': total_poches,
        'total_demandes': DemandeTransfusion.objects.count(),
        'total_sms': LogSMS.objects.count(),
        'donneurs_risque': donneurs_risque,
        'taux_utilisation': round(taux_utilisation, 2),
        'periode_active': periode,
        'date_debut': date_debut,
    }
    return render(request, 'blood_bank/stats/view.html', context)


# ============================================================
# GÉOLOCALISATION - API JSON
# ============================================================

@login_required
def api_donneurs_geo(request):
    """API pour la carte géolocalisée des donneurs"""
    donneurs = Donneur.objects.filter(actif=True, latitude__isnull=False)
    data = []
    for d in donneurs:
        data.append({
            'id': d.pk,
            'nom': d.nom_complet,
            'groupe': d.groupe_sanguin,
            'lat': d.latitude,
            'lon': d.longitude,
            'quartier': d.quartier,
            'peut_donner': d.peut_donner(),
            'type': d.type_donneur,
            'est_risque': d.est_donneur_risque,
        })
    return JsonResponse({'donneurs': data, 'total': len(data)})


@login_required
def api_stock(request):
    """API pour les données de stock en temps réel"""
    groupes = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
    data = {}
    for type_produit, _ in PocheSang.TYPE_PRODUIT_CHOICES:
        data[type_produit] = {}
        for g in groupes:
            data[type_produit][g] = PocheSang.objects.filter(
                groupe_sanguin=g,
                type_produit=type_produit,
                statut='disponible'
            ).count()
    return JsonResponse(data)


# ============================================================
# USSD ENDPOINT (Africa's Talking)
# ============================================================

@csrf_exempt
def ussd_endpoint(request):
    """
    Endpoint USSD pour Africa's Talking
    POST: sessionId, serviceCode, phoneNumber, text
    """
    if request.method == 'POST':
        session_id = request.POST.get('sessionId', '')
        service_code = request.POST.get('serviceCode', '')
        phone_number = request.POST.get('phoneNumber', '')
        text = request.POST.get('text', '')

        response = handle_ussd(session_id, service_code, phone_number, text)
        return HttpResponse(response, content_type='text/plain')

    return HttpResponse("Méthode non autorisée", status=405)


# ============================================================
# PROFIL UTILISATEUR
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


# ============================================================
# GESTION DES PRIX ET RÉDUCTIONS PAR LE DIRECTEUR
# ============================================================

@login_required
@role_required('directeur', 'admin')
def approuver_prix_solidaire(request, pk):
    demande = get_object_or_404(DemandeTransfusion, pk=pk)

    if request.method == 'POST':
        motif = request.POST.get('motif_solidaire', '').strip()
        annuler = request.POST.get('annuler_solidaire') == '1'
        nouveau_prix = request.POST.get('prix_personnalise', '')

        if annuler:
            demande.prix_solidaire_approuve = False
            demande.approuve_par = None
            demande.motif_solidaire = ''
            demande.prix_final = demande.calculer_prix()
            demande.save()
            messages.info(request, "Prix solidaire annulé — tarif standard appliqué.")
        elif nouveau_prix:
            demande.prix_solidaire_approuve = True
            demande.approuve_par = request.user
            demande.motif_solidaire = motif or "Prix personnalisé approuvé par le Directeur"
            demande.prix_final = int(nouveau_prix)
            demande.save()
            messages.success(
                request,
                f"✅ Prix personnalisé de {int(nouveau_prix)} FCFA approuvé par le Directeur."
            )
        else:
            demande.prix_solidaire_approuve = True
            demande.approuve_par = request.user
            demande.motif_solidaire = motif or "Approuvé par le Directeur"
            demande.prix_final = demande.calculer_prix()
            demande.save()
            config = Configuration.get_config()
            messages.success(
                request,
                f"✅ Prix solidaire approuvé par le Directeur. "
                f"Nouveau prix : {config.prix_reduit} FCFA/poche "
                f"au lieu de {config.prix_standard} FCFA."
            )

    return redirect('demande_detail', pk=pk)


# ============================================================
# EXAMEN MÉDICAL — 2 cas + Classification Donneur/Non-donneur
# ============================================================

@login_required
@role_required('medecin', 'admin', 'directeur')
def examen_medical_create(request, pk):
    """
    Cas 1 : Donneur déjà enregistré → médecin examine sa fiche
    Cas 2 : Nouveau candidat → si apte, donneur devient actif
    """
    donneur = get_object_or_404(Donneur, pk=pk)
    examen_existant = getattr(donneur, 'examen_medical', None)

    if request.method == 'POST':
        poids_ok = request.POST.get('poids_ok') == 'on'
        tension_ok = request.POST.get('tension_ok') == 'on'
        hemoglobine_ok = request.POST.get('hemoglobine_ok') == 'on'
        pas_de_maladie = request.POST.get('pas_de_maladie') == 'on'
        pas_de_medicament = request.POST.get('pas_de_medicament') == 'on'
        pas_operation_recente = request.POST.get('pas_operation_recente') == 'on'
        pas_grossesse = request.POST.get('pas_grossesse') == 'on'
        pas_allaitement = request.POST.get('pas_allaitement') == 'on'
        pas_tatouage = request.POST.get('pas_tatouage') == 'on'
        pas_voyage_risque = request.POST.get('pas_voyage_risque') == 'on'
        motif = request.POST.get('motif_inaptitude', '')

        # Mise à jour groupe sanguin si déterminé lors examen
        groupe_examen = request.POST.get('groupe_sanguin_examen', '').strip()
        if groupe_examen and not donneur.groupe_sanguin:
            donneur.groupe_sanguin = groupe_examen

        examen, created = ExamenMedical.objects.get_or_create(donneur=donneur)
        examen.poids_ok = poids_ok
        examen.tension_ok = tension_ok
        examen.hemoglobine_ok = hemoglobine_ok
        examen.pas_de_maladie = pas_de_maladie
        examen.pas_de_medicament = pas_de_medicament
        examen.pas_operation_recente = pas_operation_recente
        examen.pas_grossesse = pas_grossesse
        examen.pas_allaitement = pas_allaitement
        examen.pas_tatouage = pas_tatouage
        examen.pas_voyage_risque = pas_voyage_risque
        examen.motif_inaptitude = motif
        examen.medecin_examinateur = request.user

        # Tous les critères doivent être OK
        tous_ok = all([
            poids_ok, tension_ok, hemoglobine_ok,
            pas_de_maladie, pas_de_medicament,
            pas_operation_recente, pas_grossesse,
            pas_allaitement, pas_tatouage, pas_voyage_risque
        ])

        if tous_ok:
            examen.resultat = 'apte'
            # Classification : donneur actif
            donneur.actif = True
            donneur.classification = 'donneur'
            donneur.save()
            examen.save()
            messages.success(
                request,
                f"✅ {donneur.nom_complet} est déclaré APTE au don "
                f"par Dr. {request.user.get_full_name() or request.user.username}. "
                f"Il peut maintenant donner son sang !"
            )
            # Envoyer SMS au donneur avec les vraies clés API
            try:
                import africastalking
                from django.conf import settings
                africastalking.initialize(
                    settings.AFRICASTALKING_USERNAME,
                    settings.AFRICASTALKING_API_KEY
                )
                sms = africastalking.SMS
                sms.send(
                    f"Bonjour {donneur.nom_complet}, "
                    f"votre examen médical au CNTS Brazzaville est validé. "
                    f"Vous êtes apte au don de sang. Merci !",
                    [donneur.telephone]
                )
            except Exception as e:
                print(f"Erreur envoi SMS: {e}")
        else:
            examen.resultat = 'inapte_temporaire'
            # Classification : non-donneur
            donneur.actif = False
            donneur.classification = 'non_donneur'
            donneur.save()
            examen.save()
            messages.warning(
                request,
                f"⚠ {donneur.nom_complet} est déclaré INAPTE au don "
                f"pour le moment. Motif : {motif or 'Non précisé'}"
            )

        return redirect('donneur_detail', pk=pk)

    return render(request, 'blood_bank/donneurs/examen_medical.html', {
        'donneur': donneur,
        'examen': examen_existant,
        'groupe_choices': Donneur.GROUPE_CHOICES,
        'is_new': not examen_existant,
    })


@login_required
def examen_en_attente(request):
    """Liste des donneurs en attente d'examen médical"""
    donneurs_sans_examen = Donneur.objects.filter(
        actif=False,
        classification='candidat'
    ).exclude(examen_medical__isnull=False)

    donneurs_inaptes = Donneur.objects.filter(
        classification='non_donneur',
        examen_medical__resultat='inapte_temporaire'
    )

    return render(request, 'blood_bank/donneurs/examens_attente.html', {
        'donneurs_sans_examen': donneurs_sans_examen,
        'donneurs_inaptes': donneurs_inaptes,
    })


# ============================================================
# VISITEURS CNTS
# ============================================================

@login_required
def visiteur_list(request):
    visiteurs = VisiteurCNTS.objects.all().order_by('-date_visite')
    return render(request, 'blood_bank/visiteurs/list.html', {
        'visiteurs': visiteurs,
    })


@login_required
def visiteur_create(request):
    if request.method == 'POST':
        nom = request.POST.get('nom_complet', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        type_visite = request.POST.get('type_visite', 'rendu_poche')
        nom_patient = request.POST.get('nom_patient', '').strip()
        nb_poches = int(request.POST.get('nombre_poches_rendues', 0) or 0)
        notes = request.POST.get('notes', '').strip()

        if nom and telephone:
            visiteur = VisiteurCNTS.objects.create(
                nom_complet=nom,
                telephone=telephone,
                type_visite=type_visite,
                nom_patient=nom_patient,
                nombre_poches_rendues=nb_poches,
                notes=notes,
                enregistre_par=request.user,
            )
            messages.success(request, f"✅ Visiteur {nom} enregistré.")
            return redirect('visiteur_list')
        else:
            messages.error(request, "Nom et téléphone obligatoires.")

    return render(request, 'blood_bank/visiteurs/form.html', {
        'type_choices': VisiteurCNTS.TYPE_VISITE,
    })


# ============================================================
# CARTE DONNEUR AVEC PHOTO ET QR CODE - RÉSERVÉ AU DIRECTEUR
# ============================================================

@login_required
def carte_donneur_view(request, pk):
    donneur = get_object_or_404(Donneur, pk=pk)
    config = Configuration.get_config()
    nb_dons = PocheSang.objects.filter(
        donneur=donneur,
        statut__in=['disponible', 'attribuee', 'utilisee']
    ).count()

    eligible = nb_dons >= config.seuil_credits
    carte = getattr(donneur, 'carte', None)
    is_directeur = request.user.role in ['directeur', 'admin']

    # Seul le directeur peut générer la carte manuellement
    if request.method == 'POST' and is_directeur and eligible and not carte:
        carte = CarteDonneur(donneur=donneur, emise_par=request.user)

        # Générer le QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr_data = f"CNTS-DONNEUR-{donneur.code_unique}\n{donneur.nom_complet}\nGroupe: {donneur.groupe_sanguin}"
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        # Sauvegarder le QR code
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        carte.qr_code_data = qr_base64

        carte.save()
        messages.success(
            request,
            f"🎉 Carte donneur générée par le Directeur ! "
            f"Numéro : {carte.numero_carte}"
        )

        # SMS au donneur avec les vraies clés API Africa's Talking
        try:
            import africastalking
            from django.conf import settings
            africastalking.initialize(
                settings.AFRICASTALKING_USERNAME,
                settings.AFRICASTALKING_API_KEY
            )
            sms = africastalking.SMS
            sms.send(
                f"Félicitations {donneur.nom_complet} ! "
                f"Votre carte de donneur CNTS a été émise. "
                f"N° {carte.numero_carte}. Merci pour vos {nb_dons} dons !",
                [donneur.telephone]
            )
        except Exception as e:
            print(f"Erreur envoi SMS: {e}")

    return render(request, 'blood_bank/donneurs/carte_donneur.html', {
        'donneur': donneur,
        'carte': carte,
        'nb_dons': nb_dons,
        'eligible': eligible,
        'seuil': config.seuil_credits,
        'is_directeur': is_directeur,
    })


# ============================================================
# HÔPITAUX GÉOLOCALISÉS
# ============================================================

@login_required
def hopital_list(request):
    hopitaux = Hopital.objects.filter(actif=True)
    return render(request, 'blood_bank/hopitaux/list.html', {
        'hopitaux': hopitaux,
    })


@login_required
@role_required('admin', 'directeur', 'gestionnaire')
def hopital_create(request):
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        adresse = request.POST.get('adresse', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        quartier = request.POST.get('quartier', '').strip()
        lat = request.POST.get('latitude', '')
        lng = request.POST.get('longitude', '')
        if nom:
            Hopital.objects.create(
                nom=nom, adresse=adresse,
                telephone=telephone, quartier=quartier,
                latitude=float(lat) if lat else None,
                longitude=float(lng) if lng else None,
            )
            messages.success(request, f"✅ Hôpital {nom} ajouté.")
            return redirect('hopital_list')
    return render(request, 'blood_bank/hopitaux/form.html')


@login_required
def api_hopitaux_geo(request):
    hopitaux = Hopital.objects.filter(
        actif=True,
        latitude__isnull=False,
        longitude__isnull=False
    )
    data = {
        'hopitaux': [
            {
                'id': h.pk,
                'nom': h.nom,
                'adresse': h.adresse,
                'telephone': h.telephone,
                'quartier': h.quartier,
                'lat': h.latitude,
                'lng': h.longitude,
            }
            for h in hopitaux
        ],
        'total': hopitaux.count()
    }
    return JsonResponse(data)


# ============================================================
# TRAÇABILITÉ COMPLÈTE
# ============================================================

@login_required
def tracabilite_view(request, pk):
    poche = get_object_or_404(PocheSang, pk=pk)

    if request.method == 'POST':
        etape = request.POST.get('etape')
        notes = request.POST.get('notes', '')
        hopital_id = request.POST.get('hopital_id')
        temperature = request.POST.get('temperature', '')
        position = request.POST.get('position', '')
        latitude = request.POST.get('latitude', '')
        longitude = request.POST.get('longitude', '')

        evenement = TracabiliteEvenement(
            poche=poche,
            etape=etape,
            effectue_par=request.user,
            notes=notes,
            temperature=float(temperature) if temperature else None,
            position=position,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
        )
        if hopital_id:
            evenement.hopital_id = int(hopital_id)
        evenement.save()

        # Mettre à jour statut poche selon étape
        if etape == 'livraison':
            poche.statut = 'utilisee'
            poche.save()
        elif etape == 'rejet':
            poche.statut = 'rejetee'
            poche.save()

        messages.success(request, f"✅ Étape '{evenement.get_etape_display()}' enregistrée.")
        return redirect('tracabilite_view', pk=pk)

    evenements = poche.tracabilite.all().order_by('date_heure')
    hopitaux = Hopital.objects.filter(actif=True)
    return render(request, 'blood_bank/poches/tracabilite.html', {
        'poche': poche,
        'evenements': evenements,
        'hopitaux': hopitaux,
        'etapes': TracabiliteEvenement.ETAPE_CHOICES,
    })


# ============================================================
# ACCUEIL CANDIDAT — Donneur vs Non-donneur
# ============================================================

@login_required
def accueil_candidat(request):
    if request.method == 'POST':
        nom = request.POST.get('nom_complet', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        type_visite = request.POST.get('type_visite', 'nouveau_donneur')
        age_ok = request.POST.get('age_ok') == 'on'
        poids_ok = request.POST.get('poids_ok') == 'on'
        bonne_sante = request.POST.get('bonne_sante') == 'on'
        pas_don_recent = request.POST.get('pas_don_recent') == 'on'
        notes = request.POST.get('notes', '')

        # Vérifier si le candidat existe déjà
        donneur_existant = Donneur.objects.filter(telephone=telephone).first()

        if donneur_existant:
            type_visite = 'donneur_existant'
            candidat = CandidatDon(
                nom_complet=nom,
                telephone=telephone,
                type_visite=type_visite,
                age_ok=age_ok,
                poids_ok=poids_ok,
                bonne_sante=bonne_sante,
                pas_don_recent=pas_don_recent,
                notes=notes,
                accueilli_par=request.user,
                donneur_associe=donneur_existant,
            )
        else:
            candidat = CandidatDon(
                nom_complet=nom,
                telephone=telephone,
                type_visite=type_visite,
                age_ok=age_ok,
                poids_ok=poids_ok,
                bonne_sante=bonne_sante,
                pas_don_recent=pas_don_recent,
                notes=notes,
                accueilli_par=request.user,
            )

        candidat.evaluer_eligibilite()
        candidat.save()

        if candidat.eligible_don and type_visite == 'nouveau_donneur':
            messages.success(
                request,
                f"✅ {nom} est éligible au don ! "
                f"Orientez-le vers l'examen médical."
            )
            # Créer un donneur en attente d'examen
            donneur = Donneur.objects.create(
                nom_complet=nom,
                telephone=telephone,
                actif=False,
                classification='candidat'
            )
            candidat.donneur_associe = donneur
            candidat.save()
        elif type_visite == 'donneur_existant' and donneur_existant:
            messages.info(
                request,
                f"📋 Donneur existant — {donneur_existant.nom_complet} "
                f"({donneur_existant.classification})"
            )
        elif type_visite in ['rendre_poche', 'famille_patient']:
            messages.info(request, f"🩸 Enregistrement de la visite de {nom}.")
        else:
            messages.warning(
                request,
                f"⚠ {nom} n'est pas éligible au don pour le moment."
            )
        return redirect('accueil_candidat')

    candidats_jour = CandidatDon.objects.filter(
        date_visite__date=timezone.now().date()
    ).order_by('-date_visite')

    return render(request, 'blood_bank/accueil/candidat.html', {
        'type_choices': CandidatDon.TYPE_VISITE,
        'candidats_jour': candidats_jour,
    })


# ============================================================
# API POUR STATISTIQUES INTERACTIVES
# ============================================================

@login_required
def api_statistiques(request, type_stat):
    """API pour les statistiques interactives"""
    if type_stat == 'dons_par_periode':
        periode = request.GET.get('periode', 'mois')
        today = timezone.now().date()

        if periode == 'semaine':
            data = []
            for i in range(6, -1, -1):
                jour = today - timedelta(days=i)
                count = PocheSang.objects.filter(date_prelevement=jour).count()
                data.append({'date': jour.strftime('%d/%m'), 'count': count})
        elif periode == 'mois':
            data = []
            for i in range(29, -1, -1):
                jour = today - timedelta(days=i)
                if jour.month == today.month:
                    count = PocheSang.objects.filter(date_prelevement=jour).count()
                    data.append({'date': jour.strftime('%d/%m'), 'count': count})
        elif periode == 'annee':
            data = []
            for mois in range(1, 13):
                count = PocheSang.objects.filter(
                    date_prelevement__month=mois,
                    date_prelevement__year=today.year
                ).count()
                data.append({'mois': f"{mois:02d}/{today.year}", 'count': count})
        else:
            data = []

        return JsonResponse({'data': data})

    elif type_stat == 'repartition_groupes':
        data = []
        for groupe in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
            count = Donneur.objects.filter(groupe_sanguin=groupe, actif=True).count()
            data.append({'groupe': groupe, 'count': count})
        return JsonResponse({'data': data})

    elif type_stat == 'evolution_stock':
        data = {}
        for type_produit, type_label in PocheSang.TYPE_PRODUIT_CHOICES:
            data[type_label] = []
            for i in range(29, -1, -1):
                jour = timezone.now().date() - timedelta(days=i)
                count = PocheSang.objects.filter(
                    type_produit=type_produit,
                    date_prelevement__lte=jour,
                    statut='disponible'
                ).count()
                data[type_label].append({'date': jour.strftime('%d/%m'), 'count': count})
        return JsonResponse(data)

    return JsonResponse({'error': 'Type de statistique invalide'}, status=400)