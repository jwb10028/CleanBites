from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RestaurantViewSet,
    RestaurantListView,
    RestaurantAddressListView,
    RestaurantGeoJSONView,
    DynamicNYCMapView,
    CommentViewSet,
    ReplyViewSet,
)

router = DefaultRouter()
router.register(r"restaurants", RestaurantViewSet)  # Maps API to ViewSet
router.register(r"comments", CommentViewSet)  # Maps API to ViewSet
router.register(r"replies", ReplyViewSet)  # Maps API to ViewSet

urlpatterns = [
    path("", include(router.urls)),  # Include the router URLs
    path("list/", RestaurantListView.as_view(), name="restaurant-list"),
    path(
        "addresses/", RestaurantAddressListView.as_view(), name="restaurant-addresses"
    ),
    path("geojson/", RestaurantGeoJSONView.as_view(), name="restaurant-geojson"),
    path("dynamic/", DynamicNYCMapView.as_view(), name="restaurant-dynamic-map"),
]
