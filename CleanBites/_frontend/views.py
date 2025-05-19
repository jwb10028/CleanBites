from django.shortcuts import get_object_or_404, render, redirect
from _api._restaurants.models import Restaurant, Comment
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.forms import PasswordChangeForm
from _api._users.models import Customer, DM, FavoriteRestaurant, Moderator
from django.db.models import Q
from django.db import transaction
from django.http import HttpResponse
from _frontend.utils import has_unread_messages
from .forms import Review, EmailChangeForm, DeactivateAccountForm
from django.http import JsonResponse
from django.db.models import Avg
import json
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.contrib.contenttypes.models import ContentType
from datetime import date
from asgiref.sync import sync_to_async

# Get user model
User = get_user_model()

# Constants for message categories
AUTH_MESSAGE = "auth_message"  # For login/registration related messages
INBOX_MESSAGE = "inbox_message"  # For inbox related messages


# =====================================================================================
# WEBSITE VIEWS - visual endpoints
# =====================================================================================
def landing_view(request):
    return render(request, "landing.html")


@login_required(login_url="/login/")
def home_view(request):
    context = {"has_unread_messages": has_unread_messages(request.user)}
    return render(request, "home.html", context)


@login_required(login_url="/login/")
def restaurant_detail(request, id):
    restaurant = get_object_or_404(Restaurant, id=id)
    try:
        current_customer = Customer.objects.get(email=request.user.email)
    except Customer.DoesNotExist:
        current_customer = None
    reviews = Comment.objects.filter(
        Q(restaurant=restaurant),
        Q(commenter__is_activated=True)
        | Q(commenter__deactivated_until__lt=date.today()),
        parent__isnull=True,  # only include comments from active customers
    ).order_by("-posted_at")
    avg_rating = reviews.filter(parent__isnull=True).aggregate(Avg("rating"))[
        "rating__avg"
    ]
    avg_health = reviews.filter(parent__isnull=True).aggregate(Avg("health_rating"))[
        "health_rating__avg"
    ]
    is_owner = False
    if request.user.is_authenticated and request.user.username == restaurant.username:
        is_owner = True

    is_customer = not Restaurant.objects.filter(username=request.user.username).exists()

    return render(
        request,
        "maps/restaurant_detail.html",
        {
            "restaurant": restaurant,
            "reviews": reviews,
            "avg_rating": avg_rating or 0,
            "avg_health": avg_health or 0,
            "is_owner": is_owner,
            "has_unread_messages": has_unread_messages(request.user),
            "is_customer": is_customer,
            "current_customer": current_customer,
        },
    )


@login_required(login_url="/login/")
def dynamic_map_view(request):
    is_customer = not Restaurant.objects.filter(username=request.user.username).exists()
    context = {
        "has_unread_messages": has_unread_messages(request.user),
        "is_customer": is_customer,
    }
    return render(request, "maps/nycmap_dynamic.html", context)


@login_required(login_url="/login/")
def user_profile(request, username):
    user = get_object_or_404(User, username=username)
    # customer whose profile you're viewing
    try:
        profile_customer = Customer.objects.get(username=username)
    except Customer.DoesNotExist:
        profile_customer = None

    # customer who is viewing profiles
    try:
        current_customer = Customer.objects.get(email=request.user.email)
    except Customer.DoesNotExist:
        current_customer = None

    is_owner = False
    if request.user.is_authenticated and request.user.username == user.username:
        is_owner = True

    if profile_customer:
        reviews = Comment.objects.filter(
            commenter=profile_customer.id, parent__isnull=True
        ).order_by("-posted_at")
    else:
        reviews = []

    is_blocked = (
        profile_customer
        and current_customer
        and current_customer.blocked_customers.filter(id=profile_customer.id).exists()
    )
    if is_blocked:
        reviews = []

    context = {
        "profile_user": user,
        "profle_customer": profile_customer,
        "has_unread_messages": has_unread_messages(request.user),
        "customer": profile_customer,
        "is_owner": is_owner,
        "reviews": reviews,
        "is_blocked": is_blocked,
    }
    return render(request, "user_profile.html", context)


@login_required(login_url="/login/")
def admin_profile(request, username):
    admin = get_object_or_404(Moderator, username__iexact=username)
    context = {"admin": admin}
    return render(request, "admin_profile.html", context)


@csrf_exempt
def toggle_karma(request):
    if request.method == "POST":
        data = json.loads(request.body)
        comment_id = data.get("comment_id")
        customer_id = data.get("customer_id")

        # Fetch comment and customer
        try:
            comment = Comment.objects.get(id=comment_id)
            customer = Customer.objects.get(id=customer_id)
            author = comment.commenter
        except (Comment.DoesNotExist, Customer.DoesNotExist):
            return JsonResponse({"error": "Comment or Customer not found"}, status=404)
        if author.karmatotal is None:
            author.karmatotal = 0
        if customer in comment.k_voters.all():
            comment.k_voters.remove(customer)
            comment.karma -= 1
            author.karmatotal -= 1
            voted = False
        else:
            comment.k_voters.add(customer)
            comment.karma += 1
            author.karmatotal += 1
            voted = True
        author.save()
        comment.save()
        customer.save()

        return JsonResponse(
            {
                "success": True,
                "karma": comment.karma,
                "karmatotal": customer.karmatotal,
                "voted": voted,
            }
        )

    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required(login_url="/login/")
def update_restaurant_profile_view(request):
    try:
        restaurant = Restaurant.objects.get(username=request.user)
    except Restaurant.DoesNotExist:
        messages.error(request, "No restaurant is linked to your account.")
        return redirect("home")

    if request.method == "POST":
        try:
            if "name" in request.POST:
                restaurant.name = request.POST.get("name")
            if "phone" in request.POST:
                restaurant.phone = request.POST.get("phone")
            if "street" in request.POST:
                restaurant.street = request.POST.get("street")
            if "building" in request.POST and request.POST.get("building").isdigit():
                restaurant.building = int(request.POST.get("building"))
            if "zipcode" in request.POST:
                restaurant.zipcode = request.POST.get("zipcode")
            if "cuisine_description" in request.POST:
                restaurant.cuisine_description = request.POST.get("cuisine_description")

            restaurant.save()
            messages.success(request, "Restaurant profile updated successfully!")
            return redirect("restaurant_detail", id=restaurant.id)
        except Exception as e:
            messages.error(request, f"Error updating profile: {e}")
            return redirect("home")

    return redirect("restaurant_detail", id=restaurant.id)


@login_required(login_url="/login/")
def profile_router(request, username):
    try:
        user_obj = Restaurant.objects.get(username=username)

        try:
            current_customer = Customer.objects.get(email=request.user.email)
        except Customer.DoesNotExist:
            current_customer = None

        is_owner = False
        if request.user.is_authenticated and request.user.username == user_obj.username:
            is_owner = True
        reviews = Comment.objects.filter(
            Q(restaurant=user_obj.id),
            # only include comments from active customers
            Q(commenter__is_activated=True)
            | Q(commenter__deactivated_until__lt=date.today()),
            parent__isnull=True,
        )

        if current_customer:
            reviews = reviews.exclude(
                commenter__in=current_customer.blocked_customers.all()
            )

        reviews = reviews.order_by("-posted_at")

        return render(
            request,
            "maps/restaurant_detail.html",
            {
                "restaurant": user_obj,
                "is_owner": is_owner,
                "reviews": reviews,
                "has_unread_messages": has_unread_messages(request.user),
            },
        )
    except Restaurant.DoesNotExist:
        try:
            user_obj = Customer.objects.get(username=username)
            profile_user = get_object_or_404(User, username=username)
            is_owner = False

            if (
                request.user.is_authenticated
                and request.user.username == user_obj.username
            ):
                is_owner = True

            reviews = Comment.objects.filter(commenter=user_obj.id).order_by(
                "-posted_at"
            )
            return render(
                request,
                "user_profile.html",
                {
                    "customer": user_obj,
                    "profile_user": profile_user,
                    "is_owner": is_owner,
                    "reviews": reviews,
                    "has_unread_messages": has_unread_messages(request.user),
                },
            )
        except Customer.DoesNotExist:
            try:
                admin_obj = Moderator.objects.get(username=username)
                return redirect("moderator_profile")
            except Moderator.DoesNotExist:
                return redirect("home")  # or a 404 page


@login_required
def post_reply(request):
    if request.method == "POST":
        parent_id = request.POST.get("parent_id")

        restaurant_id = request.POST.get("restaurant_id")
        comment_text = request.POST.get("comment")

        parent = get_object_or_404(Comment, id=parent_id)
        restaurant = get_object_or_404(Restaurant, id=restaurant_id)
        customer = get_object_or_404(Customer, username=request.user.username)

        Comment.objects.create(
            commenter=customer,
            restaurant=restaurant,
            parent=parent,
            comment=comment_text,
            title="",
            rating=1,
            health_rating=1,
        )

    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required(login_url="/login/")
def debug_unread_messages(request):
    """Debug view to check unread messages status."""
    from django.http import JsonResponse

    try:
        user = Customer.objects.get(email=request.user.email)
        unread_count = DM.objects.filter(receiver=user, read=False).count()
        unread_messages = list(
            DM.objects.filter(receiver=user, read=False).values(
                "id", "sender__email", "sent_at"
            )
        )

        # Format sent_at for better readability
        for msg in unread_messages:
            if "sent_at" in msg:
                msg["sent_at"] = msg["sent_at"].strftime("%Y-%m-%d %H:%M:%S")

        return JsonResponse(
            {
                "has_unread_messages": has_unread_messages(request.user),
                "unread_count": unread_count,
                "unread_messages": unread_messages,
                "user_email": request.user.email,
                "is_authenticated": request.user.is_authenticated,
            }
        )
    except Customer.DoesNotExist:
        return JsonResponse(
            {
                "error": "Customer not found",
                "user_email": request.user.email,
                "is_authenticated": request.user.is_authenticated,
            }
        )
    except Exception as e:
        return JsonResponse(
            {
                "error": str(e),
                "user_email": request.user.email,
                "is_authenticated": request.user.is_authenticated,
            }
        )


@login_required(login_url="/login/")
def write_comment(request, id):
    restaurant_obj = get_object_or_404(Restaurant, id=id)
    author = get_object_or_404(Customer, username=request.user.username)

    if request.method == "POST":
        form = Review(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.commenter = author
            review.restaurant = restaurant_obj
            review.rating = request.POST.get("rating")
            review.health_rating = request.POST.get("health_rating")
            review.save()
            return redirect("restaurant_detail", id=restaurant_obj.id)
        else:
            print(form.errors)  # helpful for debugging
    else:
        form = Review()

    context = {"restaurant": restaurant_obj, "form": form}
    return render(request, "addreview.html", context)


@login_required(login_url="/login/")
def moderator_profile_view(request):
    # verify user is a moderator
    try:
        moderator = Moderator.objects.get(email=request.user.email)
    except Moderator.DoesNotExist:
        messages.error(request, "Unauthorized action.")
        return redirect("home")
    # query for flagged DMs and comments
    flagged_dms = DM.objects.filter(
        Q(flagged=True),
        Q(sender__is_activated=True) | Q(sender__deactivated_until__lt=date.today()),
    )
    flagged_comments = Comment.objects.filter(
        Q(flagged=True),
        Q(commenter__is_activated=True)
        | Q(commenter__deactivated_until__lt=date.today()),
    )

    # decode DM messages
    for dm in flagged_dms:
        try:
            dm.decoded_message = bytes(dm.message).decode("utf-8")
        except Exception as e:
            dm.decoded_message = "[Could not decode message]"

    context = {
        "moderator": moderator,
        "flagged_dms": flagged_dms,
        "flagged_comments": flagged_comments,
    }
    return render(request, "admin_profile.html", context)


@login_required(login_url="/login/")
def deactivate_account(request, user_type, user_id):
    # verify user is a moderator
    try:
        moderator = Moderator.objects.get(email=request.user.email)
    except Moderator.DoesNotExist:
        messages.error(request, "Unauthorized action.")
        return redirect("home")

    if user_type == "customer":
        user_obj = get_object_or_404(Customer, id=user_id)
    elif user_type == "restaurant":
        user_obj = get_object_or_404(Restaurant, id=user_id)
    else:
        messages.error(request, "Invalid user type.")
        return redirect("moderator_profile")

    if request.method == "POST":
        deactivation_reason = request.POST.get("deactivation_reason", "")
        deactivated_until = request.POST.get("deactivated_until", "")
        user_obj.deactivation_reason = deactivation_reason
        # permanent deactivation
        if deactivated_until == "":
            user_obj.deactivated_until = "9999-12-31"
        # suspension
        else:
            user_obj.deactivated_until = deactivated_until
        user_obj.is_activated = False
        user_obj.save()
        return redirect("moderator_profile")
    else:
        messages.error(request, "Invalid request method.")
        return redirect("moderator_profile")


@login_required(login_url="/login/")
def block_user(request, user_type, username):
    try:
        blocker = Customer.objects.get(email=request.user.email)
    except Customer.DoesNotExist:
        messages.error(request, "Only customers may block other users.")
        return redirect("home")
    if user_type == "customer":
        target = get_object_or_404(Customer, username=username)
    # elif user_type == "restaurant":
    #     target = get_object_or_404(Restaurant, id=user_id)
    else:
        messages.error(request, "Invalid user type.")
        return redirect("home")
    blocker.blocked_customers.add(target)
    messages.success(request, f"You have blocked {target}({username}).")
    return redirect("home")


@login_required(login_url="/login/")
def unblock_user(request, user_type, username):
    try:
        blocker = Customer.objects.get(email=request.user.email)
    except Customer.DoesNotExist:
        messages.error(request, "Only customers may block/unblock other users.")
        return redirect("user_settings")
    if user_type == "customer":
        target = get_object_or_404(Customer, username=username)
    # elif user_type == "restaurant":
    #     target = get_object_or_404(Restaurant, id=user_id)
    else:
        messages.error(request, "Invalid user type.")
        return redirect("home")
    blocker.blocked_customers.remove(target)
    messages.success(request, f"You have unblocked {target}({username}).")
    return redirect("user_settings")


@login_required(login_url="/login/")
def delete_comment(request, comment_id):
    try:
        moderator = Moderator.objects.get(email=request.user.email)
    except Moderator.DoesNotExist:
        messages.error(request, "Unauthorized action.")
        return redirect("home")

    comment = get_object_or_404(Comment, id=comment_id)
    comment.delete()
    messages.success(request, "Comment deleted successfully.")
    return redirect("moderator_profile")


@login_required(login_url="/login/")
def report_comment(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            comment_id = data.get("comment_id")
            if not comment_id:
                return JsonResponse(
                    {"success": False, "error": "Missing comment ID"}, status=400
                )
            comment = get_object_or_404(Comment, id=comment_id)
            comment.flagged = True
            # identify the flagger (can be a Customer, Restaurant, or Moderator)
            flagger = None
            try:
                flagger = Customer.objects.get(email=request.user.email)
            except Customer.DoesNotExist:
                try:
                    flagger = Restaurant.objects.get(email=request.user.email)
                except Restaurant.DoesNotExist:
                    try:
                        flagger = Moderator.objects.get(email=request.user.email)
                    except Moderator.DoesNotExist:
                        flagger = None
            if not flagger:
                return JsonResponse(
                    {"success": False, "error": "Flagger not found"}, status=404
                )

            # Use generic foreign key fields to store the flagger
            comment.flagged_by_content_type = ContentType.objects.get_for_model(flagger)
            comment.flagged_by_object_id = flagger.id
            comment.save()
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)
    else:
        return JsonResponse(
            {"success": False, "error": "Invalid request method"}, status=405
        )


@login_required(login_url="/login/")
def report_dm(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            partner_id = data.get("partner_id")
            if not partner_id:
                return JsonResponse(
                    {"success": False, "error": "Missing partner_id"}, status=400
                )
            try:
                reporter = Customer.objects.get(email=request.user.email)
            except Customer.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Reporter not found"}, status=404
                )
            partner = get_object_or_404(Customer, id=partner_id)

            # flag the most recent DM from the partner to the reporter
            dm = (
                DM.objects.filter(sender=partner, receiver=reporter)
                .order_by("-sent_at")
                .first()
            )
            if not dm:
                return JsonResponse(
                    {"success": False, "error": "No DM from the partner found"},
                    status=404,
                )

            dm.flagged = True
            dm.flagged_by_content_type = ContentType.objects.get_for_model(reporter)
            dm.flagged_by_object_id = reporter.id
            dm.save()
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)
    else:
        return JsonResponse(
            {"success": False, "error": "Invalid request method"}, status=405
        )


@login_required(login_url="/login/")
def global_search(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"results": []})

    customers = Customer.objects.filter(
        username__icontains=query, is_activated=True
    ).values("username")[:5]
    restaurants = Restaurant.objects.filter(
        name__icontains=query, is_activated=True
    ).values("id", "name", "username")[:5]

    results = []

    for c in customers:
        results.append(
            {"label": f"👤 {c['username']}", "url": f"/user/{c['username']}/"}
        )

    for r in restaurants:
        results.append({"label": f"🍽️ {r['name']}", "url": f"/restaurant/{r['id']}/"})

    return JsonResponse({"results": results})


# =====================================================================================
# AUTHENTICATION VIEWS - doesn't return anything but authentication data
# =====================================================================================
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            try:
                profile = Restaurant.objects.get(username=username)
            except Restaurant.DoesNotExist:
                try:
                    profile = Customer.objects.get(username=username)
                except Customer.DoesNotExist:
                    try:
                        profile = Moderator.objects.get(username=username)
                    except Moderator.DoesNotExist:
                        profile = None

            if profile is None:
                messages.error(
                    request, "Invalid username or password", extra_tags=AUTH_MESSAGE
                )
                return redirect("/")
            elif (not profile.is_activated) and profile.deactivated_until == date(
                9999, 12, 31
            ):
                messages.error(
                    request,
                    f"Your account has been deactivated. Reason: {profile.deactivation_reason}",
                )
                return redirect("landing")
            elif (
                not profile.is_activated
            ) and profile.deactivated_until >= date.today():
                messages.error(
                    request,
                    f"Your account has been suspended until {profile.deactivated_until}. Reason: {profile.deactivation_reason}",
                )
                return redirect("landing")
            else:
                login(request, user)
                return redirect("home")
        else:
            messages.error(
                request, "Invalid username or password", extra_tags=AUTH_MESSAGE
            )
            return redirect("/")  # Stay on landing page

    return redirect("/")


def logout_view(request):
    logout(request)
    return redirect("/")


def register_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if password1 != password2:
            messages.error(request, "Passwords do not match", extra_tags=AUTH_MESSAGE)
            return redirect("register")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken", extra_tags=AUTH_MESSAGE)
            return redirect("register")

        # Ensure email is unique in both User and Customer tables
        if (
            User.objects.filter(email=email).exists()
            or Customer.objects.filter(email=email).exists()
        ):
            messages.error(request, "Email is already in use", extra_tags=AUTH_MESSAGE)
            return redirect("register")

        # Create the user & customer
        user = User.objects.create_user(
            username=username, email=email, password=password1
        )
        customer = Customer.objects.create(email=email, username=username)
        # Explicitly set authentication backend to avoid 'backend' error
        user.backend = "django.contrib.auth.backends.ModelBackend"

        # Log in the user
        login(request, user)

        return redirect("home")  # Redirect to homepage after registration

    return redirect("/")


def moderator_register(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if password1 != password2:
            messages.error(request, "Passwords do not match", extra_tags=AUTH_MESSAGE)
            return redirect("register")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken", extra_tags=AUTH_MESSAGE)
            return redirect("register")

        # Ensure email is unique in both User and Moderator tables
        if (
            User.objects.filter(email=email).exists()
            or Moderator.objects.filter(email=email).exists()
        ):
            messages.error(request, "Email is already in use", extra_tags=AUTH_MESSAGE)
            return redirect("register")

        # Create the user & moderator
        user = User.objects.create_user(
            username=username, email=email, password=password1
        )
        moderator = Moderator.objects.create(email=email, username=username)

        # Explicitly set authentication backend to avoid 'backend' error
        user.backend = "django.contrib.auth.backends.ModelBackend"

        # Log in the user
        login(request, user)

        return redirect("home")  # Redirect to homepage after registration

    return redirect("/")


def restaurant_register(request):
    restaurants = Restaurant.objects.filter(email="Not Provided").order_by("name")
    return render(request, "restaurant_register.html", {"restaurants": restaurants})


HARDCODE_VERIFY = "1234"


def restaurant_verify(request):
    if request.method == "POST":
        restaurant_id = request.POST.get("restaurant")  # Get selected restaurant ID
        username = request.POST.get("username").strip()
        email = request.POST.get("email").strip()
        password = request.POST.get("password").strip()
        confirm_password = request.POST.get("confirm_password").strip()
        verification_code = request.POST.get("verify").strip()

        # Check if passwords match
        if password != confirm_password:
            messages.error(request, "Passwords do not match.", extra_tags=AUTH_MESSAGE)
            return redirect("restaurant_register")

        # Check if the verification code is correct
        if verification_code != HARDCODE_VERIFY:
            messages.error(
                request, "Invalid verification code.", extra_tags=AUTH_MESSAGE
            )
            return redirect("restaurant_register")

        # Ensure username & email are unique
        if User.objects.filter(username=username).exists():
            messages.error(
                request, "Username is already taken.", extra_tags=AUTH_MESSAGE
            )
            return redirect("restaurant_register")

        if User.objects.filter(email=email).exists():
            messages.error(
                request, "Email is already registered.", extra_tags=AUTH_MESSAGE
            )
            return redirect("restaurant_register")

        # Perform atomic transaction (user creation + restaurant email update)
        try:
            with transaction.atomic():
                # Create a new user in Django's auth_user table
                user = User.objects.create_user(
                    username=username, email=email, password=password
                )
                user.is_staff = False  # Optionally give them staff privileges
                user.save()

                # Update the selected restaurant's email
                restaurant = Restaurant.objects.get(id=restaurant_id)
                restaurant.email = email  # Assign new owner's email to restaurant
                restaurant.username = username
                restaurant.save()

            messages.success(
                request,
                "Registration successful! You can now log in.",
                extra_tags=AUTH_MESSAGE,
            )
            return redirect("/")  # Redirect to landing page

        except Restaurant.DoesNotExist:
            messages.error(
                request, "Selected restaurant does not exist.", extra_tags=AUTH_MESSAGE
            )
            return redirect("restaurant_register")

        except Exception as e:
            messages.error(
                request, f"An error occurred: {str(e)}", extra_tags=AUTH_MESSAGE
            )
            return redirect("restaurant_register")

    return redirect("restaurant_register")  # Redirect if accessed via GET


@login_required
def user_settings(request):
    user = request.user

    # Pre-fill forms
    email_form = EmailChangeForm(instance=user)
    password_form = PasswordChangeForm(user=user)
    deactivate_form = DeactivateAccountForm()

    blocked_usernames = None
    try:
        curr_customer = Customer.objects.get(email=user.email)
        blocked_customers = curr_customer.blocked_customers.all()
        blocked_usernames = [customer.username for customer in blocked_customers]
    except Customer.DoesNotExist:
        pass
    if request.method == "POST":
        if "change_email" in request.POST:
            email_form = EmailChangeForm(request.POST, instance=user)
            if email_form.is_valid():
                email_form.save()
                messages.success(request, "Email updated successfully.")
                return redirect("user_settings")

        elif "change_password" in request.POST:
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Password changed successfully.")
                return redirect("user_settings")

        elif "deactivate" in request.POST:
            deactivate_form = DeactivateAccountForm(request.POST)
            if deactivate_form.is_valid() and deactivate_form.cleaned_data["confirm"]:
                user.is_active = False
                user.save()
                logout(request)
                messages.success(request, "Your account has been deactivated.")
                return redirect("home")

    return render(
        request,
        "settings.html",
        {
            "email_form": email_form,
            "password_form": password_form,
            "deactivate_form": deactivate_form,
            "blocked_usernames": blocked_usernames,
        },
    )


# =====================================================================================
# CSRF EXEMPT/PROTECTED VIEWS - need to update this later probably
# =====================================================================================


@csrf_exempt
@login_required(login_url="/login/")
def bookmarks_view(request):
    if request.method == "POST":
        try:
            restaurant_id = request.POST.get("restaurant_id")
            if not restaurant_id:
                return JsonResponse(
                    {"success": False, "error": "Restaurant ID required"}, status=400
                )

            restaurant = Restaurant.objects.get(id=restaurant_id)
            customer = Customer.objects.get(username=request.user.username)

            # Check if bookmark exists
            if FavoriteRestaurant.objects.filter(
                customer=customer, restaurant=restaurant
            ).exists():
                return JsonResponse(
                    {"success": False, "error": "Restaurant already bookmarked"},
                    status=400,
                )

            FavoriteRestaurant.objects.create(customer=customer, restaurant=restaurant)
            return JsonResponse(
                {"success": True, "message": "Bookmark added successfully"}
            )

        except Restaurant.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Restaurant not found"}, status=404
            )
        except Customer.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "User not found"}, status=404
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    if request.method == "DELETE":
        try:
            data = json.loads(request.body)
            bookmark_id = data.get("id")  # or "bookmark_id", just keep consistent

            if not bookmark_id:
                return JsonResponse(
                    {"success": False, "error": "Missing bookmark ID"}, status=400
                )

            customer = Customer.objects.get(username=request.user.username)

            # ✅ Delete by the bookmark's actual ID (primary key of FavoriteRestaurant)
            deleted, _ = FavoriteRestaurant.objects.filter(
                id=bookmark_id, customer=customer
            ).delete()

            if deleted:
                return JsonResponse({"success": True, "message": "Bookmark deleted"})
            else:
                return JsonResponse(
                    {"success": False, "error": "Bookmark not found"}, status=404
                )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    try:
        if not hasattr(request.user, "username"):
            return JsonResponse({"error": "Customer profile missing"}, status=400)

        customer = Customer.objects.get(username=request.user.username)

        # Get restaurant IDs from the user's bookmarks
        favorite_qs = FavoriteRestaurant.objects.filter(customer=customer)

        restaurant_ids = favorite_qs.values_list("restaurant_id", flat=True)

        # Original restaurant list (unchanged)
        restaurants = list(
            Restaurant.objects.filter(id__in=restaurant_ids).values(
                "id", "name", "phone", "cuisine_description"
            )
        )

        # New bookmarks list: bookmark ID + restaurant ID
        bookmarks = list(favorite_qs.values("id", "restaurant_id"))

        return JsonResponse(
            {
                "restaurants": restaurants,
                "bookmarks": bookmarks,
                "count": len(restaurants),
            }
        )
    except Exception as e:
        return JsonResponse({"error": str(e), "type": type(e).__name__}, status=500)


@csrf_protect
@login_required(login_url="/login/")
def update_profile(request):
    print("=== HIT update_profile ===")
    print("Authenticated:", request.user.is_authenticated)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        # Parse JSON body
        data = json.loads(request.body)

        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        aboutme = data.get("aboutme", "").strip()
        currentUser = data.get("currentUsername", "").strip()

        # Split full name into first and last
        parts = name.split(" ", 1)
        request.user.first_name = parts[0]
        request.user.last_name = parts[1] if len(parts) > 1 else ""
        request.user.email = email
        request.user.save()

        customer = Customer.objects.get(username=currentUser)
        customer.first_name = parts[0]
        customer.last_name = parts[1] if len(parts) > 1 else ""
        customer.aboutme = aboutme
        customer.save()

        return JsonResponse(
            {
                "name": f"{request.user.first_name} {request.user.last_name}",
                "email": request.user.email,
                "aboutme": customer.aboutme,
            }
        )

    except Customer.DoesNotExist:
        return JsonResponse({"error": "Customer profile not found."}, status=404)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_protect
@login_required
def ensure_customer_exists(request):
    try:
        if not request.user.email:
            return JsonResponse(
                {"success": False, "error": "User has no email"}, status=400
            )

        customer, created = Customer.objects.get_or_create(
            email=request.user.email,
            defaults={
                "username": request.user.username,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
            },
        )

        return JsonResponse({"success": True, "created": created})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# =====================================================================================
# MESSAGE VIEWS
# =====================================================================================


@login_required(login_url="/login/")
def get_conversation_messages(request, receiver_id):
    sender_id = request.user.id  # Assuming the user is authenticated
    messages = DM.objects.filter(
        sender_id__in=[sender_id, receiver_id], receiver_id__in=[sender_id, receiver_id]
    ).order_by("sent_at")

    return JsonResponse(
        {
            "messages": [
                {
                    "decoded_message": message.message.decode("utf-8"),
                    "sender_id": message.sender_id,
                    "receiver_id": message.receiver_id,
                    "sent_at": message.sent_at.isoformat(),
                }
                for message in messages
            ]
        }
    )


@login_required(login_url="/login/")
def messages_view(request, chat_user_id=None):
    try:
        user = Customer.objects.get(email=request.user.email)
    except Customer.DoesNotExist:
        return render(
            request,
            "inbox.html",
            {
                "conversations": [],
                "active_chat": None,
                "messages": [],
                "error": "Your profile could not be found.",
                "has_unread_messages": has_unread_messages(request.user),
            },
        )

    # Filter DMs as before
    all_dms = DM.objects.filter(
        (Q(sender=user) & Q(receiver__is_activated=True))
        | Q(receiver__deactivated_until__lt=date.today())
        | (
            Q(sender__is_activated=True)
            | Q(sender__deactivated_until__lt=date.today()) & Q(receiver=user)
        )
    ).exclude(
        Q(sender=user, receiver__in=user.blocked_customers.all())
        | Q(receiver=user, sender__in=user.blocked_customers.all())
    )

    # Prepare conversations
    participants = {}
    for dm in all_dms:
        other = dm.receiver if dm.sender == user else dm.sender
        if other.id not in participants:
            # Check if there are actually messages between these users
            message_count = DM.objects.filter(
                (Q(sender=user) & Q(receiver=other))
                | (Q(sender=other) & Q(receiver=user))
            ).count()

            # Only add to participants if there are messages
            if message_count > 0:
                participants[other.id] = {
                    "id": other.id,
                    "name": other.first_name,
                    "email": other.email,
                    "avatar_url": "/static/images/avatar-placeholder.png",
                    "has_unread": False,
                }

    # Check for unread messages
    for participant_id in participants:
        has_unread = DM.objects.filter(
            sender_id=participant_id, receiver=user, read=False
        ).exists()
        participants[participant_id]["has_unread"] = has_unread

    conversations = list(participants.values())

    # Determine active chat
    active_chat = None
    if chat_user_id:
        active_chat = get_object_or_404(Customer, id=chat_user_id)

        # Check if there are messages before setting active_chat
        message_count = DM.objects.filter(
            (Q(sender=user) & Q(receiver=active_chat))
            | (Q(sender=active_chat) & Q(receiver=user))
        ).count()

        if message_count == 0:
            active_chat = None

    elif conversations:
        active_chat = get_object_or_404(Customer, id=conversations[0]["id"])

    # Fetch messages for the active chat
    messages = []
    if active_chat:
        raw_messages = DM.objects.filter(
            (Q(sender=user) & Q(receiver=active_chat))
            | (Q(sender=active_chat) & Q(receiver=user))
        ).order_by("sent_at")

        # Mark messages as read
        DM.objects.filter(sender=active_chat, receiver=user, read=False).update(
            read=True
        )

        for msg in raw_messages:
            try:
                byte_data = bytes(msg.message)
                msg.decoded_message = byte_data.decode("utf-8")
            except Exception:
                msg.decoded_message = "[Could not decode message]"
            messages.append(msg)

    return render(
        request,
        "inbox.html",
        {
            "conversations": conversations,
            "active_chat": active_chat,
            "messages": messages,
            "has_unread_messages": has_unread_messages(request.user),
        },
    )


@login_required(login_url="/login/")
def send_message(request, chat_user_id):
    if request.method == "POST":
        try:
            # Try to get sender from Customer
            sender = Customer.objects.get(email=request.user.email)
        except Customer.DoesNotExist:
            try:
                # If not found, try Restaurant
                sender = Restaurant.objects.get(email=request.user.email)
            except Restaurant.DoesNotExist:
                # Optional: handle case where sender is neither
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"error": "Sender not found"}, status=404)
                messages.error(
                    request,
                    "Your account was not found. Please contact support.",
                    extra_tags=INBOX_MESSAGE,
                )
                return HttpResponse("Sender not found", status=404)
        try:
            recipient = Customer.objects.get(id=chat_user_id)
        except Customer.DoesNotExist:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"error": "Recipient not found"}, status=404)
            messages.error(
                request,
                "The user you're trying to message could not be found.",
                extra_tags=INBOX_MESSAGE,
            )
            return redirect("messages inbox")

        message_text = request.POST.get("message")

        # Only able to send messages to activated users
        if (not recipient.is_activated) and recipient.deactivated_until >= date.today():
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"error": "User is deactivated"}, status=400)
            messages.error(
                request,
                "Sorry, that user has been deactivated. You can't DM them.",
                extra_tags=INBOX_MESSAGE,
            )
            return redirect("messages inbox")

        if isinstance(sender, Customer):
            if sender.blocked_customers.filter(id=recipient.id).exists():
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {"error": "Cannot message blocked user"}, status=400
                    )
                messages.error(
                    request,
                    "You can't send messages to a user you've blocked.",
                    extra_tags=INBOX_MESSAGE,
                )
                return redirect("chat", chat_user_id=recipient.id)

        if recipient == sender:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"error": "Cannot message yourself"}, status=400)
            messages.error(
                request, "You can't message yourself.", extra_tags=INBOX_MESSAGE
            )
            return redirect("chat", chat_user_id=recipient.id)

        if not message_text.strip():
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"error": "Empty message"}, status=400)
            messages.error(
                request, "Message cannot be empty.", extra_tags=INBOX_MESSAGE
            )
            return redirect("chat", chat_user_id=recipient.id)

        # Save the DM with read=False for new messages
        message = DM.objects.create(
            sender=sender,
            receiver=recipient,
            message=message_text.encode("utf-8"),
            read=False,
        )

        # For AJAX requests, return success response
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True, "message_id": message.id})

        # For regular form submissions, redirect as before
        return redirect("chat", chat_user_id=recipient.id)


@login_required(login_url="/login/")
def send_message_generic(request):
    if request.method == "POST":
        try:
            # Try to get sender from Customer
            sender = Customer.objects.get(email=request.user.email)
        except Customer.DoesNotExist:
            try:
                # If not found, try Restaurant
                sender = Restaurant.objects.get(email=request.user.email)
            except Restaurant.DoesNotExist:
                # Optional: handle case where sender is neither
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"error": "Sender not found"}, status=404)
                messages.error(
                    request,
                    "Your account was not found. Please contact support.",
                    extra_tags=INBOX_MESSAGE,
                )
                return redirect("messages inbox")

        recipient_email = request.POST.get("recipient")
        message_text = request.POST.get("message")

        if not recipient_email:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {"error": "Please enter a recipient email address"}, status=400
                )
            messages.error(
                request,
                "Please enter a recipient email address.",
                extra_tags=INBOX_MESSAGE,
            )
            return redirect("messages inbox")

        if not message_text.strip():
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"error": "Message cannot be empty"}, status=400)
            messages.error(
                request, "Message cannot be empty.", extra_tags=INBOX_MESSAGE
            )
            return redirect("messages inbox")

        try:
            # First try to find the recipient as a Customer
            recipient = Customer.objects.get(email=recipient_email)
        except Customer.DoesNotExist:
            # Check if recipient exists as a Restaurant
            try:
                restaurant_recipient = Restaurant.objects.get(email=recipient_email)
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {
                            "error": f"'{recipient_email}' is a restaurant account. Currently, you can only message customer accounts."
                        },
                        status=400,
                    )
                messages.error(
                    request,
                    f"'{recipient_email}' is a restaurant account. Currently, you can only message customer accounts.",
                    extra_tags=INBOX_MESSAGE,
                )
            except Restaurant.DoesNotExist:
                # Recipient doesn't exist at all
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {
                            "error": f"Recipient '{recipient_email}' does not exist. Please check the email address and try again."
                        },
                        status=404,
                    )
                messages.error(
                    request,
                    f"Recipient '{recipient_email}' does not exist. Please check the email address and try again.",
                    extra_tags=INBOX_MESSAGE,
                )
            return redirect("messages inbox")

        if isinstance(sender, Customer):
            if sender.blocked_customers.filter(id=recipient.id).exists():
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {"error": "You can't send messages to someone you've blocked."},
                        status=400,
                    )
                messages.error(
                    request,
                    "You can't send messages to someone you've blocked.",
                    extra_tags=INBOX_MESSAGE,
                )
                return redirect("messages inbox")

        if recipient == sender:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {"error": "You can't message yourself."}, status=400
                )
            messages.error(
                request, "You can't message yourself.", extra_tags=INBOX_MESSAGE
            )
            return redirect("messages inbox")

        # Create DM with read=False for new messages
        dm = DM.objects.create(
            sender=sender,
            receiver=recipient,
            message=message_text.encode("utf-8"),
            read=False,
        )

        # For AJAX requests, return success with chat ID
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {"success": True, "chat_user_id": recipient.id, "message_id": dm.id}
            )

        # For regular form submissions, redirect as before
        return redirect("chat", chat_user_id=recipient.id)


@login_required(login_url="/login/")
def delete_conversation(request, other_user_id, **kwargs):
    try:
        user = Customer.objects.get(email=request.user.email)
        other_user = Customer.objects.get(id=other_user_id)

        # Delete all messages between these two users (in both directions)
        DM.objects.filter(
            (Q(sender=user) & Q(receiver=other_user))
            | (Q(sender=other_user) & Q(receiver=user))
        ).delete()

        messages.success(
            request,
            f"Conversation with {other_user.first_name} has been deleted.",
            extra_tags=INBOX_MESSAGE,
        )
        return redirect("messages inbox")
    except Customer.DoesNotExist:
        messages.error(request, "Your account was not found.", extra_tags=INBOX_MESSAGE)
        return redirect("messages inbox")


async def stream_messages(request, chat_user_id=None):
    """
    Asynchronous view to stream messages for the active chat or all conversations.
    """
    # Get current user from the session asynchronously
    is_authenticated = await sync_to_async(lambda: request.user.is_authenticated)()
    if not is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    user_email = await sync_to_async(lambda: request.user.email)()

    try:
        # Fetch the current user asynchronously
        user = await sync_to_async(Customer.objects.get)(email=user_email)
    except Customer.DoesNotExist:
        return JsonResponse({"error": "Your profile could not be found."}, status=404)

    if chat_user_id:
        try:
            # Fetch the active chat user asynchronously
            active_chat = await sync_to_async(Customer.objects.get)(id=chat_user_id)
        except Customer.DoesNotExist:
            return JsonResponse({"error": "Active chat user not found."}, status=404)

        # Fetch messages for the active chat asynchronously
        messages = await sync_to_async(list)(
            DM.objects.filter(
                (Q(sender=user) & Q(receiver=active_chat))
                | (Q(sender=active_chat) & Q(receiver=user))
            )
            .order_by("sent_at")
            .values("id", "sender__id", "receiver__id", "message", "sent_at", "read")
        )
    else:
        # Fetch all messages for the user asynchronously
        messages = await sync_to_async(list)(
            DM.objects.filter(Q(sender=user) | Q(receiver=user))
            .order_by("sent_at")
            .values("id", "sender__id", "receiver__id", "message", "sent_at", "read")
        )

    # Decode binary messages - convert memoryview to bytes first
    for message in messages:
        # Convert memoryview to bytes, then decode to string
        message["message"] = bytes(message["message"]).decode("utf-8")

    return JsonResponse({"messages": messages}, safe=False)


@login_required(login_url="/login/")
def get_conversations(request):
    """API endpoint to get the current user's conversations"""
    try:
        user = Customer.objects.get(email=request.user.email)
    except Customer.DoesNotExist:
        return JsonResponse({"error": "Your profile could not be found."}, status=404)

    # Only get participants where messages actually exist between them
    all_dms = DM.objects.filter(
        (Q(sender=user) & Q(receiver__is_activated=True))
        | Q(receiver__deactivated_until__lt=date.today())
        | (
            Q(sender__is_activated=True)
            | Q(sender__deactivated_until__lt=date.today()) & Q(receiver=user)
        )
    ).exclude(
        Q(sender=user, receiver__in=user.blocked_customers.all())
        | Q(receiver=user, sender__in=user.blocked_customers.all())
    )

    # Prepare conversations
    participants = {}
    for dm in all_dms:
        other = dm.receiver if dm.sender == user else dm.sender
        if other.id not in participants:
            # Check if there are actually messages between these users
            message_count = DM.objects.filter(
                (Q(sender=user) & Q(receiver=other))
                | (Q(sender=other) & Q(receiver=user))
            ).count()

            # Only add to participants if there are messages
            if message_count > 0:
                participants[other.id] = {
                    "id": other.id,
                    "name": other.first_name,
                    "email": other.email,
                    "avatar_url": "/static/images/avatar-placeholder.png",
                    "has_unread": False,
                }

    # Check for unread messages
    for participant_id in participants:
        has_unread = DM.objects.filter(
            sender_id=participant_id, receiver=user, read=False
        ).exists()
        participants[participant_id]["has_unread"] = has_unread

    conversations = list(participants.values())

    return JsonResponse({"conversations": conversations})
