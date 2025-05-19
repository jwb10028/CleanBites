import os
import requests
import folium
from rest_framework.response import Response
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import Distance
from _api._restaurants.models import Restaurant  # adjust import as needed
from shapely.geometry import shape, Point as ShapelyPoint
from django.conf import settings

# Load NYC boundary from GeoJSON
NYC_GEOJSON_URL = (
    "https://raw.githubusercontent.com/dwillis/nyc-maps/master/boroughs.geojson"
)
nyc_geojson = requests.get(NYC_GEOJSON_URL).json()
nyc_polygons = [shape(feature["geometry"]) for feature in nyc_geojson["features"]]
