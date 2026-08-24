from collections import Counter

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from bookings.models import Booking
from hostels.models import Hostel, Room, Term


class SeedDemoDataTests(TestCase):
    def setUp(self):
        call_command('seed_demo_data')

    def test_creates_expected_reference_data(self):
        self.assertEqual(Term.objects.count(), 5)
        self.assertEqual(Hostel.objects.count(), 3)
        self.assertEqual(Room.objects.count(), 18)
        self.assertEqual(User.objects.filter(username__startswith='student').count(), 20)

    def test_never_books_more_students_into_a_room_than_it_holds(self):
        counts = Counter(
            Booking.objects.filter(status=Booking.Status.CONFIRMED).values_list('room_id', 'term_id')
        )
        rooms_by_id = {room.id: room for room in Room.objects.all()}
        for (room_id, term_id), confirmed_count in counts.items():
            self.assertLessEqual(confirmed_count, rooms_by_id[room_id].capacity)

    def test_booking_demand_rises_across_the_first_four_terms(self):
        terms = list(Term.objects.order_by('sequence_number'))
        counts = [Booking.objects.filter(term=term).count() for term in terms[:4]]
        self.assertEqual(counts, sorted(counts))
        self.assertLess(counts[0], counts[-1])

    def test_rerunning_does_not_duplicate_reference_data(self):
        call_command('seed_demo_data')
        self.assertEqual(Term.objects.count(), 5)
        self.assertEqual(Hostel.objects.count(), 3)
        self.assertEqual(Room.objects.count(), 18)
        self.assertEqual(User.objects.filter(username__startswith='student').count(), 20)

    def test_reset_removes_demo_data(self):
        call_command('seed_demo_data', reset=True)
        call_command('seed_demo_data', reset=True)
        self.assertEqual(Term.objects.count(), 5)
        self.assertEqual(Hostel.objects.count(), 3)
