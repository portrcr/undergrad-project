import random
from datetime import date

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import StudentPreference
from bookings.models import Booking
from hostels.models import Hostel, Room, Term

FIRST_NAMES = [
    'Amina', 'Brian', 'Cynthia', 'David', 'Esther', 'Felix', 'Grace', 'Hassan', 'Irene', 'James',
    'Kevin', 'Lilian', 'Moses', 'Naomi', 'Otieno', 'Purity', 'Quinter', 'Robert', 'Sarah', 'Titus',
]
LAST_NAMES = [
    'Mwangi', 'Otieno', 'Wanjiru', 'Kiptoo', 'Achieng', 'Njoroge', 'Cheruiyot', 'Wafula', 'Nyambura', 'Kamau',
]

# name, sequence_number, start_date, end_date. Occupancy rises term over term so there is
# a visible demand trend for the future ML demand-prediction model to learn from.
TERMS = [
    ('2025 Sem 1', 1, date(2025, 1, 6), date(2025, 4, 11), 0.55),
    ('2025 Sem 2', 2, date(2025, 5, 5), date(2025, 8, 15), 0.65),
    ('2025 Sem 3', 3, date(2025, 9, 1), date(2025, 12, 12), 0.75),
    ('2026 Sem 1', 4, date(2026, 1, 5), date(2026, 4, 10), 0.85),
    ('2026 Sem 2', 5, date(2026, 5, 4), date(2026, 8, 15), 0.40),  # current term, left mostly open for testing
]
CURRENT_TERM_CONFIRMED_RATIO = 0.75

HOSTELS = [
    ('Amani Hostel', 'Block A'),
    ('Uhuru Hostel', 'Block B'),
    ('Baraka Hostel', 'Block C'),
]
# capacity, price_per_term, has_private_bathroom
ROOM_TEMPLATE = [
    (1, 25000, True),
    (1, 22000, False),
    (2, 18000, True),
    (2, 15000, False),
    (4, 12000, False),
    (4, 10000, False),
]
LOCATIONS = [location for _, location in HOSTELS]
STUDENT_COUNT = 20
DEMO_PASSWORD = 'password123'


class Command(BaseCommand):
    help = 'Seed the database with demo hostels, rooms, terms, students and booking history for local development.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete existing demo students, hostels, rooms and terms before reseeding (bookings are always regenerated).',
        )

    def handle(self, *args, **options):
        random.seed(42)
        if options['reset']:
            self._reset()

        with transaction.atomic():
            terms = self._create_terms()
            rooms = self._create_hostels_and_rooms()
            students = self._create_students()
            self._create_staff()
            self._create_bookings(terms, rooms, students)

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {len(terms)} terms, {Hostel.objects.count()} hostels, {len(rooms)} rooms, '
            f'{len(students)} students. Demo login: student01 / {DEMO_PASSWORD} (also staff1, admin).'
        ))

    def _reset(self):
        term_names = [name for name, *_ in TERMS]
        hostel_names = [name for name, _ in HOSTELS]
        Booking.objects.filter(term__name__in=term_names).delete()
        User.objects.filter(username__startswith='student').delete()
        User.objects.filter(username='staff1').delete()
        Room.objects.filter(hostel__name__in=hostel_names).delete()
        Hostel.objects.filter(name__in=hostel_names).delete()
        Term.objects.filter(name__in=term_names).delete()

    def _create_terms(self):
        terms = []
        for name, sequence_number, start, end, _occupancy in TERMS:
            term, _ = Term.objects.get_or_create(
                name=name,
                defaults={'start_date': start, 'end_date': end, 'sequence_number': sequence_number},
            )
            terms.append(term)
        return terms

    def _create_hostels_and_rooms(self):
        rooms = []
        for hostel_name, location in HOSTELS:
            hostel, _ = Hostel.objects.get_or_create(
                name=hostel_name,
                defaults={'location': location, 'description': f'{hostel_name} student residence, {location}.'},
            )
            for index, (capacity, price, bathroom) in enumerate(ROOM_TEMPLATE, start=1):
                room_number = f'{hostel_name[0]}{index:02d}'
                room, _ = Room.objects.get_or_create(
                    hostel=hostel, room_number=room_number,
                    defaults={'capacity': capacity, 'price_per_term': price, 'has_private_bathroom': bathroom},
                )
                rooms.append(room)
        return rooms

    def _create_students(self):
        student_group, _ = Group.objects.get_or_create(name='Student')
        sleep_choices = StudentPreference.SleepSchedule.values
        study_choices = StudentPreference.StudyHabits.values
        level_choices = StudentPreference.Level.values

        students = []
        for i in range(1, STUDENT_COUNT + 1):
            username = f'student{i:02d}'
            first_name = FIRST_NAMES[(i - 1) % len(FIRST_NAMES)]
            last_name = LAST_NAMES[(i - 1) % len(LAST_NAMES)]
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'first_name': first_name, 'last_name': last_name, 'email': f'{username}@example.com'},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            user.groups.add(student_group)

            budget_min = random.choice([8000, 10000, 12000, 15000])
            StudentPreference.objects.get_or_create(
                student=user,
                defaults={
                    'budget_min': budget_min,
                    'budget_max': budget_min + random.choice([6000, 8000, 10000, 13000]),
                    'preferred_location': random.choice(LOCATIONS),
                    'sleep_schedule': random.choice(sleep_choices),
                    'cleanliness_level': random.choice(level_choices),
                    'study_habits': random.choice(study_choices),
                    'noise_tolerance': random.choice(level_choices),
                    'smoking': random.random() < 0.1,
                },
            )
            students.append(user)
        return students

    def _create_staff(self):
        staff_group, _ = Group.objects.get_or_create(name='Staff')
        user, created = User.objects.get_or_create(
            username='staff1',
            defaults={'email': 'staff1@example.com', 'is_staff': True},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        user.groups.add(staff_group)
        return user

    def _create_bookings(self, terms, rooms, students):
        # Bookings for the demo terms/rooms are always regenerated so re-running this command is safe.
        Booking.objects.filter(term__in=terms, room__in=rooms).delete()
        for term, (_, _, _, _, occupancy) in zip(terms, TERMS):
            is_current_term = term == terms[-1]
            confirmed_ratio = CURRENT_TERM_CONFIRMED_RATIO if is_current_term else 1.0
            self._book_term(term, rooms, students, occupancy_fraction=occupancy, confirmed_ratio=confirmed_ratio)

    def _book_term(self, term, rooms, students, occupancy_fraction, confirmed_ratio):
        room_capacity_left = {room.id: room.capacity for room in rooms}
        room_pool = list(rooms)
        shuffled_students = list(students)
        random.shuffle(shuffled_students)

        target_bookings = round(len(students) * occupancy_fraction)
        made = 0
        for student in shuffled_students:
            if made >= target_bookings or not room_pool:
                break
            room = random.choice(room_pool)
            status = Booking.Status.CONFIRMED if random.random() < confirmed_ratio else Booking.Status.PENDING
            Booking.objects.create(
                student=student,
                room=room,
                term=term,
                status=status,
                date_resolved=timezone.now() if status == Booking.Status.CONFIRMED else None,
            )
            room_capacity_left[room.id] -= 1
            if room_capacity_left[room.id] <= 0:
                room_pool.remove(room)
            made += 1
