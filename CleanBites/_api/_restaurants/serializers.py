from rest_framework import serializers
from .models import Restaurant, Comment, Reply


class RestaurantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = "__all__"  # Include all fields in serialization


class RestaurantAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = ["id", "name", "building", "street", "zipcode", "borough"]


class CommentSerializer(serializers.ModelSerializer):
    commenter_name = serializers.CharField(
        source="commenter.first_name", read_only=True
    )
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id",
            "commenter",
            "commenter_name",
            "restaurant",
            "restaurant_name",
            "comment",
            "karma",
            "flagged",
            "flagged_by",
            "posted_at",
        ]


class ReplySerializer(serializers.ModelSerializer):
    commenter_name = serializers.CharField(
        source="commenter.first_name", read_only=True
    )
    comment_text = serializers.CharField(source="comment.comment", read_only=True)

    class Meta:
        model = Reply
        fields = [
            "id",
            "commenter",
            "commenter_name",
            "comment",
            "comment_text",
            "reply",
            "karma",
            "flagged",
            "flagged_by",
            "posted_at",
        ]
