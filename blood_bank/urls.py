from django.urls import path
from . import views

urlpatterns = [
    # Authentification
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Donneurs
    path('donneurs/', views.donneur_list, name='donneur_list'),
    path('donneurs/nouveau/', views.donneur_create, name='donneur_create'),
    path('donneurs/<int:pk>/', views.donneur_detail, name='donneur_detail'),
    path('donneurs/<int:pk>/modifier/', views.donneur_edit, name='donneur_edit'),
    path('donneurs/carte/', views.donneur_carte, name='donneur_carte'),
    path('donneurs/<int:pk>/carte/', views.carte_donneur_view, name='carte_donneur_view'),
    path('donneurs/<int:pk>/examen/', views.examen_medical_create, name='examen_medical_create'),
    path('donneurs/examens/attente/', views.examen_en_attente, name='examen_en_attente'),

    # Poches de sang
    path('poches/', views.poche_list, name='poche_list'),
    path('poches/nouveau/', views.poche_create, name='poche_create'),
    path('poches/<int:pk>/', views.poche_detail, name='poche_detail'),
    path('poches/<int:pk>/analyser/', views.poche_analyser, name='poche_analyser'),
    path('poches/<int:pk>/tracabilite/', views.tracabilite_view, name='tracabilite_view'),

    # Demandes de transfusion
    path('demandes/', views.demande_list, name='demande_list'),
    path('demandes/nouvelle/', views.demande_create, name='demande_create'),
    path('demandes/<int:pk>/', views.demande_detail, name='demande_detail'),
    path('demandes/<int:pk>/traiter/', views.demande_traiter, name='demande_traiter'),
    path('demandes/<int:pk>/prix-solidaire/', views.approuver_prix_solidaire, name='approuver_prix_solidaire'),

    # Messages IEC / SMS
    path('messages/', views.message_list, name='message_list'),
    path('messages/nouveau/', views.message_create, name='message_create'),
    path('messages/<int:pk>/envoyer/', views.message_envoyer, name='message_envoyer'),

    # Stock et alertes
    path('stock/', views.stock_view, name='stock_view'),
    path('stock/alerte/<int:pk>/resoudre/', views.resoudre_alerte, name='resoudre_alerte'),

    # Configuration
    path('configuration/', views.configuration_view, name='configuration'),

    # Utilisateurs
    path('utilisateurs/', views.utilisateur_list, name='utilisateur_list'),
    path('utilisateurs/nouveau/', views.utilisateur_create, name='utilisateur_create'),
    path('utilisateurs/<int:pk>/modifier/', views.utilisateur_edit, name='utilisateur_edit'),

    # Statistiques
    path('statistiques/', views.statistiques, name='statistiques'),
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

    # Visiteurs CNTS
    path('visiteurs/', views.visiteur_list, name='visiteur_list'),
    path('visiteurs/nouveau/', views.visiteur_create, name='visiteur_create'),

    # Accueil candidats
    path('accueil/', views.accueil_candidat, name='accueil_candidat'),

    # USSD Africa's Talking
    path('ussd/', views.ussd_endpoint, name='ussd_endpoint'),
]