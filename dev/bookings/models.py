from django.conf import settings
from django.db import models

from hostels.models import Room, Term


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        CANCELLED = 'cancelled', 'Cancelled'
        REJECTED = 'rejected', 'Rejected'

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='bookings')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    date_requested = models.DateTimeField(auto_now_add=True)
    date_resolved = models.DateTimeField(null=True, blank=True)

    class Meta:
        # A confirmed booking occupies one bed; a room can hold at most `capacity` confirmed bookings,
        # enforced in application logic rather than the DB.
        ordering = ['-date_requested']

    def __str__(self):
        return f'{self.student.username} -> {self.room} ({self.term})'


class Recommendation(models.Model):
    """Logs what the recommender suggested, so acceptance rate can be measured later."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recommendations')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='recommendations')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='recommendations')
    score = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    was_accepted = models.BooleanField(null=True, blank=True, help_text='Null until the student books or dismisses it.')

    class Meta:
        ordering = ['-score']

    def __str__(self):
        return f'{self.room} for {self.student.username} (score={self.score:.2f})'


class Notification(models.Model):
    """An in-app notification for a student: either system-generated (their booking
    request was resolved - sender is null) or a note written directly by staff/admin."""

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_notifications',
        null=True, blank=True, help_text='Null for system-generated notifications (e.g. approve/reject).',
    )
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.recipient.username}: {self.message}'
