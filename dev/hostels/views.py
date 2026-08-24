from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from bookings.models import Booking
from bookings.recommender import score_room

from .forms import HostelForm, RoomForm, TermForm
from .models import Hostel, Room, Term


@login_required
def room_list(request):
    term = Term.current()
    rooms = (
        Room.objects.select_related('hostel')
        .exclude(status=Room.Status.MAINTENANCE)
        .order_by('hostel__name', 'room_number')
    )

    hostel_filter = None
    hostel_id = request.GET.get('hostel')
    if hostel_id:
        hostel_filter = get_object_or_404(Hostel, pk=hostel_id)
        rooms = rooms.filter(hostel=hostel_filter)

    if term:
        rooms = rooms.annotate(
            confirmed_count=Count('bookings', filter=Q(bookings__term=term, bookings__status='confirmed'))
        )
        for room in rooms:
            room.available_beds = room.capacity - room.confirmed_count
    else:
        for room in rooms:
            room.available_beds = room.capacity

    is_student = request.user.groups.filter(name='Student').exists()
    preference = getattr(request.user, 'preference', None) if is_student else None
    show_roommate_fit = bool(preference and term)
    if show_roommate_fit:
        for room in rooms:
            room.roommate_fit = score_room(preference, room, term).compatibility

    already_booked = (
        is_student and term is not None
        and request.user.bookings.filter(term=term, status__in=['pending', 'confirmed']).exists()
    )

    return render(request, 'hostels/room_list.html', {
        'rooms': rooms,
        'term': term,
        'is_student': is_student,
        'already_booked': already_booked,
        'show_roommate_fit': show_roommate_fit,
        'hostel_filter': hostel_filter,
    })


@login_required
def hostel_browse(request):
    term = Term.current()
    hostels = Hostel.objects.order_by('name').prefetch_related('rooms')
    for hostel in hostels:
        room_prices = [room.price_per_term for room in hostel.rooms.all()]
        hostel.room_count = len(room_prices)
        hostel.min_price = min(room_prices) if room_prices else None
        hostel.max_price = max(room_prices) if room_prices else None
        if term:
            hostel.confirmed_count = Booking.objects.filter(
                room__hostel=hostel, term=term, status=Booking.Status.CONFIRMED,
            ).count()
        else:
            hostel.confirmed_count = 0

    most_popular_id = None
    with_occupants = [h for h in hostels if h.confirmed_count > 0]
    if with_occupants:
        most_popular_id = max(with_occupants, key=lambda h: h.confirmed_count).id

    return render(request, 'hostels/browse.html', {
        'hostels': hostels, 'term': term, 'most_popular_id': most_popular_id,
    })


@login_required
@permission_required('hostels.change_hostel', raise_exception=True)
def manage_hostels(request):
    hostels = Hostel.objects.order_by('name').prefetch_related('rooms')
    return render(request, 'hostels/manage/hostel_list.html', {'hostels': hostels})


@login_required
@permission_required('hostels.add_hostel', raise_exception=True)
def hostel_create(request):
    if request.method == 'POST':
        form = HostelForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Hostel added.')
            return redirect('hostels:manage_hostels')
    else:
        form = HostelForm()
    return render(request, 'hostels/manage/hostel_form.html', {'form': form, 'title': 'Add Hostel'})


@login_required
@permission_required('hostels.change_hostel', raise_exception=True)
def hostel_edit(request, hostel_id):
    hostel = get_object_or_404(Hostel, pk=hostel_id)
    if request.method == 'POST':
        form = HostelForm(request.POST, request.FILES, instance=hostel)
        if form.is_valid():
            form.save()
            messages.success(request, 'Hostel updated.')
            return redirect('hostels:manage_hostels')
    else:
        form = HostelForm(instance=hostel)
    return render(request, 'hostels/manage/hostel_form.html', {'form': form, 'title': f'Edit {hostel.name}'})


@login_required
@permission_required('hostels.delete_hostel', raise_exception=True)
def hostel_delete(request, hostel_id):
    hostel = get_object_or_404(Hostel, pk=hostel_id)
    if request.method == 'POST':
        name = hostel.name
        hostel.delete()
        messages.success(request, f'{name} and all its rooms have been deleted.')
        return redirect('hostels:manage_hostels')

    room_count = hostel.rooms.count()
    booking_count = hostel.rooms.aggregate(total=Count('bookings'))['total'] or 0
    return render(request, 'hostels/manage/hostel_confirm_delete.html', {
        'hostel': hostel, 'room_count': room_count, 'booking_count': booking_count,
    })


@login_required
@permission_required('hostels.change_room', raise_exception=True)
def manage_rooms(request, hostel_id):
    hostel = get_object_or_404(Hostel, pk=hostel_id)
    rooms = hostel.rooms.order_by('room_number')
    return render(request, 'hostels/manage/room_list.html', {'hostel': hostel, 'rooms': rooms})


@login_required
@permission_required('hostels.add_room', raise_exception=True)
def room_create(request, hostel_id):
    hostel = get_object_or_404(Hostel, pk=hostel_id)
    if request.method == 'POST':
        form = RoomForm(request.POST)
        if form.is_valid():
            room_number = form.cleaned_data['room_number']
            # unique_together isn't checked by the form since 'hostel' isn't a form
            # field (it comes from the URL) - Django excludes any unique_together
            # clause touching a non-form field from its automatic validation.
            if Room.objects.filter(hostel=hostel, room_number=room_number).exists():
                form.add_error('room_number', f'{hostel.name} already has a room numbered "{room_number}".')
            else:
                room = form.save(commit=False)
                room.hostel = hostel
                room.save()
                messages.success(request, f'Room {room.room_number} added to {hostel.name}.')
                return redirect('hostels:manage_rooms', hostel_id=hostel.id)
    else:
        form = RoomForm()
    return render(request, 'hostels/manage/room_form.html', {'form': form, 'hostel': hostel, 'title': f'Add Room to {hostel.name}'})


@login_required
@permission_required('hostels.change_room', raise_exception=True)
def room_edit(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    if request.method == 'POST':
        form = RoomForm(request.POST, instance=room)
        if form.is_valid():
            room_number = form.cleaned_data['room_number']
            duplicate = Room.objects.filter(hostel=room.hostel, room_number=room_number).exclude(pk=room.pk).exists()
            if duplicate:
                form.add_error('room_number', f'{room.hostel.name} already has a room numbered "{room_number}".')
            else:
                form.save()
                messages.success(request, f'Room {room.room_number} updated.')
                return redirect('hostels:manage_rooms', hostel_id=room.hostel_id)
    else:
        form = RoomForm(instance=room)
    return render(request, 'hostels/manage/room_form.html', {'form': form, 'hostel': room.hostel, 'title': f'Edit {room}'})


@login_required
@permission_required('hostels.delete_room', raise_exception=True)
def room_delete(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    hostel_id = room.hostel_id
    if request.method == 'POST':
        room_label = str(room)
        room.delete()
        messages.success(request, f'{room_label} has been deleted.')
        return redirect('hostels:manage_rooms', hostel_id=hostel_id)

    return render(request, 'hostels/manage/room_confirm_delete.html', {
        'room': room, 'booking_count': room.bookings.count(),
    })


@login_required
@permission_required('hostels.change_term', raise_exception=True)
def manage_terms(request):
    terms = Term.objects.order_by('sequence_number')
    return render(request, 'hostels/manage/term_list.html', {'terms': terms, 'current_term': Term.current()})


@login_required
@permission_required('hostels.add_term', raise_exception=True)
def term_create(request):
    if request.method == 'POST':
        form = TermForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Term added.')
            return redirect('hostels:manage_terms')
    else:
        form = TermForm()
    return render(request, 'hostels/manage/term_form.html', {'form': form, 'title': 'Add Term'})


@login_required
@permission_required('hostels.change_term', raise_exception=True)
def term_edit(request, term_id):
    term = get_object_or_404(Term, pk=term_id)
    if request.method == 'POST':
        form = TermForm(request.POST, instance=term)
        if form.is_valid():
            form.save()
            messages.success(request, 'Term updated.')
            return redirect('hostels:manage_terms')
    else:
        form = TermForm(instance=term)
    return render(request, 'hostels/manage/term_form.html', {'form': form, 'title': f'Edit {term.name}'})


@login_required
@permission_required('hostels.delete_term', raise_exception=True)
def term_delete(request, term_id):
    term = get_object_or_404(Term, pk=term_id)
    if request.method == 'POST':
        name = term.name
        term.delete()
        messages.success(request, f'{name} has been deleted.')
        return redirect('hostels:manage_terms')

    return render(request, 'hostels/manage/term_confirm_delete.html', {
        'term': term, 'booking_count': term.bookings.count(), 'recommendation_count': term.recommendations.count(),
    })
