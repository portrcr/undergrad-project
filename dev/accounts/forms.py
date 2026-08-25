from django import forms

from .models import Profile, StudentPreference


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['phone', 'year_of_study']


class StudentPreferenceForm(forms.ModelForm):
    class Meta:
        model = StudentPreference
        fields = [
            'budget_min', 'budget_max', 'preferred_location',
            'sleep_schedule', 'cleanliness_level', 'study_habits', 'noise_tolerance', 'smoking',
        ]
