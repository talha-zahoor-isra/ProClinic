import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    StaffProfileForm,
    PatientPasswordChangeForm,
    PatientProfileForm,
    PatientSignUpForm,
    StaffCreationForm,
)
from .models import CustomUser, PatientOTP
from patients.models import Patient
from audit.models import AuditLog


logger = logging.getLogger(__name__)

STAFF_ROLES = {
    "ADMIN",
    "DOCTOR",
    "RECEPTIONIST",
    "PHARMACIST",
    "ACCOUNTANT",
}

OTP_MAX_ATTEMPTS = 5
OTP_COOLDOWN_MINUTES = 2


def choose_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    return render(request, "accounts/choose_login.html")


def is_hospital_admin(user):
    """
    Hospital administration is limited to ADMIN users assigned
    to a hospital. Django superuser status alone does not grant
    access through these hospital-level views.
    """
    return (
        user.is_authenticated
        and user.is_active
        and user.role == "ADMIN"
        and user.hospital_id is not None
    )


class RoleBasedLoginView(LoginView):
    redirect_authenticated_user = True
    allowed_roles = set()
    portal_label = ""

    def form_valid(self, form):
        user = form.get_user()

        if user.role not in self.allowed_roles:
            form.add_error(
                None,
                (
                    f"This account is not authorized for the "
                    f"{self.portal_label} portal."
                ),
            )
            return self.form_invalid(form)

        response = super().form_valid(form)

        try:
            AuditLog.objects.create(
                actor=user,
                action_type="LOGIN",
                entity_type="CustomUser",
                entity_id=user.pk,
                changes={
                    "ip": self.request.META.get(
                        "REMOTE_ADDR", "unknown"
                    )
                },
            )
        except Exception:
            logger.exception("Failed to record login audit event.")

        return response


class StaffLoginView(RoleBasedLoginView):
    template_name = "accounts/staff_login.html"
    allowed_roles = STAFF_ROLES
    portal_label = "Staff"


class PatientLoginView(RoleBasedLoginView):
    template_name = "accounts/patient_login.html"
    allowed_roles = {"PATIENT"}
    portal_label = "Patient"


def patient_signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = PatientSignUpForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.role = "PATIENT"
                    user.phone_number = form.cleaned_data.get(
                        "phone_number"
                    )
                    user.save()

                    Patient.objects.create(
                        user=user,
                        first_name=form.cleaned_data["first_name"],
                        last_name=form.cleaned_data["last_name"],
                        date_of_birth=form.cleaned_data["date_of_birth"],
                        gender=form.cleaned_data["gender"],
                        blood_group=form.cleaned_data["blood_group"],
                        contact_number=form.cleaned_data["phone_number"],
                        email=form.cleaned_data["email"],
                        address=form.cleaned_data["address"],
                        allergies=form.cleaned_data.get("allergies", ""),
                    )

                login(request, user)
                return redirect("dashboard")

            except Exception:
                logger.exception(
                    "Unexpected error during patient signup."
                )
                messages.error(
                    request,
                    "We could not create your account. Please try again.",
                )
    else:
        form = PatientSignUpForm()

    return render(
        request,
        "accounts/patient_signup.html",
        {"form": form},
    )


@login_required
def create_staff_account(request):
    if not is_hospital_admin(request.user):
        messages.error(
            request,
            "You must belong to a hospital administrator account "
            "to manage hospital staff.",
        )
        return redirect("dashboard")

    hospital = request.user.hospital

    if request.method == "POST":
        form = StaffCreationForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.hospital = hospital

                    # Hospital staff cannot create platform superusers.
                    user.is_superuser = False
                    user.save()

                messages.success(
                    request,
                    (
                        f"Staff account created for {user.username} "
                        f"({user.get_role_display()})."
                    ),
                )
                return redirect("create_staff_account")

            except Exception:
                logger.exception("Failed to create hospital staff account.")
                messages.error(
                    request,
                    "The staff account could not be created.",
                )
    else:
        form = StaffCreationForm()

    staff_list = (
        CustomUser.objects.filter(hospital=hospital)
        .exclude(role="PATIENT")
        .order_by("-is_active", "-date_joined")
    )

    return render(
        request,
        "accounts/create_staff_account.html",
        {
            "form": form,
            "staff_list": staff_list,
        },
    )


@require_POST
@login_required
def deactivate_staff_account(request, pk):
    if not is_hospital_admin(request.user):
        return redirect("dashboard")

    hospital = request.user.hospital

    target_user = get_object_or_404(
        CustomUser,
        pk=pk,
        hospital=hospital,
    )

    if target_user.role == "PATIENT":
        messages.error(
            request,
            "Patient accounts cannot be deactivated from this portal.",
        )
        return redirect("create_staff_account")

    if target_user == request.user:
        messages.error(
            request,
            "You cannot deactivate your own account.",
        )
        return redirect("create_staff_account")

    if target_user.role == "ADMIN" and target_user.is_active:
        active_admins = CustomUser.objects.filter(
            hospital=hospital,
            role="ADMIN",
            is_active=True,
        ).count()

        if active_admins <= 1:
            messages.error(
                request,
                "You cannot deactivate the last active hospital administrator.",
            )
            return redirect("create_staff_account")

    target_user.is_active = False
    target_user.save(update_fields=["is_active"])

    try:
        AuditLog.objects.create(
            actor=request.user,
            action_type="UPDATE",
            entity_type="CustomUser",
            entity_id=target_user.pk,
            changes={
                "action": "deactivated account",
                "target": target_user.username,
                "hospital_id": hospital.pk,
            },
        )
    except Exception:
        logger.exception("Failed to record staff deactivation audit event.")

    messages.success(
        request,
        f"Staff account {target_user.username} deactivated.",
    )
    return redirect("create_staff_account")


@require_POST
@login_required
def reactivate_staff_account(request, pk):
    if not is_hospital_admin(request.user):
        return redirect("dashboard")

    hospital = request.user.hospital

    target_user = get_object_or_404(
        CustomUser,
        pk=pk,
        hospital=hospital,
    )

    if target_user.role == "PATIENT":
        messages.error(
            request,
            "Patient accounts cannot be reactivated from this portal.",
        )
        return redirect("create_staff_account")

    if target_user.is_active:
        messages.info(
            request,
            f"Account {target_user.username} is already active.",
        )
        return redirect("create_staff_account")

    target_user.is_active = True
    target_user.save(update_fields=["is_active"])

    try:
        AuditLog.objects.create(
            actor=request.user,
            action_type="UPDATE",
            entity_type="CustomUser",
            entity_id=target_user.pk,
            changes={
                "action": "reactivated account",
                "target": target_user.username,
                "hospital_id": hospital.pk,
            },
        )
    except Exception:
        logger.exception("Failed to record staff reactivation audit event.")

    messages.success(
        request,
        f"Staff account {target_user.username} reactivated.",
    )
    return redirect("create_staff_account")


@login_required
def patient_profile(request):
    if request.user.role != "PATIENT":
        return redirect("dashboard")

    profile = getattr(request.user, "patient_profile", None)

    # Only match unlinked legacy profiles. Never attach a profile
    # already linked to another user's account.
    if profile is None:
        profile = (
            Patient.objects.filter(user__isnull=True)
            .filter(
                Q(email=request.user.email)
                | Q(contact_number=request.user.phone_number)
                | Q(contact_number=request.user.username)
            )
            .first()
        )

        if profile is not None:
            profile.user = request.user
            profile.save(update_fields=["user"])

    initial_profile_data = {}

    if profile is None:
        initial_profile_data = {
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "email": request.user.email,
            "contact_number": request.user.phone_number,
        }

    if request.method == "POST" and request.POST.get("form_type") == "password":
        profile_form = PatientProfileForm(
            instance=profile,
            initial=initial_profile_data,
        )
        password_form = PatientPasswordChangeForm(
            request.user,
            request.POST,
        )

        if password_form.is_valid():
            updated_user = password_form.save()
            update_session_auth_hash(request, updated_user)
            messages.success(request, "Password updated successfully.")
            return redirect("patient_profile")

    elif request.method == "POST":
        profile_form = PatientProfileForm(
            request.POST,
            instance=profile,
            initial=initial_profile_data,
        )
        password_form = PatientPasswordChangeForm(request.user)

        if profile_form.is_valid():
            with transaction.atomic():
                saved_profile = profile_form.save()

                request.user.first_name = saved_profile.first_name
                request.user.last_name = saved_profile.last_name
                request.user.email = saved_profile.email
                request.user.phone_number = saved_profile.contact_number

                request.user.save(
                    update_fields=[
                        "first_name",
                        "last_name",
                        "email",
                        "phone_number",
                    ]
                )

            messages.success(request, "Profile updated successfully.")
            return redirect("patient_profile")

    else:
        profile_form = PatientProfileForm(
            instance=profile,
            initial=initial_profile_data,
        )
        password_form = PatientPasswordChangeForm(request.user)

    return render(
        request,
        "accounts/patient_profile.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
        },
    )


@login_required
def staff_profile(request):
    if request.user.role == "PATIENT":
        return redirect("dashboard")

    if request.method == "POST":
        form = StaffProfileForm(
            request.POST,
            instance=request.user,
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("staff_profile")
    else:
        form = StaffProfileForm(instance=request.user)

    return render(
        request,
        "accounts/staff_profile.html",
        {"form": form},
    )


def patient_forgot_password_request(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()

        # Clear any previous reset authorization before a new request.
        request.session.pop("can_reset_password", None)
        request.session.pop("reset_user_id", None)
        request.session["otp_attempts"] = 0

        success_msg = (
            "If an account matches that identifier, an OTP has been "
            "sent to its registered email."
        )

        user = CustomUser.objects.filter(
            Q(username=identifier) | Q(email=identifier),
            role="PATIENT",
            is_active=True,
        ).first()

        if user and user.email:
            recent_otp = (
                PatientOTP.objects.filter(user=user)
                .order_by("-created_at")
                .first()
            )

            cooldown_active = (
                recent_otp is not None
                and timezone.now() - recent_otp.created_at
                < timedelta(minutes=OTP_COOLDOWN_MINUTES)
            )

            if not cooldown_active:
                otp = PatientOTP.generate(user)

                subject = "Your TalMedix Password Reset Code"
                message = (
                    f"Hello {user.first_name or user.username},\n\n"
                    f"Your password reset code is: {otp.otp_code}\n\n"
                    "This code expires in 10 minutes. "
                    "If you did not request this, please ignore this email.\n\n"
                    "TalMedix Team"
                )

                try:
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                        fail_silently=False,
                    )
                except Exception:
                    logger.exception("Failed to send a password reset email.")

        request.session["reset_identifier"] = identifier

        messages.success(request, success_msg)
        return redirect("patient_forgot_password_verify")

    return render(request, "accounts/forgot_password_request.html")


def patient_forgot_password_verify(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    identifier = request.session.get("reset_identifier")

    if not identifier:
        return redirect("patient_forgot_password_request")

    if request.session.get("can_reset_password"):
        return redirect("patient_forgot_password_reset")

    if request.method == "POST":
        attempts = request.session.get("otp_attempts", 0)

        if attempts >= OTP_MAX_ATTEMPTS:
            request.session.pop("reset_identifier", None)
            request.session.pop("otp_attempts", None)

            messages.error(
                request,
                "Too many verification attempts. Please request a new code.",
            )
            return redirect("patient_forgot_password_request")

        otp_code = request.POST.get("otp", "").strip()
        request.session["otp_attempts"] = attempts + 1

        user = CustomUser.objects.filter(
            Q(username=identifier) | Q(email=identifier),
            role="PATIENT",
            is_active=True,
        ).first()

        if user and otp_code.isdigit() and len(otp_code) == 6:
            otp_obj = (
                PatientOTP.objects.filter(
                    user=user,
                    otp_code=otp_code,
                    is_used=False,
                )
                .order_by("-created_at")
                .first()
            )

            if otp_obj and otp_obj.is_valid():
                otp_obj.is_used = True
                otp_obj.save(update_fields=["is_used"])

                request.session["can_reset_password"] = True
                request.session["reset_user_id"] = user.pk
                request.session.pop("otp_attempts", None)

                messages.success(
                    request,
                    "Code verified. Please choose a new password.",
                )
                return redirect("patient_forgot_password_reset")

        messages.error(request, "Invalid or expired verification code.")

    return render(
        request,
        "accounts/forgot_password_verify.html",
        {"identifier": identifier},
    )


def patient_forgot_password_reset(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if not request.session.get("can_reset_password"):
        return redirect("patient_forgot_password_request")

    user_id = request.session.get("reset_user_id")

    if not user_id:
        return redirect("patient_forgot_password_request")

    user = get_object_or_404(
        CustomUser,
        pk=user_id,
        role="PATIENT",
        is_active=True,
    )

    if request.method == "POST":
        form = SetPasswordForm(user, request.POST)

        if form.is_valid():
            user = form.save()

            # Clear the reset authorization before logging in.
            request.session.pop("reset_identifier", None)
            request.session.pop("can_reset_password", None)
            request.session.pop("reset_user_id", None)
            request.session.pop("otp_attempts", None)

            login(request, user)

            try:
                AuditLog.objects.create(
                    actor=user,
                    action_type="UPDATE",
                    entity_type="CustomUser",
                    entity_id=user.pk,
                    changes={"action": "password_reset_via_otp"},
                )
            except Exception:
                logger.exception("Failed to record password reset audit event.")

            messages.success(
                request,
                "Your password has been reset successfully.",
            )
            return redirect("dashboard")
    else:
        form = SetPasswordForm(user)

    return render(
        request,
        "accounts/forgot_password_reset.html",
        {"form": form},
    )
