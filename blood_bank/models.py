from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid


class Utilisateur(AbstractUser):
    ROLES = [
        ('admin', 'Administrateur'),
        ('directeur', 'Directeur CNTS'),
        ('medecin', 'Médecin du centre'),
        ('infirmier', 'Infirmier'),
        ('technicien', 'Technicien de laboratoire'),
        ('gestionnaire', 'Gestionnaire de stock'),
        ('responsable', 'Responsable de délivrance'),
        ('prescripteur', 'Prescripteur hospitalier'),
        ('autorite', 'Autorité sanitaire'),
    ]
    role = models.CharField(max_length=20, choices=ROLES, default='infirmier')
    centre_ref = models.CharField(max_length=200, blank=True, default='Centre National de Transfusion Sanguine')
    telephone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    def is_admin(self):
        return self.role == 'admin'

    def is_personnel_medical(self):
        return self.role in ['medecin', 'infirmier', 'technicien']

    def is_logistique(self):
        return self.role in ['gestionnaire', 'responsable']


class Donneur(models.Model):
    SEXE_CHOICES = [('M', 'Masculin'), ('F', 'Féminin')]
    GROUPE_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]
    TYPE_DONNEUR = [
        ('benevole', 'Bénévole'),
        ('familial', 'Don familial'),
        ('remunere', 'Rémunéré'),
    ]
    CLASSIFICATION_CHOICES = [
        ('candidat', 'Candidat au don'),
        ('donneur', 'Donneur actif'),
        ('non_donneur', 'Non-donneur'),
        ('suspendu', 'Suspendu temporairement'),
    ]

    code_unique = models.CharField(max_length=20, unique=True, blank=True)
    nom_complet = models.CharField(max_length=200)
    sexe = models.CharField(max_length=1, choices=SEXE_CHOICES)
    date_naissance = models.DateField()
    poids = models.IntegerField(help_text="Poids en kg")
    telephone = models.CharField(max_length=20)
    groupe_sanguin = models.CharField(
        max_length=3,
        choices=GROUPE_CHOICES,
        blank=True,
        default='',
        verbose_name="Groupe sanguin",
        help_text="Laissez vide si inconnu — sera déterminé après analyses labo"
    )
    type_donneur = models.CharField(max_length=20, choices=TYPE_DONNEUR, default='benevole')
    credit_solidaire = models.IntegerField(default=0)
    adresse = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    date_inscription = models.DateTimeField(auto_now_add=True)
    actif = models.BooleanField(default=True)
    date_dernier_don = models.DateField(null=True, blank=True)

    # Nouveaux champs pour la classification et les risques
    classification = models.CharField(
        max_length=20,
        choices=CLASSIFICATION_CHOICES,
        default='candidat',
        verbose_name="Classification donneur"
    )
    est_donneur_risque = models.BooleanField(
        default=False,
        verbose_name="Donneur à risque",
        help_text="Identifié lors des examens médicaux ou tests positifs"
    )
    motif_risque = models.TextField(
        blank=True,
        verbose_name="Motif de risque",
        help_text="Raison pour laquelle le donneur est identifié comme à risque"
    )
    date_dernier_examen = models.DateField(null=True, blank=True)

    # Géolocalisation du donneur
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    quartier = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "Donneur"
        verbose_name_plural = "Donneurs"
        ordering = ['-date_inscription']

    def __str__(self):
        return f"{self.nom_complet} ({self.groupe_sanguin}) - {self.get_classification_display()}"

    def save(self, *args, **kwargs):
        if not self.code_unique:
            self.code_unique = f"DON-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    @property
    def age(self):
        today = timezone.now().date()
        return today.year - self.date_naissance.year - (
                (today.month, today.day) < (self.date_naissance.month, self.date_naissance.day)
        )

    @property
    def nombre_dons(self):
        return self.pochesang_set.filter(
            statut__in=['disponible', 'attribuee', 'utilisee']
        ).count()

    def peut_donner(self):
        """Vérifie si le donneur peut donner (intervalle min 56 jours)"""
        if not self.date_dernier_don:
            return self.classification == 'donneur' and self.actif
        delta = (timezone.now().date() - self.date_dernier_don).days
        return delta >= 56 and self.classification == 'donneur' and self.actif


class PocheSang(models.Model):
    STATUT_CHOICES = [
        ('collecte', 'Collectée'),
        ('en_analyse', 'En analyse'),
        ('validee', 'Validée'),
        ('disponible', 'Disponible'),
        ('attribuee', 'Attribuée'),
        ('utilisee', 'Utilisée'),
        ('expiree', 'Expirée'),
        ('rejetee', 'Rejetée'),
    ]

    # ── 4 TYPES DE PRODUITS SANGUINS ──────────────────────────
    TYPE_PRODUIT_CHOICES = [
        ('sang_total', 'Sang total'),
        ('culot_erythrocytaire', 'Culot érythrocytaire'),
        ('culot_plaquettaire', 'Culot plaquettaire'),
        ('cryoprecipite', 'Cryoprécipité'),
    ]

    # Durées de conservation par type (en jours)
    DUREE_CONSERVATION = {
        'sang_total': 42,
        'culot_erythrocytaire': 42,
        'culot_plaquettaire': 5,
        'cryoprecipite': 365,
    }

    code_barre = models.CharField(max_length=50, unique=True, blank=True)
    type_produit = models.CharField(
        max_length=30,
        choices=TYPE_PRODUIT_CHOICES,
        default='sang_total',
        verbose_name="Type de produit sanguin"
    )
    date_prelevement = models.DateField()
    date_expiration = models.DateField()
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='collecte')

    # Tests médicaux complets (selon l'image fournie)
    test_vih = models.BooleanField(null=True, blank=True, verbose_name="Test VIH négatif")
    test_hepatite_b = models.BooleanField(null=True, blank=True, verbose_name="Test Hépatite B négatif")
    test_hepatite_c = models.BooleanField(null=True, blank=True, verbose_name="Test Hépatite C négatif")
    test_syphilis = models.BooleanField(null=True, blank=True, verbose_name="Test Syphilis négatif")
    test_paludisme = models.BooleanField(null=True, blank=True, verbose_name="Test Paludisme négatif")
    test_chagas = models.BooleanField(null=True, blank=True, verbose_name="Test Maladie de Chagas négatif")
    test_htlv = models.BooleanField(null=True, blank=True, verbose_name="Test HTLV négatif")
    test_cytomegalovirus = models.BooleanField(null=True, blank=True, verbose_name="Test Cytomégalovirus négatif")
    test_ebv = models.BooleanField(null=True, blank=True, verbose_name="Test Virus Epstein-Barr négatif")
    test_parvovirus = models.BooleanField(null=True, blank=True, verbose_name="Test Parvovirus B19 négatif")

    donneur = models.ForeignKey(Donneur, on_delete=models.PROTECT)
    volume_ml = models.IntegerField(default=450)
    groupe_sanguin = models.CharField(max_length=3, blank=True)
    notes = models.TextField(blank=True)
    tests_ok = models.BooleanField(default=False, verbose_name="Tous les tests sont négatifs")

    creee_par = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='poches_creees'
    )
    date_analyse = models.DateTimeField(null=True, blank=True)
    analysee_par = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='poches_analysees'
    )

    class Meta:
        verbose_name = "Poche de sang"
        verbose_name_plural = "Poches de sang"
        ordering = ['-date_prelevement']

    def __str__(self):
        return f"{self.code_barre} - {self.get_type_produit_display()} {self.groupe_sanguin} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code_barre:
            # Préfixe selon le type de produit
            prefixes = {
                'sang_total': 'ST',
                'culot_erythrocytaire': 'CE',
                'culot_plaquettaire': 'CP',
                'cryoprecipite': 'CR',
            }
            prefix = prefixes.get(self.type_produit, 'PS')
            self.code_barre = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
        if not self.groupe_sanguin:
            self.groupe_sanguin = self.donneur.groupe_sanguin
        if not self.date_expiration:
            from datetime import timedelta
            duree = self.DUREE_CONSERVATION.get(self.type_produit, 42)
            self.date_expiration = self.date_prelevement + timedelta(days=duree)

        # Vérifier si tous les tests sont négatifs
        tests_list = [
            self.test_vih, self.test_hepatite_b, self.test_hepatite_c,
            self.test_syphilis, self.test_paludisme, self.test_chagas,
            self.test_htlv, self.test_cytomegalovirus, self.test_ebv,
            self.test_parvovirus
        ]
        self.tests_ok = all(test is True for test in tests_list if test is not None)

        super().save(*args, **kwargs)

    @property
    def est_expiree(self):
        return timezone.now().date() > self.date_expiration

    @property
    def jours_restants(self):
        delta = self.date_expiration - timezone.now().date()
        return delta.days

    @staticmethod
    def groupes_compatibles_receveur(groupe_donneur):
        """
        Compatibilité stricte — même groupe + même rhésus UNIQUEMENT.
        Règle CNTS : on ne transfuse qu'avec le groupe identique du patient.
        """
        return [groupe_donneur]

    @staticmethod
    def groupes_donneurs_compatibles(groupe_receveur):
        """
        Même règle stricte — seul le groupe identique est compatible.
        """
        return [groupe_receveur]

    @staticmethod
    def verifier_compatibilite_patient(groupe_poche, groupe_patient):
        """
        Vérification OBLIGATOIRE avant délivrance :
        Le groupe de la poche doit être identique au groupe du patient.
        Retourne True si compatible, False sinon.
        """
        return groupe_poche == groupe_patient


class Configuration(models.Model):
    prix_standard = models.IntegerField(
        default=7500,
        help_text="Prix standard en FCFA (défaut CNTS Brazzaville : 7500 FCFA)"
    )
    prix_reduit = models.IntegerField(
        default=3750,
        help_text="Prix solidaire en FCFA — appliqué par le directeur aux donneurs réguliers et leur famille"
    )
    seuil_credits = models.IntegerField(
        default=3,
        help_text="Nombre minimum de dons pour bénéficier du prix solidaire"
    )
    seuil_alerte_stock = models.IntegerField(
        default=10,
        help_text="Seuil d'alerte stock par groupe sanguin"
    )
    message_prix_solidaire = models.TextField(
        blank=True,
        default="Le prix solidaire est accordé aux donneurs réguliers et à leur famille selon décision du Directeur du CNTS.",
        help_text="Message explicatif affiché pour le prix solidaire"
    )
    date_modification = models.DateTimeField(auto_now=True)
    modifie_par = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "Configuration"
        verbose_name_plural = "Configurations"

    def __str__(self):
        return f"Config ({self.date_modification.strftime('%d/%m/%Y')})"

    @classmethod
    def get_config(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config


class DemandeTransfusion(models.Model):
    URGENCE_CHOICES = [
        ('normal', 'Normal'),
        ('urgent', 'Urgent'),
        ('critique', 'Critique'),
    ]
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('en_cours', 'En cours de traitement'),
        ('validee', 'Validée'),
        ('preparee', 'Préparée'),
        ('livree', 'Livrée'),
        ('refusee', 'Refusée'),
    ]
    GROUPE_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]
    TYPE_PRODUIT_CHOICES = [
        ('sang_total', 'Sang total'),
        ('culot_erythrocytaire', 'Culot érythrocytaire'),
        ('culot_plaquettaire', 'Culot plaquettaire'),
        ('cryoprecipite', 'Cryoprécipité'),
    ]

    hopital = models.CharField(max_length=200)
    medecin = models.CharField(max_length=200)
    groupe_requis = models.CharField(max_length=3, choices=GROUPE_CHOICES)
    type_produit = models.CharField(
        max_length=30,
        choices=TYPE_PRODUIT_CHOICES,
        default='sang_total',
        verbose_name="Type de produit requis"
    )
    quantite = models.IntegerField(default=1)
    urgence = models.CharField(max_length=10, choices=URGENCE_CHOICES, default='normal')
    prix_final = models.IntegerField(default=0)
    statut_demande = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')

    # ── VÉRIFICATION GROUPE PATIENT ──────────────────────────
    groupe_patient_verifie = models.CharField(
        max_length=3,
        choices=GROUPE_CHOICES,
        blank=True,
        verbose_name="Groupe sanguin vérifié du patient",
        help_text="Groupe confirmé par le labo avant délivrance"
    )
    verification_groupe_ok = models.BooleanField(
        default=False,
        verbose_name="Groupe patient vérifié et concordant"
    )
    donneur_parrain = models.ForeignKey(
        Donneur, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_parrainées'
    )
    prescripteur = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_prescrites'
    )
    poches_attribuees = models.ManyToManyField(PocheSang, blank=True, related_name='demandes')
    date_demande = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)
    date_livraison = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    patient_nom = models.CharField(max_length=200, blank=True)
    telephone_contact = models.CharField(max_length=20, blank=True)
    # Compatibilité sanguine vérifiée
    compatibilite_verifiee = models.BooleanField(default=False)
    disponibilite_verifiee = models.BooleanField(default=False)
    tracabilite_verifiee = models.BooleanField(default=False)

    # Gestion des prix par le directeur
    prix_solidaire_approuve = models.BooleanField(
        default=False,
        verbose_name="Prix solidaire approuvé par le directeur"
    )
    approuve_par = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_approuvees',
        verbose_name="Approuvé par"
    )
    motif_solidaire = models.TextField(
        blank=True,
        verbose_name="Motif de la réduction",
        help_text="Justification de l'application du prix solidaire"
    )
    prix_personnalise = models.IntegerField(
        null=True, blank=True,
        verbose_name="Prix personnalisé",
        help_text="Prix fixé directement par le directeur"
    )

    class Meta:
        verbose_name = "Demande de transfusion"
        verbose_name_plural = "Demandes de transfusion"
        ordering = ['-date_demande']

    def __str__(self):
        return f"Demande #{self.pk} - {self.hopital} - {self.groupe_requis}"

    def calculer_prix(self):
        config = Configuration.get_config()
        if self.prix_personnalise:
            return self.prix_personnalise * self.quantite
        if self.prix_solidaire_approuve or (
                self.donneur_parrain and self.donneur_parrain.credit_solidaire >= config.seuil_credits):
            return config.prix_reduit * self.quantite
        return config.prix_standard * self.quantite

    def verifier_compatibilite(self):
        self.compatibilite_verifiee = True
        self.save(update_fields=['compatibilite_verifiee'])

    def verifier_disponibilite(self):
        groupes_compatibles = PocheSang.groupes_donneurs_compatibles(self.groupe_requis)
        dispo = PocheSang.objects.filter(
            groupe_sanguin__in=groupes_compatibles,
            type_produit=self.type_produit,
            statut='disponible'
        ).count()
        self.disponibilite_verifiee = True
        self.save(update_fields=['disponibilite_verifiee'])
        return dispo >= self.quantite


class MessageIEC(models.Model):
    CIBLE_CHOICES = [
        ('tous', 'Tous les donneurs'),
        ('benevoles', 'Donneurs bénévoles'),
        ('familiaux', 'Donneurs familiaux'),
        ('inactifs', 'Donneurs inactifs'),
        ('groupe_a', 'Groupe A'),
        ('groupe_b', 'Groupe B'),
        ('groupe_o', 'Groupe O'),
        ('groupe_ab', 'Groupe AB'),
        ('risque', 'Donneurs à risque'),
    ]
    TYPE_CHOICES = [
        ('sms', 'SMS'),
        ('ussd', 'USSD'),
        ('notification', 'Notification'),
    ]

    titre = models.CharField(max_length=200)
    contenu = models.TextField()
    cible = models.CharField(max_length=20, choices=CIBLE_CHOICES, default='tous')
    type_message = models.CharField(max_length=20, choices=TYPE_CHOICES, default='sms')
    createur = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True,
        related_name='messages_crees'
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_envoi = models.DateTimeField(null=True, blank=True)
    envoye = models.BooleanField(default=False)
    nombre_destinataires = models.IntegerField(default=0)
    statut_envoi = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Message IEC"
        verbose_name_plural = "Messages IEC"
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.titre} → {self.get_cible_display()}"


class AlerteStock(models.Model):
    NIVEAU_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Avertissement'),
        ('critical', 'Critique'),
    ]
    groupe_sanguin = models.CharField(max_length=3)
    type_produit = models.CharField(
        max_length=30,
        choices=PocheSang.TYPE_PRODUIT_CHOICES,
        default='sang_total',
        verbose_name="Type de produit"
    )
    niveau = models.CharField(max_length=10, choices=NIVEAU_CHOICES)
    message = models.TextField()
    stock_actuel = models.IntegerField()
    seuil = models.IntegerField()
    date_alerte = models.DateTimeField(auto_now_add=True)
    resolue = models.BooleanField(default=False)
    date_resolution = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Alerte de stock"
        verbose_name_plural = "Alertes de stock"
        ordering = ['-date_alerte']

    def __str__(self):
        return f"Alerte {self.groupe_sanguin} - {self.type_produit} - {self.get_niveau_display()}"


class LogSMS(models.Model):
    destinataire = models.CharField(max_length=20)
    message = models.TextField()
    statut = models.CharField(max_length=50)
    reference_at = models.CharField(max_length=100, blank=True)
    date_envoi = models.DateTimeField(auto_now_add=True)
    donneur = models.ForeignKey(Donneur, on_delete=models.SET_NULL, null=True, blank=True)
    message_iec = models.ForeignKey(MessageIEC, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Log SMS"
        verbose_name_plural = "Logs SMS"
        ordering = ['-date_envoi']

    def __str__(self):
        return f"SMS → {self.destinataire} ({self.statut})"


# ============================================================
# VISITEUR CNTS — celui qui vient rendre le sang sans être donneur
# ============================================================

# models.py

class VisiteurCNTS(models.Model):
    """
    Donneur familial/remplaçant : personne qui vient donner son sang
    pour un patient spécifique (rendu de poche = don de sang)
    """
    TYPE_VISITE = [
        ('don_familial', 'Don familial (pour un patient)'),
        ('retrait_resultats', 'Retrait de résultats'),
        ('renseignement', 'Renseignement'),
    ]

    STATUT_DON = [
        ('en_attente', 'En attente de prélèvement'),
        ('preleve', 'Prélèvement effectué'),
        ('en_analyse', 'En analyse'),
        ('disponible', 'Disponible pour patient'),
        ('utilisee', 'Utilisée pour patient'),
        ('rejetee', 'Rejetée'),
    ]

    # Informations du visiteur (donneur familial)
    nom_complet = models.CharField(max_length=200, verbose_name="Nom et prénom")
    telephone = models.CharField(max_length=20)
    type_visite = models.CharField(max_length=30, choices=TYPE_VISITE, default='don_familial')

    # Informations sur le patient
    nom_patient = models.CharField(max_length=200, verbose_name="Nom du patient concerné")
    prenom_patient = models.CharField(max_length=200, blank=True, verbose_name="Prénom du patient")
    telephone_patient = models.CharField(max_length=20, blank=True, verbose_name="Téléphone du patient")
    groupe_patient = models.CharField(
        max_length=3,
        blank=True,
        choices=Donneur.GROUPE_CHOICES,
        verbose_name="Groupe sanguin du patient"
    )
    hopital_patient = models.CharField(max_length=200, blank=True, verbose_name="Hôpital du patient")
    demande_associee = models.ForeignKey(
        'DemandeTransfusion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='visiteurs_associes',
        verbose_name="Demande de transfusion associée"
    )

    # Don du sang
    poche_associee = models.OneToOneField(
        'PocheSang',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='visiteur_donneur',
        verbose_name="Poche de sang associée"
    )
    statut_don = models.CharField(
        max_length=20,
        choices=STATUT_DON,
        default='en_attente',
        verbose_name="Statut du don"
    )
    date_prelevement = models.DateTimeField(null=True, blank=True, verbose_name="Date de prélèvement")
    preleve_par = models.ForeignKey(
        Utilisateur,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prelevements_visiteurs',
        verbose_name="Prélevé par"
    )

    # Autres informations
    notes = models.TextField(blank=True)
    date_visite = models.DateTimeField(auto_now_add=True)
    enregistre_par = models.ForeignKey(
        Utilisateur,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='visiteurs_enregistres'
    )
    sms_resultats_envoye = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Donneur familial"
        verbose_name_plural = "Donneurs familiaux"
        ordering = ['-date_visite']

    def __str__(self):
        return f"{self.nom_complet} → Patient: {self.nom_patient} ({self.get_statut_don_display()})"

    def creer_poche_sang(self, utilisateur):
        """
        Crée une poche de sang à partir du don du visiteur
        """
        from django.utils import timezone
        from datetime import timedelta

        # Créer un donneur temporaire si ce visiteur n'est pas encore donneur
        donneur, created = Donneur.objects.get_or_create(
            telephone=self.telephone,
            defaults={
                'nom_complet': self.nom_complet,
                'telephone': self.telephone,
                'sexe': 'M',  # À déterminer lors de l'examen
                'date_naissance': timezone.now().date() - timedelta(days=365 * 25),  # Âge par défaut
                'poids': 70,  # Valeur par défaut
                'type_donneur': 'familial',
                'classification': 'candidat',
                'actif': False,
            }
        )

        # Créer la poche de sang
        poche = PocheSang.objects.create(
            donneur=donneur,
            type_produit='sang_total',
            date_prelevement=timezone.now().date(),
            statut='en_analyse',
            volume_ml=450,
            groupe_sanguin='',  # Sera déterminé par les tests
            creee_par=utilisateur,
            notes=f"Don familial pour patient: {self.nom_patient} - Hôpital: {self.hopital_patient}"
        )

        self.poche_associee = poche
        self.statut_don = 'preleve'
        self.date_prelevement = timezone.now()
        self.preleve_par = utilisateur
        self.save()

        return poche

# ============================================================
# EXAMEN MÉDICAL COMPLET — avant enregistrement comme donneur
# ============================================================

class ExamenMedical(models.Model):
    """
    Résultats de l'examen médical obligatoire avant
    d'enregistrer quelqu'un comme donneur.
    """
    RESULTAT_CHOICES = [
        ('apte', 'Apte au don'),
        ('inapte_temporaire', 'Inapte temporaire'),
        ('inapte_definitif', 'Inapte définitif'),
        ('en_attente', 'En attente de résultats'),
    ]

    donneur = models.OneToOneField(
        Donneur,
        on_delete=models.CASCADE,
        related_name='examen_medical'
    )

    # Critères médicaux complets
    poids_ok = models.BooleanField(
        default=False,
        verbose_name="Poids ≥ 50 kg"
    )
    tension_ok = models.BooleanField(
        default=False,
        verbose_name="Tension artérielle normale"
    )
    hemoglobine_ok = models.BooleanField(
        default=False,
        verbose_name="Taux d'hémoglobine suffisant (≥ 12.5 g/dL)"
    )
    pas_de_maladie = models.BooleanField(
        default=False,
        verbose_name="Pas de maladie chronique"
    )
    pas_de_medicament = models.BooleanField(
        default=False,
        verbose_name="Pas sous médication incompatible"
    )
    pas_operation_recente = models.BooleanField(
        default=False,
        verbose_name="Pas d'opération récente (6 derniers mois)"
    )
    pas_grossesse = models.BooleanField(
        default=False,
        verbose_name="Pas de grossesse en cours (pour femmes)"
    )
    pas_allaitement = models.BooleanField(
        default=False,
        verbose_name="Pas d'allaitement en cours"
    )
    pas_tatouage = models.BooleanField(
        default=False,
        verbose_name="Pas de tatouage/percing récent (12 mois)"
    )
    pas_voyage_risque = models.BooleanField(
        default=False,
        verbose_name="Pas de voyage en zone endémique récent"
    )

    # Résultat global
    resultat = models.CharField(
        max_length=30,
        choices=RESULTAT_CHOICES,
        default='en_attente'
    )
    motif_inaptitude = models.TextField(
        blank=True,
        verbose_name="Motif d'inaptitude si applicable"
    )
    date_examen = models.DateTimeField(auto_now_add=True)
    medecin_examinateur = models.ForeignKey(
        Utilisateur,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='examens_effectues'
    )
    date_prochain_examen = models.DateField(
        null=True, blank=True,
        verbose_name="Date du prochain examen (si inapte temporaire)"
    )
    notes_examen = models.TextField(
        blank=True,
        verbose_name="Notes complémentaires"
    )

    class Meta:
        verbose_name = "Examen médical"
        verbose_name_plural = "Examens médicaux"
        ordering = ['-date_examen']

    def __str__(self):
        return f"Examen {self.donneur.nom_complet} — {self.get_resultat_display()}"

    @property
    def tous_criteres_ok(self):
        return all([
            self.poids_ok,
            self.tension_ok,
            self.hemoglobine_ok,
            self.pas_de_maladie,
            self.pas_de_medicament,
            self.pas_operation_recente,
            self.pas_grossesse,
            self.pas_allaitement,
            self.pas_tatouage,
            self.pas_voyage_risque,
        ])


# ============================================================
# CARTE DONNEUR — avec photo et QR code, réservée au Directeur
# ============================================================

class CarteDonneur(models.Model):
    """
    Carte officielle générée uniquement par le Directeur après 3 dons.
    Contient photo + QR code unique.
    """
    donneur = models.OneToOneField(
        Donneur,
        on_delete=models.CASCADE,
        related_name='carte'
    )
    numero_carte = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        verbose_name="Numéro de carte"
    )
    qr_code = models.ImageField(
        upload_to='cartes/qr/',
        blank=True, null=True,
        verbose_name="QR Code"
    )
    qr_code_data = models.TextField(
        blank=True,
        verbose_name="Données du QR code (base64)",
        help_text="Stockage temporaire du QR code en base64"
    )
    photo = models.ImageField(
        upload_to='cartes/photos/',
        blank=True, null=True,
        verbose_name="Photo du donneur"
    )
    date_emission = models.DateTimeField(auto_now_add=True)
    date_expiration_carte = models.DateField(
        null=True, blank=True,
        verbose_name="Date d'expiration de la carte"
    )
    active = models.BooleanField(default=True)
    emise_par = models.ForeignKey(
        Utilisateur,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cartes_emises'
    )

    class Meta:
        verbose_name = "Carte donneur"
        verbose_name_plural = "Cartes donneurs"
        ordering = ['-date_emission']

    def __str__(self):
        return f"Carte {self.numero_carte} — {self.donneur.nom_complet}"

    def save(self, *args, **kwargs):
        if not self.numero_carte:
            # Format : CNTS-BRAZZA-XXXXXX
            self.numero_carte = f"CNTS-BZV-{uuid.uuid4().hex[:6].upper()}"
        if not self.date_expiration_carte:
            from datetime import timedelta
            # Carte valable 2 ans
            self.date_expiration_carte = timezone.now().date() + timedelta(days=730)
        super().save(*args, **kwargs)

    @property
    def est_valide(self):
        return self.active and self.date_expiration_carte >= timezone.now().date()

    @classmethod
    def generer_si_eligible(cls, donneur):
        """
        Note: Cette méthode n'est plus automatique.
        Seul le Directeur peut générer la carte via l'interface.
        Cette méthode est conservée pour compatibilité mais n'est plus appelée automatiquement.
        """
        return None


# ============================================================
# HÔPITAL — pour géolocalisation
# ============================================================

class Hopital(models.Model):
    nom = models.CharField(max_length=200)
    adresse = models.TextField(blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    quartier = models.CharField(max_length=100, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    actif = models.BooleanField(default=True)
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Hôpital"
        verbose_name_plural = "Hôpitaux"
        ordering = ['nom']

    def __str__(self):
        return self.nom


# ============================================================
# TRACABILITÉ COMPLÈTE — du prélèvement à la livraison
# ============================================================

class TracabiliteEvenement(models.Model):
    ETAPE_CHOICES = [
        ('prelevement', 'Prélèvement'),
        ('transport_labo', 'Transport vers laboratoire'),
        ('reception_labo', 'Réception laboratoire'),
        ('analyse', 'Analyse en laboratoire'),
        ('validation', 'Validation des tests'),
        ('stockage', 'Stockage'),
        ('attribution', 'Attribution à une demande'),
        ('preparation', 'Préparation à la livraison'),
        ('transport_hopital', 'Transport vers hôpital'),
        ('livraison', 'Livraison à l\'hôpital'),
        ('transfusion', 'Transfusion au patient'),
        ('rejet', 'Rejet/Destruction'),
    ]

    poche = models.ForeignKey(PocheSang, on_delete=models.CASCADE, related_name='tracabilite')
    etape = models.CharField(max_length=30, choices=ETAPE_CHOICES)
    date_heure = models.DateTimeField(auto_now_add=True)
    effectue_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    hopital = models.ForeignKey(Hopital, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    temperature = models.FloatField(null=True, blank=True, help_text="Température en °C")
    position = models.CharField(max_length=200, blank=True, help_text="Position/GPS")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Événement de traçabilité"
        verbose_name_plural = "Événements de traçabilité"
        ordering = ['date_heure']

    def __str__(self):
        return f"{self.poche.code_barre} - {self.get_etape_display()} - {self.date_heure.strftime('%d/%m/%Y %H:%M')}"


# ============================================================
# CANDIDAT DON — Accueil et classification
# ============================================================

class CandidatDon(models.Model):
    TYPE_VISITE = [
        ('nouveau_donneur', 'Nouveau donneur'),
        ('donneur_existant', 'Donneur existant'),
        ('rendre_poche', 'Rendre une poche'),
        ('famille_patient', 'Famille de patient'),
        ('information', 'Demande d\'information'),
    ]

    nom_complet = models.CharField(max_length=200)
    telephone = models.CharField(max_length=20)
    type_visite = models.CharField(max_length=30, choices=TYPE_VISITE)
    date_visite = models.DateTimeField(auto_now_add=True)
    accueilli_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)

    # Critères d'éligibilité
    age_ok = models.BooleanField(default=False, verbose_name="Âge entre 18 et 65 ans")
    poids_ok = models.BooleanField(default=False, verbose_name="Poids ≥ 50 kg")
    bonne_sante = models.BooleanField(default=False, verbose_name="Bonne santé générale")
    pas_don_recent = models.BooleanField(default=False, verbose_name="Pas de don dans les 56 derniers jours")

    eligible_don = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    donneur_associe = models.ForeignKey(Donneur, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Candidat au don"
        verbose_name_plural = "Candidats au don"
        ordering = ['-date_visite']

    def __str__(self):
        return f"{self.nom_complet} - {self.get_type_visite_display()} - {'Éligible' if self.eligible_don else 'Non éligible'}"

    def evaluer_eligibilite(self):
        """Évalue si le candidat est éligible au don"""
        self.eligible_don = all([
            self.age_ok,
            self.poids_ok,
            self.bonne_sante,
            self.pas_don_recent,
            self.type_visite in ['nouveau_donneur', 'donneur_existant']
        ])
        return self.eligible_don