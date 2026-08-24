from datetime import date

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from bookings.analytics import recommendation_effectiveness
from bookings.models import Recommendation
from hostels.models import Hostel, Room, Term


def make_term(sequence_number, name=None):
    return Term.objects.create(
        name=name or f'Term {sequence_number}', start_date=date(2026, 1, 1), end_date=date(2026, 4, 1),
        sequence_number=sequence_number,
    )


class RecommendationEffectivenessTests(TestCase):
    def setUp(self):
        self.hostel = Hostel.objects.create(name='Amani Hostel')
        self.room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        self.term = make_term(1)

    def make_recommendation(self, student_suffix, score, was_accepted):
        student = User.objects.create_user(username=f'student{student_suffix}', password='pass12345')
        return Recommendation.objects.create(
            student=student, room=self.room, term=self.term, score=score, was_accepted=was_accepted,
        )

    def test_no_recommendations_yields_no_rate(self):
        stats = recommendation_effectiveness()
        self.assertEqual(stats['total_shown'], 0)
        self.assertIsNone(stats['acceptance_rate'])
        self.assertEqual(stats['per_term'], [])

    def test_counts_and_rate_with_mixed_outcomes(self):
        self.make_recommendation(1, 0.9, True)
        self.make_recommendation(2, 0.8, True)
        self.make_recommendation(3, 0.5, False)
        self.make_recommendation(4, 0.4, None)

        stats = recommendation_effectiveness()
        self.assertEqual(stats['total_shown'], 4)
        self.assertEqual(stats['accepted_count'], 2)
        self.assertEqual(stats['declined_count'], 1)
        self.assertEqual(stats['unresolved_count'], 1)
        self.assertAlmostEqual(stats['acceptance_rate'], 66.7, places=1)

    def test_average_scores_split_by_outcome(self):
        self.make_recommendation(1, 1.0, True)
        self.make_recommendation(2, 0.2, False)

        stats = recommendation_effectiveness()
        self.assertAlmostEqual(stats['avg_accepted_score'], 1.0)
        self.assertAlmostEqual(stats['avg_declined_score'], 0.2)

    def test_average_scores_are_none_without_resolved_recommendations(self):
        self.make_recommendation(1, 0.5, None)
        stats = recommendation_effectiveness()
        self.assertIsNone(stats['avg_accepted_score'])
        self.assertIsNone(stats['avg_declined_score'])

    def test_per_term_breakdown_only_includes_terms_with_recommendations(self):
        other_term = make_term(2)
        self.make_recommendation(1, 0.9, True)

        stats = recommendation_effectiveness()
        term_names = [row['term'] for row in stats['per_term']]
        self.assertEqual(term_names, [self.term])
        self.assertNotIn(other_term, term_names)

    def test_per_term_rate_is_none_when_nothing_resolved_that_term(self):
        self.make_recommendation(1, 0.5, None)
        stats = recommendation_effectiveness()
        self.assertEqual(stats['per_term'][0]['shown'], 1)
        self.assertIsNone(stats['per_term'][0]['rate'])


class RecommendationInsightsViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='steve', password='pass12345')
        self.staff.user_permissions.add(*Permission.objects.filter(codename='change_booking'))
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.create(name='Student'))

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('bookings:recommendation_insights'))
        self.assertEqual(response.status_code, 302)

    def test_student_cannot_view_insights(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('bookings:recommendation_insights'))
        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_insights(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('bookings:recommendation_insights'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Acceptance rate')
