from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Min
from django.shortcuts import redirect, render

from bookings.models import Booking
from hostels.models import Hostel, Room, Term

from .forms import ProfileForm, StudentPreferenceForm
from .models import StudentPreference

PACKAGE_ICONS = {1: '🛏️', 2: '🛏️🛏️', 3: '🛏️🛏️🛏️'}


def _package_label(capacity):
    if capacity == 1:
        return 'Single Room'
    if capacity == 2:
        return 'Double Room'
    if capacity == 3:
        return 'Triple Room'
    return f'{capacity}-Bed Room'


def home(request):
    term = Term.current()
    stats = {
        'hostel_count': Hostel.objects.count(),
        'room_count': Room.objects.count(),
        'housed_count': Booking.objects.filter(term=term, status=Booking.Status.CONFIRMED).count() if term else 0,
    }

    packages = (
        Room.objects.exclude(status=Room.Status.MAINTENANCE)
        .values('capacity')
        .annotate(min_price=Min('price_per_term'), room_count=Count('id'))
        .order_by('capacity')
    )
    for package in packages:
        package['label'] = _package_label(package['capacity'])
        package['icon'] = PACKAGE_ICONS.get(package['capacity'], '🛌')

    return render(request, 'home.html', {'stats': stats, 'packages': packages})


@login_required
def profile(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('profile')
    else:
        form = ProfileForm(instance=request.user.profile)

    context = {'form': form}
    if request.user.groups.filter(name='Student').exists():
        context['bookings'] = (
            Booking.objects.select_related('room', 'room__hostel', 'term').filter(student=request.user)
        )

    return render(request, 'accounts/profile.html', context)


@login_required
def edit_preferences(request):
    if not request.user.groups.filter(name='Student').exists():
        messages.error(request, 'Only students have room preferences.')
        return redirect('home')

    instance = getattr(request.user, 'preference', None) or StudentPreference(student=request.user)

    if request.method == 'POST':
        form = StudentPreferenceForm(request.POST, instance=instance)
        if form.is_valid():
            preference = form.save(commit=False)
            preference.student = request.user
            preference.save()
            messages.success(request, 'Preferences saved.')
            return redirect('bookings:recommendations')
    else:
        form = StudentPreferenceForm(instance=instance)

    return render(request, 'accounts/preferences_form.html', {'form': form})
