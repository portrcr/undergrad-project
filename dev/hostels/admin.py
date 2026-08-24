from django.contrib import admin

from .models import Hostel, Room, Term


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'sequence_number')


@admin.register(Hostel)
class HostelAdmin(admin.ModelAdmin):
    list_display = ('name', 'location')
    search_fields = ('name', 'location')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('hostel', 'room_number', 'capacity', 'price_per_term', 'status')
    list_filter = ('hostel', 'status')
    search_fields = ('room_number',)
