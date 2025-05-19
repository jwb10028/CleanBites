from django.shortcuts import render
from rest_framework import viewsets, generics, filters
from .serializers import (
    RestaurantSerializer,
    RestaurantAddressSerializer,
    CommentSerializer,
    ReplySerializer,
)
from .models import Restaurant, Comment, Reply
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponse
from django.views import View
from django.conf import settings
from django.http import JsonResponse
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import Q


# Create your views here.
class RestaurantViewSet(viewsets.ModelViewSet):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    # Filters: allow ?borough=1 or ?cuisine_description=Pizza
    filterset_fields = ["borough", "cuisine_description", "hygiene_rating"]

    # Search: allow ?search=Joe's Diner (search in name and street)
    search_fields = ["name", "street"]

    # Ordering: allow ?ordering=inspection_date (or ?ordering=-inspection_date for descending)
    ordering_fields = ["inspection_date", "hygiene_rating"]


class RestaurantListView(generics.ListAPIView):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer


class RestaurantAddressListView(generics.ListAPIView):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantAddressSerializer


class RestaurantGeoJSONView(APIView):
    def get(self, request):
        # Get query parameters
        name = request.GET.get("name", "").strip()
        rating = request.GET.get("rating", "").strip()
        cuisine = request.GET.get("cuisine", "").strip()
        distance_km = request.GET.get("distance", "").strip()
        lat = request.GET.get("lat", "").strip()
        lng = request.GET.get("lng", "").strip()

        # Start with all restaurants
        queryset = Restaurant.objects.filter(is_activated=True)

        # Filter by name
        if name:
            queryset = queryset.filter(name__icontains=name)

        # Filter by hygiene rating
        if rating:
            try:
                ratings = rating.split(",")
                # Q allows you to build OR conditions
                rating_filter = Q()
                if "A" in ratings:
                    rating_filter |= Q(hygiene_rating__lte=13)
                if "B" in ratings:
                    rating_filter |= Q(hygiene_rating__gte=14, hygiene_rating__lte=27)
                if "C" in ratings:
                    rating_filter |= Q(hygiene_rating__gte=28)
                queryset = queryset.filter(rating_filter)

            except ValueError:
                pass  # Ignore invalid ratings

        # Filter by cuisine type
        if cuisine:
            queryset = queryset.filter(cuisine_description__icontains=cuisine)

        # Filter by distance if lat/lng provided
        if lat and lng and distance_km:
            try:
                lat, lng, distance_km = float(lat), float(lng), float(distance_km)
                user_location = Point(lng, lat, srid=4326)  # Ensure correct SRID
                queryset = queryset.filter(
                    geo_coords__distance_lte=(user_location, D(km=distance_km))
                )
            except ValueError:
                pass  # Ignore invalid coordinates

        # Convert queryset to GeoJSON format
        features = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [restaurant.geo_coords.x, restaurant.geo_coords.y],
                },
                "properties": {
                    "id": restaurant.id,
                    "name": restaurant.name,
                    "hygiene_rating": restaurant.hygiene_rating,
                    "cuisine": restaurant.cuisine_description,
                    "street": restaurant.street,
                    "zipcode": restaurant.zipcode,
                    "building": restaurant.building,
                },
            }
            for restaurant in queryset
        ]

        geojson_data = {"type": "FeatureCollection", "features": features}

        return JsonResponse(geojson_data)


class DynamicNYCMapView(View):
    def get(self, request):
        return HttpResponse("<h1>🚧 Under Maintenance 🚧</h1>")


class CommentViewSet(viewsets.ModelViewSet):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = ["restaurant", "commenter", "flagged"]
    search_fields = ["comment"]
    ordering_fields = ["posted_at", "karma"]


class ReplyViewSet(viewsets.ModelViewSet):
    queryset = Reply.objects.all()
    serializer_class = ReplySerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = ["comment", "commenter", "flagged"]
    search_fields = ["reply"]
    ordering_fields = ["posted_at", "karma"]
