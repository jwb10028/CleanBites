from django.shortcuts import render
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import login, get_user_model
from rest_framework.permissions import AllowAny
from google.oauth2 import id_token
from google.auth.transport import requests
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .models import Customer, Moderator, DM, FavoriteRestaurant
from .serializers import (
    CustomerSerializer,
    ModeratorSerializer,
    DMSerializer,
    FavoriteRestaurantSerializer,
)

import logging

logger = logging.getLogger(__name__)


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """

    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    # Filters: allow ?email=john@example.com or ?first_name=John
    filterset_fields = ["email", "first_name", "last_name"]

    # Search: allow ?search=John (search in first name and last name)
    search_fields = ["first_name", "last_name"]

    # Ordering: allow ?ordering=first_name (or ?ordering=-first_name for descending)
    ordering_fields = ["first_name", "last_name", "email"]


class ModeratorViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows moderators to be viewed or edited.
    """

    queryset = Moderator.objects.all()
    serializer_class = ModeratorSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    # Filters: allow ?email=admin@example.com or ?first_name=John
    filterset_fields = ["email", "first_name", "last_name"]

    # Search: allow ?search=John (search in first name and last name)
    search_fields = ["first_name", "last_name"]

    # Ordering: allow ?ordering=first_name
    ordering_fields = ["first_name", "last_name", "email"]


class DMViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows direct messages (DMs) to be viewed or edited.
    """

    queryset = DM.objects.all()
    serializer_class = DMSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    # Filters: allow ?sender=1 or ?receiver=2
    filterset_fields = ["sender", "receiver", "flagged"]
    # Search: allow ?search=message (binary field so not applicable, but can be used for metadata)
    search_fields = []
    # Ordering: allow ?ordering=sent_at
    ordering_fields = ["sent_at"]


class FavoriteRestaurantViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows favorite restaurants to be managed.
    """

    queryset = FavoriteRestaurant.objects.all()
    serializer_class = FavoriteRestaurantSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    # Filters: allow ?customer=1 or ?restaurant=2
    filterset_fields = ["customer", "restaurant"]
    # Search: allow ?search=restaurant_name (not needed as we filter by ID)
    search_fields = []
    # Ordering: No explicit ordering needed
    ordering_fields = []


User = get_user_model()


@method_decorator(csrf_exempt, name="dispatch")
class GoogleSignInView(APIView):
    """
    API endpoint to verify a Google ID token, log the user in (or create them),
    and return a JSON response.
    """

    permission_classes = [
        AllowAny
    ]  # Allow unauthenticated users to access this endpoint

    def post(self, request, *args, **kwargs):
        logger.info("Received Google sign-in request: %s", request.data)
        token = request.data.get("credential")
        if not token:
            logger.warning("No token provided")
            return Response(
                {"success": False, "error": "No token provided"}, status=400
            )
        try:
            # Verify the token against your client ID
            CLIENT_ID = "405283966911-hr2n3vbrackk4ed28bbltm9li5nlv1o4.apps.googleusercontent.com"
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), CLIENT_ID)
            # Extract user info from the token
            email = idinfo.get("email")
            first_name = idinfo.get("given_name", "")
            last_name = idinfo.get("family_name", "")
            # Use the email as the username (or adjust as needed)
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": first_name,
                    "last_name": last_name,
                },
            )
            # Specify we're using the authentication backend
            user.backend = "allauth.account.auth_backends.AuthenticationBackend"
            # Log the user in (this creates a session)
            login(request, user)
            return Response({"success": True, "redirect_url": "/home/"})
        except ValueError as e:
            # This exception is raised if the token is invalid
            return Response({"success": False, "error": str(e)}, status=401)
        except Exception as e:
            return Response(
                {"success": False, "error": "Internal server error"}, status=500
            )
