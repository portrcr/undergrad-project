from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from accounts.models import StudentPreference
from bookings.models import Booking, Recommendation
from bookings.recommender import (
    RoomScore,
    budget_score,
    compatibility_score,
    location_score,
    recommend_rooms,
    record_recommendations,
    score_room,
)
from hostels.models import Hostel, Room, Term


def make_preference(student, **overrides):
    defaults = dict(
        budget_min=10000, budget_max=20000, preferred_location='Block A',
        sleep_schedule=StudentPreference.SleepSchedule.EARLY,
        cleanliness_level=StudentPreference.Level.MEDIUM,
        study_habits=StudentPreference.StudyHabits.QUIET,
        noise_tolerance=StudentPreference.Level.MEDIUM,
        smoking=False,
    )
    defaults.update(overrides)
    return StudentPreference.objects.create(student=student, **defaults)


class ScoreComponentTests(TestCase):
    def setUp(self):
        self.hostel = Hostel.objects.create(name='Amani Hostel', location='Block A')
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.preference = make_preference(self.student)

    def test_budget_within_range_scores_highest(self):
        room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        self.assertEqual(budget_score(self.preference, room), 1.0)

    def test_budget_below_range_scores_slightly_lower_than_in_range(self):
        room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=5000)
        self.assertEqual(budget_score(self.preference, room), 0.85)

    def test_zero_budget_max_does_not_crash_and_returns_neutral_score(self):
        # Bypasses model/form validation on purpose to prove the scoring function itself
        # is defensive against bad data (e.g. from a script or fixture), not just the form.
        self.preference.budget_max = 0
        room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=5000)
        self.assertEqual(budget_score(self.preference, room), 0.5)

    def test_budget_above_range_decays_towards_zero(self):
        cheap_over = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=22000)
        way_over = Room.objects.create(hostel=self.hostel, room_number='A02', price_per_term=40000)
        self.assertGreater(budget_score(self.preference, cheap_over), budget_score(self.preference, way_over))
        self.assertGreaterEqual(budget_score(self.preference, way_over), 0.0)

    def test_location_match_scores_highest(self):
        room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        self.assertEqual(location_score(self.preference, room), 1.0)

    def test_location_mismatch_scores_lower(self):
        other_hostel = Hostel.objects.create(name='Uhuru Hostel', location='Block B')
        room = Room.objects.create(hostel=other_hostel, room_number='U01', price_per_term=15000)
        self.assertLess(location_score(self.preference, room), 1.0)

    def test_no_preferred_location_is_neutral(self):
        self.preference.preferred_location = ''
        self.preference.save()
        room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        self.assertEqual(location_score(self.preference, room), 0.5)

    def test_identical_preferences_are_fully_compatible(self):
        other_student = User.objects.create_user(username='mary', password='pass12345')
        other_preference = make_preference(other_student)
        self.assertEqual(compatibility_score(self.preference, other_preference), 1.0)

    def test_opposite_preferences_score_lower(self):
        other_student = User.objects.create_user(username='mary', password='pass12345')
        other_preference = make_preference(
            other_student,
            sleep_schedule=StudentPreference.SleepSchedule.LATE,
            study_habits=StudentPreference.StudyHabits.SOCIAL,
            cleanliness_level=StudentPreference.Level.LOW,
            noise_tolerance=StudentPreference.Level.HIGH,
            smoking=True,
        )
        self.assertLess(compatibility_score(self.preference, other_preference), 0.5)


class ScoreRoomTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.hostel = Hostel.objects.create(name='Amani Hostel', location='Block A')
        self.room = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=2, price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.preference = make_preference(self.student)

    def test_empty_room_uses_budget_and_location_only(self):
        score = score_room(self.preference, self.room, self.term)
        expected = round(0.6 * budget_score(self.preference, self.room) + 0.4 * location_score(self.preference, self.room), 4)
        self.assertEqual(score.overall, expected)

    def test_empty_room_has_no_compatibility_score(self):
        # None, not 0.0 - there's no roommate yet to be compatible *with*.
        score = score_room(self.preference, self.room, self.term)
        self.assertIsNone(score.compatibility)

    def test_room_with_occupant_has_a_compatibility_score(self):
        occupant = User.objects.create_user(username='mary', password='pass12345')
        make_preference(occupant)
        Booking.objects.create(student=occupant, room=self.room, term=self.term, status=Booking.Status.CONFIRMED)

        score = score_room(self.preference, self.room, self.term)
        self.assertIsNotNone(score.compatibility)

    def test_room_with_compatible_occupant_scores_higher_than_incompatible(self):
        compatible_student = User.objects.create_user(username='mary', password='pass12345')
        make_preference(compatible_student)
        Booking.objects.create(student=compatible_student, room=self.room, term=self.term, status=Booking.Status.CONFIRMED)
        compatible_score = score_room(self.preference, self.room, self.term)

        other_room = Room.objects.create(hostel=self.hostel, room_number='A02', capacity=2, price_per_term=15000)
        incompatible_student = User.objects.create_user(username='bob', password='pass12345')
        make_preference(
            incompatible_student,
            sleep_schedule=StudentPreference.SleepSchedule.LATE,
            study_habits=StudentPreference.StudyHabits.SOCIAL,
            smoking=True,
        )
        Booking.objects.create(student=incompatible_student, room=other_room, term=self.term, status=Booking.Status.CONFIRMED)
        incompatible_score = score_room(self.preference, other_room, self.term)

        self.assertGreater(compatible_score.compatibility, incompatible_score.compatibility)
        self.assertGreater(compatible_score.overall, incompatible_score.overall)


class RecommendRoomsTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.hostel = Hostel.objects.create(name='Amani Hostel', location='Block A')
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')

    def test_returns_empty_list_without_a_preference(self):
        self.assertEqual(recommend_rooms(self.student, self.term), [])

    def test_full_rooms_are_excluded(self):
        make_preference(self.student)
        full_room = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=1, price_per_term=15000)
        occupant = User.objects.create_user(username='mary', password='pass12345')
        Booking.objects.create(student=occupant, room=full_room, term=self.term, status=Booking.Status.CONFIRMED)

        ranked = recommend_rooms(self.student, self.term)
        self.assertNotIn(full_room, [room for room, _ in ranked])

    def test_results_are_sorted_highest_score_first(self):
        preference = make_preference(self.student)
        good_fit = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=1, price_per_term=15000)
        poor_fit_hostel = Hostel.objects.create(name='Uhuru Hostel', location='Block B')
        poor_fit = Room.objects.create(hostel=poor_fit_hostel, room_number='U01', capacity=1, price_per_term=40000)

        ranked = recommend_rooms(self.student, self.term)
        rooms_in_order = [room for room, _ in ranked]
        self.assertLess(rooms_in_order.index(good_fit), rooms_in_order.index(poor_fit))

    def test_respects_limit(self):
        make_preference(self.student)
        for i in range(3):
            Room.objects.create(hostel=self.hostel, room_number=f'A0{i}', capacity=1, price_per_term=15000)
        self.assertEqual(len(recommend_rooms(self.student, self.term, limit=2)), 2)


class RecordRecommendationsTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        hostel = Hostel.objects.create(name='Amani Hostel', location='Block A')
        self.room = Room.objects.create(hostel=hostel, room_number='A01', price_per_term=15000)
        self.term = Term.objects.create(
            name='Current Term', start_date=today - timedelta(days=5), end_date=today + timedelta(days=5), sequence_number=1,
        )
        self.student = User.objects.create_user(username='jane', password='pass12345')

    @staticmethod
    def make_score(overall, compatibility=None):
        return RoomScore(budget=1.0, location=1.0, compatibility=compatibility, overall=overall)

    def test_logs_a_recommendation_row_per_room(self):
        record_recommendations(self.student, self.term, [(self.room, self.make_score(0.75))])
        self.assertTrue(Recommendation.objects.filter(student=self.student, room=self.room, term=self.term, score=0.75).exists())

    def test_calling_again_updates_the_score_without_duplicating(self):
        record_recommendations(self.student, self.term, [(self.room, self.make_score(0.5))])
        record_recommendations(self.student, self.term, [(self.room, self.make_score(0.9))])
        self.assertEqual(Recommendation.objects.filter(student=self.student, room=self.room, term=self.term).count(), 1)
        self.assertEqual(Recommendation.objects.get(student=self.student, room=self.room, term=self.term).score, 0.9)
