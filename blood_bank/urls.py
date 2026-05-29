from django.urls import path
from . import views
from .views import (
    visiteur_list, visiteur_create, visiteur_detail,
    visiteur_prelever, demandes_a_livrer, demande_livrer
)

urlpatterns = [
    # Auth
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Donneurs
    path('donneurs/', views.donneur_list, name='donneur_list'),
    path('donneurs/nouveau/', views.donneur_create, name='donneur_create'),
    path('donneurs/carte/', views.donneur_carte, name='donneur_carte'),
    path('donneurs/examens/attente/', views.examen_en_attente, name='examen_en_attente'),
    path('donneurs/recherche/', views.recherche_medicale, name='recherche_medicale'),
    path('donneurs/<int:pk>/', views.donneur_detail, name='donneur_detail'),
    path('donneurs/<int:pk>/modifier/', views.donneur_edit, name='donneur_edit'),
    path('donneurs/<int:pk>/carte/', views.carte_donneur_view, name='carte_donneur_view'),
    path('donneurs/<int:pk>/examen/', views.examen_medical_create, name='examen_medical_create'),

    # Poches
    path('poches/', views.poche_list, name='poche_list'),
    path('poches/nouveau/', views.poche_create, name='poche_create'),
    path('poches/pooling/', views.pooling_plaquettes, name='pooling_plaquettes'),
    path('poches/<int:pk>/', views.poche_detail, name='poche_detail'),
    path('poches/<int:pk>/analyser/', views.poche_analyser, name='poche_analyser'),
    path('poches/<int:pk>/tracabilite/', views.tracabilite_view, name='tracabilite_view'),
    path('poches/<int:pk>/fractionner/', views.fractionner_poche, name='fractionner_poche'),

    # Demandes
    path('demandes/', views.demande_list, name='demande_list'),
    path('demandes/nouvelle/', views.demande_create, name='demande_create'),
    path('demandes/a-livrer/', demandes_a_livrer, name='demandes_a_livrer'),
    path('demandes/<int:pk>/', views.demande_detail, name='demande_detail'),
    path('demandes/<int:pk>/traiter/', views.demande_traiter, name='demande_traiter'),
    path('demandes/<int:pk>/livrer/', demande_livrer, name='demande_livrer'),
    path('demandes/<int:pk>/prix-solidaire/', views.approuver_prix_solidaire, name='approuver_prix_solidaire'),

    # Messages IEC / SMS
    path('messages/', views.message_list, name='message_list'),
    path('messages/nouveau/', views.message_create, name='message_create'),
    path('messages/<int:pk>/envoyer/', views.message_envoyer, name='message_envoyer'),

    # Stock
    path('stock/', views.stock_view, name='stock_view'),
    path('stock/alerte/<int:pk>/resoudre/', views.resoudre_alerte, name='resoudre_alerte'),

    # Configuration
    path('configuration/', views.configuration_view, name='configuration'),

    # Utilisateurs
    path('utilisateurs/', views.utilisateur_list, name='utilisateur_list'),
    path('utilisateurs/nouveau/', views.utilisateur_create, name='utilisateur_create'),
    path('utilisateurs/<int:pk>/modifier/', views.utilisateur_edit, name='utilisateur_edit'),

    # Statistiques + IA
    path('statistiques/', views.statistiques, name='statistiques'),
    path('statistiques/ia/', views.lancer_prediction_ia, name='lancer_prediction_ia'),
    path('api/statistiques/<str:type_stat>/', views.api_statistiques, name='api_statistiques'),

    # Profil
    path('profil/', views.profil, name='profil'),
    path('profil/modifier/', views.profil_edit, name='profil_edit'),

    # API
    path('api/donneurs/geo/', views.api_donneurs_geo, name='api_donneurs_geo'),
    path('api/stock/', views.api_stock, name='api_stock'),
    path('api/hopitaux/geo/', views.api_hopitaux_geo, name='api_hopitaux_geo'),

    # Hôpitaux
    path('hopitaux/', views.hopital_list, name='hopital_list'),
    path('hopitaux/nouveau/', views.hopital_create, name='hopital_create'),

    # Visiteurs
    path('visiteurs/', visiteur_list, name='visiteur_list'),
    path('visiteurs/creer/', visiteur_create, name='visiteur_create'),
    path('visiteurs/<int:pk>/', visiteur_detail, name='visiteur_detail'),
    path('visiteurs/<int:pk>/prelever/', visiteur_prelever, name='visiteur_prelever'),

    # Accueil candidats
    path('accueil/', views.accueil_candidat, name='accueil_candidat'),
    path('prelevement/candidats/', views.candidats_a_prelever, name='candidats_a_prelever'),
    path('prelevement/candidat/<int:pk>/', views.prelever_candidat, name='prelever_candidat'),

    # Résultats publics
    path('resultats/donneur/<str:code_unique>/', views.resultats_donneur, name='resultats_donneur'),
    path('resultats/visiteur/<str:telephone>/', views.resultats_visiteur, name='resultats_visiteur'),
    path('resultats/<str:code_acces>/', views.candidat_resultats, name='candidat_resultats'),

    # USSD
    path('ussd/', views.ussd_endpoint, name='ussd_endpoint'),

    
    path('recherche/medicale/', views.recherche_medicale, name='recherche_medicale'),
    path('resultats/donneur/<str:code>/', views.resultats_donneur, name='resultats_donneur'),
    path('examens/candidats/', views.examen_candidats, name='examen_candidats'), 
    path('examen/candidat/<int:pk>/', views.examen_medical_candidat, name='examen_medical_candidat'),
    path('donneur/readmettre/<int:pk>/', views.readmettre_donneur, name='readmettre_donneur'),
    path('pre-enregistrement/', views.pre_enregistrement_donneur, name='pre_enregistrement_donneur'),
    path('pre-enregistrements/', views.liste_pre_enregistrements, name='liste_pre_enregistrements'),
    path('pre-enregistrement/traiter/<int:pk>/', views.traiter_pre_enregistrement, name='traiter_pre_enregistrement'),
    path('utilisateurs/<int:pk>/supprimer/', views.utilisateur_delete, name='utilisateur_delete'),
]