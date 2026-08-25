"""Lightweight rule-based room recommender.

No ML library involved on purpose: budget/location fit are simple scoring rules, and
roommate compatibility is a weighted comparison against a room's existing confirmed
occupants (the "greedy incremental match" from the project design). Every score is a
0.0-1.0 fit, combined with fixed weights so the result stays easy to explain.
"""

from collections import namedtuple

from hostels.models import Room

from .models import Booking, Recommendation

RoomScore = namedtuple('RoomScore', ['budget', 'location', 'compatibility', 'overall'])

BUDGET_WEIGHT_WITH_ROOMMATES = 0.4
LOCATION_WEIGHT_WITH_ROOMMATES = 0.3
COMPATIBILITY_WEIGHT = 0.3

BUDGET_WEIGHT_EMPTY_ROOM = 0.6
LOCATION_WEIGHT_EMPTY_ROOM = 0.4

LEVEL_ORDER = {'low': 0, 'medium': 1, 'high': 2}
LEVEL_CLOSENESS_BY_DIFF = {0: 1.0, 1: 0.5}


def budget_score(preference, room):
    price = room.price_per_term
    if preference.budget_max <= 0:
        # Invalid/unset budget range (shouldn't happen via the form's own validation,
        # but guards against bad data slipping in through fixtures/scripts) - neutral
        # rather than a crash from dividing by a zero budget below.
        return 0.5
    if preference.budget_min <= price <= preference.budget_max:
        return 1.0
    if price < preference.budget_min:
        return 0.85
    over_budget = price - preference.budget_max
    return max(0.0, 1 - float(over_budget) / float(preference.budget_max))


def location_score(preference, room):
    if not preference.preferred_location:
        return 0.5
    if preference.preferred_location.strip().lower() == room.hostel.location.strip().lower():
        return 1.0
    return 0.3


def _level_closeness(value_a, value_b):
    diff = abs(LEVEL_ORDER.get(value_a, 1) - LEVEL_ORDER.get(value_b, 1))
    return LEVEL_CLOSENESS_BY_DIFF.get(diff, 0.0)


def compatibility_score(preference_a, preference_b):
    sleep_match = 1.0 if preference_a.sleep_schedule == preference_b.sleep_schedule else 0.0
    study_match = 1.0 if preference_a.study_habits == preference_b.study_habits else 0.0
    smoking_match = 1.0 if preference_a.smoking == preference_b.smoking else 0.0
    cleanliness_match = _level_closeness(preference_a.cleanliness_level, preference_b.cleanliness_level)
    noise_match = _level_closeness(preference_a.noise_tolerance, preference_b.noise_tolerance)
    return (sleep_match + study_match + smoking_match + cleanliness_match + noise_match) / 5


def score_room(preference, room, term):
    """Scores a room 0.0-1.0 for this student, broken down by factor.

    'compatibility' is None (not 0.0) for an empty room - there's no roommate to be
    compatible *with* yet, which is a different thing from a bad compatibility match.
    """
    occupant_preferences = [
        booking.student.preference
        for booking in Booking.objects.filter(room=room, term=term, status=Booking.Status.CONFIRMED).select_related('student')
        if hasattr(booking.student, 'preference')
    ]

    budget = budget_score(preference, room)
    location = location_score(preference, room)

    if occupant_preferences:
        compatibility = sum(compatibility_score(preference, other) for other in occupant_preferences) / len(occupant_preferences)
        overall = (
            BUDGET_WEIGHT_WITH_ROOMMATES * budget
            + LOCATION_WEIGHT_WITH_ROOMMATES * location
            + COMPATIBILITY_WEIGHT * compatibility
        )
    else:
        compatibility = None
        overall = BUDGET_WEIGHT_EMPTY_ROOM * budget + LOCATION_WEIGHT_EMPTY_ROOM * location

    return RoomScore(
        budget=round(budget, 4),
        location=round(location, 4),
        compatibility=round(compatibility, 4) if compatibility is not None else None,
        overall=round(overall, 4),
    )


def recommend_rooms(student, term, limit=5):
    """Top-ranked available rooms for a student this term, as a list of (room, RoomScore)."""
    preference = getattr(student, 'preference', None)
    if preference is None or term is None:
        return []

    ranked = []
    rooms = Room.objects.select_related('hostel').exclude(status=Room.Status.MAINTENANCE)
    for room in rooms:
        confirmed_count = Booking.objects.filter(room=room, term=term, status=Booking.Status.CONFIRMED).count()
        if confirmed_count >= room.capacity:
            continue
        ranked.append((room, score_room(preference, room, term)))

    ranked.sort(key=lambda pair: pair[1].overall, reverse=True)
    return ranked[:limit]


def record_recommendations(student, term, ranked_rooms):
    """Logs what was shown, so acceptance rate can be measured later. Safe to call repeatedly."""
    for room, score in ranked_rooms:
        Recommendation.objects.update_or_create(
            student=student, room=room, term=term,
            defaults={'score': score.overall},
        )
