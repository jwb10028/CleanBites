from django.db import models
from django.contrib.gis.db import models as GISmodels
from django.contrib.gis.geos import Point
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

User = get_user_model()


# Create your models here.
class Restaurant(models.Model):
    id = models.AutoField(primary_key=True)  # SERIAL in PostgreSQL
    username = models.CharField(max_length=255, null=True, blank=True)
    name = models.CharField(max_length=255)  # Restaurant name
    email = models.EmailField(max_length=255)  # Email field
    phone = models.CharField(max_length=15)  # Phone number
    menu = models.BinaryField(
        null=True, blank=True
    )  # BYTEA for binary data (menu file)
    building = models.IntegerField()  # Building number
    street = models.CharField(max_length=255)  # Street name
    zipcode = models.CharField(max_length=10)  # Zip code
    hygiene_rating = models.IntegerField()  # Hygiene rating
    inspection_date = models.DateField()  # Inspection date
    borough = models.IntegerField()  # Borough ID
    cuisine_description = models.CharField(max_length=255)  # Cuisine type
    violation_description = models.TextField()  # Violation description
    geo_coords = GISmodels.PointField(default=Point(0.0, 0.0))  # latitude coord
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="restaurant", null=True, blank=True
    )
    is_activated = models.BooleanField(default=True)
    deactivation_reason = models.TextField(null=True, blank=True)
    deactivated_until = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.street}, {self.zipcode})"


class Comment(models.Model):
    id = models.AutoField(primary_key=True)
    commenter = models.ForeignKey("_users.Customer", on_delete=models.CASCADE)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    title = models.CharField(max_length=80)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="replies", on_delete=models.CASCADE
    )
    comment = models.TextField()
    rating = models.IntegerField(default=1)
    health_rating = models.IntegerField(default=1)
    karma = models.IntegerField(default=0)
    k_voters = models.ManyToManyField(
        "_users.Customer", blank=True, related_name="voted_comments"
    )
    flagged = models.BooleanField(default=False)
    # flagged_by = models.ForeignKey(
    #     "_users.Moderator", null=True, blank=True, on_delete=models.SET_NULL
    # )
    flagged_by_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    flagged_by_object_id = models.PositiveIntegerField(null=True, blank=True)
    flagged_by = GenericForeignKey("flagged_by_content_type", "flagged_by_object_id")

    posted_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Ensure the comment and title are stored as proper strings
        if isinstance(self.comment, memoryview):
            self.comment = self.comment.tobytes().decode("utf-8")
        if isinstance(self.title, memoryview):
            self.title = self.title.tobytes().decode("utf-8")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Comment {self.id} by {self.commenter}"

    @property
    def decoded_comment(self):
        """
        Returns the comment text as a decoded string if it is a memoryview.
        """
        # Check if the stored comment is a memoryview object
        if isinstance(self.comment, memoryview):
            return self.comment.tobytes().decode("utf-8")
        return self.comment

    @property
    def decoded_title(self):
        """
        Returns the title text as a decoded string if it is a memoryview.
        """
        # Check if the stored comment is a memoryview object
        if isinstance(self.title, memoryview):
            return self.title.tobytes().decode("utf-8")
        return self.title


class Reply(models.Model):
    id = models.AutoField(primary_key=True)
    commenter = models.ForeignKey("_users.Customer", on_delete=models.CASCADE)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE)
    reply = models.BinaryField(null=True, blank=True)  # BYTEA for binary data
    karma = models.IntegerField(default=0)
    flagged = models.BooleanField(default=False)
    flagged_by = models.ForeignKey(
        "_users.Moderator", null=True, blank=True, on_delete=models.SET_NULL
    )
    posted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reply {self.id} to Comment {self.comment.id}"
