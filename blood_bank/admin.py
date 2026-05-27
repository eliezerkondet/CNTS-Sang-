from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Utilisateur, Donneur, PocheSang, DemandeTransfusion,
    Configuration, MessageIEC, AlerteStock, LogSMS,
    VisiteurCNTS, ExamenMedical, CarteDonneur, Hopital,
    TracabiliteEvenement, CandidatDon
)


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ['username', 'get_full_name', 'role', 'centre_ref', 'telephone', 'is_active']
    list_filter = ['role', 'is_active', 'is_staff']
    search_fields = ['username', 'first_name', 'last_name', 'email', 'telephone']

    fieldsets = UserAdmin.fieldsets + (
        ('Informations CNTS', {
            'fields': ('role', 'centre_ref', 'telephone', 'avatar'),
            'classes': ('wide',)
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'role', 'centre_ref', 'telephone'),
        }),
    )


@admin.register(Donneur)
class DonneurAdmin(admin.ModelAdmin):
    list_display = [
        'nom_complet', 'code_unique', 'groupe_sanguin', 'type_donneur',
        'classification', 'credit_solidaire', 'est_donneur_risque', 'actif'
    ]
    list_filter = [
        'groupe_sanguin', 'type_donneur', 'sexe', 'actif',
        'classification', 'est_donneur_risque'
    ]
    search_fields = ['nom_complet', 'code_unique', 'telephone', 'email']
    readonly_fields = ['code_unique', 'credit_solidaire', 'date_inscription']

    fieldsets = (
        ('Informations personnelles', {
            'fields': ('nom_complet', 'sexe', 'date_naissance', 'poids', 'telephone', 'email')
        }),
        ('Adresse et géolocalisation', {
            'fields': ('adresse', 'quartier', 'latitude', 'longitude')
        }),
        ('Donneur', {
            'fields': ('groupe_sanguin', 'type_donneur', 'classification', 'actif')
        }),
        ('Crédits et dons', {
            'fields': ('credit_solidaire', 'date_dernier_don', 'code_unique')
        }),
        ('Risque', {
            'fields': ('est_donneur_risque', 'motif_risque'),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('date_inscription',),
            'classes': ('collapse',)
        }),
    )


@admin.register(PocheSang)
class PocheSangAdmin(admin.ModelAdmin):
    list_display = [
        'code_barre', 'type_produit', 'groupe_sanguin', 'statut',
        'date_prelevement', 'date_expiration', 'tests_ok'
    ]
    list_filter = [
        'statut', 'groupe_sanguin', 'type_produit', 'tests_ok',
        'test_vih', 'test_hepatite_b', 'test_hepatite_c', 'test_syphilis'
    ]
    search_fields = ['code_barre', 'donneur__nom_complet']
    readonly_fields = ['code_barre', 'date_expiration', 'tests_ok']

    fieldsets = (
        ('Identification', {
            'fields': ('code_barre', 'donneur', 'type_produit', 'statut')
        }),
        ('Dates', {
            'fields': ('date_prelevement', 'date_expiration', 'date_analyse')
        }),
        ('Caractéristiques', {
            'fields': ('groupe_sanguin', 'volume_ml', 'notes')
        }),
        ('Tests médicaux', {
            'fields': (
                'test_vih', 'test_hepatite_b', 'test_hepatite_c', 'test_syphilis',
                'test_paludisme', 'test_chagas', 'test_htlv', 'test_cytomegalovirus',
                'test_ebv', 'test_parvovirus', 'tests_ok'
            ),
            'classes': ('wide',)
        }),
        ('Personnel', {
            'fields': ('creee_par', 'analysee_par'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DemandeTransfusion)
class DemandeTransfusionAdmin(admin.ModelAdmin):
    list_display = [
        'pk', 'hopital', 'groupe_requis', 'type_produit', 'quantite',
        'urgence', 'prix_final', 'statut_demande', 'date_demande'
    ]
    list_filter = [
        'statut_demande', 'urgence', 'groupe_requis', 'type_produit',
        'compatibilite_verifiee', 'disponibilite_verifiee'
    ]
    search_fields = ['hopital', 'medecin', 'patient_nom', 'telephone_contact']
    readonly_fields = ['prix_final', 'date_demande']

    fieldsets = (
        ('Demande', {
            'fields': ('hopital', 'medecin', 'patient_nom', 'telephone_contact')
        }),
        ('Produit requis', {
            'fields': ('groupe_requis', 'type_produit', 'quantite', 'urgence')
        }),
        ('Prix', {
            'fields': ('prix_final', 'prix_personnalise', 'prix_solidaire_approuve', 'motif_solidaire', 'approuve_par')
        }),
        ('Vérifications', {
            'fields': (
                'groupe_patient_verifie', 'verification_groupe_ok',
                'compatibilite_verifiee', 'disponibilite_verifiee', 'tracabilite_verifiee'
            )
        }),
        ('Suivi', {
            'fields': ('statut_demande', 'donneur_parrain', 'prescripteur', 'poches_attribuees')
        }),
        ('Dates', {
            'fields': ('date_demande', 'date_traitement', 'date_livraison')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )

    filter_horizontal = ['poches_attribuees']


@admin.register(Configuration)
class ConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        'pk', 'prix_standard', 'prix_reduit', 'seuil_credits',
        'seuil_alerte_stock', 'date_modification'
    ]
    readonly_fields = ['date_modification']

    def has_add_permission(self, request):
        # Empêcher la création de plusieurs configurations
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(MessageIEC)
class MessageIECAdmin(admin.ModelAdmin):
    list_display = [
        'titre', 'cible', 'type_message', 'envoye',
        'nombre_destinataires', 'date_creation', 'date_envoi'
    ]
    list_filter = ['cible', 'type_message', 'envoye']
    search_fields = ['titre', 'contenu']
    readonly_fields = ['date_creation', 'date_envoi', 'nombre_destinataires', 'statut_envoi']

    actions = ['envoyer_message']

    def envoyer_message(self, request, queryset):
        for message in queryset:
            if not message.envoye:
                # Logique d'envoi (à implémenter)
                message.envoye = True
                message.date_envoi = timezone.now()
                message.save()
        self.message_user(request, f"{queryset.count()} message(s) marqué(s) comme envoyé.")

    envoyer_message.short_description = "Marquer comme envoyé"


@admin.register(AlerteStock)
class AlerteStockAdmin(admin.ModelAdmin):
    list_display = [
        'groupe_sanguin', 'type_produit', 'niveau', 'stock_actuel',
        'seuil', 'resolue', 'date_alerte'
    ]
    list_filter = ['niveau', 'resolue', 'groupe_sanguin', 'type_produit']
    search_fields = ['groupe_sanguin']
    readonly_fields = ['date_alerte', 'date_resolution']

    actions = ['resoudre_alertes']

    def resoudre_alertes(self, request, queryset):
        from django.utils import timezone
        queryset.update(resolue=True, date_resolution=timezone.now())
        self.message_user(request, f"{queryset.count()} alerte(s) résolue(s).")

    resoudre_alertes.short_description = "Résoudre les alertes sélectionnées"


@admin.register(LogSMS)
class LogSMSAdmin(admin.ModelAdmin):
    list_display = ['destinataire', 'statut', 'date_envoi', 'donneur']
    list_filter = ['statut', 'date_envoi']
    search_fields = ['destinataire', 'reference_at']
    readonly_fields = ['date_envoi']


@admin.register(VisiteurCNTS)
class VisiteurCNTSAdmin(admin.ModelAdmin):
    list_display = ['nom_complet', 'telephone', 'type_visite', 'date_visite', 'enregistre_par']
    list_filter = ['type_visite', 'sms_resultats_envoye']
    search_fields = ['nom_complet', 'telephone', 'nom_patient']
    readonly_fields = ['date_visite']


@admin.register(ExamenMedical)
class ExamenMedicalAdmin(admin.ModelAdmin):
    list_display = ['donneur', 'resultat', 'date_examen', 'medecin_examinateur']
    list_filter = ['resultat', 'poids_ok', 'tension_ok', 'hemoglobine_ok']
    search_fields = ['donneur__nom_complet', 'motif_inaptitude']
    readonly_fields = ['date_examen']

    fieldsets = (
        ('Donneur', {
            'fields': ('donneur', 'medecin_examinateur')
        }),
        ('Critères médicaux', {
            'fields': (
                'poids_ok', 'tension_ok', 'hemoglobine_ok', 'pas_de_maladie',
                'pas_de_medicament', 'pas_operation_recente', 'pas_grossesse',
                'pas_allaitement', 'pas_tatouage', 'pas_voyage_risque'
            )
        }),
        ('Résultat', {
            'fields': ('resultat', 'motif_inaptitude', 'date_prochain_examen', 'notes_examen')
        }),
        ('Dates', {
            'fields': ('date_examen',)
        }),
    )


@admin.register(CarteDonneur)
class CarteDonneurAdmin(admin.ModelAdmin):
    list_display = ['numero_carte', 'donneur', 'date_emission', 'date_expiration_carte', 'active', 'emise_par']
    list_filter = ['active', 'date_emission']
    search_fields = ['numero_carte', 'donneur__nom_complet']
    readonly_fields = ['numero_carte', 'date_emission']

    fieldsets = (
        ('Carte', {
            'fields': ('numero_carte', 'donneur', 'active', 'emise_par')
        }),
        ('Médias', {
            'fields': ('photo', 'qr_code', 'qr_code_data')
        }),
        ('Validité', {
            'fields': ('date_emission', 'date_expiration_carte')
        }),
    )


@admin.register(Hopital)
class HopitalAdmin(admin.ModelAdmin):
    list_display = ['nom', 'quartier', 'telephone', 'actif', 'date_ajout']
    list_filter = ['actif', 'quartier']
    search_fields = ['nom', 'adresse', 'telephone', 'quartier']
    readonly_fields = ['date_ajout']


@admin.register(TracabiliteEvenement)
class TracabiliteEvenementAdmin(admin.ModelAdmin):
    list_display = ['poche', 'etape', 'date_heure', 'effectue_par', 'hopital']
    list_filter = ['etape', 'date_heure']
    search_fields = ['poche__code_barre', 'notes']
    readonly_fields = ['date_heure']

    fieldsets = (
        ('Événement', {
            'fields': ('poche', 'etape', 'effectue_par')
        }),
        ('Lieu', {
            'fields': ('hopital', 'position', 'latitude', 'longitude')
        }),
        ('Détails', {
            'fields': ('temperature', 'notes')
        }),
        ('Date', {
            'fields': ('date_heure',)
        }),
    )


@admin.register(CandidatDon)
class CandidatDonAdmin(admin.ModelAdmin):
    list_display = ['nom_complet', 'telephone', 'type_visite', 'eligible_don', 'date_visite', 'accueilli_par']
    list_filter = ['type_visite', 'eligible_don', 'age_ok', 'bonne_sante', 'pas_don_recent']  # ← corrigé ici
    search_fields = ['nom_complet', 'telephone', 'notes']
    readonly_fields = ['date_visite', 'eligible_don']

    fieldsets = (
        ('Candidat', {
            'fields': ('nom_complet', 'telephone', 'type_visite', 'accueilli_par')
        }),
        ('Critères d\'éligibilité', {
            'fields': ('age_ok', 'bonne_sante', 'pas_don_recent')  # ← poids_ok enlevé
        }),
        ('Résultat', {
            'fields': ('eligible_don', 'donneur_associe', 'notes')
        }),
        ('Date', {
            'fields': ('date_visite',)
        }),
    )


# Import pour timezone dans l'action envoyer_message
from django.utils import timezone 