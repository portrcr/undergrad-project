from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentPreference
from bookings.models import Booking, Recommendation
from hostels.models import Hostel, Room, Term


class BookingModelTests(TestCase):
    def test_str_includes_student_room_and_term(self):
        student = User.objects.create_user(username='jane', password='pass12345')
        hostel = Hostel.objects.create(name='Amani Hostel')
        room = Room.objects.create(hostel=hostel, room_number='A01', price_per_term=15000)
        term = Term.objects.create(name='Term 1', start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), sequence_number=1)
        booking = Booking.objects.create(student=student, room=room, term=term)
        self.assertIn('jane', str(booking))
        self.assertIn('A01', str(booking))


class ViewAccessTests(TestCase):
    def setUp(self):
        self.hostel = Hostel.objects.create(name='Amani Hostel')
        Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        self.student = User.objects.create_user(username='jane', password='pass12345')

    def test_room_list_redirects_anonymous_users_to_login(self):
        response = self.client.get(reverse('hostels:room_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_room_list_shows_available_rooms_when_logged_in(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('hostels:room_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A01')

class RequestBookingTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.hostel = Hostel.objects.create(name='Amani Hostel')
        self.room = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=2, price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.create(name='Student'))
        self.staff = User.objects.create_user(username='steve', password='pass12345')

    def request_url(self, room=None):
        return reverse('bookings:request_booking', args=[(room or self.room).id])

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.post(self.request_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_get_is_not_allowed(self):
        self.client.force_login(self.student)
        response = self.client.get(self.request_url())
        self.assertEqual(response.status_code, 405)

    def test_student_can_request_a_room(self):
        self.client.force_login(self.student)
        response = self.client.post(self.request_url())
        self.assertRedirects(response, reverse('profile'))
        booking = Booking.objects.get(student=self.student, room=self.room, term=self.term)
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_non_student_cannot_request_a_room(self):
        self.client.force_login(self.staff)
        self.client.post(self.request_url())
        self.assertFalse(Booking.objects.filter(student=self.staff).exists())

    def test_student_cannot_have_two_active_requests_in_the_same_term(self):
        other_room = Room.objects.create(hostel=self.hostel, room_number='A02', capacity=2, price_per_term=15000)
        self.client.force_login(self.student)
        self.client.post(self.request_url())
        self.client.post(self.request_url(other_room))
        self.assertEqual(Booking.objects.filter(student=self.student).count(), 1)

    def test_cannot_request_a_full_room(self):
        self.room.capacity = 1
        self.room.save()
        Booking.objects.create(
            student=User.objects.create_user(username='mary', password='pass12345'),
            room=self.room, term=self.term, status=Booking.Status.CONFIRMED,
        )
        self.client.force_login(self.student)
        self.client.post(self.request_url())
        self.assertFalse(Booking.objects.filter(student=self.student).exists())


class CancelBookingTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        hostel = Hostel.objects.create(name='Amani Hostel')
        self.room = Room.objects.create(hostel=hostel, room_number='A01', price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.other_student = User.objects.create_user(username='john', password='pass12345')

    def test_student_can_cancel_own_pending_booking(self):
        booking = Booking.objects.create(student=self.student, room=self.room, term=self.term, status=Booking.Status.PENDING)
        self.client.force_login(self.student)
        self.client.post(reverse('bookings:cancel_booking', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_cannot_cancel_a_confirmed_booking(self):
        booking = Booking.objects.create(student=self.student, room=self.room, term=self.term, status=Booking.Status.CONFIRMED)
        self.client.force_login(self.student)
        self.client.post(reverse('bookings:cancel_booking', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_cannot_cancel_another_students_booking(self):
        booking = Booking.objects.create(student=self.other_student, room=self.room, term=self.term, status=Booking.Status.PENDING)
        self.client.force_login(self.student)
        response = self.client.post(reverse('bookings:cancel_booking', args=[booking.id]))
        self.assertEqual(response.status_code, 404)


class StaffApprovalTests(TestCase):
    def setUp(self):
        call_command('setup_roles')
        today = timezone.now().date()
        self.hostel = Hostel.objects.create(name='Amani Hostel')
        self.room = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=1, price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.staff = User.objects.create_user(username='steve', password='pass12345')
        self.staff.groups.add(Group.objects.get(name='Staff'))
        self.booking = Booking.objects.create(student=self.student, room=self.room, term=self.term, status=Booking.Status.PENDING)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('bookings:pending_bookings'))
        self.assertEqual(response.status_code, 302)

    def test_student_cannot_view_pending_requests(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('bookings:pending_bookings'))
        self.assertEqual(response.status_code, 403)

    def test_staff_sees_pending_bookings(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('bookings:pending_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jane')

    def test_staff_can_approve_a_pending_booking(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('bookings:approve_booking', args=[self.booking.id]))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)
        self.assertIsNotNone(self.booking.date_resolved)

    def test_staff_can_reject_a_pending_booking(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('bookings:reject_booking', args=[self.booking.id]))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.REJECTED)

    def test_cannot_approve_into_a_room_that_filled_up_meanwhile(self):
        other_student = User.objects.create_user(username='mary', password='pass12345')
        Booking.objects.create(student=other_student, room=self.room, term=self.term, status=Booking.Status.CONFIRMED)

        self.client.force_login(self.staff)
        self.client.post(reverse('bookings:approve_booking', args=[self.booking.id]))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

    def test_student_cannot_approve_via_direct_post(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse('bookings:approve_booking', args=[self.booking.id]))
        self.assertEqual(response.status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

    def test_cannot_re_approve_an_already_resolved_booking(self):
        self.booking.status = Booking.Status.CONFIRMED
        self.booking.save()
        self.client.force_login(self.staff)
        response = self.client.post(reverse('bookings:approve_booking', args=[self.booking.id]))
        self.assertEqual(response.status_code, 404)


class RecommendationsViewTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.hostel = Hostel.objects.create(name='Amani Hostel', location='Block A')
        self.room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.create(name='Student'))
        self.non_student = User.objects.create_user(username='steve', password='pass12345')

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('bookings:recommendations'))
        self.assertEqual(response.status_code, 302)

    def test_non_student_is_redirected_home(self):
        self.client.force_login(self.non_student)
        response = self.client.get(reverse('bookings:recommendations'))
        self.assertRedirects(response, reverse('home'))

    def test_student_without_preferences_is_sent_to_set_them(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('bookings:recommendations'))
        self.assertRedirects(response, reverse('edit_preferences'))

    def test_student_with_preferences_sees_ranked_rooms_and_they_get_logged(self):
        StudentPreference.objects.create(
            student=self.student, budget_min=10000, budget_max=20000, preferred_location='Block A',
            sleep_schedule=StudentPreference.SleepSchedule.EARLY,
            cleanliness_level=StudentPreference.Level.MEDIUM,
            study_habits=StudentPreference.StudyHabits.QUIET,
            noise_tolerance=StudentPreference.Level.MEDIUM,
        )
        self.client.force_login(self.student)
        response = self.client.get(reverse('bookings:recommendations'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A01')
        self.assertTrue(Recommendation.objects.filter(student=self.student, room=self.room, term=self.term).exists())


class RecommendationAcceptanceTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.hostel = Hostel.objects.create(name='Amani Hostel')
        self.room = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=2, price_per_term=15000)
        self.other_room = Room.objects.create(hostel=self.hostel, room_number='A02', capacity=2, price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.create(name='Student'))

    def test_requesting_a_recommended_room_marks_it_accepted(self):
        Recommendation.objects.create(student=self.student, room=self.room, term=self.term, score=0.9)
        Recommendation.objects.create(student=self.student, room=self.other_room, term=self.term, score=0.5)

        self.client.force_login(self.student)
        self.client.post(reverse('bookings:request_booking', args=[self.room.id]))

        accepted = Recommendation.objects.get(student=self.student, room=self.room, term=self.term)
        declined = Recommendation.objects.get(student=self.student, room=self.other_room, term=self.term)
        self.assertTrue(accepted.was_accepted)
        self.assertFalse(declined.was_accepted)
