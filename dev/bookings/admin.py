from django.contrib import admin

from .models import Booking, Notification, Recommendation


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('student', 'room', 'term', 'status', 'date_requested')
    list_filter = ('status', 'term')
    search_fields = ('student__username', 'room__room_number')


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ('student', 'room', 'term', 'score', 'was_accepted', 'created_at')
    list_filter = ('term', 'was_accepted')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'sender', 'message', 'is_read', 'created_at')
    list_filter = ('is_read',)
    search_fields = ('recipient__username', 'sender__username', 'message')
