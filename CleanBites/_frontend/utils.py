from _api._users.models import Customer, DM
from django.db.models import Q
import logging

# Get logger
logger = logging.getLogger(__name__)


def has_unread_messages(user):
    """Check if a user has any unread messages."""
    if not user or not user.is_authenticated:
        logger.debug(f"User not authenticated, returning False")
        return False

    try:
        customer = Customer.objects.get(email=user.email)
        has_unread = DM.objects.filter(receiver=customer, read=False).exists()
        logger.debug(f"User {user.email} has unread messages: {has_unread}")
        return has_unread
    except Customer.DoesNotExist:
        logger.debug(f"Customer with email {user.email} does not exist")
        return False
    except Exception as e:
        logger.error(f"Error checking unread messages: {str(e)}")
        return False
