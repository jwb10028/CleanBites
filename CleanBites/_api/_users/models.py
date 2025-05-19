from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


class Customer(models.Model):
    id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=255)
    is_activated = models.BooleanField(default=True)
    deactivation_reason = models.TextField(null=True, blank=True)
    deactivated_until = models.DateField(null=True, blank=True)
    karmatotal = models.IntegerField(default=0, null=True, blank=True)
    blocked_customers = models.ManyToManyField(
        "self",
        symmetrical=True,  # if a user blocks someone, they are blocked back
        # related_name='blocked_by',
        blank=True,
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Moderator(models.Model):
    id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField()
    username = models.CharField(max_length=255)
    is_activated = models.BooleanField(default=True)
    deactivation_reason = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class DM(models.Model):
    id = models.AutoField(primary_key=True)
    sender = models.ForeignKey(
        Customer, related_name="sent_dms", on_delete=models.CASCADE
    )
    receiver = models.ForeignKey(
        Customer, related_name="received_dms", on_delete=models.CASCADE
    )
    message = models.BinaryField()  # BYTEA for binary message storage
    flagged = models.BooleanField(default=False)
    # flagged_by = models.ForeignKey(
    #     Moderator, null=True, blank=True, on_delete=models.SET_NULL
    # )
    flagged_by_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    flagged_by_object_id = models.PositiveIntegerField(null=True, blank=True)
    flagged_by = GenericForeignKey("flagged_by_content_type", "flagged_by_object_id")

    sent_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)  # Track if message has been read

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~models.Q(sender=models.F("receiver")),
                name="chk_dm_sender_receiver",  # Prevent sending DMs to self
            )
        ]

    def save(self, *args, **kwargs):
        if isinstance(self.message, memoryview):
            # Convert memoryview to bytes.
            self.message = self.message.tobytes()
        elif isinstance(self.message, str):
            # Convert string to bytes using UTF-8 encoding.
            self.message = self.message.encode("utf-8")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"DM from {self.sender} to {self.receiver} at {self.sent_at}"


class FavoriteRestaurant(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    restaurant = models.ForeignKey("_restaurants.Restaurant", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("customer", "restaurant")  # Enforces unique pairs in the DB

    def __str__(self):
        return f"{self.customer} likes {self.restaurant}"
