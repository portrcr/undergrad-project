from django.urls import path

from . import views

app_name = 'bookings'

urlpatterns = [
    path('recommendations/', views.recommendations, name='recommendations'),
    path('notifications/', views.notification_list, name='notifications'),
    path('rooms/<int:room_id>/request/', views.request_booking, name='request_booking'),
    path('<int:booking_id>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('staff/dashboard/', views.dashboard, name='dashboard'),
    path('staff/pending/', views.pending_bookings, name='pending_bookings'),
    path('staff/demand-forecast/', views.demand_forecast, name='demand_forecast'),
    path('staff/recommendation-insights/', views.recommendation_insights, name='recommendation_insights'),
    path('staff/<int:booking_id>/message/', views.message_student, name='message_student'),
    path('staff/hostels/', views.message_hostel_list, name='message_hostel_list'),
    path('staff/hostels/<int:hostel_id>/message/', views.message_hostel, name='message_hostel'),
    path('staff/<int:booking_id>/approve/', views.approve_booking, name='approve_booking'),
    path('staff/<int:booking_id>/reject/', views.reject_booking, name='reject_booking'),
]
