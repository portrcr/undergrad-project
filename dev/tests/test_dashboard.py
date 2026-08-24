from datetime import timedelta

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking, Recommendation
from hostels.models import Hostel, Room, Term


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='steve', password='pass12345')
        self.staff.user_permissions.add(*Permission.objects.filter(codename='change_booking'))
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.create(name='Student'))

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('bookings:dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_student_cannot_view_dashboard(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('bookings:dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_dashboard(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('bookings:dashboard'))
        self.assertEqual(response.status_code, 200)


class DashboardStatsTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='steve', password='pass12345')
        self.staff.user_permissions.add(*Permission.objects.filter(codename='change_booking'))
        self.client.force_login(self.staff)

        today = timezone.now().date()
        self.hostel = Hostel.objects.create(name='Amani Hostel')
        self.full_room = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=1, price_per_term=15000)
        self.open_room = Room.objects.create(hostel=self.hostel, room_number='A02', capacity=2, price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )

    def make_student(self, suffix):
        return User.objects.create_user(username=f'student{suffix}', password='pass12345')

    def test_pending_count_reflects_all_pending_bookings(self):
        Booking.objects.create(student=self.make_student(1), room=self.open_room, term=self.term, status=Booking.Status.PENDING)
        Booking.objects.create(student=self.make_student(2), room=self.open_room, term=self.term, status=Booking.Status.PENDING)
        Booking.objects.create(student=self.make_student(3), room=self.open_room, term=self.term, status=Booking.Status.CONFIRMED)

        response = self.client.get(reverse('bookings:dashboard'))
        self.assertEqual(response.context['pending_count'], 2)

    def test_room_availability_counts_full_rooms_correctly(self):
        Booking.objects.create(student=self.make_student(1), room=self.full_room, term=self.term, status=Booking.Status.CONFIRMED)

        response = self.client.get(reverse('bookings:dashboard'))
        self.assertEqual(response.context['total_rooms'], 2)
        self.assertEqual(response.context['available_rooms'], 1)

    def test_confirmed_bookings_only_counts_current_term(self):
        other_term = Term.objects.create(
            name='Older Term', start_date=timezone.now().date() - timedelta(days=200),
            end_date=timezone.now().date() - timedelta(days=100), sequence_number=0,
        )
        Booking.objects.create(student=self.make_student(1), room=self.open_room, term=self.term, status=Booking.Status.CONFIRMED)
        Booking.objects.create(student=self.make_student(2), room=self.open_room, term=other_term, status=Booking.Status.CONFIRMED)

        response = self.client.get(reverse('bookings:dashboard'))
        self.assertEqual(response.context['confirmed_this_term'], 1)

    def test_acceptance_rate_is_none_without_data(self):
        response = self.client.get(reverse('bookings:dashboard'))
        self.assertIsNone(response.context['acceptance_rate'])

    def test_acceptance_rate_reflects_recommendation_outcomes(self):
        student = self.make_student(1)
        Recommendation.objects.create(student=student, room=self.open_room, term=self.term, score=0.9, was_accepted=True)
        Recommendation.objects.create(student=student, room=self.full_room, term=self.term, score=0.5, was_accepted=False)

        response = self.client.get(reverse('bookings:dashboard'))
        self.assertEqual(response.context['acceptance_rate'], 50.0)

    def test_handles_no_current_term_without_crashing(self):
        Term.objects.all().delete()
        response = self.client.get(reverse('bookings:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['term'])
        self.assertEqual(response.context['confirmed_this_term'], 0)
