from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.messages import get_messages
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.contenttypes.models import ContentType
from datetime import date, datetime, timedelta

from _api._users.models import Moderator, Customer, DM, FavoriteRestaurant
from _api._restaurants.models import Restaurant, Comment
from _frontend.utils import has_unread_messages
from django.contrib.gis.geos import Point
from django.test import RequestFactory
import json

User = get_user_model()


# ALL FRONTEND TESTS ==================================================================
class ViewTests(TestCase):
    def setUp(self):
        # Create test user
        self.user1 = User.objects.create_user(
            username="user1", email="user1@test.com", password="testpass123"
        )
        self.customer1 = Customer.objects.create(
            username="user1", email="user1@test.com", first_name="User", last_name="One"
        )

        self.user2 = User.objects.create_user(
            username="user2", email="user2@test.com", password="testpass123"
        )
        self.customer2 = Customer.objects.create(
            username="user2", email="user2@test.com", first_name="User", last_name="Two"
        )

        self.client = Client()

    def test_landing_view(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "landing.html")

    def test_home_view_authenticated(self):
        self.client.login(username="user1", password="testpass123")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")

    def test_home_view_unauthenticated(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_register_view_post_valid(self):
        data = {
            "username": "newuser",
            "email": "new@test.com",
            "password1": "complexpassword123",
            "password2": "complexpassword123",
        }
        response = self.client.post(reverse("register"), data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_profile_router(self):
        # Create restaurant user and associated restaurant
        restaurant_user = User.objects.create_user(
            username="restaurant1",
            password="testpass123",
            email="restaurant@test.com",
        )

        # Create the restaurant record with matching username
        restaurant = Restaurant.objects.create(
            username="restaurant1",
            name="Test Restaurant",
            email="restaurant@test.com",
            phone="123-456-7890",
            building=123,
            street="Test St",
            zipcode="10001",
            borough=1,
            cuisine_description="American",
            hygiene_rating=1,
            violation_description="No violations",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),
        )

        # Login as restaurant
        self.client.login(username="restaurant1", password="testpass123")

        # Test profile router redirect
        response = self.client.get(reverse("user_profile", args=[restaurant.username]))

        # Verify the redirected page loads correctly
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["restaurant"], restaurant)

    def test_messages_view(self):
        """Test messages_view functionality"""
        # Test with no messages
        self.client.login(username="user1", password="testpass123")
        response = self.client.get(reverse("messages inbox"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inbox.html")
        self.assertIn("conversations", response.context)
        self.assertEqual(len(response.context["conversations"]), 0)
        self.assertIsNone(response.context["active_chat"])
        self.assertEqual(len(response.context["messages"]), 0)

        # Create test messages
        DM.objects.create(
            sender=self.customer1,
            receiver=self.customer2,
            message=b"Test message 1",
        )
        DM.objects.create(
            sender=self.customer2,
            receiver=self.customer1,
            message=b"Test message 2",
            read=False,
        )

        # Test conversation list
        response = self.client.get(reverse("messages inbox"))
        self.assertEqual(len(response.context["conversations"]), 1)
        self.assertEqual(response.context["conversations"][0]["id"], self.customer2.id)
        self.assertTrue(response.context["conversations"][0]["has_unread"])

        # Test message decoding
        chat_response = self.client.get(
            reverse("chat", kwargs={"chat_user_id": self.customer2.id})
        )
        self.assertEqual(len(chat_response.context["messages"]), 2)
        self.assertEqual(
            chat_response.context["messages"][0].decoded_message, "Test message 1"
        )
        self.assertEqual(
            chat_response.context["messages"][1].decoded_message, "Test message 2"
        )

        # Verify unread message was marked as read
        updated_dm = DM.objects.get(message=b"Test message 2")
        self.assertTrue(updated_dm.read)

        # Test error handling for missing profile
        self.customer1.delete()
        error_response = self.client.get(reverse("messages inbox"))
        self.assertEqual(len(error_response.context["conversations"]), 0)
        self.assertEqual(
            error_response.context["error"], "Your profile could not be found."
        )

    def test_active_chat_selection(self):
        """Test active chat selection logic in messages_view"""
        # Create test messages
        DM.objects.create(
            sender=self.customer1,
            receiver=self.customer2,
            message=b"First message",
        )
        DM.objects.create(
            sender=self.customer2,
            receiver=self.customer1,
            message=b"Second message",
        )

        # Test 1: No chat_user_id specified - should default to first conversation
        self.client.login(username="user1", password="testpass123")
        response = self.client.get(reverse("messages inbox"))
        self.assertEqual(response.context["active_chat"].id, self.customer2.id)
        self.assertEqual(len(response.context["messages"]), 2)
        self.assertEqual(
            response.context["messages"][0].decoded_message, "First message"
        )
        self.assertEqual(
            response.context["messages"][1].decoded_message, "Second message"
        )

        # Test 2: Specific chat_user_id specified
        response = self.client.get(
            reverse("chat", kwargs={"chat_user_id": self.customer2.id})
        )
        self.assertEqual(response.context["active_chat"].id, self.customer2.id)
        self.assertEqual(len(response.context["messages"]), 2)

        # Test 3: Invalid chat_user_id should 404
        response = self.client.get(
            reverse("chat", kwargs={"chat_user_id": 999}), follow=True
        )
        self.assertEqual(response.status_code, 404)

    def test_messages_view_missing_profile(self):
        """Test error handling when customer profile doesn't exist"""
        # Create a user without a customer profile
        user = User.objects.create_user(
            username="orphanuser", email="orphan@test.com", password="testpass123"
        )

        self.client.login(username="orphanuser", password="testpass123")
        response = self.client.get(reverse("messages inbox"))

        # Verify error message is shown (matches view exactly)
        self.assertEqual(response.context["error"], "Your profile could not be found.")
        # Verify empty conversation data
        self.assertEqual(response.context["conversations"], [])
        self.assertIsNone(response.context["active_chat"])
        self.assertEqual(response.context["messages"], [])

    def test_dynamic_map_view(self):
        """Test dynamic_map_view returns 200 and correct context"""
        self.client.login(username="user1", password="testpass123")
        response = self.client.get(reverse("dynamic-map"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("has_unread_messages", response.context)
        self.assertTemplateUsed(response, "maps/nycmap_dynamic.html")


class MessageSystemTests(TestCase):
    def setUp(self):
        # Create test users
        self.user1 = User.objects.create_user(
            username="user1", email="user1@test.com", password="testpass123"
        )
        self.customer1 = Customer.objects.create(
            username="user1", email="user1@test.com", first_name="User", last_name="One"
        )

        self.user2 = User.objects.create_user(
            username="user2", email="user2@test.com", password="testpass123"
        )
        self.customer2 = Customer.objects.create(
            username="user2", email="user2@test.com", first_name="User", last_name="Two"
        )

        self.client = Client()

    def test_send_message_orphaned_user(self):
        """Test error handling when user has no Customer or Restaurant profile"""
        # Create user without any profile
        orphan_user = User.objects.create_user(
            username="orphan", email="orphan@test.com", password="testpass123"
        )

        self.client.login(username="orphan", password="testpass123")
        response = self.client.post(
            reverse("send_message", kwargs={"chat_user_id": self.customer1.id}),
            {"message": "Test message"},
        )

        # Verify error response
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content.decode(), "Sender not found")

        # Verify error message was added
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            str(messages[0]), "Your account was not found. Please contact support."
        )

    def test_dm_creation(self):
        """Test basic DM creation"""
        dm = DM.objects.create(
            sender=self.customer1,
            receiver=self.customer2,
            message=b"Test message",
            read=False,
        )
        self.assertEqual(dm.sender, self.customer1)
        self.assertEqual(dm.receiver, self.customer2)
        self.assertEqual(dm.message, b"Test message")
        self.assertFalse(dm.read)
        self.assertFalse(dm.flagged)
        self.assertIsNone(dm.flagged_by)

    def test_dm_self_send_prevention(self):
        """Test that users can't send DMs to themselves"""
        with self.assertRaises(ValidationError):
            dm = DM(
                sender=self.customer1, receiver=self.customer1, message=b"Test message"
            )
            dm.full_clean()

    def test_has_unread_messages(self):
        """Test the has_unread_messages utility function"""
        # No messages initially
        self.assertFalse(has_unread_messages(self.user1))

        # Create unread message
        DM.objects.create(
            sender=self.customer2,
            receiver=self.customer1,
            message=b"Test message",
            read=False,
        )
        self.assertTrue(has_unread_messages(self.user1))

        # Mark as read
        DM.objects.filter(receiver=self.customer1).update(read=True)
        self.assertFalse(has_unread_messages(self.user1))

    def test_message_view_mark_read(self):
        """Test that viewing messages marks them as read"""
        # Create unread message
        DM.objects.create(
            sender=self.customer2,
            receiver=self.customer1,
            message=b"Test message",
            read=False,
        )

        # Login and view messages
        self.client.login(username="user1", password="testpass123")
        response = self.client.get(reverse("messages inbox"))

        # Message should now be marked as read
        self.assertFalse(
            DM.objects.filter(receiver=self.customer1, read=False).exists()
        )

    def test_delete_conversation(self):
        """Test that conversation deletion works correctly"""
        # Create test messages between users
        DM.objects.create(
            sender=self.customer1,
            receiver=self.customer2,
            message=b"Message 1",
        )
        DM.objects.create(
            sender=self.customer2,
            receiver=self.customer1,
            message=b"Message 2",
        )

        self.client.login(username="user1", password="testpass123")
        response = self.client.post(
            reverse("delete_conversation", kwargs={"other_user_id": self.customer2.id})
        )

        # Verify redirect
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("messages inbox"))

        # Verify messages were deleted
        self.assertEqual(DM.objects.count(), 0)

        # Verify success message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn(
            f"Conversation with {self.customer2.first_name}", str(messages[0])
        )

    def test_send_message_generic_success(self):
        """Test successful message sending via generic endpoint"""
        self.client.login(username="user1", password="testpass123")
        response = self.client.post(
            reverse("send_message_generic"),
            {"recipient": "user2@test.com", "message": "Test message"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            DM.objects.filter(sender=self.customer1, receiver=self.customer2).exists()
        )

    def test_send_message_generic_orphaned_user(self):
        """Test error when sender has no profile"""
        orphan_user = User.objects.create_user(
            username="orphan", email="orphan@test.com", password="testpass123"
        )
        self.client.login(username="orphan", password="testpass123")
        response = self.client.post(
            reverse("send_message_generic"),
            {"recipient": "user1@test.com", "message": "Test message"},
        )
        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(
            str(messages[0]), "Your account was not found. Please contact support."
        )

    def test_send_message_generic_missing_recipient(self):
        """Test error when recipient email is missing"""
        self.client.login(username="user1", password="testpass123")
        response = self.client.post(
            reverse("send_message_generic"), {"message": "Test message"}
        )
        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(str(messages[0]), "Please enter a recipient email address.")

    def test_send_message_generic_empty_message(self):
        """Test error when message is empty"""
        self.client.login(username="user1", password="testpass123")
        response = self.client.post(
            reverse("send_message_generic"),
            {"recipient": "user2@test.com", "message": ""},
        )
        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(str(messages[0]), "Message cannot be empty.")

    def test_send_message_generic_self_message(self):
        """Test error when messaging self"""
        self.client.login(username="user1", password="testpass123")
        response = self.client.post(
            reverse("send_message_generic"),
            {"recipient": "user1@test.com", "message": "Test message"},
        )
        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(str(messages[0]), "You can't message yourself.")

    def test_send_message_generic_restaurant_recipient(self):
        """Test error when recipient is a restaurant"""
        restaurant = Restaurant.objects.create(
            name="Test Restaurant",
            username="restaurant1",
            email="restaurant@test.com",
            borough=1,  # Manhattan is typically represented as 1
            building=123,
            street="Test St",
            zipcode="10001",
            phone="123-456-7890",
            cuisine_description="American",
            hygiene_rating=1,
            violation_description="No violations",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),  # Example NYC coordinates
        )
        self.client.login(username="user1", password="testpass123")
        response = self.client.post(
            reverse("send_message_generic"),
            {"recipient": "restaurant@test.com", "message": "Test message"},
        )
        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(
            str(messages[0]),
            "'restaurant@test.com' is a restaurant account. Currently, you can only message customer accounts.",
        )

    def test_send_message_generic_invalid_recipient(self):
        """Test error when recipient doesn't exist"""
        self.client.login(username="user1", password="testpass123")
        response = self.client.post(
            reverse("send_message_generic"),
            {"recipient": "nonexistent@test.com", "message": "Test message"},
        )
        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(
            str(messages[0]),
            "Recipient 'nonexistent@test.com' does not exist. Please check the email address and try again.",
        )


class UtilityTests(TestCase):
    """Basic tests for utility functions"""

    def setUp(self):
        # Create two test users
        self.user1 = User.objects.create_user(
            username="test1", email="test1@test.com", password="testpass123"
        )
        self.customer1 = Customer.objects.create(
            username="test1", email="test1@test.com"
        )

        self.user2 = User.objects.create_user(
            username="test2", email="test2@test.com", password="testpass123"
        )
        self.customer2 = Customer.objects.create(
            username="test2", email="test2@test.com"
        )

        self.restaurant = Restaurant.objects.create(
            name="Test Restaurant",
            username="restaurant1",
            email="restaurant@test.com",
            borough=1,  # Manhattan is typically represented as 1
            building=123,
            street="Test St",
            zipcode="10001",
            phone="123-456-7890",
            cuisine_description="American",
            hygiene_rating=1,
            violation_description="No violations",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),  # Example NYC coordinates
        )

    def test_has_unread_messages_utility(self):
        """Test has_unread_messages returns correct boolean"""
        # No messages
        self.assertFalse(has_unread_messages(self.user1))

        # User2 sends message to User1
        DM.objects.create(
            sender=self.customer2, receiver=self.customer1, message=b"test", read=False
        )
        self.assertTrue(has_unread_messages(self.user1))
        self.assertFalse(has_unread_messages(self.user2))

    def test_has_unread_messages_unauthenticated(self):
        """Test with unauthenticated/anonymous users"""
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(has_unread_messages(None))
        self.assertFalse(has_unread_messages(AnonymousUser()))

    def test_has_unread_messages_no_customer(self):
        """Test when user has no associated customer"""
        user = User.objects.create_user("no_customer@test.com", "password")
        self.assertFalse(has_unread_messages(user))

    def test_has_unread_messages_read_status(self):
        """Test read/unread message detection"""
        # Create read message
        DM.objects.create(
            sender=self.customer2, receiver=self.customer1, message=b"read", read=True
        )
        self.assertFalse(has_unread_messages(self.user1))

        # Create unread message
        DM.objects.create(
            sender=self.customer2,
            receiver=self.customer1,
            message=b"unread",
            read=False,
        )
        self.assertTrue(has_unread_messages(self.user1))

        # Mark as read and verify
        DM.objects.filter(receiver=self.customer1).update(read=True)
        self.assertFalse(has_unread_messages(self.user1))


class RestaurantViewTests(TestCase):
    def setUp(self):
        # Create test users
        self.user1 = User.objects.create_user(
            username="user1", email="user1@test.com", password="testpass123"
        )
        self.customer1 = Customer.objects.create(
            username="user1", email="user1@test.com", first_name="User", last_name="One"
        )

        # Create test restaurant
        self.restaurant = Restaurant.objects.create(
            name="Test Restaurant",
            username="restaurant1",
            email="restaurant@test.com",
            borough=1,  # Manhattan is typically represented as 1
            building=123,
            street="Test St",
            zipcode="10001",
            phone="123-456-7890",
            cuisine_description="American",
            hygiene_rating=1,
            violation_description="No violations",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),  # Example NYC coordinates
        )

        self.client = Client()

    def test_restaurant_detail_view(self):
        """Test restaurant detail view for both owners and regular users"""
        # Test as non-owner
        self.client.login(username="user1", password="testpass123")
        response = self.client.get(
            reverse("restaurant_detail", args=[self.restaurant.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_owner"])
        self.assertEqual(response.context["restaurant"], self.restaurant)

        # Test as owner
        owner = User.objects.create_user(
            username="restaurant1", email="restaurant@test.com", password="testpass123"
        )
        self.client.login(username="restaurant1", password="testpass123")
        response = self.client.get(
            reverse("restaurant_detail", args=[self.restaurant.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_owner"])

    # using the restaurant id for detail view and this test is no longer needed
    # def test_restaurant_detail_case_insensitive(self):
    #     """Test restaurant name matching is case insensitive"""
    #     self.client.login(username="user1", password="testpass123")
    #     response = self.client.get(
    #         reverse("restaurant_detail", args=["test restaurant"])
    #     )
    #     self.assertEqual(response.status_code, 200)

    def test_restaurant_register_view(self):
        """Test restaurant registration page shows unverified restaurants"""
        # Create unverified restaurant
        Restaurant.objects.create(
            name="Unverified Restaurant",
            email="Not Provided",
            phone="123-456-7890",
            building=123,
            street="Test St",
            zipcode="10001",
            borough=1,  # Manhattan
            cuisine_description="American",
            hygiene_rating=1,
            violation_description="No violations",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),  # NYC coordinates
        )

        response = self.client.get(reverse("restaurant_register"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["restaurants"]), 1)

    def test_restaurant_verify_success(self):
        """Test successful restaurant verification"""
        restaurant = Restaurant.objects.create(
            name="Unverified Restaurant",
            email="Not Provided",
            phone="123-456-7890",
            building=123,
            street="Test St",
            zipcode="10001",
            borough=1,  # Manhattan
            cuisine_description="American",
            hygiene_rating=1,
            violation_description="No violations",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),  # NYC coordinates
        )

        data = {
            "restaurant": restaurant.id,
            "username": "newowner",
            "email": "owner@test.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
            "verify": "1234",
        }

        response = self.client.post(reverse("restaurant_verify"), data)
        self.assertEqual(response.status_code, 302)

        # Verify updates
        updated = Restaurant.objects.get(id=restaurant.id)
        self.assertEqual(updated.email, "owner@test.com")
        self.assertEqual(updated.username, "newowner")
        self.assertTrue(User.objects.filter(username="newowner").exists())

    def test_restaurant_verify_failures(self):
        """Test various failure cases for restaurant verification"""
        restaurant = Restaurant.objects.create(
            name="Unverified Restaurant",
            email="test@example.com",
            phone="123-456-7890",
            building=123,
            street="Test St",
            zipcode="10001",
            borough=1,  # Manhattan
            cuisine_description="American",
            hygiene_rating=1,
            violation_description="No violations",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),  # NYC coordinates
        )

        # Test wrong verification code
        data = {
            "restaurant": restaurant.id,
            "username": "newowner",
            "email": "owner@test.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
            "verify": "wrongcode",
        }
        response = self.client.post(reverse("restaurant_verify"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Restaurant.objects.get(id=restaurant.id).email, "test@example.com"
        )

        # Test password mismatch
        data = {
            "restaurant": restaurant.id,
            "username": "newowner",
            "email": "owner@test.com",
            "password": "testpass123",
            "confirm_password": "mismatch",
            "verify": "1234",
        }
        response = self.client.post(reverse("restaurant_verify"), data)
        self.assertEqual(response.status_code, 302)


class ModeratorViewTests(TestCase):
    def setUp(self):
        # Create a moderator user and associated Moderator record.
        self.mod_user = User.objects.create_user(
            username="mod1", email="mod1@test.com", password="modpass"
        )
        self.moderator = Moderator.objects.create(
            username="mod1", email="mod1@test.com", first_name="Mod", last_name="One"
        )
        self.restaurant = Restaurant.objects.create(
            username="res1",
            email="res1@test.com",
            name="Res",
            phone="555-555-5555",
            building=123,
            street="Main St",
            zipcode="12345",
            hygiene_rating=5,
            inspection_date="2023-01-01",
            borough=1,
            cuisine_description="Italian",
            violation_description="None",
            geo_coords=Point(-73.966, 40.78),
        )
        # Create two customer records.
        self.cust_user1 = User.objects.create_user(
            username="cust1", email="cust1@test.com", password="custpass"
        )
        self.customer1 = Customer.objects.create(
            username="cust1", email="cust1@test.com", first_name="Cust", last_name="One"
        )

        self.cust_user2 = User.objects.create_user(
            username="cust2", email="cust2@test.com", password="custpass"
        )
        self.customer2 = Customer.objects.create(
            username="cust2", email="cust2@test.com", first_name="Cust", last_name="Two"
        )

        # Create a flagged DM:
        # For example, a DM from customer1 to customer2 flagged by customer2.
        self.flagged_dm = DM.objects.create(
            sender=self.customer1,
            receiver=self.customer2,
            message=b"Flagged DM",  # Stored as bytes
            flagged=True,
            flagged_by=self.moderator,
            read=False,
        )

        # Create a flagged Comment:
        # For example, a comment by customer1 flagged by customer2.
        self.flagged_comment = Comment.objects.create(
            commenter=self.customer1,
            comment=b"Flagged Comment",
            posted_at=timezone.now(),
            flagged=True,
            flagged_by=self.moderator,
            karma=0,
            restaurant=self.restaurant,
        )

    def test_moderator_profile_view_context(self):
        """
        Test that moderator_profile_view returns the flagged DMs and flagged Comments
        in the context and decodes DM messages.
        """
        self.client.login(username="mod1", password="modpass")
        response = self.client.get(reverse("moderator_profile"))
        self.assertEqual(response.status_code, 200)

        # Check that context contains flagged_dms and flagged_comments.
        self.assertIn("flagged_dms", response.context)
        self.assertIn("flagged_comments", response.context)
        flagged_dms = response.context["flagged_dms"]
        flagged_comments = response.context["flagged_comments"]

        # Verify that our flagged DM is among those in context.
        self.assertIn(self.flagged_dm, list(flagged_dms))
        # Verify the DM message is decoded properly (should be "Flagged DM").
        for dm in flagged_dms:
            self.assertEqual(dm.decoded_message, "Flagged DM")

        # Verify that our flagged comment is among those in context.
        self.assertIn(self.flagged_comment, list(flagged_comments))
        self.assertEqual(self.flagged_comment.comment, b"Flagged Comment")

    def test_deactivate_account_customer(self):
        """
        Test that a POST to the deactivate_account endpoint for a customer properly deactivates
        the associated user account.
        """
        self.client.login(username="mod1", password="modpass")
        url = reverse("deactivate_account", args=["customer", self.customer1.id])
        response = self.client.post(url)
        self.customer1.refresh_from_db()
        self.assertFalse(self.customer1.is_activated)

    def test_deactivate_account_restaurant(self):
        """
        Test that a POST to deactivate_account for a restaurant properly deactivates that account.
        """
        # Create a restaurant user and record.
        rest_user = User.objects.create_user(
            username="rest1", email="rest1@test.com", password="restpass"
        )
        restaurant = Restaurant.objects.create(
            username="rest1",
            name="Test Restaurant",
            email="rest1@test.com",
            phone="111-222-3333",
            building=100,
            street="Test Rd",
            zipcode="12345",
            borough=1,
            cuisine_description="Test Cuisine",
            hygiene_rating=1,
            violation_description="None",
            inspection_date="2023-01-01",
            geo_coords=Point(0, 0),
        )
        self.client.login(username="mod1", password="modpass")
        url = reverse("deactivate_account", args=["restaurant", restaurant.id])
        response = self.client.post(url)

        restaurant.refresh_from_db()
        self.assertFalse(restaurant.is_activated)

    def test_delete_comment(self):
        """
        Test that a POST to delete_comment removes the comment from the database.
        """
        self.client.login(username="mod1", password="modpass")
        url = reverse("delete_comment", args=[self.flagged_comment.id])
        response = self.client.post(url)
        with self.assertRaises(Comment.DoesNotExist):
            Comment.objects.get(id=self.flagged_comment.id)


class AuthenticationTests(TestCase):
    """Tests for user authentication views (login, logout, register)"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.customer = Customer.objects.create(
            username="testuser", email="test@example.com"
        )

    def test_login_success(self):
        """Test successful login redirects to home"""
        response = self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "testpass123"},
            follow=True,
        )
        self.assertRedirects(response, reverse("home"))

    def test_login_failure(self):
        """Test failed login shows error"""
        response = self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "wrongpass"},
            follow=True,
        )
        self.assertContains(response, "Invalid username or password")
        self.assertRedirects(response, reverse("landing"))

    def test_logout(self):
        """Test logout redirects to landing page"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("logout"))
        self.assertRedirects(response, "/")

    def test_register_success(self):
        """Test successful registration"""
        response = self.client.post(
            reverse("register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password1": "Testpass123!",
                "password2": "Testpass123!",
            },
        )
        self.assertRedirects(response, "/home/")
        self.assertTrue(User.objects.filter(email="new@example.com").exists())

    def test_register_password_mismatch(self):
        """Test registration with mismatched passwords"""
        response = self.client.post(
            reverse("register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password1": "Testpass123!",
                "password2": "Different123!",
            },
            follow=True,
        )
        self.assertContains(response, "Passwords do not match")

    def test_register_username_already_taken(self):
        """Test registration fails when username is already taken"""
        response = self.client.post(
            reverse("register"),
            {
                "username": "testuser",  # Same as existing user
                "email": "new@example.com",
                "password1": "Testpass123!",
                "password2": "Testpass123!",
            },
            follow=True,
        )
        self.assertContains(response, "Username already taken")
        self.assertEqual(response.status_code, 200)  # Should stay on same page

    def test_register_email_already_taken(self):
        """Test registration fails when email is already taken"""
        response = self.client.post(
            reverse("register"),
            {
                "username": "newuser",
                "email": "test@example.com",
                "password1": "Testpass123!",
                "password2": "Testpass123!",
            },
            follow=True,
        )
        self.assertContains(response, "Email is already in use")
        self.assertEqual(response.status_code, 200)  # Should stay on same page


class SmokeTests(TestCase):
    """Basic smoke tests to verify views load without errors"""

    def test_landing_view(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "landing.html")

    def test_home_view_authenticated(self):
        user = User.objects.create_user(
            username="test", email="test@example.com", password="test123"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")

    def test_dynamic_map_view(self):
        user = User.objects.create_user(
            username="test", email="test@example.com", password="test123"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dynamic-map"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maps/nycmap_dynamic.html")


class RestaurantVerificationTests(TestCase):
    """Tests for restaurant verification and registration"""

    def setUp(self):
        self.client = Client()
        # Create existing user and restaurant for testing conflicts
        self.user = User.objects.create_user(
            username="existinguser",
            email="existing@example.com",
            password="testpass123",
        )
        self.restaurant = Restaurant.objects.create(
            id=1,
            name="Test Restaurant",
            username="restaurant1",
            email="restaurant@test.com",
            borough=1,
            building=123,
            street="Test St",
            zipcode="10001",
            phone="123-456-7890",
            cuisine_description="American",
            hygiene_rating=1,
            violation_description="No violations",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),
        )
        self.valid_restaurant = Restaurant.objects.create(
            id=2,
            name="Valid Restaurant",
            username="",
            email="",
            borough=1,
            building=456,
            street="Valid St",
            zipcode="10002",
            phone="987-654-3210",
            cuisine_description="Italian",
            hygiene_rating=0,
            violation_description="__",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.985, 40.758),
        )

    def test_password_mismatch(self):
        """Test verification fails when passwords don't match"""
        response = self.client.post(
            reverse("restaurant_verify"),
            {
                "restaurant": "2",
                "username": "newuser",
                "email": "new@example.com",
                "password": "Testpass123!",
                "confirm_password": "Mismatch123!",
                "verify": "0000",  # Default verification code
            },
            follow=True,
        )
        self.assertContains(response, "Passwords do not match.")

    def test_invalid_verification_code(self):
        """Test verification fails with wrong code"""
        response = self.client.post(
            reverse("restaurant_verify"),
            {
                "restaurant": "2",
                "username": "newuser",
                "email": "new@example.com",
                "password": "Testpass123!",
                "confirm_password": "Testpass123!",
                "verify": "wrongcode",
            },
            follow=True,
        )
        self.assertContains(response, "Invalid verification code.")

    def test_username_taken(self):
        """Test verification fails when username exists"""
        response = self.client.post(
            reverse("restaurant_verify"),
            {
                "restaurant": "2",
                "username": "existinguser",
                "email": "new@example.com",
                "password": "Testpass123!",
                "confirm_password": "Testpass123!",
                "verify": "1234",
            },
            follow=True,
        )
        self.assertContains(response, "Username is already taken.")

    def test_email_taken(self):
        """Test verification fails when email exists"""
        response = self.client.post(
            reverse("restaurant_verify"),
            {
                "restaurant": "2",
                "username": "newuser",
                "email": "existing@example.com",
                "password": "Testpass123!",
                "confirm_password": "Testpass123!",
                "verify": "1234",
            },
            follow=True,
        )
        self.assertContains(response, "Email is already registered.")

    def test_restaurant_not_found(self):
        """Test verification fails when restaurant doesn't exist"""
        response = self.client.post(
            reverse("restaurant_verify"),
            {
                "restaurant": "999",  # Non-existent ID
                "username": "newuser",
                "email": "new@example.com",
                "password": "Testpass123!",
                "confirm_password": "Testpass123!",
                "verify": "1234",
            },
            follow=True,
        )
        self.assertContains(response, "Selected restaurant does not exist.")


class BookmarksTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="user1", password="testpass123", email="user1@test.com"
        )
        self.customer = Customer.objects.create(
            username="user1", email="user1@test.com", first_name="User", last_name="One"
        )
        self.restaurant = Restaurant.objects.create(
            name="Test Restaurant",
            username="restaurant1",
            email="restaurant@test.com",
            borough=1,  # Manhattan
            building=123,
            street="Test St",
            zipcode="10001",
            phone="123-456-7890",
            cuisine_description="American",
            hygiene_rating=1,
            violation_description="No violations",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),
        )
        self.bookmarks_url = reverse("bookmarks_view")

    def test_bookmark_view_requires_login(self):
        response = self.client.get(self.bookmarks_url)
        self.assertEqual(response.status_code, 302)  # Should redirect to login

    def test_add_bookmark_success(self):
        self.client.login(username="user1", password="testpass123")
        response = self.client.post(
            self.bookmarks_url, {"restaurant_id": self.restaurant.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertTrue(
            FavoriteRestaurant.objects.filter(
                customer=self.customer, restaurant=self.restaurant
            ).exists()
        )

    def test_add_duplicate_bookmark(self):
        FavoriteRestaurant.objects.create(
            customer=self.customer, restaurant=self.restaurant
        )
        self.client.login(username="user1", password="testpass123")
        response = self.client.post(
            self.bookmarks_url, {"restaurant_id": self.restaurant.id}
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_add_bookmark_invalid_restaurant(self):
        self.client.login(username="user1", password="testpass123")
        response = self.client.post(
            self.bookmarks_url, {"restaurant_id": 9999}  # Non-existent ID
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["success"])

    def test_get_bookmarks_empty(self):
        self.client.login(username="user1", password="testpass123")
        response = self.client.get(self.bookmarks_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["restaurants"]), 0)
        self.assertEqual(data["count"], 0)

    def test_get_bookmarks_with_data(self):
        FavoriteRestaurant.objects.create(
            customer=self.customer, restaurant=self.restaurant
        )
        self.client.login(username="user1", password="testpass123")
        response = self.client.get(self.bookmarks_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["restaurants"]), 1)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["restaurants"][0]["name"], "Test Restaurant")

    def test_missing_customer_profile(self):
        # Create user without customer profile
        user2 = User.objects.create_user(
            username="user2", password="testpass123", email="testuser2@test.com"
        )
        self.client.login(username="user2", password="testpass123")
        response = self.client.get(self.bookmarks_url)
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.json())


class SearchTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="searchuser", email="search@test.com", password="searchpass"
        )
        self.customer = Customer.objects.create(
            username="CoolCustomer",
            email="cool@test.com",
            first_name="Cool",
            last_name="Customer",
        )
        self.restaurant_user = User.objects.create_user(
            username="restuser", email="rest@test.com", password="restpass"
        )
        self.restaurant = Restaurant.objects.create(
            name="Pizza Palace",
            username="PizzaPalace",
            email="rest@test.com",
            phone="123-456-7890",
            building=123,
            street="Main St",
            zipcode="10001",
            borough=1,
            cuisine_description="Pizza",
            hygiene_rating=1,
            violation_description="None",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),
        )
        self.client.login(username="searchuser", password="searchpass")

    def test_empty_query_returns_empty_results(self):
        response = self.client.get(reverse("global_search"), {"q": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": []})

    def test_search_customer_username(self):
        response = self.client.get(reverse("global_search"), {"q": "Cool"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["results"]
        self.assertTrue(any("👤 CoolCustomer" in r["label"] for r in data))
        self.assertTrue(any("/user/CoolCustomer/" in r["url"] for r in data))

    def test_search_restaurant_name(self):
        response = self.client.get(reverse("global_search"), {"q": "Pizza"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["results"]
        self.assertTrue(any("🍽️ Pizza Palace" in r["label"] for r in data))
        self.assertTrue(
            any(f"/restaurant/{self.restaurant.id}/" in r["url"] for r in data)
        )

    def test_search_returns_both_customer_and_restaurant(self):
        # Query that hits both "CoolCustomer" and "Pizza Palace"
        response = self.client.get(reverse("global_search"), {"q": "a"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["results"]
        self.assertTrue(
            any("👤 CoolCustomer" in r["label"] for r in data)
            or any("🍽️ Pizza Palace" in r["label"] for r in data)
        )

    def test_search_no_results(self):
        response = self.client.get(reverse("global_search"), {"q": "Zebra"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": []})


class BookmarksDeleteTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.customer = Customer.objects.create(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )

        self.restaurant = Restaurant.objects.create(
            name="Delete Me Diner",
            username="deleteme",
            email="rest@test.com",
            borough=1,
            building=123,
            street="Main St",
            zipcode="10001",
            phone="555-555-5555",
            cuisine_description="BBQ",
            hygiene_rating=1,
            violation_description="None",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),
        )

        self.bookmark = FavoriteRestaurant.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
        )

        self.url = reverse("bookmarks_view")  # Ensure this matches your urls.py name
        self.client.login(username="testuser", password="testpass123")

    def test_delete_bookmark_success(self):
        response = self.client.delete(
            self.url,
            data=json.dumps({"id": self.bookmark.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertFalse(
            FavoriteRestaurant.objects.filter(id=self.bookmark.id).exists()
        )

    def test_delete_bookmark_missing_id(self):
        response = self.client.delete(
            self.url,
            data=json.dumps({}),  # No "id" field
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing bookmark ID", response.json()["error"])

    def test_delete_bookmark_invalid_id(self):
        response = self.client.delete(
            self.url,
            data=json.dumps({"id": 9999}),  # Non-existent
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Bookmark not found", response.json()["error"])

    def test_delete_bookmark_unauthorized(self):
        other_user = User.objects.create_user(
            username="intruder", password="pass123", email="intruder@test.com"
        )
        Customer.objects.create(username="intruder", email="intruder@test.com")

        self.client.login(username="intruder", password="pass123")
        response = self.client.delete(
            self.url,
            data=json.dumps({"id": self.bookmark.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Bookmark not found", response.json()["error"])
        self.assertTrue(FavoriteRestaurant.objects.filter(id=self.bookmark.id).exists())

    def test_delete_bookmark_missing_customer_profile(self):
        # Create user without Customer profile
        orphan = User.objects.create_user(
            username="orphan", password="pass123", email="orphan@test.com"
        )
        self.client.login(username="orphan", password="pass123")
        response = self.client.delete(
            self.url,
            data=json.dumps({"id": self.bookmark.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn(
            "Customer matching query does not exist.", response.json()["error"]
        )


class EditProfileTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.customer = Customer.objects.create(
            username="testuser", email="test@example.com"
        )
        self.url = reverse(
            "update_profile"
        )  # Update this if your url name is different

    def test_successful_profile_update(self):
        self.client.login(username="testuser", password="testpass123")
        data = {
            "name": "New Name",
            "email": "newemail@example.com",
            "currentUsername": "testuser",
        }
        response = self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "New Name")
        self.assertEqual(response.json()["email"], "newemail@example.com")

        # Check DB values were updated
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "New")
        self.assertEqual(self.user.last_name, "Name")
        self.assertEqual(self.user.email, "newemail@example.com")

    def test_unauthenticated_user(self):
        response = self.client.post(self.url, content_type="application/json")
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_invalid_method_get(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"], "Invalid method")

    def test_customer_not_found(self):
        self.client.login(username="testuser", password="testpass123")
        self.customer.delete()
        data = {
            "name": "John Smith",
            "email": "john@example.com",
            "currentUsername": "testuser",
        }
        response = self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Customer profile not found.")

    def test_partial_name(self):
        self.client.login(username="testuser", password="testpass123")
        data = {
            "name": "John",  # No last name
            "email": "john@example.com",
            "currentUsername": "testuser",
        }
        response = self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "John")
        self.assertEqual(self.user.last_name, "")  # Handles single-name input

    def test_malformed_json(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            self.url,
            data="{bad json}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())


class WriteCommentTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.customer = Customer.objects.create(
            username="testuser", email="test@example.com"
        )

        self.restaurant = Restaurant.objects.create(
            name="Food Place",
            username="foodplace",
            email="place@example.com",
            borough=1,
            building=123,
            street="Main St",
            zipcode="10001",
            phone="123-456-7890",
            cuisine_description="Deli",
            hygiene_rating=3,
            violation_description="None",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),
        )

        self.url = reverse("addreview", args=[self.restaurant.id])
        self.client.login(username="testuser", password="testpass123")

    def test_get_review_form_view(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "addreview.html")
        self.assertIn("form", response.context)
        self.assertEqual(response.context["restaurant"], self.restaurant)

    def test_post_valid_comment(self):
        post_data = {
            "title": "Loved It",
            "comment": "Amazing spot!",
            "rating": "5",
            "health_rating": "4",
        }
        response = self.client.post(self.url, post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response, reverse("restaurant_detail", args=[self.restaurant.id])
        )

        # Confirm the review was created
        self.assertEqual(Comment.objects.count(), 1)
        comment = Comment.objects.first()
        self.assertEqual(comment.commenter, self.customer)
        self.assertEqual(comment.restaurant, self.restaurant)
        self.assertEqual(comment.rating, 5)
        self.assertEqual(comment.health_rating, 4)
        self.assertEqual(comment.title, "Loved It")
        self.assertEqual(comment.comment, "Amazing spot!")

    def test_post_invalid_comment_missing_fields(self):
        post_data = {"rating": "5", "health_rating": "3"}  # Missing title and comment
        response = self.client.post(self.url, post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "addreview.html")
        self.assertFormError(response, "form", "title", "This field is required.")
        self.assertFormError(response, "form", "comment", "This field is required.")
        self.assertEqual(Comment.objects.count(), 0)

    def test_redirects_if_not_logged_in(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_comment_belongs_to_correct_user_and_restaurant(self):
        post_data = {
            "title": "Solid place",
            "comment": "Great experience!",
            "rating": "4",
            "health_rating": "4",
        }
        self.client.post(self.url, post_data)
        comment = Comment.objects.first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.commenter.username, "testuser")
        self.assertEqual(comment.restaurant.name, "Food Place")


class ProfileTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.customer = Customer.objects.create(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )

        self.other_user = User.objects.create_user(
            username="visitor", email="visitor@example.com", password="visitorpass"
        )
        self.other_customer = Customer.objects.create(
            username="visitor", email="visitor@example.com"
        )

        self.restaurant = Restaurant.objects.create(
            name="Review Spot",
            username="reviewspot",
            email="spot@example.com",
            borough=1,
            building=123,
            street="Main St",
            zipcode="10001",
            phone="123-456-7890",
            cuisine_description="Fusion",
            hygiene_rating=3,
            violation_description="None",
            inspection_date="2023-01-01",
            geo_coords=Point(-73.966, 40.78),
        )

        self.profile_url = lambda username: reverse("user_profile", args=[username])

    def test_redirect_if_not_logged_in(self):
        response = self.client.get(self.profile_url("testuser"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_profile_view_as_owner(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.profile_url("testuser"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "user_profile.html")
        self.assertTrue(response.context["is_owner"])
        self.assertEqual(response.context["profile_user"], self.user)
        self.assertEqual(response.context["customer"], self.customer)
        self.assertEqual(list(response.context["reviews"]), [])

    def test_profile_view_as_non_owner(self):
        self.client.login(username="visitor", password="visitorpass")
        response = self.client.get(self.profile_url("testuser"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "user_profile.html")
        self.assertFalse(response.context["is_owner"])
        self.assertEqual(response.context["profile_user"], self.user)
        self.assertEqual(response.context["customer"], self.customer)

    def test_profile_with_reviews(self):
        Comment.objects.create(
            commenter=self.customer,
            restaurant=self.restaurant,
            title="Good",
            comment="Food was good",
            rating=4,
            health_rating=3,
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.profile_url("testuser"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reviews"]), 1)
        self.assertEqual(response.context["reviews"][0].title, "Good")


class UserProfileViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.customer = Customer.objects.create(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )

    def test_profile_view_owner(self):
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("user_profile", args=["testuser"]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "user_profile.html")
        self.assertTrue(response.context["is_owner"])

    def test_profile_view_not_owner(self):
        other_user = User.objects.create_user(username="other", password="pass123")
        self.client.login(username="other", password="pass123")
        response = self.client.get(reverse("user_profile", args=["testuser"]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_owner"])

    def test_profile_view_user_not_found(self):
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("user_profile", args=["nonexistent"]))
        self.assertEqual(response.status_code, 302 or 404)


class AdminProfileViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="adminuser", password="pass123", email="admin@example.com"
        )
        self.moderator = Moderator.objects.create(
            username="adminuser", email="admin@example.com"
        )
        self.client.login(username="adminuser", password="pass123")

    def test_admin_profile_view(self):
        response = self.client.get(reverse("moderator_profile"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin_profile.html")

    def test_admin_profile_not_moderator(self):
        # Login as a user who is not a moderator
        User.objects.create_user(
            username="user2", password="pass123", email="user2@example.com"
        )
        self.client.login(username="user2", password="pass123")

        response = self.client.get(reverse("moderator_profile"))
        self.assertEqual(response.status_code, 302)


class UpdateRestaurantProfileTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="restouser", password="testpass")

        self.restaurant = Restaurant.objects.create(
            username="restouser",
            name="Old Name",
            phone="1234567890",
            street="Old Street",
            building=123,
            zipcode="10001",
            cuisine_description="Old Cuisine",
            hygiene_rating=10,
            inspection_date=date.today(),
            geo_coords=Point(0.0, 0.0),
            borough=0,  # ✅ NEW required field
        )

    def test_update_profile_success(self):
        self.client.login(username="restouser", password="testpass")
        data = {
            "name": "New Name",
            "phone": "0987654321",
            "street": "New Street",
            "building": "456",
            "zipcode": "10002",
            "cuisine_description": "New Cuisine",
        }
        response = self.client.post(reverse("update-profile"), data)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.name, "New Name")
        self.assertRedirects(
            response, reverse("restaurant_detail", kwargs={"id": self.restaurant.id})
        )

    def test_update_profile_no_restaurant(self):
        self.restaurant.delete()
        self.client.login(username="restouser", password="testpass")
        response = self.client.post(reverse("update-profile"))
        self.assertRedirects(response, reverse("home"))

    def test_update_profile_invalid_building(self):
        self.client.login(username="restouser", password="testpass")
        data = {"building": "notanumber"}
        response = self.client.post(reverse("update-profile"), data)
        self.assertRedirects(
            response, reverse("restaurant_detail", kwargs={"id": self.restaurant.id})
        )  # triggers the exception block


class ModeratorRegisterTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse("moderator_register")  # Matches your new URL path

    def test_successful_registration(self):
        data = {
            "username": "moduser",
            "email": "mod@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
        }
        response = self.client.post(self.register_url, data)
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(User.objects.filter(username="moduser").exists())
        self.assertTrue(Moderator.objects.filter(email="mod@example.com").exists())

    def test_password_mismatch(self):
        data = {
            "username": "moduser",
            "email": "mod@example.com",
            "password1": "pass1",
            "password2": "pass2",
        }
        response = self.client.post(self.register_url, data, follow=True)
        self.assertRedirects(response, "/")
        self.assertFalse(User.objects.filter(username="moduser").exists())

    def test_username_already_taken(self):
        User.objects.create_user(
            username="moduser", email="other@example.com", password="test123"
        )
        data = {
            "username": "moduser",
            "email": "newmod@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
        }
        response = self.client.post(self.register_url, data, follow=True)
        self.assertRedirects(response, "/")
        self.assertEqual(User.objects.filter(username="moduser").count(), 1)

    def test_email_already_used_by_user(self):
        User.objects.create_user(
            username="someuser", email="mod@example.com", password="test123"
        )
        data = {
            "username": "newmod",
            "email": "mod@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
        }
        response = self.client.post(self.register_url, data, follow=True)
        self.assertRedirects(response, "/")
        self.assertFalse(Moderator.objects.filter(username="newmod").exists())

    def test_email_already_used_by_moderator(self):
        Moderator.objects.create(username="moduser", email="mod@example.com")
        data = {
            "username": "anotheruser",
            "email": "mod@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
        }
        response = self.client.post(self.register_url, data, follow=True)
        self.assertRedirects(response, "/")
        self.assertFalse(User.objects.filter(username="anotheruser").exists())

    def test_get_request_redirects(self):
        response = self.client.get(self.register_url)
        self.assertRedirects(response, "/")


class ReportDMTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="reporter", email="reporter@example.com", password="testpass"
        )
        self.partner_user = User.objects.create_user(
            username="partner", email="partner@example.com", password="testpass"
        )
        self.reporter = Customer.objects.create(
            username="reporter", email="reporter@example.com"
        )
        self.partner = Customer.objects.create(
            username="partner", email="partner@example.com"
        )

        # Login reporter
        self.client.login(username="reporter", password="testpass")

        # Create a DM from partner to reporter
        self.dm = DM.objects.create(
            sender=self.partner,
            receiver=self.reporter,
            message=b"Test DM",
            sent_at=datetime.now() - timedelta(minutes=1),
        )

        self.url = reverse("report_dm")  # Ensure this is defined in your urls.py

    def test_successful_report(self):
        data = {"partner_id": self.partner.id}
        response = self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"success": True})

        self.dm.refresh_from_db()
        self.assertTrue(self.dm.flagged)
        self.assertEqual(self.dm.flagged_by_object_id, self.reporter.id)
        self.assertEqual(
            self.dm.flagged_by_content_type,
            ContentType.objects.get_for_model(self.reporter),
        )

    def test_missing_partner_id(self):
        response = self.client.post(
            self.url,
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing partner_id", response.json()["error"])

    def test_reporter_not_found(self):
        self.reporter.delete()  # simulate missing reporter
        data = {"partner_id": self.partner.id}
        response = self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Reporter not found", response.json()["error"])

    def test_no_dm_found(self):
        DM.objects.all().delete()
        data = {"partner_id": self.partner.id}
        response = self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("No DM from the partner found", response.json()["error"])

    def test_invalid_method(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertIn("Invalid request method", response.json()["error"])

    def test_invalid_json(self):
        # Invalid JSON payload (simulate parse error)
        response = self.client.post(
            self.url, data="not-json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.json())


class MessagesViewTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(
            username="user1", email="user1@example.com", password="testpass"
        )
        self.partner_user = User.objects.create_user(
            username="user2", email="user2@example.com", password="testpass"
        )

        self.customer = Customer.objects.create(
            username="user1", email="user1@example.com", first_name="UserOne"
        )
        self.partner = Customer.objects.create(
            username="user2", email="user2@example.com", first_name="UserTwo"
        )

        self.client.login(username="user1", password="testpass")
        self.url = reverse("messages inbox")

    def test_inbox_basic_render(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inbox.html")
        self.assertIn("conversations", response.context)
        self.assertIn("has_unread_messages", response.context)

    def test_inbox_no_customer_found(self):
        self.customer.delete()  # Remove user profile
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertEqual(response.context["error"], "Your profile could not be found.")

    def test_inbox_with_conversation(self):
        DM.objects.create(
            sender=self.partner,
            receiver=self.customer,
            message=b"Hello!",
            read=False,
            sent_at=datetime.now() - timedelta(minutes=10),
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.context["conversations"]) > 0)
        self.assertIsNotNone(response.context["active_chat"])
        self.assertEqual(response.context["active_chat"].id, self.partner.id)
        self.assertTrue(
            any(
                "decoded_message" in str(msg.__dict__)
                for msg in response.context["messages"]
            )
        )

    def test_chat_user_id_explicit_param(self):
        DM.objects.create(
            sender=self.partner,
            receiver=self.customer,
            message=b"Hi!",
            sent_at=datetime.now(),
        )
        url = reverse("messages inbox") + f"?chat_user_id={self.partner.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_message_decoding_failure(self):
        # Create message with invalid byte sequence
        DM.objects.create(
            sender=self.partner,
            receiver=self.customer,
            message=b"\xff",
            sent_at=datetime.now(),
        )
        response = self.client.get(self.url)
        messages = response.context["messages"]
        self.assertIn(
            "[Could not decode message]", [msg.decoded_message for msg in messages]
        )

    def test_messages_marked_as_read(self):
        DM.objects.create(
            sender=self.partner,
            receiver=self.customer,
            message=b"Unread",
            read=False,
            sent_at=datetime.now(),
        )
        self.client.get(self.url)
        dm = DM.objects.filter(sender=self.partner, receiver=self.customer).first()
        self.assertTrue(dm.read)

    def test_no_conversations(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["conversations"], [])
        self.assertEqual(response.context["messages"], [])


class ReportCommentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="user1", email="user1@example.com", password="testpass"
        )
        self.customer = Customer.objects.create(
            username="user1", email="user1@example.com"
        )
        self.restaurant = Restaurant.objects.create(
            username="restouser",
            name="Old Name",
            phone="1234567890",
            street="Old Street",
            building=123,
            zipcode="10001",
            cuisine_description="Old Cuisine",
            hygiene_rating=10,
            inspection_date=date.today(),
            geo_coords=Point(0.0, 0.0),
            borough=0,  #
        )
        self.moderator = Moderator.objects.create(
            username="mod1", email="mod@example.com"
        )
        self.comment = Comment.objects.create(
            commenter=self.customer,
            restaurant=self.restaurant,
            title="Clean place",
            comment="Very hygienic and friendly staff.",
            rating=5,
            health_rating=5,
            flagged=False,
        )
        self.url = reverse("report_comment")

    def test_report_by_customer(self):
        self.client.login(username="user1", password="testpass")
        data = {"comment_id": self.comment.id}
        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"success": True})

        self.comment.refresh_from_db()
        self.assertTrue(self.comment.flagged)
        self.assertEqual(self.comment.flagged_by_object_id, self.customer.id)
        self.assertEqual(
            self.comment.flagged_by_content_type,
            ContentType.objects.get_for_model(self.customer),
        )

    def test_report_by_restaurant(self):
        self.client.login(
            username="rest1", password="testpass"
        )  # Use a restaurant user
        self.restaurant_user = User.objects.create_user(
            username="rest1", email="rest@example.com", password="testpass"
        )
        self.client.login(username="rest1", password="testpass")
        data = {"comment_id": self.comment.id}
        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.flagged_by_object_id, None)

    def test_report_by_moderator(self):
        self.moderator_user = User.objects.create_user(
            username="mod1", email="mod@example.com", password="testpass"
        )
        self.client.login(username="mod1", password="testpass")
        data = {"comment_id": self.comment.id}
        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.flagged_by_object_id, self.moderator.id)

    def test_missing_comment_id(self):
        self.client.login(username="user1", password="testpass")
        response = self.client.post(
            self.url, json.dumps({}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing comment ID", response.json()["error"])

    def test_comment_not_found(self):
        self.client.login(username="user1", password="testpass")
        response = self.client.post(
            self.url, json.dumps({"comment_id": 999}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 500 or 404)

    def test_flagger_not_found(self):
        # Simulate a user with no profile
        other_user = User.objects.create_user(
            username="ghost", email="ghost@example.com", password="ghostpass"
        )
        self.client.login(username="ghost", password="ghostpass")
        response = self.client.post(
            self.url,
            json.dumps({"comment_id": self.comment.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Flagger not found", response.json()["error"])

    def test_invalid_method(self):
        self.client.login(
            username="user1", password="testpass"
        )  # ensure you're logged in
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertIn("Invalid request method", response.json()["error"])

    def test_invalid_json(self):
        self.client.login(username="user1", password="testpass")
        response = self.client.post(
            self.url, data="not-json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.json())


class DebugUnreadMessagesTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="reader", email="reader@example.com", password="testpass"
        )
        self.customer = Customer.objects.create(
            username="reader", email="reader@example.com", first_name="Reader"
        )
        self.partner_user = User.objects.create_user(
            username="partner", email="partner@example.com", password="testpass"
        )
        self.partner = Customer.objects.create(
            username="partner", email="partner@example.com", first_name="Partner"
        )

        self.url = reverse("debug_unread_messages")

    def test_unread_messages_with_data(self):
        # Create some unread and read messages
        DM.objects.create(
            sender=self.partner,
            receiver=self.customer,
            message=b"Unread 1",
            read=False,
            sent_at=datetime.now(),
        )
        DM.objects.create(
            sender=self.partner,
            receiver=self.customer,
            message=b"Unread 2",
            read=False,
            sent_at=datetime.now(),
        )
        DM.objects.create(
            sender=self.partner,
            receiver=self.customer,
            message=b"Read msg",
            read=True,
            sent_at=datetime.now(),
        )

        self.client.login(username="reader", password="testpass")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data["has_unread_messages"])
        self.assertEqual(data["unread_count"], 2)
        self.assertEqual(data["user_email"], "reader@example.com")
        self.assertTrue(data["is_authenticated"])
        self.assertEqual(len(data["unread_messages"]), 2)
        for msg in data["unread_messages"]:
            self.assertIn("sent_at", msg)
            self.assertIn("sender__email", msg)

    def test_no_customer_profile(self):
        self.customer.delete()
        self.client.login(username="reader", password="testpass")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Customer not found")

    def test_unauthenticated_user(self):
        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])


class EnsureCustomerViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.url = reverse("ensure_customer")

    def test_redirects_if_not_logged_in(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_creates_customer_if_missing(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"success": True, "created": True})
        self.assertTrue(Customer.objects.filter(email="test@example.com").exists())

    def test_does_nothing_if_customer_exists(self):
        Customer.objects.create(
            username="testuser", email="test@example.com", first_name="Test"
        )
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"success": True, "created": False})


class UserSettingsViewTests(TestCase):
    def setUp(self):
        # Create a test user and login
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="password123"
        )
        self.customer = Customer.objects.create(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )
        self.client.login(username="testuser", password="password123")

    def test_get_user_settings_page(self):
        """Test GET request to settings page loads successfully."""
        response = self.client.get(reverse("user_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "settings.html")
        self.assertIn("email_form", response.context)
        self.assertIn("password_form", response.context)
        self.assertIn("deactivate_form", response.context)
        self.assertIn("blocked_usernames", response.context)

    def test_change_email_success(self):
        """Test successfully changing the email address."""
        response = self.client.post(
            reverse("user_settings"),
            {
                "change_email": True,
                "email": "newemail@example.com",
            },
            follow=True,
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "newemail@example.com")

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Email updated successfully." in str(m) for m in messages))

    def test_change_password_success(self):
        """Test successfully changing the password."""
        response = self.client.post(
            reverse("user_settings"),
            {
                "change_password": True,
                "old_password": "password123",
                "new_password1": "newsecurepass123",
                "new_password2": "newsecurepass123",
            },
            follow=True,
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newsecurepass123"))

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("Password changed successfully." in str(m) for m in messages)
        )

    def test_deactivate_account(self):
        """Test deactivating the user account."""
        response = self.client.post(
            reverse("user_settings"),
            {
                "deactivate": True,
                "confirm": True,
            },
            follow=True,
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("Your account has been deactivated." in str(m) for m in messages)
        )

    def test_blocked_users_display(self):
        """Test blocked usernames appear in context."""
        blocked_user = Customer.objects.create(
            username="blockeduser",
            email="blocked@example.com",
            first_name="Blocked",
            last_name="User",
        )
        self.customer.blocked_customers.add(blocked_user)

        response = self.client.get(reverse("user_settings"))
        self.assertIn("blocked_usernames", response.context)
        self.assertIn("blockeduser", response.context["blocked_usernames"])
