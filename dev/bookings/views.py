from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from hostels.models import Hostel, Room, Term

from .analytics import recommendation_effectiveness
from .demand import forecast_all_hostels
from .forms import MessageStudentForm
from .models import Booking, Notification, Recommendation
from .recommender import record_recommendations, recommend_rooms


@login_required
@require_POST
def request_booking(request, room_id):
    if not request.user.groups.filter(name='Student').exists():
        messages.error(request, 'Only students can request room bookings.')
        return redirect('hostels:room_list')

    room = get_object_or_404(Room, pk=room_id)
    term = Term.current()
    if term is None:
        messages.error(request, 'There is no term open for booking right now.')
        return redirect('hostels:room_list')

    active_statuses = [Booking.Status.PENDING, Booking.Status.CONFIRMED]
    if Booking.objects.filter(student=request.user, term=term, status__in=active_statuses).exists():
        messages.error(request, 'You already have an active booking request for this term.')
        return redirect('profile')

    confirmed_count = Booking.objects.filter(room=room, term=term, status=Booking.Status.CONFIRMED).count()
    if confirmed_count >= room.capacity:
        messages.error(request, f'{room} is already full for {term}.')
        return redirect('hostels:room_list')

    Booking.objects.create(student=request.user, room=room, term=term, status=Booking.Status.PENDING)

    # Resolve any recommendations shown for this term: the chosen room was accepted,
    # any other unresolved ones the student saw but didn't take were effectively declined.
    unresolved = Recommendation.objects.filter(student=request.user, term=term, was_accepted__isnull=True)
    unresolved.filter(room=room).update(was_accepted=True)
    unresolved.exclude(room=room).update(was_accepted=False)

    messages.success(request, f'Booking request submitted for {room}. Staff will review it shortly.')
    return redirect('profile')


@login_required
@require_POST
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, student=request.user)
    if booking.status != Booking.Status.PENDING:
        messages.error(request, 'Only pending requests can be cancelled.')
    else:
        booking.status = Booking.Status.CANCELLED
        booking.date_resolved = timezone.now()
        booking.save()
        messages.success(request, 'Booking request cancelled.')
    return redirect('profile')


@login_required
def recommendations(request):
    if not request.user.groups.filter(name='Student').exists():
        messages.error(request, 'Recommendations are only available to students.')
        return redirect('home')

    if not hasattr(request.user, 'preference'):
        messages.info(request, 'Set your preferences first so we can recommend rooms for you.')
        return redirect('edit_preferences')

    term = Term.current()
    ranked = recommend_rooms(request.user, term, limit=5)
    record_recommendations(request.user, term, ranked)

    already_booked = term is not None and Booking.objects.filter(
        student=request.user, term=term, status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
    ).exists()

    return render(request, 'bookings/recommendations.html', {
        'ranked': ranked, 'term': term, 'already_booked': already_booked,
    })


@login_required
@permission_required('bookings.change_booking', raise_exception=True)
def dashboard(request):
    term = Term.current()
    pending_count = Booking.objects.filter(status=Booking.Status.PENDING).count()

    rooms = Room.objects.exclude(status=Room.Status.MAINTENANCE)
    total_rooms = rooms.count()
    full_rooms = 0
    confirmed_this_term = 0
    if term:
        rooms = rooms.annotate(
            confirmed_count=Count('bookings', filter=Q(bookings__term=term, bookings__status='confirmed'))
        )
        full_rooms = sum(1 for room in rooms if room.confirmed_count >= room.capacity)
        confirmed_this_term = Booking.objects.filter(term=term, status=Booking.Status.CONFIRMED).count()

    forecasts = forecast_all_hostels()
    rising_count = sum(1 for forecast in forecasts if forecast['trend'] == 'rising')

    stats = recommendation_effectiveness()

    return render(request, 'bookings/dashboard.html', {
        'term': term,
        'pending_count': pending_count,
        'total_rooms': total_rooms,
        'available_rooms': total_rooms - full_rooms,
        'confirmed_this_term': confirmed_this_term,
        'forecasts_count': len(forecasts),
        'rising_count': rising_count,
        'acceptance_rate': stats['acceptance_rate'],
    })


@login_required
@permission_required('bookings.change_booking', raise_exception=True)
def demand_forecast(request):
    forecasts = forecast_all_hostels()
    return render(request, 'bookings/demand_forecast.html', {'forecasts': forecasts})


@login_required
@permission_required('bookings.change_booking', raise_exception=True)
def recommendation_insights(request):
    stats = recommendation_effectiveness()
    return render(request, 'bookings/recommendation_insights.html', {'stats': stats})


@login_required
@permission_required('bookings.change_booking', raise_exception=True)
def pending_bookings(request):
    bookings = (
        Booking.objects.select_related('student', 'room', 'room__hostel', 'term')
        .filter(status=Booking.Status.PENDING)
        .order_by('date_requested')
    )
    return render(request, 'bookings/pending_bookings.html', {'bookings': bookings})


@login_required
@permission_required('bookings.change_booking', raise_exception=True)
def message_student(request, booking_id):
    booking = get_object_or_404(Booking.objects.select_related('student', 'room', 'room__hostel', 'term'), pk=booking_id)
    if request.method == 'POST':
        form = MessageStudentForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.recipient = booking.student
            note.sender = request.user
            note.booking = booking
            note.save()
            messages.success(request, f'Message sent to {booking.student.username}.')
            return redirect('bookings:pending_bookings')
    else:
        form = MessageStudentForm()
    return render(request, 'bookings/message_student.html', {'form': form, 'booking': booking})


@login_required
@permission_required('bookings.change_booking', raise_exception=True)
def message_hostel_list(request):
    term = Term.current()
    hostels = list(Hostel.objects.order_by('name'))
    for hostel in hostels:
        hostel.occupant_count = (
            Booking.objects.filter(room__hostel=hostel, term=term, status=Booking.Status.CONFIRMED).count()
            if term else 0
        )
    return render(request, 'bookings/message_hostel_list.html', {'hostels': hostels, 'term': term})


@login_required
@permission_required('bookings.change_booking', raise_exception=True)
def message_hostel(request, hostel_id):
    hostel = get_object_or_404(Hostel, pk=hostel_id)
    term = Term.current()
    occupant_bookings = (
        Booking.objects.filter(room__hostel=hostel, term=term, status=Booking.Status.CONFIRMED).select_related('student')
        if term else Booking.objects.none()
    )
    occupant_count = occupant_bookings.count()

    if request.method == 'POST':
        form = MessageStudentForm(request.POST)
        if form.is_valid():
            if occupant_count == 0:
                messages.error(request, f'{hostel.name} has no confirmed students this term to message.')
            else:
                message_text = form.cleaned_data['message']
                Notification.objects.bulk_create([
                    Notification(recipient=booking.student, sender=request.user, booking=booking, message=message_text)
                    for booking in occupant_bookings
                ])
                messages.success(request, f'Message sent to {occupant_count} student{"s" if occupant_count != 1 else ""} in {hostel.name}.')
                return redirect('bookings:message_hostel_list')
    else:
        form = MessageStudentForm()

    return render(request, 'bookings/message_hostel.html', {
        'form': form, 'hostel': hostel, 'term': term, 'occupant_count': occupant_count,
    })


@login_required
@permission_required('bookings.change_booking', raise_exception=True)
@require_POST
def approve_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, status=Booking.Status.PENDING)

    confirmed_count = Booking.objects.filter(
        room=booking.room, term=booking.term, status=Booking.Status.CONFIRMED,
    ).count()
    if confirmed_count >= booking.room.capacity:
        messages.error(request, f'{booking.room} is already full for {booking.term} - cannot approve.')
    else:
        booking.status = Booking.Status.CONFIRMED
        booking.date_resolved = timezone.now()
        booking.save()
        Notification.objects.create(
            recipient=booking.student, booking=booking,
            message=f'Your booking request for {booking.room} ({booking.term}) was confirmed.',
        )
        messages.success(request, f'Approved {booking.student.username} for {booking.room}.')
    return redirect('bookings:pending_bookings')


@login_required
@permission_required('bookings.change_booking', raise_exception=True)
@require_POST
def reject_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, status=Booking.Status.PENDING)
    booking.status = Booking.Status.REJECTED
    booking.date_resolved = timezone.now()
    booking.save()
    Notification.objects.create(
        recipient=booking.student, booking=booking,
        message=f'Your booking request for {booking.room} ({booking.term}) was rejected.',
    )
    messages.success(request, f'Rejected {booking.student.username}\'s request for {booking.room}.')
    return redirect('bookings:pending_bookings')


@login_required
def notification_list(request):
    notifications = list(request.user.notifications.all())
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'bookings/notifications.html', {'notifications': notifications})
