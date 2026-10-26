import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Hospital(models.Model):
    """
    Represents a hospital registered on the TalMedix platform.
    Each hospital can have its own users and medical records.
    """

    name = models.CharField(max_length=200, unique=True)
    address = models.TextField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Hospital"
        verbose_name_plural = "Hospitals"

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ("ADMIN", "Hospital Administrator"),
        ("DOCTOR", "Doctor"),
        ("RECEPTIONIST", "Receptionist"),
        ("PHARMACIST", "Pharmacist"),
        ("ACCOUNTANT", "Accountant"),
        ("PATIENT", "Patient"),
    )

    # A null hospital allows existing accounts and platform-level
    # administrators to remain compatible during the transition.
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="PATIENT",
    )

    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
    )

    specialization = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="For doctors (e.g., Cardiology, General Practice)",
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class PatientOTP(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="otps",
    )

    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        return (
            not self.is_used
            and timezone.now() - self.created_at < timedelta(minutes=10)
        )

    @classmethod
    def generate(cls, user):
        # Generate a cryptographically secure six-digit OTP.
        otp = f"{secrets.randbelow(900000) + 100000}"
        return cls.objects.create(user=user, otp_code=otp)
