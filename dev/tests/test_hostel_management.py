import shutil
import tempfile
from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from bookings.models import Booking
from hostels.models import Hostel, Room, Term

# Uploaded files land on real disk even inside a TestCase (unlike DB writes, they
# aren't rolled back), so image-upload tests get their own throwaway MEDIA_ROOT
# instead of writing into the project's real media/ folder.
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix='hostel_test_media_')


def make_test_image(name='photo.png'):
    buffer = BytesIO()
    Image.new('RGB', (10, 10), color='blue').save(buffer, format='PNG')
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type='image/png')


class HostelManagementAccessTests(TestCase):
    """Only Admin (not Staff, not Student) should reach any manage_* view."""

    def setUp(self):
        call_command('setup_roles')
        self.admin = User.objects.create_user(username='alice', password='pass12345')
        self.admin.groups.add(Group.objects.get(name='Admin'))
        self.staff = User.objects.create_user(username='steve', password='pass12345')
        self.staff.groups.add(Group.objects.get(name='Staff'))
        self.student = User.objects.create_user(username='jane', password='pass12345')
        self.student.groups.add(Group.objects.get(name='Student'))
        self.hostel = Hostel.objects.create(name='Amani Hostel', location='Block A')
        self.room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)

    def urls(self):
        return [
            reverse('hostels:manage_hostels'),
            reverse('hostels:hostel_create'),
            reverse('hostels:hostel_edit', args=[self.hostel.id]),
            reverse('hostels:hostel_delete', args=[self.hostel.id]),
            reverse('hostels:manage_rooms', args=[self.hostel.id]),
            reverse('hostels:room_create', args=[self.hostel.id]),
            reverse('hostels:room_edit', args=[self.room.id]),
            reverse('hostels:room_delete', args=[self.room.id]),
        ]

    def test_anonymous_user_is_redirected_to_login(self):
        for url in self.urls():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)

    def test_student_is_forbidden(self):
        self.client.force_login(self.student)
        for url in self.urls():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, url)

    def test_staff_is_forbidden_even_though_staff_can_view_rooms_elsewhere(self):
        self.client.force_login(self.staff)
        for url in self.urls():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, url)

    def test_admin_can_reach_every_page(self):
        self.client.force_login(self.admin)
        for url in self.urls():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)


class HostelCrudTests(TestCase):
    def setUp(self):
        call_command('setup_roles')
        self.admin = User.objects.create_user(username='alice', password='pass12345')
        self.admin.groups.add(Group.objects.get(name='Admin'))
        self.client.force_login(self.admin)

    def test_create_hostel(self):
        response = self.client.post(reverse('hostels:hostel_create'), {
            'name': 'Amani Hostel', 'location': 'Block A', 'description': 'Nice place',
        })
        self.assertRedirects(response, reverse('hostels:manage_hostels'))
        self.assertTrue(Hostel.objects.filter(name='Amani Hostel').exists())

    @override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
    def test_create_hostel_with_photo(self):
        response = self.client.post(reverse('hostels:hostel_create'), {
            'name': 'Amani Hostel', 'location': 'Block A', 'description': '', 'image': make_test_image(),
        })
        self.assertRedirects(response, reverse('hostels:manage_hostels'))
        hostel = Hostel.objects.get(name='Amani Hostel')
        self.assertTrue(hostel.image)
        self.assertIn('hostels/', hostel.image.name)

    def test_hostel_without_photo_has_falsy_image_field(self):
        hostel = Hostel.objects.create(name='Amani Hostel')
        self.assertFalse(hostel.image)

    def test_duplicate_hostel_name_is_rejected(self):
        Hostel.objects.create(name='Amani Hostel')
        response = self.client.post(reverse('hostels:hostel_create'), {
            'name': 'Amani Hostel', 'location': 'Block B', 'description': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Hostel.objects.filter(name='Amani Hostel').count(), 1)

    def test_edit_hostel(self):
        hostel = Hostel.objects.create(name='Amani Hostel', location='Block A')
        self.client.post(reverse('hostels:hostel_edit', args=[hostel.id]), {
            'name': 'Amani Hostel', 'location': 'Block Z', 'description': '',
        })
        hostel.refresh_from_db()
        self.assertEqual(hostel.location, 'Block Z')

    def test_delete_hostel_shows_confirmation_before_deleting(self):
        hostel = Hostel.objects.create(name='Amani Hostel')
        get_response = self.client.get(reverse('hostels:hostel_delete', args=[hostel.id]))
        self.assertEqual(get_response.status_code, 200)
        self.assertTrue(Hostel.objects.filter(id=hostel.id).exists())

    def test_delete_hostel_removes_it_and_cascades_to_rooms(self):
        hostel = Hostel.objects.create(name='Amani Hostel')
        Room.objects.create(hostel=hostel, room_number='A01', price_per_term=15000)
        self.client.post(reverse('hostels:hostel_delete', args=[hostel.id]))
        self.assertFalse(Hostel.objects.filter(id=hostel.id).exists())
        self.assertFalse(Room.objects.filter(hostel_id=hostel.id).exists())

    def test_delete_confirmation_shows_booking_count(self):
        today = timezone.now().date()
        hostel = Hostel.objects.create(name='Amani Hostel')
        room = Room.objects.create(hostel=hostel, room_number='A01', price_per_term=15000)
        term = Term.objects.create(name='Term 1', start_date=today, end_date=today + timedelta(days=90), sequence_number=1)
        student = User.objects.create_user(username='mary', password='pass12345')
        Booking.objects.create(student=student, room=room, term=term, status=Booking.Status.CONFIRMED)

        response = self.client.get(reverse('hostels:hostel_delete', args=[hostel.id]))
        self.assertEqual(response.context['booking_count'], 1)


class RoomCrudTests(TestCase):
    def setUp(self):
        call_command('setup_roles')
        self.admin = User.objects.create_user(username='alice', password='pass12345')
        self.admin.groups.add(Group.objects.get(name='Admin'))
        self.client.force_login(self.admin)
        self.hostel = Hostel.objects.create(name='Amani Hostel')

    def test_create_room(self):
        response = self.client.post(reverse('hostels:room_create', args=[self.hostel.id]), {
            'room_number': 'A01', 'capacity': 2, 'price_per_term': 15000,
            'has_private_bathroom': False, 'status': Room.Status.AVAILABLE,
        })
        self.assertRedirects(response, reverse('hostels:manage_rooms', args=[self.hostel.id]))
        room = Room.objects.get(hostel=self.hostel, room_number='A01')
        self.assertEqual(room.capacity, 2)

    def test_duplicate_room_number_in_same_hostel_is_rejected_not_crashed(self):
        Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        response = self.client.post(reverse('hostels:room_create', args=[self.hostel.id]), {
            'room_number': 'A01', 'capacity': 2, 'price_per_term': 18000,
            'has_private_bathroom': False, 'status': Room.Status.AVAILABLE,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Room.objects.filter(hostel=self.hostel, room_number='A01').count(), 1)

    def test_same_room_number_allowed_in_different_hostels(self):
        other_hostel = Hostel.objects.create(name='Uhuru Hostel')
        Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        response = self.client.post(reverse('hostels:room_create', args=[other_hostel.id]), {
            'room_number': 'A01', 'capacity': 2, 'price_per_term': 18000,
            'has_private_bathroom': False, 'status': Room.Status.AVAILABLE,
        })
        self.assertRedirects(response, reverse('hostels:manage_rooms', args=[other_hostel.id]))
        self.assertTrue(Room.objects.filter(hostel=other_hostel, room_number='A01').exists())

    def test_edit_room_without_changing_room_number_does_not_false_positive_on_uniqueness(self):
        room = Room.objects.create(hostel=self.hostel, room_number='A01', capacity=1, price_per_term=15000)
        response = self.client.post(reverse('hostels:room_edit', args=[room.id]), {
            'room_number': 'A01', 'capacity': 3, 'price_per_term': 20000,
            'has_private_bathroom': True, 'status': Room.Status.MAINTENANCE,
        })
        self.assertRedirects(response, reverse('hostels:manage_rooms', args=[self.hostel.id]))
        room.refresh_from_db()
        self.assertEqual(room.capacity, 3)
        self.assertEqual(room.status, Room.Status.MAINTENANCE)

    def test_delete_room_shows_confirmation_before_deleting(self):
        room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        get_response = self.client.get(reverse('hostels:room_delete', args=[room.id]))
        self.assertEqual(get_response.status_code, 200)
        self.assertTrue(Room.objects.filter(id=room.id).exists())

    def test_delete_room_removes_it(self):
        room = Room.objects.create(hostel=self.hostel, room_number='A01', price_per_term=15000)
        self.client.post(reverse('hostels:room_delete', args=[room.id]))
        self.assertFalse(Room.objects.filter(id=room.id).exists())

    def test_rejects_zero_capacity(self):
        response = self.client.post(reverse('hostels:room_create', args=[self.hostel.id]), {
            'room_number': 'A01', 'capacity': 0, 'price_per_term': 15000,
            'has_private_bathroom': False, 'status': Room.Status.AVAILABLE,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Room.objects.filter(hostel=self.hostel, room_number='A01').exists())


def tearDownModule():
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)
