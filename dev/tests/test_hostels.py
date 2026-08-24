from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentPreference
from bookings.models import Booking
from hostels.models import Hostel, Room, Term


class HostelAndRoomTests(TestCase):
    def setUp(self):
        self.hostel = Hostel.objects.create(name='Amani Hostel', location='Block A')

    def test_hostel_str_is_its_name(self):
        self.assertEqual(str(self.hostel), 'Amani Hostel')

    def test_room_str_includes_hostel_and_room_number(self):
        room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        self.assertEqual(str(room), 'Amani Hostel - A01')

    def test_room_defaults_to_available_status(self):
        room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        self.assertEqual(room.status, Room.Status.AVAILABLE)

    def test_room_number_must_be_unique_within_a_hostel(self):
        Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=18000)

    def test_rejects_zero_capacity(self):
        room = Room(hostel=self.hostel, room_number='A01', capacity=0, price_per_term=15000)
        with self.assertRaises(ValidationError):
            room.full_clean()

    def test_rejects_negative_price(self):
        room = Room(hostel=self.hostel, room_number='A01', price_per_term=-100)
        with self.assertRaises(ValidationError):
            room.full_clean()


class TermTests(TestCase):
    def test_terms_are_ordered_by_sequence_number(self):
        Term.objects.create(name='Term 2', start_date=date(2026, 5, 1), end_date=date(2026, 8, 1), sequence_number=2)
        Term.objects.create(name='Term 1', start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), sequence_number=1)
        self.assertEqual(list(Term.objects.values_list('name', flat=True)), ['Term 1', 'Term 2'])

    def test_current_returns_the_term_covering_today(self):
        today = timezone.now().date()
        past = Term.objects.create(
            name='Past', start_date=today - timedelta(days=100), end_date=today - timedelta(days=10), sequence_number=1,
        )
        current = Term.objects.create(
            name='Current', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=2,
        )
        self.assertEqual(Term.current(), current)
        self.assertNotEqual(Term.current(), past)

    def test_current_falls_back_to_most_recent_term_when_none_covers_today(self):
        today = timezone.now().date()
        Term.objects.create(
            name='Older', start_date=today - timedelta(days=200), end_date=today - timedelta(days=150), sequence_number=1,
        )
        latest = Term.objects.create(
            name='Newer', start_date=today - timedelta(days=100), end_date=today - timedelta(days=50), sequence_number=2,
        )
        self.assertEqual(Term.current(), latest)

    def test_current_returns_none_when_no_terms_exist(self):
        self.assertIsNone(Term.current())

    def test_rejects_end_date_before_start_date(self):
        term = Term(name='Broken', start_date=date(2026, 5, 1), end_date=date(2026, 1, 1), sequence_number=1)
        with self.assertRaises(ValidationError):
            term.full_clean()

    def test_rejects_end_date_equal_to_start_date(self):
        term = Term(name='Zero-length', start_date=date(2026, 5, 1), end_date=date(2026, 5, 1), sequence_number=1)
        with self.assertRaises(ValidationError):
            term.full_clean()


class RoommateFitDisplayTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.hostel = Hostel.objects.create(name='Amani Hostel', location='Block A')
        self.room = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=2, price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.create(name='Student'))

    def make_preference(self, user):
        return StudentPreference.objects.create(
            student=user, budget_min=10000, budget_max=20000, preferred_location='Block A',
            sleep_schedule=StudentPreference.SleepSchedule.EARLY,
            cleanliness_level=StudentPreference.Level.MEDIUM,
            study_habits=StudentPreference.StudyHabits.QUIET,
            noise_tolerance=StudentPreference.Level.MEDIUM,
        )

    def test_hidden_for_student_without_preferences(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('hostels:room_list'))
        self.assertFalse(response.context['show_roommate_fit'])

    def test_shown_for_student_with_preferences(self):
        self.make_preference(self.student)
        self.client.force_login(self.student)
        response = self.client.get(reverse('hostels:room_list'))
        self.assertTrue(response.context['show_roommate_fit'])
        self.assertContains(response, 'Roommate Fit')

    def test_empty_room_shows_as_new_room_not_a_percentage(self):
        self.make_preference(self.student)
        self.client.force_login(self.student)
        response = self.client.get(reverse('hostels:room_list'))
        room = next(r for r in response.context['rooms'] if r.id == self.room.id)
        self.assertIsNone(room.roommate_fit)
        self.assertContains(response, 'New room')

    def test_room_with_occupant_shows_a_fit_percentage(self):
        self.make_preference(self.student)
        occupant = User.objects.create_user(username='mary', password='pass12345')
        self.make_preference(occupant)
        Booking.objects.create(student=occupant, room=self.room, term=self.term, status=Booking.Status.CONFIRMED)

        self.client.force_login(self.student)
        response = self.client.get(reverse('hostels:room_list'))
        room = next(r for r in response.context['rooms'] if r.id == self.room.id)
        self.assertIsNotNone(room.roommate_fit)

    def test_hidden_for_non_students(self):
        staff = User.objects.create_user(username='steve', password='pass12345')
        self.client.force_login(staff)
        response = self.client.get(reverse('hostels:room_list'))
        self.assertFalse(response.context['show_roommate_fit'])
