from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import Hospital
from patients.models import HospitalPatient, Patient


ACTIVE_APPOINTMENT_STATUSES = (
    "SCHEDULED",
    "RESCHEDULED",
    "CHECKED_IN",
)


class DoctorUnavailability(models.Model):
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.PROTECT,
        related_name="doctor_unavailability",
        null=True,
        blank=True,
    )

    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="unavailable_slots",
    )

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_time"]

    def clean(self):
        super().clean()
        errors = {}

        if self.start_time and timezone.is_naive(self.start_time):
            self.start_time = timezone.make_aware(
                self.start_time,
                timezone.get_current_timezone(),
            )

        if self.end_time and timezone.is_naive(self.end_time):
            self.end_time = timezone.make_aware(
                self.end_time,
                timezone.get_current_timezone(),
            )

        User = get_user_model()
        doctor = None

        if self.doctor_id:
            doctor = User.objects.filter(pk=self.doctor_id).first()

            if not doctor or doctor.role != "DOCTOR":
                errors["doctor"] = (
                    "Unavailability can only be assigned to a doctor."
                )
            elif self.hospital_id:
                if doctor.hospital_id != self.hospital_id:
                    errors["hospital"] = (
                        "The doctor must belong to the selected hospital."
                    )
            elif doctor.hospital_id:
                self.hospital_id = doctor.hospital_id

        if self.start_time and self.start_time < timezone.now():
            errors["start_time"] = (
                "Start time cannot be in the past."
            )

        if (
            self.start_time
            and self.end_time
            and self.end_time <= self.start_time
        ):
            errors["end_time"] = (
                "End time must be after start time."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.doctor} unavailable from "
            f"{self.start_time} to {self.end_time}"
        )


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("SCHEDULED", "Scheduled"),
        ("CHECKED_IN", "Checked In"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
        ("NOSHOW", "No Show"),
        ("RESCHEDULED", "Rescheduled"),
    ]

    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.PROTECT,
        related_name="appointments",
        null=True,
        blank=True,
    )

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="appointments",
    )

    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="doctor_appointments",
    )

    scheduled_time = models.DateTimeField()
    reason = models.TextField(blank=True)

    room_assignment = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Room assigned during check-in",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="SCHEDULED",
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_appointments",
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the appointment was cancelled.",
    )

    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_appointments",
        help_text="User who cancelled the appointment.",
    )

    cancellation_reason = models.TextField(
        blank=True,
        help_text="Optional reason for cancellation.",
    )

    class Meta:
        ordering = ["scheduled_time"]
        indexes = [
            models.Index(
                fields=["hospital", "scheduled_time", "status"],
                name="appt_hosp_time_status_idx",
            ),
            models.Index(
                fields=["doctor", "scheduled_time", "status"],
                name="appt_doctor_time_status_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if (
            self.scheduled_time
            and timezone.is_naive(self.scheduled_time)
        ):
            self.scheduled_time = timezone.make_aware(
                self.scheduled_time,
                timezone.get_current_timezone(),
            )

        original = None

        if self.pk:
            original = (
                Appointment.objects.filter(pk=self.pk)
                .first()
            )

        time_changed = (
            original is None
            or original.scheduled_time != self.scheduled_time
        )

        doctor_changed = (
            original is None
            or original.doctor_id != self.doctor_id
        )

        patient_changed = (
            original is None
            or original.patient_id != self.patient_id
        )

        hospital_changed = (
            original is None
            or original.hospital_id != self.hospital_id
        )

        is_active_booking = (
            self.status in ACTIVE_APPOINTMENT_STATUSES
        )

        # Automatically assign the doctor's hospital for new bookings.
        # Existing legacy appointments are not reassigned automatically.
        if (
            original is None
            and not self.hospital_id
            and self.doctor_id
        ):
            User = get_user_model()
            doctor = User.objects.filter(
                pk=self.doctor_id
            ).first()

            if doctor and doctor.hospital_id:
                self.hospital_id = doctor.hospital_id

        if (
            is_active_booking
            and (original is None or time_changed)
            and self.scheduled_time
            and self.scheduled_time <= timezone.now()
        ):
            errors["scheduled_time"] = (
                "Scheduled time must be in the future."
            )

        User = get_user_model()
        doctor = None

        if self.doctor_id:
            doctor = User.objects.filter(
                pk=self.doctor_id
            ).first()

            if not doctor or doctor.role != "DOCTOR":
                errors["doctor"] = (
                    "Please select a valid doctor."
                )

        # Enforce hospital boundaries for hospital-assigned bookings.
        if self.hospital_id and doctor:
            if doctor.hospital_id != self.hospital_id:
                errors["doctor"] = (
                    "The doctor must belong to the selected hospital."
                )

        if self.hospital_id and self.patient_id:
            registration_exists = HospitalPatient.objects.filter(
                hospital_id=self.hospital_id,
                patient_id=self.patient_id,
                is_active=True,
            ).exists()

            if not registration_exists:
                errors["patient"] = (
                    "Register this patient with the hospital before "
                    "booking an appointment."
                )

        # Check blocked availability when the booking is being changed.
        if (
            is_active_booking
            and self.doctor_id
            and self.scheduled_time
            and (
                original is None
                or time_changed
                or doctor_changed
                or hospital_changed
            )
            and not getattr(self, "override_conflict", False)
        ):
            blocked_slots = DoctorUnavailability.objects.filter(
                doctor_id=self.doctor_id,
                start_time__lt=self.scheduled_time,
                end_time__gt=self.scheduled_time,
            )

            if self.hospital_id:
                blocked_slots = blocked_slots.filter(
                    hospital_id=self.hospital_id
                )

            if blocked_slots.exists():
                errors["scheduled_time"] = (
                    "The doctor is unavailable at this time."
                )

        # Prevent doctor double-booking at the same timestamp.
        if (
            is_active_booking
            and self.doctor_id
            and self.scheduled_time
            and not getattr(self, "override_conflict", False)
        ):
            conflicts = Appointment.objects.filter(
                doctor_id=self.doctor_id,
                scheduled_time=self.scheduled_time,
                status__in=ACTIVE_APPOINTMENT_STATUSES,
            ).exclude(pk=self.pk)

            if self.hospital_id:
                conflicts = conflicts.filter(
                    hospital_id=self.hospital_id
                )

            if conflicts.exists():
                errors["doctor"] = (
                    "This doctor already has an appointment at that time."
                )

        # Prevent a patient from having two active appointments at the
        # same timestamp at the same hospital.
        if (
            is_active_booking
            and self.patient_id
            and self.scheduled_time
            and not getattr(self, "override_conflict", False)
        ):
            conflicts = Appointment.objects.filter(
                patient_id=self.patient_id,
                scheduled_time=self.scheduled_time,
                status__in=ACTIVE_APPOINTMENT_STATUSES,
            ).exclude(pk=self.pk)

            if self.hospital_id:
                conflicts = conflicts.filter(
                    hospital_id=self.hospital_id
                )

            if conflicts.exists():
                errors["scheduled_time"] = (
                    "This patient already has an appointment at that time."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def cancel(self, user, reason=""):
        self.status = "CANCELLED"
        self.cancelled_at = timezone.now()
        self.cancelled_by = user
        self.cancellation_reason = reason

        self.save(
            update_fields=[
                "status",
                "cancelled_at",
                "cancelled_by",
                "cancellation_reason",
            ]
        )

    def reschedule(self, new_time):
        self.status = "RESCHEDULED"
        self.scheduled_time = new_time
        self.save(update_fields=["status", "scheduled_time"])

    @property
    def is_cancellable(self):
        return self.status in ACTIVE_APPOINTMENT_STATUSES

    def __str__(self):
        return (
            f"{self.patient} with Dr. {self.doctor.last_name} "
            f"on {self.scheduled_time}"
        )
