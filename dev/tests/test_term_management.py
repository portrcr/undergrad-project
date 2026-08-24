from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking, Recommendation
from hostels.models import Hostel, Room, Term


class TermManagementAccessTests(TestCase):
    def setUp(self):
        call_command('setup_roles')
        self.admin = User.objects.create_user(username='alice', password='pass12345')
        self.admin.groups.add(Group.objects.get(name='Admin'))
        self.staff = User.objects.create_user(username='steve', password='pass12345')
        self.staff.groups.add(Group.objects.get(name='Staff'))
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.get(name='Student'))
        self.term = Term.objects.create(
            name='Term 1', start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), sequence_number=1,
        )

    def urls(self):
        return [
            reverse('hostels:manage_terms'),
            reverse('hostels:term_create'),
            reverse('hostels:term_edit', args=[self.term.id]),
            reverse('hostels:term_delete', args=[self.term.id]),
        ]

    def test_anonymous_user_is_redirected_to_login(self):
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_student_is_forbidden(self):
        self.client.force_login(self.student)
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_staff_is_forbidden(self):
        self.client.force_login(self.staff)
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_admin_can_reach_every_page(self):
        self.client.force_login(self.admin)
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 200, url)


class TermCrudTests(TestCase):
    def setUp(self):
        call_command('setup_roles')
        self.admin = User.objects.create_user(username='alice', password='pass12345')
        self.admin.groups.add(Group.objects.get(name='Admin'))
        self.client.force_login(self.admin)

    def test_create_term(self):
        response = self.client.post(reverse('hostels:term_create'), {
            'name': 'Term 1', 'start_date': '2026-01-01', 'end_date': '2026-04-01', 'sequence_number': 1,
        })
        self.assertRedirects(response, reverse('hostels:manage_terms'))
        self.assertTrue(Term.objects.filter(name='Term 1').exists())

    def test_end_date_before_start_date_is_rejected(self):
        response = self.client.post(reverse('hostels:term_create'), {
            'name': 'Broken', 'start_date': '2026-04-01', 'end_date': '2026-01-01', 'sequence_number': 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Term.objects.filter(name='Broken').exists())

    def test_duplicate_name_is_rejected(self):
        Term.objects.create(name='Term 1', start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), sequence_number=1)
        response = self.client.post(reverse('hostels:term_create'), {
            'name': 'Term 1', 'start_date': '2026-05-01', 'end_date': '2026-08-01', 'sequence_number': 2,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Term.objects.filter(name='Term 1').count(), 1)

    def test_duplicate_sequence_number_is_rejected(self):
        Term.objects.create(name='Term 1', start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), sequence_number=1)
        response = self.client.post(reverse('hostels:term_create'), {
            'name': 'Term 2', 'start_date': '2026-05-01', 'end_date': '2026-08-01', 'sequence_number': 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Term.objects.filter(name='Term 2').exists())

    def test_edit_term(self):
        term = Term.objects.create(name='Term 1', start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), sequence_number=1)
        self.client.post(reverse('hostels:term_edit', args=[term.id]), {
            'name': 'Term 1 Renamed', 'start_date': '2026-01-01', 'end_date': '2026-04-01', 'sequence_number': 1,
        })
        term.refresh_from_db()
        self.assertEqual(term.name, 'Term 1 Renamed')

    def test_editing_without_changing_fields_does_not_false_positive_on_uniqueness(self):
        term = Term.objects.create(name='Term 1', start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), sequence_number=1)
        response = self.client.post(reverse('hostels:term_edit', args=[term.id]), {
            'name': 'Term 1', 'start_date': '2026-01-15', 'end_date': '2026-04-01', 'sequence_number': 1,
        })
        self.assertRedirects(response, reverse('hostels:manage_terms'))
        term.refresh_from_db()
        self.assertEqual(term.start_date, date(2026, 1, 15))

    def test_delete_term_shows_confirmation_before_deleting(self):
        term = Term.objects.create(name='Term 1', start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), sequence_number=1)
        response = self.client.get(reverse('hostels:term_delete', args=[term.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Term.objects.filter(id=term.id).exists())

    def test_delete_term_cascades_to_bookings_and_recommendations(self):
        today = timezone.now().date()
        term = Term.objects.create(
            name='Term 1', start_date=today - timedelta(days=5), end_date=today + timedelta(days=85), sequence_number=1,
        )
        hostel = Hostel.objects.create(name='Amani Hostel')
        room = Room.objects.create(hostel=hostel, room_number='A01', price_per_term=15000)
        student = User.objects.create_user(username='mary', password='pass12345')
        Booking.objects.create(student=student, room=room, term=term, status=Booking.Status.CONFIRMED)
        Recommendation.objects.create(student=student, room=room, term=term, score=0.8)

        response = self.client.get(reverse('hostels:term_delete', args=[term.id]))
        self.assertEqual(response.context['booking_count'], 1)
        self.assertEqual(response.context['recommendation_count'], 1)

        self.client.post(reverse('hostels:term_delete', args=[term.id]))
        self.assertFalse(Term.objects.filter(id=term.id).exists())
        self.assertFalse(Booking.objects.filter(term_id=term.id).exists())
        self.assertFalse(Recommendation.objects.filter(term_id=term.id).exists())
