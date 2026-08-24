from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from hostels.models import Hostel, Room, Term


class HostelBrowseViewTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.hostel_a = Hostel.objects.create(name='Amani Hostel', location='Block A')
        self.hostel_b = Hostel.objects.create(name='Uhuru Hostel', location='Block B')
        self.room_a1 = Room.objects.create(hostel=self.hostel_a, room_number='A01', capacity=2, price_per_term=15000)
        self.room_a2 = Room.objects.create(hostel=self.hostel_a, room_number='A02', capacity=1, price_per_term=20000)
        self.room_b1 = Room.objects.create(hostel=self.hostel_b, room_number='B01', capacity=2, price_per_term=12000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('hostels:hostel_browse'))
        self.assertEqual(response.status_code, 302)

    def test_shows_room_count_and_price_range_per_hostel(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('hostels:hostel_browse'))
        hostels_by_name = {h.name: h for h in response.context['hostels']}
        self.assertEqual(hostels_by_name['Amani Hostel'].room_count, 2)
        self.assertEqual(hostels_by_name['Amani Hostel'].min_price, 15000)
        self.assertEqual(hostels_by_name['Amani Hostel'].max_price, 20000)

    def test_hostel_with_no_rooms_has_no_price(self):
        Hostel.objects.create(name='Baraka Hostel')
        self.client.force_login(self.student)
        response = self.client.get(reverse('hostels:hostel_browse'))
        baraka = next(h for h in response.context['hostels'] if h.name == 'Baraka Hostel')
        self.assertIsNone(baraka.min_price)
        self.assertEqual(baraka.room_count, 0)

    def test_most_popular_hostel_is_the_one_with_most_confirmed_bookings(self):
        occupant = User.objects.create_user(username='mary', password='pass12345')
        Booking.objects.create(student=occupant, room=self.room_a1, term=self.term, status=Booking.Status.CONFIRMED)

        self.client.force_login(self.student)
        response = self.client.get(reverse('hostels:hostel_browse'))
        self.assertEqual(response.context['most_popular_id'], self.hostel_a.id)

    def test_no_most_popular_when_nobody_is_confirmed_anywhere(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('hostels:hostel_browse'))
        self.assertIsNone(response.context['most_popular_id'])


class RoomListHostelFilterTests(TestCase):
    def setUp(self):
        self.hostel_a = Hostel.objects.create(name='Amani Hostel')
        self.hostel_b = Hostel.objects.create(name='Uhuru Hostel')
        Room.objects.create(hostel=self.hostel_a, room_number='A01', price_per_term=15000)
        Room.objects.create(hostel=self.hostel_b, room_number='B01', price_per_term=12000)
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.client.force_login(self.student)

    def test_no_filter_shows_all_rooms(self):
        response = self.client.get(reverse('hostels:room_list'))
        self.assertContains(response, 'A01')
        self.assertContains(response, 'B01')

    def test_filter_by_hostel_shows_only_that_hostels_rooms(self):
        response = self.client.get(reverse('hostels:room_list'), {'hostel': self.hostel_a.id})
        self.assertContains(response, 'A01')
        self.assertNotContains(response, 'B01')
        self.assertEqual(response.context['hostel_filter'], self.hostel_a)

    def test_invalid_hostel_id_returns_404(self):
        response = self.client.get(reverse('hostels:room_list'), {'hostel': 999})
        self.assertEqual(response.status_code, 404)
