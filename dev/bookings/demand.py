"""Lightweight demand-prediction model.

Deliberately hand-rolled instead of pulling in scikit-learn/numpy: with only a handful
of terms of history per hostel, a plain least-squares line fit is exactly as capable and
stays fully explainable line-by-line (see the proposal's "lightweight AI/ML" scope).
"""

from django.utils import timezone

from hostels.models import Hostel, Term

from .models import Booking

ACTIVE_STATUSES = [Booking.Status.PENDING, Booking.Status.CONFIRMED]
TREND_THRESHOLD = 0.05


def least_squares_fit(x_values, y_values):
    """Best-fit line (slope, intercept) through the given points, or None if there
    are fewer than 2 points or the x-values don't vary (no line can be fit)."""
    n = len(x_values)
    if n < 2:
        return None

    sum_x = sum(x_values)
    sum_y = sum(y_values)
    sum_xy = sum(x * y for x, y in zip(x_values, y_values))
    sum_x2 = sum(x * x for x in x_values)

    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0:
        return None

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


def predict_hostel_demand(hostel):
    """Fits a trend line over each *completed* term's active-booking count for this hostel
    and extrapolates to the term after the latest one. Returns None if there aren't at
    least two completed terms to fit.

    A term that hasn't ended yet is still taking bookings, so its running total isn't
    comparable with a finished term's - feeding it to the fit as though it were drags the
    line down and reports a falling trend for a hostel that is actually growing. It stays
    in `history` (flagged complete=False) so staff can still see it, but it is left out of
    the fit itself.
    """
    today = timezone.now().date()
    terms = list(Term.objects.order_by('sequence_number'))

    # A term that hasn't started is not history; it has nothing to show or fit.
    history = [
        {
            'term': term,
            'count': Booking.objects.filter(room__hostel=hostel, term=term, status__in=ACTIVE_STATUSES).count(),
            'complete': term.end_date < today,
        }
        for term in terms
        if term.start_date <= today
    ]

    completed = [point for point in history if point['complete']]
    if len(completed) < 2:
        return None

    fit = least_squares_fit(
        [point['term'].sequence_number for point in completed],
        [point['count'] for point in completed],
    )
    if fit is None:
        return None
    slope, intercept = fit

    next_sequence = terms[-1].sequence_number + 1
    predicted_count = max(0, round(slope * next_sequence + intercept))

    if slope > TREND_THRESHOLD:
        trend = 'rising'
    elif slope < -TREND_THRESHOLD:
        trend = 'falling'
    else:
        trend = 'flat'

    max_count = max([point['count'] for point in history] + [predicted_count, 1])

    return {
        'hostel': hostel,
        'history': history,
        'predicted_count': predicted_count,
        'trend': trend,
        'max_count': max_count,
    }


def forecast_all_hostels():
    forecasts = [predict_hostel_demand(hostel) for hostel in Hostel.objects.order_by('name')]
    return [forecast for forecast in forecasts if forecast is not None]
