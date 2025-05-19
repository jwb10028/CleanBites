from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet,
    ModeratorViewSet,
    DMViewSet,
    FavoriteRestaurantViewSet,
    GoogleSignInView,
)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"moderators", ModeratorViewSet, basename="moderator")
router.register(r"dms", DMViewSet, basename="dm")
router.register(r"favorites", FavoriteRestaurantViewSet, basename="favorite-restaurant")

urlpatterns = [
    path("google-signin/", GoogleSignInView.as_view(), name="google_signin"),
]
