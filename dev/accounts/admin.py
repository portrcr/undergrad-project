from django.contrib import admin

from .models import Profile, StudentPreference


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone', 'year_of_study')
    search_fields = ('user__username', 'user__email')


@admin.register(StudentPreference)
class StudentPreferenceAdmin(admin.ModelAdmin):
    list_display = ('student', 'budget_min', 'budget_max', 'preferred_location')
    search_fields = ('student__username',)
