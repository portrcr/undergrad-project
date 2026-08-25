"""Recommendation-effectiveness metrics (proposal objective 4: evaluate the system).

A Recommendation row's was_accepted is set when the student resolves it by requesting
a room this term (see request_booking): True for the room they chose, False for other
unresolved recommendations they were shown that term, still null if they haven't
requested anything yet.
"""

from django.db.models import Avg

from hostels.models import Term

from .models import Recommendation


def _rate(accepted_count, resolved_count):
    if resolved_count == 0:
        return None
    return round(100 * accepted_count / resolved_count, 1)


def recommendation_effectiveness():
    all_recommendations = Recommendation.objects.all()
    resolved = all_recommendations.exclude(was_accepted__isnull=True)
    accepted = resolved.filter(was_accepted=True)
    declined = resolved.filter(was_accepted=False)

    total_shown = all_recommendations.count()
    accepted_count = accepted.count()
    declined_count = declined.count()

    per_term = []
    for term in Term.objects.order_by('sequence_number'):
        term_shown = all_recommendations.filter(term=term).count()
        if term_shown == 0:
            continue
        term_accepted = accepted.filter(term=term).count()
        term_declined = declined.filter(term=term).count()
        per_term.append({
            'term': term,
            'shown': term_shown,
            'accepted': term_accepted,
            'declined': term_declined,
            'rate': _rate(term_accepted, term_accepted + term_declined),
        })

    return {
        'total_shown': total_shown,
        'accepted_count': accepted_count,
        'declined_count': declined_count,
        'unresolved_count': total_shown - accepted_count - declined_count,
        'acceptance_rate': _rate(accepted_count, accepted_count + declined_count),
        'avg_accepted_score': accepted.aggregate(avg=Avg('score'))['avg'],
        'avg_declined_score': declined.aggregate(avg=Avg('score'))['avg'],
        'per_term': per_term,
    }
