from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.context_processors import notifications as notifications_context
from bookings.models import Booking, Notification
from hostels.models import Hostel, Room, Term


class NotificationModelTests(TestCase):
    def test_str_includes_recipient_and_message(self):
        user = User.objects.create_user(username='jane', password='pass12345')
        note = Notification.objects.create(recipient=user, message='Your booking was confirmed.')
        self.assertIn('jane', str(note))
        self.assertIn('confirmed', str(note))

    def test_defaults_to_unread(self):
        user = User.objects.create_user(username='jane', password='pass12345')
        note = Notification.objects.create(recipient=user, message='Hi')
        self.assertFalse(note.is_read)


class NotificationsCreatedOnBookingResolutionTests(TestCase):
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

    def test_approving_creates_a_notification_for_the_student(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('bookings:approve_booking', args=[self.booking.id]))

        note = Notification.objects.get(recipient=self.student, booking=self.booking)
        self.assertIn('confirmed', note.message)
        self.assertFalse(note.is_read)

    def test_rejecting_creates_a_notification_for_the_student(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('bookings:reject_booking', args=[self.booking.id]))

        note = Notification.objects.get(recipient=self.student, booking=self.booking)
        self.assertIn('rejected', note.message)

    def test_failed_approval_does_not_create_a_notification(self):
        other_student = User.objects.create_user(username='mary', password='pass12345')
        Booking.objects.create(student=other_student, room=self.room, term=self.term, status=Booking.Status.CONFIRMED)

        self.client.force_login(self.staff)
        self.client.post(reverse('bookings:approve_booking', args=[self.booking.id]))

        self.assertFalse(Notification.objects.filter(booking=self.booking).exists())


class NotificationListViewTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.other_student = User.objects.create_user(username='mary', password='pass12345')

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('bookings:notifications'))
        self.assertEqual(response.status_code, 302)

    def test_shows_only_the_logged_in_users_notifications(self):
        Notification.objects.create(recipient=self.student, message='For jane')
        Notification.objects.create(recipient=self.other_student, message='For mary')

        self.client.force_login(self.student)
        response = self.client.get(reverse('bookings:notifications'))
        self.assertEqual(len(response.context['notifications']), 1)
        self.assertEqual(response.context['notifications'][0].message, 'For jane')

    def test_unread_notifications_show_as_unread_on_the_page_that_reads_them(self):
        Notification.objects.create(recipient=self.student, message='Hello')
        self.client.force_login(self.student)
        response = self.client.get(reverse('bookings:notifications'))
        self.assertFalse(response.context['notifications'][0].is_read)

    def test_viewing_marks_notifications_as_read(self):
        Notification.objects.create(recipient=self.student, message='Hello')
        self.client.force_login(self.student)
        self.client.get(reverse('bookings:notifications'))

        self.assertFalse(Notification.objects.filter(recipient=self.student, is_read=False).exists())


class MessageStudentViewTests(TestCase):
    def setUp(self):
        call_command('setup_roles')
        today = timezone.now().date()
        hostel = Hostel.objects.create(name='Amani Hostel')
        self.room = Room.objects.create(hostel=hostel, room_number='A01', price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.staff = User.objects.create_user(username='steve', password='pass12345')
        self.staff.groups.add(Group.objects.get(name='Staff'))
        self.other_student = User.objects.create_user(username='mary', password='pass12345')
        self.booking = Booking.objects.create(
            student=self.student, room=self.room, term=self.term, status=Booking.Status.CONFIRMED,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('bookings:message_student', args=[self.booking.id]))
        self.assertEqual(response.status_code, 302)

    def test_student_cannot_message_students(self):
        self.client.force_login(self.other_student)
        response = self.client.get(reverse('bookings:message_student', args=[self.booking.id]))
        self.assertEqual(response.status_code, 403)

    def test_staff_can_send_a_message(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('bookings:message_student', args=[self.booking.id]), {
            'message': 'Please confirm your move-in date by Friday.',
        })
        self.assertRedirects(response, reverse('bookings:pending_bookings'))

        note = Notification.objects.get(recipient=self.student, booking=self.booking)
        self.assertEqual(note.sender, self.staff)
        self.assertEqual(note.message, 'Please confirm your move-in date by Friday.')
        self.assertFalse(note.is_read)

    def test_empty_message_is_rejected(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('bookings:message_student', args=[self.booking.id]), {'message': ''})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Notification.objects.filter(booking=self.booking).exists())

    def test_works_regardless_of_booking_status(self):
        # Booking is CONFIRMED (not pending) in setUp - messaging isn't restricted to pending requests.
        self.client.force_login(self.staff)
        response = self.client.post(reverse('bookings:message_student', args=[self.booking.id]), {
            'message': 'Reminder about your room inspection.',
        })
        self.assertRedirects(response, reverse('bookings:pending_bookings'))
        self.assertTrue(Notification.objects.filter(booking=self.booking, recipient=self.student).exists())


class MessageHostelTests(TestCase):
    def setUp(self):
        call_command('setup_roles')
        today = timezone.now().date()
        self.hostel = Hostel.objects.create(name='Amani Hostel')
        self.other_hostel = Hostel.objects.create(name='Uhuru Hostel')
        self.room_a = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=2, price_per_term=15000)
        self.room_b = Room.objects.create(hostel=self.hostel, room_number='A02', capacity=2, price_per_term=15000)
        self.other_room = Room.objects.create(hostel=self.other_hostel, room_number='U01', capacity=2, price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.staff = User.objects.create_user(username='steve', password='pass12345')
        self.staff.groups.add(Group.objects.get(name='Staff'))
        self.student1 = User.objects.create_user(username='jane', password='pass12345')
        self.student2 = User.objects.create_user(username='mary', password='pass12345')
        self.pending_student = User.objects.create_user(username='bob', password='pass12345')
        self.other_hostel_student = User.objects.create_user(username='alice', password='pass12345')

        Booking.objects.create(student=self.student1, room=self.room_a, term=self.term, status=Booking.Status.CONFIRMED)
        Booking.objects.create(student=self.student2, room=self.room_b, term=self.term, status=Booking.Status.CONFIRMED)
        Booking.objects.create(student=self.pending_student, room=self.room_a, term=self.term, status=Booking.Status.PENDING)
        Booking.objects.create(student=self.other_hostel_student, room=self.other_room, term=self.term, status=Booking.Status.CONFIRMED)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('bookings:message_hostel_list'))
        self.assertEqual(response.status_code, 302)

    def test_student_cannot_access_hostel_list(self):
        self.client.force_login(self.student1)
        response = self.client.get(reverse('bookings:message_hostel_list'))
        self.assertEqual(response.status_code, 403)

    def test_hostel_list_shows_correct_occupant_counts(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('bookings:message_hostel_list'))
        counts = {h.name: h.occupant_count for h in response.context['hostels']}
        self.assertEqual(counts['Amani Hostel'], 2)
        self.assertEqual(counts['Uhuru Hostel'], 1)

    def test_sending_notifies_only_confirmed_students_in_that_hostel(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('bookings:message_hostel', args=[self.hostel.id]), {
            'message': 'Water will be off Tuesday for maintenance.',
        })
        self.assertRedirects(response, reverse('bookings:message_hostel_list'))

        self.assertTrue(Notification.objects.filter(recipient=self.student1, message__icontains='Water will be off').exists())
        self.assertTrue(Notification.objects.filter(recipient=self.student2, message__icontains='Water will be off').exists())
        self.assertFalse(Notification.objects.filter(recipient=self.pending_student).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.other_hostel_student).exists())

    def test_notifications_carry_the_sender_and_correct_booking(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('bookings:message_hostel', args=[self.hostel.id]), {'message': 'Hello all.'})

        note = Notification.objects.get(recipient=self.student1)
        self.assertEqual(note.sender, self.staff)
        self.assertEqual(note.booking.room, self.room_a)

    def test_hostel_with_no_current_occupants_shows_empty_state_not_form(self):
        empty_hostel = Hostel.objects.create(name='Baraka Hostel')
        self.client.force_login(self.staff)
        response = self.client.get(reverse('bookings:message_hostel', args=[empty_hostel.id]))
        self.assertEqual(response.context['occupant_count'], 0)
        self.assertContains(response, 'No students currently confirmed')

    def test_cannot_send_to_a_hostel_with_no_current_occupants(self):
        empty_hostel = Hostel.objects.create(name='Baraka Hostel')
        self.client.force_login(self.staff)
        response = self.client.post(reverse('bookings:message_hostel', args=[empty_hostel.id]), {'message': 'Hello?'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Notification.objects.filter(message='Hello?').exists())

    def test_student_cannot_send_hostel_messages(self):
        self.client.force_login(self.student1)
        response = self.client.post(reverse('bookings:message_hostel', args=[self.hostel.id]), {'message': 'Hi'})
        self.assertEqual(response.status_code, 403)


class NotificationContextProcessorTests(TestCase):
    def setUp(self):
        self.factory_user = User.objects.create_user(username='jane', password='pass12345')

    class FakeRequest:
        def __init__(self, user):
            self.user = user

    def test_zero_for_anonymous_user(self):
        from django.contrib.auth.models import AnonymousUser
        result = notifications_context(self.FakeRequest(AnonymousUser()))
        self.assertEqual(result['unread_notification_count'], 0)

    def test_counts_only_unread_notifications(self):
        Notification.objects.create(recipient=self.factory_user, message='Unread 1')
        Notification.objects.create(recipient=self.factory_user, message='Unread 2')
        Notification.objects.create(recipient=self.factory_user, message='Read', is_read=True)

        result = notifications_context(self.FakeRequest(self.factory_user))
        self.assertEqual(result['unread_notification_count'], 2)

    def test_zero_after_all_marked_read(self):
        Notification.objects.create(recipient=self.factory_user, message='Hi', is_read=True)
        result = notifications_context(self.FakeRequest(self.factory_user))
        self.assertEqual(result['unread_notification_count'], 0)
