import os
import logging

logger = logging.getLogger(__name__)

firebase_app = None

try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    FIREBASE_CRED_PATH = os.getenv("FIREBASE_CRED_PATH", "serviceAccountKey.json")

    if os.path.isfile(FIREBASE_CRED_PATH):
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_CRED_PATH)
            firebase_app = firebase_admin.initialize_app(cred)
            logger.info("Initialized Firebase app using credentials at %s", FIREBASE_CRED_PATH)
        else:
            firebase_app = firebase_admin.get_app()
    else:
        firebase_app = None
        logger.warning("Firebase credentials not found at %s; FCM disabled", FIREBASE_CRED_PATH)
except Exception as e:
    firebase_app = None
    logger.exception("Failed to initialize Firebase app: %s", e)


def send_fault_notification(tokens, node_id, confidence):
    if not tokens:
        logger.info("No FCM tokens provided; skipping notification")
        return
    if firebase_app is None:
        logger.warning("Firebase app not initialized; cannot send FCM notification")
        return
    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title="⚡ Fault Detected",
                body=f"Node {node_id} reported faulty with confidence {confidence}%"
            ),
            tokens=tokens
        )
        response = messaging.send_multicast(message, app=firebase_app)
        logger.info("Sent FCM multicast: success=%s failure=%s", response.success_count, response.failure_count)
    except Exception:
        logger.exception("Error sending FCM notification")
        return
