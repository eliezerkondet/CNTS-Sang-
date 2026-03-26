from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import (
    Utilisateur, Donneur, PocheSang, DemandeTransfusion,
    Configuration, MessageIEC, ExamenMedical, Hopital, CandidatDon
)


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': "Nom d'utilisateur",
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe',
        })
    )


class DonneurForm(forms.ModelForm):
    class Meta:
        model = Donneur
        fields = [
            'nom_complet', 'sexe', 'date_naissance', 'poids',
            'telephone', 'groupe_sanguin', 'type_donneur',
            'adresse', 'email', 'quartier', 'latitude', 'longitude',
            'classification', 'est_donneur_risque', 'motif_risque'
        ]
        widgets = {
            'nom_complet': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom et prénom'}),
            'sexe': forms.Select(attrs={'class': 'form-select'}),
            'date_naissance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'poids': forms.NumberInput(attrs={'class': 'form-control', 'min': 50, 'max': 200}),
            'telephone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+242 XX XXX XXXX'}),
            'groupe_sanguin': forms.Select(attrs={'class': 'form-select'}),
            'type_donneur': forms.Select(attrs={'class': 'form-select'}),
            'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'quartier': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Quartier / Zone'}),
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
            'classification': forms.Select(attrs={'class': 'form-select'}),
            'est_donneur_risque': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'motif_risque': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Raison du marquage à risque'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Groupe sanguin optionnel — sera déterminé après analyses labo
        self.fields['groupe_sanguin'].required = False
        self.fields['groupe_sanguin'].empty_label = "Inconnu (à déterminer au labo)"
        self.fields['groupe_sanguin'].help_text = (
            "Laissez vide si le groupe n'est pas encore connu. "
            "Il sera mis à jour après les analyses biologiques."
        )
        # Email optionnel
        self.fields['email'].required = False
        # Adresse optionnelle
        self.fields['adresse'].required = False
        # Classification optionnelle
        self.fields['classification'].required = False
        self.fields['classification'].help_text = "Classification du donneur (candidat, donneur, non-donneur)"
        # Motif risque optionnel
        self.fields['motif_risque'].required = False
        # Masquer certains champs pour certains utilisateurs
        if not self.instance.pk:
            # Pour un nouveau donneur, par défaut classification = candidat
            self.initial['classification'] = 'candidat'


class PocheSangForm(forms.ModelForm):
    class Meta:
        model = PocheSang
        fields = ['donneur', 'date_prelevement', 'type_produit', 'volume_ml', 'notes']
        widgets = {
            'donneur': forms.Select(attrs={'class': 'form-select'}),
            'date_prelevement': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'type_produit': forms.Select(attrs={'class': 'form-select'}),
            'volume_ml': forms.NumberInput(attrs={'class': 'form-control', 'min': 300, 'max': 600}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['type_produit'].help_text = "Type de produit sanguin à collecter"


class AnalysePocheForm(forms.ModelForm):
    class Meta:
        model = PocheSang
        fields = [
            'test_vih', 'test_hepatite_b', 'test_hepatite_c', 'test_syphilis',
            'test_paludisme', 'test_chagas', 'test_htlv', 'test_cytomegalovirus',
            'test_ebv', 'test_parvovirus', 'notes'
        ]
        widgets = {
            'test_vih': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'test_hepatite_b': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'test_hepatite_c': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'test_syphilis': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'test_paludisme': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'test_chagas': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'test_htlv': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'test_cytomegalovirus': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'test_ebv': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'test_parvovirus': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'test_vih': 'Test VIH négatif ✓',
            'test_hepatite_b': 'Test Hépatite B négatif ✓',
            'test_hepatite_c': 'Test Hépatite C négatif ✓',
            'test_syphilis': 'Test Syphilis négatif ✓',
            'test_paludisme': 'Test Paludisme négatif ✓',
            'test_chagas': 'Test Maladie de Chagas négatif ✓',
            'test_htlv': 'Test HTLV négatif ✓',
            'test_cytomegalovirus': 'Test Cytomégalovirus négatif ✓',
            'test_ebv': 'Test EBV négatif ✓',
            'test_parvovirus': 'Test Parvovirus B19 négatif ✓',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].help_text = "Notes supplémentaires sur l'analyse"


class DemandeTransfusionForm(forms.ModelForm):
    class Meta:
        model = DemandeTransfusion
        fields = [
            'hopital', 'medecin', 'groupe_requis', 'type_produit',
            'quantite', 'urgence', 'patient_nom', 'telephone_contact',
            'donneur_parrain', 'notes', 'prix_personnalise'
        ]
        widgets = {
            'hopital': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom de l\'hôpital'}),
            'medecin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Dr. Nom Prénom'}),
            'groupe_requis': forms.Select(attrs={'class': 'form-select', 'id': 'id_groupe_requis'}),
            'type_produit': forms.Select(attrs={'class': 'form-select', 'id': 'id_type_produit'}),
            'quantite': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 20}),
            'urgence': forms.Select(attrs={'class': 'form-select'}),
            'patient_nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom du patient'}),
            'telephone_contact': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+242 XX XXX XXXX'}),
            'donneur_parrain': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'prix_personnalise': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0, 'placeholder': 'Prix personnalisé (FCFA)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['donneur_parrain'].queryset = Donneur.objects.filter(actif=True, classification='donneur')
        self.fields['donneur_parrain'].empty_label = "--- Aucun (prix standard) ---"
        self.fields['donneur_parrain'].required = False
        self.fields['prix_personnalise'].required = False
        self.fields['prix_personnalise'].help_text = "Prix personnalisé fixé par le Directeur (optionnel)"


class MessageIECForm(forms.ModelForm):
    class Meta:
        model = MessageIEC
        fields = ['titre', 'contenu', 'cible', 'type_message']
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Titre du message'}),
            'contenu': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Contenu du SMS (max 160 caractères recommandé)',
                'maxlength': 480,
            }),
            'cible': forms.Select(attrs={'class': 'form-select'}),
            'type_message': forms.Select(attrs={'class': 'form-select'}),
        }


class ConfigurationForm(forms.ModelForm):
    class Meta:
        model = Configuration
        fields = [
            'prix_standard', 'prix_reduit', 'seuil_credits',
            'seuil_alerte_stock', 'message_prix_solidaire'
        ]
        widgets = {
            'prix_standard': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 0,
                'placeholder': '7500'
            }),
            'prix_reduit': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 0,
                'placeholder': 'Ex: 3750'
            }),
            'seuil_credits': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1
            }),
            'seuil_alerte_stock': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1
            }),
            'message_prix_solidaire': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3
            }),
        }
        labels = {
            'prix_standard': 'Prix standard (FCFA/poche)',
            'prix_reduit': 'Prix solidaire (FCFA/poche) — décidé par le Directeur',
            'seuil_credits': 'Nombre de dons minimum pour le prix solidaire',
            'seuil_alerte_stock': 'Seuil d\'alerte stock (poches par groupe)',
            'message_prix_solidaire': 'Message d\'explication du prix solidaire',
        }
        help_texts = {
            'prix_reduit': 'Prix réduit accordé aux donneurs réguliers et à leur famille selon décision du Directeur.',
            'seuil_credits': 'Ex: 3 dons minimum pour bénéficier du prix solidaire',
        }


class UtilisateurForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Mot de passe',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=False
    )
    password2 = forms.CharField(
        label='Confirmer le mot de passe',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=False
    )

    class Meta:
        model = Utilisateur
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'centre_ref', 'telephone', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'centre_ref': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p1 != p2:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('password1'):
            user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class ExamenMedicalForm(forms.ModelForm):
    class Meta:
        model = ExamenMedical
        fields = [
            'poids_ok', 'tension_ok', 'hemoglobine_ok', 'pas_de_maladie',
            'pas_de_medicament', 'pas_operation_recente', 'pas_grossesse',
            'pas_allaitement', 'pas_tatouage', 'pas_voyage_risque',
            'resultat', 'motif_inaptitude', 'date_prochain_examen', 'notes_examen'
        ]
        widgets = {
            'poids_ok': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tension_ok': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'hemoglobine_ok': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pas_de_maladie': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pas_de_medicament': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pas_operation_recente': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pas_grossesse': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pas_allaitement': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pas_tatouage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pas_voyage_risque': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'resultat': forms.Select(attrs={'class': 'form-select'}),
            'motif_inaptitude': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date_prochain_examen': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes_examen': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'poids_ok': 'Poids ≥ 50 kg',
            'tension_ok': 'Tension artérielle normale',
            'hemoglobine_ok': 'Taux d\'hémoglobine suffisant (≥ 12.5 g/dL)',
            'pas_de_maladie': 'Pas de maladie chronique',
            'pas_de_medicament': 'Pas sous médication incompatible',
            'pas_operation_recente': 'Pas d\'opération récente (6 derniers mois)',
            'pas_grossesse': 'Pas de grossesse en cours (pour femmes)',
            'pas_allaitement': 'Pas d\'allaitement en cours',
            'pas_tatouage': 'Pas de tatouage/percing récent (12 mois)',
            'pas_voyage_risque': 'Pas de voyage en zone endémique récent',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_prochain_examen'].required = False
        self.fields['motif_inaptitude'].required = False
        self.fields['notes_examen'].required = False


class HopitalForm(forms.ModelForm):
    class Meta:
        model = Hopital
        fields = ['nom', 'adresse', 'telephone', 'quartier', 'latitude', 'longitude', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom de l\'hôpital'}),
            'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Adresse complète'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+242 XX XXX XXXX'}),
            'quartier': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Quartier'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CandidatDonForm(forms.ModelForm):
    class Meta:
        model = CandidatDon
        fields = [
            'nom_complet', 'telephone', 'type_visite', 'age_ok', 'poids_ok',
            'bonne_sante', 'pas_don_recent', 'notes'
        ]
        widgets = {
            'nom_complet': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom et prénom'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+242 XX XXX XXXX'}),
            'type_visite': forms.Select(attrs={'class': 'form-select'}),
            'age_ok': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'poids_ok': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'bonne_sante': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pas_don_recent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'age_ok': 'Âge entre 18 et 65 ans',
            'poids_ok': 'Poids ≥ 50 kg',
            'bonne_sante': 'Bonne santé générale',
            'pas_don_recent': 'Pas de don dans les 56 derniers jours',
        }