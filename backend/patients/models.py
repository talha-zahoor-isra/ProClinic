
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from cloudinary.models import CloudinaryField
from accounts.models import Hospital


class Patient(models.Model):
    BLOOD_GROUP_CHOICES = [
        ("A+", "A+"),
        ("A-", "A-"),
        ("B+", "B+"),
        ("B-", "B-"),
        ("O+", "O+"),
        ("O-", "O-"),
        ("AB+", "AB+"),
        ("AB-", "AB-"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_profile",
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()

    gender = models.CharField(
        max_length=10,
        choices=[
            ("Male", "Male"),
            ("Female", "Female"),
            ("Other", "Other"),
        ],
    )

    blood_group = models.CharField(
        max_length=5,
        choices=BLOOD_GROUP_CHOICES,
    )

    contact_number = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField()
    allergies = models.TextField(
        blank=True,
        help_text="List known allergies",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class HospitalPatient(models.Model):
    """
    Links a patient profile to a hospital.

    A patient can receive care at multiple hospitals while each
    hospital maintains its own patient relationship.
    """

    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.PROTECT,
        related_name="patient_relationships",
    )

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="hospital_relationships",
    )

    is_active = models.BooleanField(default=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["hospital__name", "patient__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "patient"],
                name="unique_patient_per_hospital",
            ),
        ]

    def __str__(self):
        return f"{self.patient} — {self.hospital}"


class Visit(models.Model):
    """Electronic health record visit."""

    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.PROTECT,
        related_name="visits",
        null=True,
        blank=True,
    )

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="visits",
    )

    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="doctor_visits",
    )

    appointment = models.OneToOneField(
        "appointments.Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visit",
    )

    visit_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-visit_date"]

    def clean(self):
        super().clean()

        if self.hospital_id and self.doctor_id:
            if self.doctor.hospital_id != self.hospital_id:
                raise ValidationError(
                    {
                        "doctor": (
                            "The doctor must belong to the selected hospital."
                        )
                    }
                )

        if self.hospital_id and self.patient_id:
            enrolled = HospitalPatient.objects.filter(
                hospital_id=self.hospital_id,
                patient_id=self.patient_id,
                is_active=True,
            ).exists()

            if not enrolled:
                raise ValidationError(
                    {
                        "patient": (
                            "The patient must be registered with this hospital."
                        )
                    }
                )

    def __str__(self):
        return f"Visit for {self.patient} on {self.visit_date:%Y-%m-%d}"


def _validate_lab_report_pdf(value):
    """Validate lab report extension and file size (maximum 5 MB)."""

    if not value:
        return

    max_size = 5 * 1024 * 1024

    if value.size > max_size:
        raise ValidationError("Lab report files must not exceed 5 MB.")

    extension = (
        "." + value.name.rsplit(".", 1)[-1].lower()
        if "." in value.name
        else ""
    )

    if extension != ".pdf":
        raise ValidationError("Only PDF files are accepted.")


class LabReport(models.Model):
    """
    Lab report associated with a patient and, where assigned,
    a hospital. Hospital authorization must also be enforced in views.
    """

    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_ARCHIVED = "archived"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.PROTECT,
        related_name="lab_reports",
        null=True,
        blank=True,
    )

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="lab_reports",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_lab_reports",
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_lab_reports",
    )

    test_name = models.CharField(max_length=255)

    report_date = models.DateField()

    pdf_file = CloudinaryField(
        "pdf_file",
        resource_type="raw",
        format="pdf",
        validators=[_validate_lab_report_pdf],
        help_text="PDF lab report, maximum 5 MB.",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Lab Report"
        verbose_name_plural = "Lab Reports"

    def clean(self):
        super().clean()

        if self.hospital_id and self.patient_id:
            enrolled = HospitalPatient.objects.filter(
                hospital_id=self.hospital_id,
                patient_id=self.patient_id,
                is_active=True,
            ).exists()

            if not enrolled:
                raise ValidationError(
                    {
                        "patient": (
                            "The patient must be registered with this hospital."
                        )
                    }
                )

        if self.hospital_id and self.uploaded_by_id:
            if self.uploaded_by.hospital_id != self.hospital_id:
                raise ValidationError(
                    {
                        "uploaded_by": (
                            "The uploader must belong to this hospital."
                        )
                    }
                )

        if self.hospital_id and self.verified_by_id:
            if self.verified_by.hospital_id != self.hospital_id:
                raise ValidationError(
                    {
                        "verified_by": (
                            "The verifier must belong to this hospital."
                        )
                    }
                )

    def mark_verified(self, user):
        self.status = self.STATUS_VERIFIED
        self.verified_by = user
        self.save(
            update_fields=["status", "verified_by", "updated_at"]
        )

    def mark_archived(self):
        self.status = self.STATUS_ARCHIVED
        self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return f"{self.test_name} — {self.patient} ({self.report_date})"
