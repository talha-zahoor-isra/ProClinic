
import datetime

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from accounts.models import CustomUser
from audit.utils import log_action
from core.utils import send_appointment_notification
from patients.models import Patient, Visit
from patients.utils import get_patient_profile
from prescriptions.forms import MedicineFormSet

from .forms import AppointmentForm, DoctorUnavailabilityForm, VisitNoteForm
from .models import Appointment, DoctorUnavailability


BOOKING_ALLOWED_ROLES = {"ADMIN", "RECEPTIONIST", "PATIENT"}
RECEPTIONIST_ROLES = {"ADMIN", "RECEPTIONIST"}
ACTIVE_BOOKING_STATUSES = ("SCHEDULED", "RESCHEDULED", "CHECKED_IN")


def _has_field(model, field_name):
    """Return True only when a Django model contains the requested field."""
    try:
        model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _hospital_for(user):
    return getattr(user, "hospital", None)


def _appointments_for_staff(user):
    """
    Return appointments the staff member is permitted to manage.

    Platform superusers may manage all hospitals. Hospital staff are restricted
    to their own hospital. The doctor-based fallback supports older models
    that do not yet have an Appointment.hospital field.
    """
    if user.is_superuser:
        return Appointment.objects.all()

    hospital = _hospital_for(user)
    if not hospital:
        return Appointment.objects.none()

    if _has_field(Appointment, "hospital"):
        return Appointment.objects.filter(hospital=hospital)

    return Appointment.objects.filter(doctor__hospital=hospital)


def _can_manage_appointment(user, appointment):
    if user.is_superuser:
        return True

    if user.role not in RECEPTIONIST_ROLES:
        return False

    return _appointments_for_staff(user).filter(pk=appointment.pk).exists()


def _patient_is_registered(patient, hospital):
    """
    Check hospital registration if the optional HospitalPatient model exists.
    If it does not exist yet, leave registration enforcement to the current
    model/form validation until the migration is reconciled.
    """
    try:
        registration_model = apps.get_model("patients", "HospitalPatient")
    except LookupError:
        return True

    return registration_model.objects.filter(
        patient=patient,
        hospital=hospital,
        is_active=True,
    ).exists()


def _set_appointment_hospital(appointment, hospital):
    if hospital and _has_field(Appointment, "hospital"):
        appointment.hospital = hospital


def _staff_hospital_is_valid(user, doctor):
    if user.is_superuser:
        return True

    hospital = _hospital_for(user)
    return bool(hospital and getattr(doctor, "hospital_id", None) == hospital.pk)


def _appointment_room_field():
    if _has_field(Appointment, "room_assignment"):
        return "room_assignment"
    if _has_field(Appointment, "room"):
        return "room"
    return None


@login_required
def book_appointment(request):
    user = request.user

    if user.role == "DOCTOR":
        return redirect("doctor_appointments")

    if user.role not in BOOKING_ALLOWED_ROLES and not user.is_superuser:
        return redirect("dashboard")

    patient_profile = None
    if user.role == "PATIENT":
        patient_profile = get_patient_profile(user)
        if not patient_profile:
            messages.error(
                request,
                "Your patient profile could not be found. Please contact the hospital.",
            )
            return redirect("dashboard")

    form = AppointmentForm(
        request.POST or None,
        request_user=user,
        patient_profile=patient_profile,
    )

    if user.role == "PATIENT" and patient_profile:
        form.instance.patient = patient_profile

    if request.method == "POST" and form.is_valid():
        appointment = form.save(commit=False)

        if user.role == "PATIENT":
            appointment.patient = patient_profile

        doctor = appointment.doctor

        if user.role in RECEPTIONIST_ROLES and not user.is_superuser:
            if not _staff_hospital_is_valid(user, doctor):
                form.add_error(
                    "doctor",
                    "You can only book appointments with doctors in your hospital.",
                )
                return render(request, "appointments/book_appointment.html", {
                    "form": form,
                    "is_patient_portal": False,
                    "patient_profile": patient_profile,
                })

        hospital = getattr(doctor, "hospital", None) or _hospital_for(user)
        _set_appointment_hospital(appointment, hospital)

        if hospital and not user.is_superuser:
            if not _patient_is_registered(appointment.patient, hospital):
                form.add_error(
                    None,
                    "This patient is not registered with the selected hospital.",
                )
                return render(request, "appointments/book_appointment.html", {
                    "form": form,
                    "is_patient_portal": user.role == "PATIENT",
                    "patient_profile": patient_profile,
                })

        appointment.created_by = user

        try:
            with transaction.atomic():
                appointment.save()

            send_appointment_notification(appointment, "created")
            messages.success(request, "Appointment booked successfully.")

            if user.role == "PATIENT":
                return redirect("dashboard")
            return redirect("patient_list")

        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        except Exception:
            # Keep the failure safe; log the underlying exception server-side.
            import logging
            logging.getLogger(__name__).exception("Appointment booking failed.")
            form.add_error(
                None,
                "The appointment could not be booked. Check the selected slot and try again.",
            )

    return render(request, "appointments/book_appointment.html", {
        "form": form,
        "is_patient_portal": user.role == "PATIENT",
        "patient_profile": patient_profile,
    })


@login_required
def doctor_appointments(request):
    if request.user.role != "DOCTOR":
        return redirect("dashboard")

    now = timezone.now()
    doctor_appointments_qs = Appointment.objects.filter(doctor=request.user)

    upcoming = doctor_appointments_qs.filter(
        status="SCHEDULED",
        scheduled_time__gte=now,
    ).select_related("patient", "prescription").order_by("scheduled_time")

    past = doctor_appointments_qs.filter(
        Q(status__in=["COMPLETED", "CANCELLED", "NOSHOW"])
        | Q(scheduled_time__lt=now)
    ).select_related("patient", "prescription").order_by("-scheduled_time")

    return render(request, "appointments/doctor_appointments.html", {
        "upcoming_appointments": upcoming,
        "past_appointments": past[:20],
    })


@login_required
def doctor_appointment_detail(request, appointment_id):
    if request.user.role != "DOCTOR":
        return redirect("dashboard")

    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        pk=appointment_id,
        doctor=request.user,
    )

    visit = getattr(appointment, "visit", None)
    prescription = None
    if visit:
        prescription = (
            visit.prescriptions.select_related("doctor")
            .prefetch_related("items")
            .first()
        )

    if request.method == "POST":
        if appointment.status in ("CANCELLED", "NOSHOW"):
            messages.error(
                request,
                "Cannot write prescriptions for cancelled or no-show appointments.",
            )
            return redirect(
                "doctor_appointment_detail", appointment_id=appointment.pk
            )

        if prescription:
            messages.info(
                request, "Prescription already exists for this appointment."
            )
            return redirect(
                "doctor_appointment_detail", appointment_id=appointment.pk
            )

        visit_form = VisitNoteForm(request.POST)
        medicine_formset = MedicineFormSet(request.POST, prefix="medicine")

        if visit_form.is_valid() and medicine_formset.is_valid():
            try:
                with transaction.atomic():
                    visit, created = Visit.objects.get_or_create(
                        appointment=appointment,
                        defaults={
                            "patient": appointment.patient,
                            "doctor": request.user,
                            "visit_date": appointment.scheduled_time,
                            "notes": visit_form.cleaned_data.get("notes", ""),
                            "diagnosis": visit_form.cleaned_data.get("diagnosis", ""),
                        },
                    )

                    if not created:
                        visit.notes = visit_form.cleaned_data.get(
                            "notes", visit.notes
                        )
                        visit.diagnosis = visit_form.cleaned_data.get(
                            "diagnosis", visit.diagnosis
                        )
                        visit.save(update_fields=["notes", "diagnosis"])

                    from prescriptions.models import Prescription

                    new_prescription = Prescription(
                        visit=visit,
                        patient=appointment.patient,
                        doctor=request.user,
                        appointment=appointment,
                    )
                    new_prescription.save()

                    medicine_formset.instance = new_prescription
                    medicine_formset.save()

                    appointment.status = "COMPLETED"
                    appointment.save(update_fields=["status"])

                messages.success(
                    request,
                    "Visit recorded, prescription issued, and appointment completed.",
                )
                return redirect("doctor_appointments")

            except (ValidationError, ValueError) as exc:
                visit_form.add_error(None, str(exc))
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Visit or prescription creation failed."
                )
                visit_form.add_error(
                    None,
                    "The visit could not be saved. Please try again or contact support.",
                )
    else:
        visit_form = VisitNoteForm(initial={
            "notes": visit.notes if visit else "",
            "diagnosis": visit.diagnosis if visit else "",
        })
        medicine_formset = MedicineFormSet(prefix="medicine")

    return render(request, "appointments/doctor_appointment_detail.html", {
        "appointment": appointment,
        "visit": visit,
        "prescription": prescription,
        "prescription_form": visit_form,
        "medicine_formset": medicine_formset,
    })


@login_required
def doctor_unavailability(request):
    if request.user.role != "DOCTOR":
        return redirect("dashboard")

    form = DoctorUnavailabilityForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        block = form.save(commit=False)
        block.doctor = request.user

        if _has_field(DoctorUnavailability, "hospital"):
            block.hospital = _hospital_for(request.user)

        try:
            block.save()
            messages.success(request, "Unavailability added successfully.")
            return redirect("doctor_unavailability")
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))

    blocks = DoctorUnavailability.objects.filter(
        doctor=request.user
    ).order_by("-start_time")

    return render(request, "appointments/doctor_unavailability.html", {
        "form": form,
        "blocks": blocks,
    })


@require_POST
@login_required
def delete_doctor_unavailability(request, block_id):
    if request.user.role != "DOCTOR":
        return redirect("dashboard")

    block = get_object_or_404(
        DoctorUnavailability,
        pk=block_id,
        doctor=request.user,
    )
    block.delete()
    messages.success(request, "Unavailability entry removed.")
    return redirect("doctor_unavailability")


@login_required
def get_available_slots(request):
    user = request.user

    if user.role not in BOOKING_ALLOWED_ROLES and not user.is_superuser:
        return JsonResponse({"slots": [], "error": "Not authorized."}, status=403)

    doctor_id = request.GET.get("doctor_id")
    date_str = request.GET.get("date")

    if not doctor_id or not date_str:
        return JsonResponse({"slots": []})

    try:
        query_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        now_local = timezone.localtime(timezone.now())

        if query_date < now_local.date():
            return JsonResponse({
                "slots": [],
                "error": "The selected date is in the past.",
            })

        if query_date > (now_local + datetime.timedelta(days=7)).date():
            return JsonResponse({
                "slots": [],
                "error": "Appointments can only be booked up to 7 days ahead.",
            })

        doctor = CustomUser.objects.get(pk=doctor_id, role="DOCTOR")
    except (ValueError, CustomUser.DoesNotExist):
        return JsonResponse({"slots": []})

    hospital = _hospital_for(user)

    if user.role in RECEPTIONIST_ROLES and not user.is_superuser:
        if not _staff_hospital_is_valid(user, doctor):
            return JsonResponse({"slots": [], "error": "Not authorized."}, status=403)

    patient_profile = None
    if user.role == "PATIENT":
        patient_profile = get_patient_profile(user)
        if not patient_profile:
            return JsonResponse({"slots": []}, status=403)

        hospital = getattr(doctor, "hospital", None)
        if hospital and not _patient_is_registered(patient_profile, hospital):
            return JsonResponse({"slots": [], "error": "Patient is not registered with this hospital."}, status=403)

    start_time = timezone.make_aware(
        datetime.datetime.combine(query_date, datetime.time(9, 0)),
        timezone.get_current_timezone(),
    )
    end_time = timezone.make_aware(
        datetime.datetime.combine(query_date, datetime.time(17, 0)),
        timezone.get_current_timezone(),
    )

    slots = []
    current = start_time
    while current < end_time:
        slots.append(current)
        current += datetime.timedelta(minutes=30)

    busy_query = Appointment.objects.filter(
        doctor=doctor,
        status__in=ACTIVE_BOOKING_STATUSES,
        scheduled_time__gte=start_time,
        scheduled_time__lt=end_time,
    )
    if hospital and _has_field(Appointment, "hospital"):
        busy_query = busy_query.filter(hospital=hospital)

    busy_doctor_slots = set(busy_query.values_list("scheduled_time", flat=True))

    busy_patient_slots = set()
    if patient_profile:
        patient_query = Appointment.objects.filter(
            patient=patient_profile,
            status__in=ACTIVE_BOOKING_STATUSES,
            scheduled_time__gte=start_time,
            scheduled_time__lt=end_time,
        )
        if hospital and _has_field(Appointment, "hospital"):
            patient_query = patient_query.filter(hospital=hospital)
        busy_patient_slots = set(
            patient_query.values_list("scheduled_time", flat=True)
        )

    blocks = DoctorUnavailability.objects.filter(
        doctor=doctor,
        end_time__gt=start_time,
        start_time__lt=end_time,
    )

    available = []
    now = timezone.now()

    for slot in slots:
        if slot <= now:
            continue
        if slot in busy_doctor_slots or slot in busy_patient_slots:
            continue

        slot_end = slot + datetime.timedelta(minutes=30)
        conflict = any(
            max(slot, block.start_time) < min(slot_end, block.end_time)
            for block in blocks
        )
        if conflict:
            continue

        local_slot = timezone.localtime(slot)
        available.append({
            "iso": local_slot.strftime("%Y-%m-%dT%H:%M"),
            "label": local_slot.strftime("%I:%M %p"),
        })

    return JsonResponse({"slots": available})


@login_required
def receptionist_appointments(request):
    if request.user.role not in RECEPTIONIST_ROLES and not request.user.is_superuser:
        return redirect("dashboard")

    qs = _appointments_for_staff(request.user).select_related(
        "patient", "doctor", "created_by"
    ).order_by("-scheduled_time")

    status_filter = request.GET.get("status", "")
    date_filter = request.GET.get("date", "")
    search_query = request.GET.get("q", "").strip()

    if status_filter in (
        "SCHEDULED", "CHECKED_IN", "COMPLETED",
        "CANCELLED", "NOSHOW", "RESCHEDULED",
    ):
        qs = qs.filter(status=status_filter)

    if date_filter:
        try:
            filter_date = datetime.datetime.strptime(date_filter, "%Y-%m-%d").date()
            qs = qs.filter(scheduled_time__date=filter_date)
        except ValueError:
            pass

    if search_query:
        qs = qs.filter(
            Q(patient__first_name__icontains=search_query)
            | Q(patient__last_name__icontains=search_query)
            | Q(doctor__first_name__icontains=search_query)
            | Q(doctor__last_name__icontains=search_query)
        )

    counts = {
        "all": _appointments_for_staff(request.user).count(),
    }
    for status in (
        "SCHEDULED", "CHECKED_IN", "COMPLETED",
        "CANCELLED", "NOSHOW", "RESCHEDULED",
    ):
        counts[status] = _appointments_for_staff(request.user).filter(
            status=status
        ).count()

    return render(request, "appointments/receptionist_appointments.html", {
        "appointments": qs,
        "current_status": status_filter,
        "date_filter": date_filter,
        "search_query": search_query,
        "counts": counts,
    })


@require_POST
@login_required
def receptionist_cancel_appointment(request, pk):
    if request.user.role not in RECEPTIONIST_ROLES and not request.user.is_superuser:
        return redirect("dashboard")

    appointment = get_object_or_404(_appointments_for_staff(request.user), pk=pk)

    if not appointment.is_cancellable:
        messages.error(
            request,
            f"Appointment #{pk} cannot be cancelled "
            f"(status: {appointment.get_status_display()}).",
        )
        return redirect("receptionist_appointments")

    reason = request.POST.get("reason", "").strip()

    try:
        appointment.cancel(user=request.user, reason=reason)
    except (ValidationError, ValueError) as exc:
        messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
        return redirect("receptionist_appointments")

    send_appointment_notification(appointment, "cancelled")
    log_action(
        actor=request.user,
        action_type="UPDATE",
        entity_type="Appointment",
        entity_id=pk,
        changes={
            "action": "cancel",
            "patient": str(appointment.patient),
            "reason": reason or "(none)",
        },
    )
    messages.success(request, f"Appointment #{pk} successfully cancelled.")
    return redirect("receptionist_appointments")


@require_POST
@login_required
def receptionist_reschedule_appointment(request, pk):
    if request.user.role not in RECEPTIONIST_ROLES and not request.user.is_superuser:
        return redirect("dashboard")

    appointment = get_object_or_404(_appointments_for_staff(request.user), pk=pk)

    if appointment.status in {"CANCELLED", "COMPLETED", "NOSHOW"}:
        messages.error(request, "This appointment cannot be rescheduled.")
        return redirect("receptionist_appointments")

    new_time = parse_datetime(request.POST.get("new_time", "").strip())
    if new_time is None:
        messages.error(request, "Invalid date/time. Please use the date picker.")
        return redirect("receptionist_appointments")

    if timezone.is_naive(new_time):
        new_time = timezone.make_aware(new_time, timezone.get_current_timezone())

    if new_time <= timezone.now():
        messages.error(request, "The new appointment time must be in the future.")
        return redirect("receptionist_appointments")

    old_time = appointment.scheduled_time

    try:
        # Do not set override_conflict: model validation should reject conflicts.
        appointment.reschedule(new_time)
    except (ValidationError, ValueError) as exc:
        messages.error(
            request,
            "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc),
        )
        return redirect("receptionist_appointments")

    send_appointment_notification(appointment, "rescheduled")
    log_action(
        actor=request.user,
        action_type="UPDATE",
        entity_type="Appointment",
        entity_id=pk,
        changes={
            "action": "reschedule",
            "patient": str(appointment.patient),
            "old_time": old_time.isoformat(),
            "new_time": new_time.isoformat(),
        },
    )
    messages.success(request, "Appointment rescheduled successfully.")
    return redirect("receptionist_appointments")


@require_POST
@login_required
def receptionist_mark_noshow(request, pk):
    if request.user.role not in RECEPTIONIST_ROLES and not request.user.is_superuser:
        return redirect("dashboard")

    appointment = get_object_or_404(_appointments_for_staff(request.user), pk=pk)

    if appointment.status not in ("SCHEDULED", "RESCHEDULED"):
        messages.error(request, "Only scheduled appointments can be marked as No Show.")
        return redirect("receptionist_appointments")

    appointment.status = "NOSHOW"
    appointment.save(update_fields=["status"])

    log_action(
        actor=request.user,
        action_type="UPDATE",
        entity_type="Appointment",
        entity_id=pk,
        changes={"action": "mark_noshow", "patient": str(appointment.patient)},
    )
    messages.success(request, "Appointment marked as No Show.")
    return redirect("receptionist_appointments")


@require_POST
@login_required
def receptionist_checkin_appointment(request, pk):
    if request.user.role not in RECEPTIONIST_ROLES and not request.user.is_superuser:
        return redirect("dashboard")

    appointment = get_object_or_404(_appointments_for_staff(request.user), pk=pk)

    if appointment.status not in ("SCHEDULED", "RESCHEDULED"):
        messages.error(request, "Only scheduled appointments can be checked in.")
        return redirect("receptionist_appointments")

    room = request.POST.get("room_assignment", "").strip()
    room_field = _appointment_room_field()

    appointment.status = "CHECKED_IN"
    update_fields = ["status"]

    if room and room_field:
        setattr(appointment, room_field, room)
        update_fields.append(room_field)

    appointment.save(update_fields=update_fields)

    log_action(
        actor=request.user,
        action_type="UPDATE",
        entity_type="Appointment",
        entity_id=pk,
        changes={
            "action": "checkin",
            "room": room,
            "patient": str(appointment.patient),
        },
    )

    if room and room_field:
        messages.success(request, f"Patient checked in to {room}.")
    else:
        messages.success(request, "Patient checked in successfully.")

    return redirect("receptionist_appointments")
