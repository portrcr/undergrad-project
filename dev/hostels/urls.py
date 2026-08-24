from django.urls import path

from . import views

app_name = 'hostels'

urlpatterns = [
    path('', views.room_list, name='room_list'),
    path('browse/', views.hostel_browse, name='hostel_browse'),
    path('manage/', views.manage_hostels, name='manage_hostels'),
    path('manage/add/', views.hostel_create, name='hostel_create'),
    path('manage/<int:hostel_id>/edit/', views.hostel_edit, name='hostel_edit'),
    path('manage/<int:hostel_id>/delete/', views.hostel_delete, name='hostel_delete'),
    path('manage/<int:hostel_id>/rooms/', views.manage_rooms, name='manage_rooms'),
    path('manage/<int:hostel_id>/rooms/add/', views.room_create, name='room_create'),
    path('manage/rooms/<int:room_id>/edit/', views.room_edit, name='room_edit'),
    path('manage/rooms/<int:room_id>/delete/', views.room_delete, name='room_delete'),
    path('manage/terms/', views.manage_terms, name='manage_terms'),
    path('manage/terms/add/', views.term_create, name='term_create'),
    path('manage/terms/<int:term_id>/edit/', views.term_edit, name='term_edit'),
    path('manage/terms/<int:term_id>/delete/', views.term_delete, name='term_delete'),
]
