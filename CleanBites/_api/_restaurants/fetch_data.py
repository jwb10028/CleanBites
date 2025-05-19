import requests
from datetime import datetime
from django.core.exceptions import ValidationError
import time
from geopy.geocoders import Nominatim
from _api._restaurants.models import Restaurant
from django.contrib.gis.geos import Point
from geopy.exc import GeocoderTimedOut

NYC_DATA_URL = "https://data.cityofnewyork.us/resource/43nn-pn8j.json"


def clean_int(value, default=0):
    """Convert value to integer safely."""
    try:
        return int(value) if value else default
    except ValueError:
        return default


def clean_hygiene_rating(value):
    """Convert score to integer, default to -1 if missing."""
    try:
        return int(value) if value else -1
    except ValueError:
        return -1


def clean_string(value, default="Unknown"):
    """Ensure the value is a valid string."""
    return str(value).strip() if value else default


def clean_date(value):
    """Convert date string to Python date object safely."""
    try:
        return (
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f").date() if value else None
        )
    except ValueError:
        return None


def clean_email(value):
    """Ensure email is valid, default to 'Not Provided' if missing."""
    return value if value else "Not Provided"


# ======================================================================================================
def fetch_and_store_data(URL):
    """Fetch restaurant data from NYC Open Data and store it in PostgreSQL."""
    response = requests.get(URL)

    if response.status_code == 200:
        data = response.json()

        for item in data:
            try:
                geo_point = None
                longitude = item.get("longitude")
                latitude = item.get("latitude")

                if longitude and latitude:
                    geo_point = Point(float(longitude), float(latitude))
                else:
                    # Fall back to geocoding if lat/lon are missing
                    geo_point = get_coords(
                        item.get("building"),
                        item.get("street"),
                        item.get("boro"),
                        item.get("zipcode"),
                    )

                restaurant, created = Restaurant.objects.update_or_create(
                    id=clean_int(
                        item.get("camis")
                    ),  # NYC API uses 'camis' as unique ID
                    defaults={
                        "name": clean_string(item.get("dba")),
                        "email": clean_email(item.get("email")),  # Placeholder email
                        "phone": clean_string(item.get("phone", "000-000-0000")),
                        "building": clean_int(item.get("building")),
                        "street": clean_string(item.get("street")),
                        "zipcode": clean_string(item.get("zipcode", "00000")),
                        "hygiene_rating": clean_hygiene_rating(
                            item.get("score")
                        ),  # Hygiene rating is based on score
                        "inspection_date": clean_date(item.get("record_date")),
                        "borough": clean_int(
                            item.get("boro")
                        ),  # Convert borough to integer
                        "cuisine_description": clean_string(
                            item.get("cuisine_description")
                        ),
                        "violation_description": clean_string(
                            item.get("violation_description", "No Violation")
                        ),
                        "geo_coords": geo_point,
                    },
                )

                if created:
                    print(f"✅ Added: {restaurant.name}")
                else:
                    print(f"🔄 Updated: {restaurant.name}")

            except ValidationError as e:
                print(f"⚠️ Skipping record due to validation error: {e}")
            except Exception as e:
                print(f"❌ Error processing record {item.get('camis')}: {e}")

    else:
        print(f"❌ Failed to fetch data. Status Code: {response.status_code}")


def get_coords(building, street, boro, zipcode):
    """
    Return a GeoDjango Point object (longitude, latitude) for the given address,
    constrained to New York City.
    """
    geolocator = Nominatim(user_agent="CleanBites2025")

    if not street:
        return None  # No address available

    q_address = (
        f"{building} {street}, {boro}, NY {zipcode}"
        if building
        else f"{street}, {boro}, NY {zipcode}"
    )

    try:
        # NYC bounding box: west, south, east, north (lon/lat)
        nyc_bounds = [(-75.5, 39.5), (-70.5, 43.5)]

        location = geolocator.geocode(
            q_address,
            timeout=10,
            viewbox=nyc_bounds,
        )

        if location:
            return Point(location.longitude, location.latitude)  # (X=lon, Y=lat)
        else:
            print(f"⚠️ Could not geocode: {q_address}")
            return None

    except GeocoderTimedOut:
        print(f"⚠️ Geocoding timeout for: {q_address}")
        return None
