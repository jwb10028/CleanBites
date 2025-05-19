from django.test import TestCase
from django.db import transaction
from .models import Customer, Moderator, DM, FavoriteRestaurant
from _api._restaurants.models import Restaurant


# Create your tests here.


class CustomerModelTests(TestCase):
    def test_required_fields(self):
        # Test that required fields are enforced
        with self.assertRaises(Exception):
            with transaction.atomic():
                Customer.objects.create(
                    first_name=None, last_name=None, email=None, username=None
                )

        # Test valid creation
        customer = Customer.objects.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            username="johndoe",
        )
        self.assertEqual(Customer.objects.count(), 1)


class ModeratorModelTests(TestCase):
    def test_required_fields(self):
        # Test that required fields are enforced
        with self.assertRaises(Exception):
            with transaction.atomic():
                Moderator.objects.create(first_name=None, last_name=None, email=None)

        # Test valid creation
        moderator = Moderator.objects.create(
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            username="TestAdmin",
        )
        self.assertEqual(Moderator.objects.count(), 1)


class DMModelTests(TestCase):
    def setUp(self):
        self.customer1 = Customer.objects.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            username="johndoe",
        )
        self.customer2 = Customer.objects.create(
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            username="janesmith",
        )

    def test_required_fields(self):
        # Test that required fields are enforced
        with self.assertRaises(Exception):
            with transaction.atomic():
                DM.objects.create(sender=None, receiver=None, message=b"")

        # Test valid creation
        dm = DM.objects.create(
            sender=self.customer1, receiver=self.customer2, message=b"Test message"
        )
        self.assertEqual(DM.objects.count(), 1)
        self.assertFalse(dm.read)  # Default value check


class FavoriteRestaurantModelTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            username="johndoe",
        )
        self.restaurant = Restaurant.objects.create(
            name="Test Restaurant",
            email="test@example.com",
            phone="1234567890",
            building=123,
            street="Test St",
            zipcode="10001",
            hygiene_rating=90,
            inspection_date="2025-01-01",
            borough=1,
            cuisine_description="Test",
            violation_description="None",
            is_activated=True,
        )

    def test_required_fields(self):
        # Test that required fields are enforced
        with self.assertRaises(Exception):
            with transaction.atomic():
                FavoriteRestaurant.objects.create(customer=None, restaurant=None)

        # Test valid creation and unique constraint
        fav = FavoriteRestaurant.objects.create(
            customer=self.customer, restaurant=self.restaurant
        )
        self.assertEqual(FavoriteRestaurant.objects.count(), 1)

        # Test unique constraint
        with self.assertRaises(Exception):
            with transaction.atomic():
                FavoriteRestaurant.objects.create(
                    customer=self.customer, restaurant=self.restaurant
                )
