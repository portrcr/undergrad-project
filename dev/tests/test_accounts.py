from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile, StudentPreference
from bookings.models import Booking
from hostels.models import Hostel, Room, Term


class ProfileTests(TestCase):
    def test_profile_is_created_automatically_for_new_user(self):
        user = User.objects.create_user(username='jane', password='pass12345')
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_role_reflects_group_membership(self):
        user = User.objects.create_user(username='jane', password='pass12345')
        self.assertIsNone(user.profile.role)

        admin_group, _ = Group.objects.get_or_create(name='Admin')
        user.groups.add(admin_group)
        self.assertEqual(user.profile.role, 'Admin')


class StudentPreferenceTests(TestCase):
    def test_str_includes_student_username(self):
        user = User.objects.create_user(username='jane', password='pass12345')
        preference = StudentPreference.objects.create(
            student=user,
            budget_min=8000,
            budget_max=15000,
            sleep_schedule=StudentPreference.SleepSchedule.EARLY,
            cleanliness_level=StudentPreference.Level.MEDIUM,
            study_habits=StudentPreference.StudyHabits.QUIET,
            noise_tolerance=StudentPreference.Level.LOW,
        )
        self.assertIn('jane', str(preference))

    def make_preference(self, **overrides):
        user = User.objects.create_user(username=overrides.pop('username', 'jane'), password='pass12345')
        defaults = dict(
            student=user, budget_min=8000, budget_max=15000,
            sleep_schedule=StudentPreference.SleepSchedule.EARLY,
            cleanliness_level=StudentPreference.Level.MEDIUM,
            study_habits=StudentPreference.StudyHabits.QUIET,
            noise_tolerance=StudentPreference.Level.MEDIUM,
        )
        defaults.update(overrides)
        return StudentPreference(**defaults)

    def test_rejects_zero_budget_max(self):
        preference = self.make_preference(budget_max=0)
        with self.assertRaises(ValidationError):
            preference.full_clean()

    def test_rejects_budget_min_greater_than_budget_max(self):
        preference = self.make_preference(budget_min=20000, budget_max=15000)
        with self.assertRaises(ValidationError):
            preference.full_clean()

    def test_valid_preference_passes_full_clean(self):
        preference = self.make_preference()
        preference.full_clean()  # should not raise


class EditPreferencesViewTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.create(name='Student'))
        self.non_student = User.objects.create_user(username='steve', password='pass12345')

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('edit_preferences'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_non_student_is_redirected_home(self):
        self.client.force_login(self.non_student)
        response = self.client.get(reverse('edit_preferences'))
        self.assertRedirects(response, reverse('home'))

    def test_student_can_create_preferences(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse('edit_preferences'), {
            'budget_min': 8000, 'budget_max': 15000, 'preferred_location': 'Block A',
            'sleep_schedule': StudentPreference.SleepSchedule.EARLY,
            'cleanliness_level': StudentPreference.Level.MEDIUM,
            'study_habits': StudentPreference.StudyHabits.QUIET,
            'noise_tolerance': StudentPreference.Level.MEDIUM,
        })
        self.assertRedirects(response, reverse('bookings:recommendations'))
        preference = StudentPreference.objects.get(student=self.student)
        self.assertEqual(preference.preferred_location, 'Block A')

    def test_student_can_update_existing_preferences(self):
        StudentPreference.objects.create(
            student=self.student, budget_min=5000, budget_max=10000,
            sleep_schedule=StudentPreference.SleepSchedule.EARLY,
            cleanliness_level=StudentPreference.Level.LOW,
            study_habits=StudentPreference.StudyHabits.QUIET,
            noise_tolerance=StudentPreference.Level.LOW,
        )
        self.client.force_login(self.student)
        self.client.post(reverse('edit_preferences'), {
            'budget_min': 9000, 'budget_max': 20000, 'preferred_location': 'Block B',
            'sleep_schedule': StudentPreference.SleepSchedule.LATE,
            'cleanliness_level': StudentPreference.Level.HIGH,
            'study_habits': StudentPreference.StudyHabits.SOCIAL,
            'noise_tolerance': StudentPreference.Level.HIGH,
        })
        self.assertEqual(StudentPreference.objects.filter(student=self.student).count(), 1)
        preference = StudentPreference.objects.get(student=self.student)
        self.assertEqual(preference.preferred_location, 'Block B')
        self.assertEqual(preference.budget_min, 9000)

    def test_rejects_zero_budget_max_without_crashing(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse('edit_preferences'), {
            'budget_min': 0, 'budget_max': 0, 'preferred_location': 'Block A',
            'sleep_schedule': StudentPreference.SleepSchedule.EARLY,
            'cleanliness_level': StudentPreference.Level.MEDIUM,
            'study_habits': StudentPreference.StudyHabits.QUIET,
            'noise_tolerance': StudentPreference.Level.MEDIUM,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StudentPreference.objects.filter(student=self.student).exists())

    def test_rejects_budget_min_above_budget_max(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse('edit_preferences'), {
            'budget_min': 30000, 'budget_max': 15000, 'preferred_location': 'Block A',
            'sleep_schedule': StudentPreference.SleepSchedule.EARLY,
            'cleanliness_level': StudentPreference.Level.MEDIUM,
            'study_habits': StudentPreference.StudyHabits.QUIET,
            'noise_tolerance': StudentPreference.Level.MEDIUM,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StudentPreference.objects.filter(student=self.student).exists())


class ProfileViewTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.create(name='Student'))
        self.staff = User.objects.create_user(username='steve', password='pass12345')

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_shows_account_details(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jane')

    def test_student_can_update_phone_and_year_of_study(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse('profile'), {'phone': '0712345678', 'year_of_study': 2})
        self.assertRedirects(response, reverse('profile'))
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.phone, '0712345678')
        self.assertEqual(self.student.profile.year_of_study, 2)

    def test_non_student_can_also_update_their_profile(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('profile'), {'phone': '0700000000', 'year_of_study': ''})
        self.assertRedirects(response, reverse('profile'))
        self.staff.profile.refresh_from_db()
        self.assertEqual(self.staff.profile.phone, '0700000000')

    def test_non_student_does_not_see_booking_history_section(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('profile'))
        self.assertNotIn('bookings', response.context)

    def test_student_sees_their_own_booking_history_only(self):
        today = timezone.now().date()
        hostel = Hostel.objects.create(name='Amani Hostel')
        room = Room.objects.create(hostel=hostel, room_number='A01', price_per_term=15000)
        term = Term.objects.create(
            name='Term 1', start_date=today - timedelta(days=100), end_date=today - timedelta(days=10), sequence_number=1,
        )
        other_student = User.objects.create_user(username='mary', password='pass12345')
        Booking.objects.create(student=self.student, room=room, term=term, status=Booking.Status.CONFIRMED)
        Booking.objects.create(student=other_student, room=room, term=term, status=Booking.Status.CONFIRMED)

        self.client.force_login(self.student)
        response = self.client.get(reverse('profile'))
        self.assertEqual(len(response.context['bookings']), 1)
        self.assertEqual(response.context['bookings'][0].student, self.student)

    def test_can_cancel_pending_booking_from_profile_page(self):
        today = timezone.now().date()
        hostel = Hostel.objects.create(name='Amani Hostel')
        room = Room.objects.create(hostel=hostel, room_number='A01', price_per_term=15000)
        term = Term.objects.create(
            name='Term 1', start_date=today - timedelta(days=5), end_date=today + timedelta(days=85), sequence_number=1,
        )
        booking = Booking.objects.create(student=self.student, room=room, term=term, status=Booking.Status.PENDING)

        self.client.force_login(self.student)
        self.client.post(reverse('bookings:cancel_booking', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)


class HomePackagesTests(TestCase):
    def test_no_packages_when_no_rooms_exist(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(list(response.context['packages']), [])

    def test_groups_rooms_by_capacity_with_lowest_price_and_label(self):
        hostel = Hostel.objects.create(name='Amani Hostel')
        Room.objects.create(hostel=hostel, room_number='A01', capacity=1, price_per_term=25000)
        Room.objects.create(hostel=hostel, room_number='A02', capacity=1, price_per_term=18000)
        Room.objects.create(hostel=hostel, room_number='A03', capacity=2, price_per_term=15000)

        response = self.client.get(reverse('home'))
        packages_by_capacity = {p['capacity']: p for p in response.context['packages']}

        self.assertEqual(packages_by_capacity[1]['min_price'], 18000)
        self.assertEqual(packages_by_capacity[1]['room_count'], 2)
        self.assertEqual(packages_by_capacity[1]['label'], 'Single Room')
        self.assertEqual(packages_by_capacity[2]['label'], 'Double Room')

    def test_maintenance_rooms_are_excluded_from_packages(self):
        hostel = Hostel.objects.create(name='Amani Hostel')
        Room.objects.create(
            hostel=hostel, room_number='A01', capacity=1, price_per_term=15000, status=Room.Status.MAINTENANCE,
        )
        response = self.client.get(reverse('home'))
        self.assertEqual(list(response.context['packages']), [])

    def test_four_bed_room_gets_a_generic_label(self):
        hostel = Hostel.objects.create(name='Amani Hostel')
        Room.objects.create(hostel=hostel, room_number='A01', capacity=4, price_per_term=10000)
        response = self.client.get(reverse('home'))
        self.assertEqual(response.context['packages'][0]['label'], '4-Bed Room')
