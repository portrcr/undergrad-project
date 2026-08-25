from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Profile(models.Model):
    """Extra fields for a Django User. Role itself lives in Django Groups
    (Admin / Staff / Student) so permissions can be managed from the admin site."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True)
    year_of_study = models.PositiveSmallIntegerField(null=True, blank=True)

    @property
    def role(self):
        group_names = set(self.user.groups.values_list('name', flat=True))
        for role in ('Admin', 'Staff', 'Student'):
            if role in group_names:
                return role
        return None

    def __str__(self):
        return f'{self.user.username} profile'


class StudentPreference(models.Model):
    """Drives the AI room recommendation scoring."""

    class SleepSchedule(models.TextChoices):
        EARLY = 'early', 'Early sleeper'
        LATE = 'late', 'Late sleeper'

    class StudyHabits(models.TextChoices):
        QUIET = 'quiet', 'Prefers quiet'
        SOCIAL = 'social', 'Prefers social'

    class Level(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'

    student = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='preference')
    budget_min = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    budget_max = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    preferred_location = models.CharField(max_length=100, blank=True)

    sleep_schedule = models.CharField(max_length=10, choices=SleepSchedule.choices)
    cleanliness_level = models.CharField(max_length=10, choices=Level.choices)
    study_habits = models.CharField(max_length=10, choices=StudyHabits.choices)
    noise_tolerance = models.CharField(max_length=10, choices=Level.choices)
    smoking = models.BooleanField(default=False)

    def clean(self):
        super().clean()
        if self.budget_max is not None and self.budget_max <= 0:
            raise ValidationError({'budget_max': 'Budget max must be greater than zero.'})
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValidationError({'budget_min': 'Budget min cannot be greater than budget max.'})

    def __str__(self):
        return f'Preferences for {self.student.username}'
