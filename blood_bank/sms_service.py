"""
Service SMS / USSD via Africa's Talking
Centre National de Transfusion Sanguine - Brazzaville, Congo
"""
import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_africastalking_client():
    """Initialise le client Africa's Talking"""
    try:
        import africastalking
        africastalking.initialize(
            settings.AFRICASTALKING_USERNAME,
            settings.AFRICASTALKING_API_KEY
        )
        return africastalking.SMS
    except ImportError:
        logger.warning("Package africastalking non installé. Mode simulation activé.")
        return None
    except Exception as e:
        logger.error(f"Erreur initialisation Africa's Talking: {e}")
        return None


def envoyer_sms(telephone, message, donneur=None, message_iec=None):
    """
    Envoie un SMS via Africa's Talking
    Retourne True si succès, False sinon
    """
    from .models import LogSMS

    # Normaliser le numéro de téléphone (format international)
    tel = normaliser_telephone(telephone)

    log = LogSMS(
        destinataire=tel,
        message=message,
        statut='en_attente',
        donneur=donneur,
        message_iec=message_iec,
    )

    sms_service = get_africastalking_client()

    if sms_service is None:
        # Mode simulation pour développement
        logger.info(f"[SIMULATION SMS] À: {tel} | Message: {message[:50]}...")
        log.statut = 'simule'
        log.reference_at = f"SIM-{timezone.now().timestamp():.0f}"
        log.save()
        return True, "SMS simulé (mode développement)"

    try:
        response = sms_service.send(
            message=message,
            recipients=[tel],
            sender_id=getattr(settings, 'AFRICASTALKING_SENDER_ID', 'BanqueSang')
        )

        if response and 'SMSMessageData' in response:
            recipients_data = response['SMSMessageData'].get('Recipients', [])
            if recipients_data:
                recipient = recipients_data[0]
                status = recipient.get('status', 'Unknown')
                msg_id = recipient.get('messageId', '')

                log.statut = 'envoye' if status == 'Success' else 'echec'
                log.reference_at = msg_id
                log.save()

                if status == 'Success':
                    logger.info(f"SMS envoyé avec succès à {tel}, ID: {msg_id}")
                    return True, f"SMS envoyé (ID: {msg_id})"
                else:
                    logger.warning(f"Échec envoi SMS à {tel}: {status}")
                    return False, f"Échec: {status}"

    except Exception as e:
        logger.error(f"Erreur envoi SMS à {tel}: {e}")
        log.statut = 'erreur'
        log.reference_at = str(e)[:100]
        log.save()
        return False, f"Erreur: {str(e)}"

    log.save()
    return False, "Réponse inattendue"


def normaliser_telephone(telephone):
    """Normalise le numéro au format international +242XXXXXXXXX"""
    tel = str(telephone).strip().replace(' ', '').replace('-', '').replace('.', '')
    if tel.startswith('00242'):
        tel = '+' + tel[2:]
    elif tel.startswith('242'):
        tel = '+' + tel
    elif tel.startswith('0') and len(tel) == 9:
        tel = '+242' + tel[1:]
    elif not tel.startswith('+'):
        tel = '+242' + tel
    return tel


def envoyer_sms_campagne(message_iec):
    """
    Envoie un SMS de campagne à tous les donneurs ciblés
    """
    from .models import Donneur

    donneurs = get_donneurs_cibles(message_iec.cible)
    success_count = 0
    fail_count = 0

    for donneur in donneurs:
        if donneur.telephone:
            ok, _ = envoyer_sms(
                telephone=donneur.telephone,
                message=message_iec.contenu,
                donneur=donneur,
                message_iec=message_iec
            )
            if ok:
                success_count += 1
            else:
                fail_count += 1

    message_iec.envoye = True
    message_iec.date_envoi = timezone.now()
    message_iec.nombre_destinataires = success_count
    message_iec.statut_envoi = f"Envoyé: {success_count}, Échec: {fail_count}"
    message_iec.save()

    return success_count, fail_count


def get_donneurs_cibles(cible):
    """Retourne le queryset des donneurs selon la cible"""
    from .models import Donneur
    from datetime import timedelta

    qs = Donneur.objects.filter(actif=True)

    mapping = {
        'tous': qs,
        'benevoles': qs.filter(type_donneur='benevole'),
        'familiaux': qs.filter(type_donneur='familial'),
        'inactifs': qs.filter(
            date_dernier_don__lt=timezone.now().date() - timedelta(days=180)
        ),
        'groupe_a': qs.filter(groupe_sanguin__startswith='A'),
        'groupe_b': qs.filter(groupe_sanguin__startswith='B'),
        'groupe_o': qs.filter(groupe_sanguin__startswith='O'),
        'groupe_ab': qs.filter(groupe_sanguin__startswith='AB'),
    }
    return mapping.get(cible, qs)


def envoyer_notification_don(donneur):
    """Notifie un donneur après son don"""
    message = (
        f"Merci {donneur.nom_complet.split()[0]} pour votre don de sang! "
        f"Votre geste sauve des vies. "
        f"Crédit solidaire: {donneur.credit_solidaire}. "
        f"CNTS Brazzaville"
    )
    return envoyer_sms(donneur.telephone, message, donneur=donneur)


def envoyer_alerte_stock(groupe_sanguin, stock_actuel, seuil):
    """Envoie une alerte SMS aux gestionnaires quand le stock est bas"""
    from .models import Utilisateur

    message = (
        f"[ALERTE STOCK] Groupe {groupe_sanguin}: "
        f"seulement {stock_actuel} poche(s) disponible(s). "
        f"Seuil critique: {seuil}. "
        f"Action requise immédiatement. CNTS Brazzaville"
    )

    gestionnaires = Utilisateur.objects.filter(
        role__in=['gestionnaire', 'admin'],
        is_active=True
    )

    for user in gestionnaires:
        if user.telephone:
            envoyer_sms(user.telephone, message)

    return True


def envoyer_confirmation_demande(demande):
    """Confirme une demande de transfusion au prescripteur"""
    if not demande.telephone_contact:
        return False, "Pas de téléphone de contact"

    statut_fr = {
        'validee': 'VALIDÉE',
        'preparee': 'PRÉPARÉE - En cours de livraison',
        'livree': 'LIVRÉE',
        'refusee': 'REFUSÉE',
    }.get(demande.statut_demande, demande.statut_demande.upper())

    message = (
        f"Demande #{demande.pk} ({demande.groupe_requis}): "
        f"{statut_fr}. "
        f"Hôpital: {demande.hopital}. "
        f"CNTS Brazzaville +242 06 XXX XXXX"
    )

    return envoyer_sms(demande.telephone_contact, message)


# ============================================================
# Gestion USSD (Africa's Talking USSD)
# ============================================================

USSD_SESSIONS = {}  # En production, utiliser Redis/Cache

def handle_ussd(session_id, service_code, phone_number, text):
    """
    Gestionnaire USSD pour les donneurs
    Permet de consulter l'état des dons via téléphone simple
    """
    response = ""
    inputs = text.split('*') if text else ['']
    level = len([x for x in inputs if x])

    # Normaliser le numéro
    tel = normaliser_telephone(phone_number)

    if text == '' or text is None:
        # Menu principal
        response = (
            "CON Bienvenue au CNTS Brazzaville\n"
            "1. Mes informations de don\n"
            "2. Stock sanguin disponible\n"
            "3. Campagnes en cours\n"
            "4. Contacter le centre\n"
            "0. Quitter"
        )

    elif text == '1':
        response = (
            "CON Espace Donneur\n"
            "1. Mon dernier don\n"
            "2. Mes crédits solidaires\n"
            "3. Puis-je donner?\n"
            "0. Retour"
        )

    elif text == '1*1':
        from .models import Donneur
        try:
            donneur = Donneur.objects.get(telephone__icontains=tel[-9:])
            if donneur.date_dernier_don:
                response = f"END Votre dernier don: {donneur.date_dernier_don.strftime('%d/%m/%Y')}\nMerci pour votre générosité!"
            else:
                response = "END Aucun don enregistré. Venez au CNTS pour votre 1er don!"
        except Donneur.DoesNotExist:
            response = "END Numéro non trouvé. Inscrivez-vous au CNTS Brazzaville."

    elif text == '1*2':
        from .models import Donneur
        try:
            donneur = Donneur.objects.get(telephone__icontains=tel[-9:])
            response = f"END Crédits solidaires: {donneur.credit_solidaire}\nGroupe: {donneur.groupe_sanguin}\nMerci {donneur.nom_complet.split()[0]}!"
        except Donneur.DoesNotExist:
            response = "END Numéro non enregistré au CNTS."

    elif text == '1*3':
        from .models import Donneur
        try:
            donneur = Donneur.objects.get(telephone__icontains=tel[-9:])
            if donneur.peut_donner():
                response = "END ✓ Vous pouvez donner votre sang!\nVenez au CNTS, Ave. 3 Martyrs, Brazzaville."
            else:
                from datetime import timedelta
                prochaine = donneur.date_dernier_don + timedelta(days=56)
                response = f"END Prochain don possible le {prochaine.strftime('%d/%m/%Y')}.\nMerci pour votre fidélité!"
        except Donneur.DoesNotExist:
            response = "END Venez vous inscrire au CNTS pour donner votre sang!"

    elif text == '2':
        from .models import PocheSang
        stocks = []
        for groupe in ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']:
            count = PocheSang.objects.filter(groupe_sanguin=groupe, statut='disponible').count()
            if count > 0:
                stocks.append(f"{groupe}:{count}")
        if stocks:
            response = f"END Stock disponible:\n" + " | ".join(stocks) + "\nCNTS Brazzaville"
        else:
            response = "END Stock critique! Venez donner votre sang urgemment!\nCNTS Ave. 3 Martyrs, Brazzaville"

    elif text == '3':
        from .models import MessageIEC
        msg = MessageIEC.objects.filter(envoye=False).first()
        if msg:
            response = f"END Campagne en cours:\n{msg.titre}\n{msg.contenu[:100]}"
        else:
            response = "END Aucune campagne en cours.\nMerci de votre intérêt!"

    elif text == '4':
        response = (
            "END Centre National de Transfusion Sanguine\n"
            "Adresse: Ave. des 3 Martyrs, Brazzaville\n"
            "Tél: +242 06 XXX XXXX\n"
            "Lun-Sam: 7h-17h"
        )

    elif text == '0':
        response = "END Merci d'avoir contacté le CNTS.\nEnsemble, sauvons des vies!"

    else:
        response = "END Option invalide.\nRecomposez *XXX# pour recommencer."

    return response