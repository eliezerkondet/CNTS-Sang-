from datetime import date
import re
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from .models import (
    Utilisateur, Donneur, PocheSang, DemandeTransfusion,
    Configuration, MessageIEC, ExamenMedical, Hopital, CandidatDon
)

# ============================================================
# FONCTION COMMUNE : VALIDATION TÉLÉPHONE CONGO
# ============================================================
def valider_numero_congo(numero):
    if not numero:
        return numero
    # Enlève les espaces et tirets
    num = str(numero).replace(' ', '').replace('-', '')
    # Vérifie si ça commence par +242 ou 0, suivi de 4, 5 ou 6, et de 7 chiffres
    if not re.match(r'^(?:\+242|0)[456][0-9]{7}$', num):
        raise ValidationError("Numéro invalide. Format exigé : +24206XXXXXXX ou 06XXXXXXX (Congo uniquement).")
    return num


# ============================================================
# FORMULAIRES
# ============================================================

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
        self.fields['groupe_sanguin'].required = False
        self.fields['groupe_sanguin'].empty_label = "Inconnu (à déterminer au labo)"
        self.fields['groupe_sanguin'].help_text = "Laissez vide si inconnu."
        self.fields['email'].required = False
        self.fields['adresse'].required = False
        self.fields['classification'].required = False
        self.fields['motif_risque'].required = False
        if not self.instance.pk:
            self.initial['classification'] = 'candidat'

    # --- SÉCURITÉ : VÉRIFICATION DE L'ÂGE ---
    def clean_date_naissance(self):
        date_naiss = self.cleaned_data.get('date_naissance')
        if date_naiss:
            aujourd_hui = date.today()
            age = aujourd_hui.year - date_naiss.year - ((aujourd_hui.month, aujourd_hui.day) < (date_naiss.month, date_naiss.day))
            if age < 18:
                raise ValidationError(f"Le donneur doit avoir au moins 18 ans. (Âge actuel : {age} ans).")
            if age > 65:
                raise ValidationError(f"Le donneur ne peut pas avoir plus de 65 ans. (Âge actuel : {age} ans).")
        return date_naiss

    # --- SÉCURITÉ : VÉRIFICATION DU TÉLÉPHONE CONGO ---
    def clean_telephone(self):
        return valider_numero_congo(self.cleaned_data.get('telephone'))


class PocheSangForm(forms.ModelForm):
    class Meta:
        model = PocheSang
        fields = ['code_barre', 'donneur', 'volume_ml', 'lieu_collecte', 'notes']
        widgets = {
            'date_prelevement': forms.DateInput(attrs={'type': 'date'}),
            'date_expiration': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})


class AnalysePocheForm(forms.ModelForm):
    class Meta:
        model = PocheSang
        fields = [
            'test_vih', 'test_hepatite_b', 'test_hepatite_c',
            'test_syphilis', 'test_paludisme', 'test_chagas',
            'test_htlv', 'test_cytomegalovirus', 'test_ebv',
            'test_parvovirus', 'notes'
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
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'test_vih': 'Test VIH négatif',
            'test_hepatite_b': 'Test Hépatite B négatif',
            'test_hepatite_c': 'Test Hépatite C négatif',
            'test_syphilis': 'Test Syphilis négatif',
            'test_paludisme': 'Test Paludisme négatif',
            'test_chagas': 'Test Maladie de Chagas négatif',
            'test_htlv': 'Test HTLV négatif',
            'test_cytomegalovirus': 'Test Cytomégalovirus négatif',
            'test_ebv': 'Test Virus Epstein-Barr négatif',
            'test_parvovirus': 'Test Parvovirus B19 négatif',
        }


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
            'prix_personnalise': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': 'Prix personnalisé (FCFA)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['donneur_parrain'].queryset = Donneur.objects.filter(actif=True, classification='donneur')
        self.fields['donneur_parrain'].empty_label = "--- Aucun (prix standard) ---"
        self.fields['donneur_parrain'].required = False
        self.fields['prix_personnalise'].required = False


class MessageIECForm(forms.ModelForm):
    class Meta:
        model = MessageIEC
        fields = ['titre', 'contenu', 'cible', 'type_message']
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'contenu': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'maxlength': 480}),
            'cible': forms.Select(attrs={'class': 'form-select'}),
            'type_message': forms.Select(attrs={'class': 'form-select'}),
        }


class ConfigurationForm(forms.ModelForm):
    class Meta:
        model = Configuration
        fields = ['prix_standard', 'prix_reduit', 'seuil_credits', 'seuil_alerte_stock', 'message_prix_solidaire']
        widgets = {
            'prix_standard': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'prix_reduit': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'seuil_credits': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'seuil_alerte_stock': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'message_prix_solidaire': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
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

    # --- SÉCURITÉ : VÉRIFICATION DU TÉLÉPHONE CONGO POUR LES AGENTS ---
    def clean_telephone(self):
        return valider_numero_congo(self.cleaned_data.get('telephone'))

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
            'resultat': forms.Select(attrs={'class': 'form-select'}),
            'motif_inaptitude': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date_prochain_examen': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes_examen': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ['poids_ok', 'tension_ok', 'hemoglobine_ok', 'pas_de_maladie', 'pas_de_medicament', 'pas_operation_recente', 'pas_grossesse', 'pas_allaitement', 'pas_tatouage', 'pas_voyage_risque']:
            self.fields[field].widget.attrs.update({'class': 'form-check-input'})


class HopitalForm(forms.ModelForm):
    class Meta:
        model = Hopital
        fields = ['nom', 'adresse', 'telephone', 'quartier', 'latitude', 'longitude', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'quartier': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CandidatDonForm(forms.ModelForm):
    class Meta:
        model = CandidatDon
        fields = [
            'nom_complet', 'telephone', 'date_naissance', 'poids',
            'type_visite', 'age_ok', 'bonne_sante', 'pas_don_recent', 'notes'
        ]
        widgets = {
            'nom_complet': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'date_naissance': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'poids': forms.NumberInput(attrs={'class': 'form-control', 'min': 50}),
            'type_visite': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ['age_ok', 'bonne_sante', 'pas_don_recent']:
            self.fields[field].widget.attrs.update({'class': 'form-check-input'})

    # --- SÉCURITÉ : VÉRIFICATION DE L'ÂGE DES CANDIDATS ---
    def clean_date_naissance(self):
        date_naiss = self.cleaned_data.get('date_naissance')
        if date_naiss:
            aujourd_hui = date.today()
            age = aujourd_hui.year - date_naiss.year - ((aujourd_hui.month, aujourd_hui.day) < (date_naiss.month, date_naiss.day))
            if age < 18:
                raise ValidationError(f"Le candidat doit avoir au moins 18 ans. (Âge actuel : {age} ans).")
            if age > 65:
                raise ValidationError(f"Le candidat ne peut pas avoir plus de 65 ans. (Âge actuel : {age} ans).")
        return date_naiss

    # --- SÉCURITÉ : VÉRIFICATION DU TÉLÉPHONE CONGO (CANDIDATS) ---
    def clean_telephone(self):
        return valider_numero_congo(self.cleaned_data.get('telephone'))