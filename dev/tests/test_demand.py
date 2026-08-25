from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.demand import forecast_all_hostels, least_squares_fit, predict_hostel_demand
from bookings.models import Booking
from hostels.models import Hostel, Room, Term


class LeastSquaresFitTests(TestCase):
    def test_returns_none_with_fewer_than_two_points(self):
        self.assertIsNone(least_squares_fit([1], [5]))
        self.assertIsNone(least_squares_fit([], []))

    def test_returns_none_when_x_values_do_not_vary(self):
        self.assertIsNone(least_squares_fit([2, 2, 2], [5, 6, 7]))

    def test_fits_an_exact_line(self):
        # y = 2x + 1
        slope, intercept = least_squares_fit([1, 2, 3, 4], [3, 5, 7, 9])
        self.assertAlmostEqual(slope, 2.0)
        self.assertAlmostEqual(intercept, 1.0)

    def test_fits_a_flat_line(self):
        slope, intercept = least_squares_fit([1, 2, 3], [4, 4, 4])
        self.assertAlmostEqual(slope, 0.0)
        self.assertAlmostEqual(intercept, 4.0)


def make_terms(n):
    """n terms that have already ended, so every one of them counts as completed history."""
    return [
        Term.objects.create(
            name=f'Term {i}', start_date=date(2025, 1, 1), end_date=date(2025, 4, 1), sequence_number=i,
        )
        for i in range(1, n + 1)
    ]


def make_current_term(sequence_number):
    """A term that has started but not ended - still taking bookings."""
    today = timezone.now().date()
    return Term.objects.create(
        name=f'Term {sequence_number}', start_date=today - timedelta(days=5),
        end_date=today + timedelta(days=25), sequence_number=sequence_number,
    )


def make_future_term(sequence_number):
    today = timezone.now().date()
    return Term.objects.create(
        name=f'Term {sequence_number}', start_date=today + timedelta(days=30),
        end_date=today + timedelta(days=120), sequence_number=sequence_number,
    )


class DemandTestCase(TestCase):
    """Shared fixture: one hostel with a single big room, plus a helper to fill terms."""

    _user_counter = 0

    def setUp(self):
        self.hostel = Hostel.objects.create(name='Amani Hostel')
        self.room = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=10, price_per_term=15000)

    def book(self, term, count, status=Booking.Status.CONFIRMED):
        for _ in range(count):
            DemandTestCase._user_counter += 1
            student = User.objects.create_user(username=f'student_{DemandTestCase._user_counter}', password='pass12345')
            Booking.objects.create(student=student, room=self.room, term=term, status=status)


class PredictHostelDemandTests(DemandTestCase):
    def test_returns_none_with_fewer_than_two_terms(self):
        make_terms(1)
        self.assertIsNone(predict_hostel_demand(self.hostel))

    def test_returns_none_when_no_terms_exist(self):
        self.assertIsNone(predict_hostel_demand(self.hostel))

    def test_extrapolates_a_rising_trend(self):
        terms = make_terms(4)
        for term, count in zip(terms, [2, 3, 4, 5]):
            self.book(term, count)

        forecast = predict_hostel_demand(self.hostel)
        self.assertEqual(forecast['predicted_count'], 6)
        self.assertEqual(forecast['trend'], 'rising')

    def test_flat_trend_when_demand_is_steady(self):
        terms = make_terms(3)
        for term in terms:
            self.book(term, 4)

        forecast = predict_hostel_demand(self.hostel)
        self.assertEqual(forecast['predicted_count'], 4)
        self.assertEqual(forecast['trend'], 'flat')

    def test_excludes_cancelled_and_rejected_bookings(self):
        terms = make_terms(2)
        self.book(terms[0], 3, status=Booking.Status.CONFIRMED)
        self.book(terms[0], 2, status=Booking.Status.CANCELLED)
        self.book(terms[1], 3, status=Booking.Status.PENDING)
        self.book(terms[1], 1, status=Booking.Status.REJECTED)

        forecast = predict_hostel_demand(self.hostel)
        counts = [point['count'] for point in forecast['history']]
        self.assertEqual(counts, [3, 3])

    def test_predicted_count_never_goes_negative(self):
        terms = make_terms(3)
        for term, count in zip(terms, [3, 1, 0]):
            self.book(term, count)

        forecast = predict_hostel_demand(self.hostel)
        self.assertGreaterEqual(forecast['predicted_count'], 0)


class InProgressTermTests(DemandTestCase):
    """A term that hasn't ended is still accumulating bookings, so its running total must
    not be fitted as though it were a finished term's - doing so reported a falling trend
    for hostels that were in fact growing."""

    def test_in_progress_term_is_excluded_from_the_trend(self):
        for term, count in zip(make_terms(4), [2, 3, 4, 5]):
            self.book(term, count)
        self.book(make_current_term(5), 1)      # barely started - would drag the line down

        forecast = predict_hostel_demand(self.hostel)
        self.assertEqual(forecast['trend'], 'rising')

    def test_fit_uses_the_completed_terms_only(self):
        # y = x + 1 over the four completed terms, so term 6 extrapolates to 7 - the lone
        # booking in the in-progress term 5 must not pull that down.
        for term, count in zip(make_terms(4), [2, 3, 4, 5]):
            self.book(term, count)
        self.book(make_current_term(5), 1)

        forecast = predict_hostel_demand(self.hostel)
        self.assertEqual(forecast['predicted_count'], 7)

    def test_in_progress_term_is_still_reported_in_the_history(self):
        for term, count in zip(make_terms(2), [2, 3]):
            self.book(term, count)
        self.book(make_current_term(3), 1)

        history = predict_hostel_demand(self.hostel)['history']
        self.assertEqual([point['count'] for point in history], [2, 3, 1])
        self.assertEqual([point['complete'] for point in history], [True, True, False])

    def test_terms_that_have_not_started_are_left_out_of_the_history(self):
        for term, count in zip(make_terms(2), [2, 3]):
            self.book(term, count)
        make_future_term(3)

        history = predict_hostel_demand(self.hostel)['history']
        self.assertEqual(len(history), 2)

    def test_returns_none_with_fewer_than_two_completed_terms(self):
        self.book(make_terms(1)[0], 2)
        self.book(make_current_term(2), 3)

        self.assertIsNone(predict_hostel_demand(self.hostel))

    def test_returns_none_when_every_term_is_still_in_progress(self):
        self.book(make_current_term(1), 2)
        self.book(make_current_term(2), 3)

        self.assertIsNone(predict_hostel_demand(self.hostel))


class ForecastAllHostelsTests(TestCase):
    def test_empty_when_no_hostels(self):
        make_terms(2)
        self.assertEqual(forecast_all_hostels(), [])

    def test_skips_hostels_without_enough_term_history(self):
        Hostel.objects.create(name='Amani Hostel')
        make_terms(1)
        self.assertEqual(forecast_all_hostels(), [])

    def test_includes_hostels_with_enough_history(self):
        hostel = Hostel.objects.create(name='Amani Hostel')
        room = Room.objects.create(hostel=hostel, room_number='A01', capacity=5, price_per_term=15000)
        terms = make_terms(2)
        for term in terms:
            student = User.objects.create_user(username=f'student_{term.id}', password='pass12345')
            Booking.objects.create(student=student, room=room, term=term, status=Booking.Status.CONFIRMED)

        forecasts = forecast_all_hostels()
        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0]['hostel'], hostel)


class DemandForecastViewTests(TestCase):
    def setUp(self):
        Hostel.objects.create(name='Amani Hostel')
        make_terms(2)
        self.staff = User.objects.create_user(username='steve', password='pass12345')
        self.staff.user_permissions.add(*self._change_booking_permission())
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.create(name='Student'))

    @staticmethod
    def _change_booking_permission():
        from django.contrib.auth.models import Permission
        return Permission.objects.filter(codename='change_booking')

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('bookings:demand_forecast'))
        self.assertEqual(response.status_code, 302)

    def test_student_cannot_view_forecast(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('bookings:demand_forecast'))
        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_forecast(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('bookings:demand_forecast'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Amani Hostel')
