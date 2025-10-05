from django.db import models
from django.contrib.auth.models import User
import uuid # <-- Import the standard Python UUID library

# --- PROFILE TABLES (Linked to Django's built-in User) ---

class AdminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    cit_id = models.CharField(max_length=15, unique=True, db_column='cit_id')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admins'

    def __str__(self):
        return self.name


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    cit_id = models.CharField(max_length=15, unique=True, db_column='cit_id')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'students'

    def __str__(self):
        return self.name


# --- EVENT TABLES (Managed) ---

class Event(models.Model):
    # FIX: Use uuid.uuid4 to generate the default UUID
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    admin = models.ForeignKey(
        AdminProfile,
        on_delete=models.CASCADE,
        db_column='admin_id',
        related_name='created_events'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    date = models.DateField()
    location = models.CharField(max_length=255, null=True, blank=True)
    start_time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    max_attendees = models.IntegerField(null=True, blank=True)
    picture_url = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'events'

    def __str__(self):
        return self.title


# Maps to the 'event_registrations' SQL table
class EventRegistration(models.Model):
    # FIX: Use uuid.uuid4 to generate the default UUID
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        db_column='student_id',
        related_name='registrations'
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        db_column='event_id',
        related_name='registrations'
    )
    registration_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'event_registrations'
        unique_together = ('student', 'event')

    def __str__(self):
        return f"{self.student.name} registered for {self.event.title}"