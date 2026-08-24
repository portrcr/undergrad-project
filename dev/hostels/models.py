from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Term(models.Model):
    """An academic term/semester. Gives bookings a time axis for demand prediction."""

    name = models.CharField(max_length=50, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    sequence_number = models.PositiveIntegerField(unique=True, help_text='Order terms chronologically, e.g. 1, 2, 3...')

    class Meta:
        ordering = ['sequence_number']

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({'end_date': 'End date must be after start date.'})

    def __str__(self):
        return self.name

    @classmethod
    def current(cls):
        """The term covering today, or the most recent one if none does. May return None if no terms exist yet."""
        today = timezone.now().date()
        term = cls.objects.filter(start_date__lte=today, end_date__gte=today).order_by('sequence_number').first()
        return term or cls.objects.order_by('-sequence_number').first()


class Hostel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='hostels/', blank=True, null=True)

    def __str__(self):
        return self.name


class Room(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        FULL = 'full', 'Full'
        MAINTENANCE = 'maintenance', 'Under maintenance'

    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='rooms')
    room_number = models.CharField(max_length=20)
    capacity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    price_per_term = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    has_private_bathroom = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)

    class Meta:
        unique_together = ('hostel', 'room_number')

    def __str__(self):
        return f'{self.hostel.name} - {self.room_number}'
