from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase


class SetupRolesTests(TestCase):
    def setUp(self):
        call_command('setup_roles')

    def test_creates_the_three_groups(self):
        self.assertEqual(
            set(Group.objects.values_list('name', flat=True)),
            {'Admin', 'Staff', 'Student'},
        )

    def test_admin_can_fully_manage_hostels(self):
        admin = Group.objects.get(name='Admin')
        codenames = set(admin.permissions.values_list('codename', flat=True))
        for action in ('add', 'change', 'delete', 'view'):
            self.assertIn(f'{action}_hostel', codenames)

    def test_staff_can_view_but_not_add_hostels(self):
        staff = Group.objects.get(name='Staff')
        codenames = set(staff.permissions.values_list('codename', flat=True))
        self.assertIn('view_hostel', codenames)
        self.assertNotIn('add_hostel', codenames)
        self.assertNotIn('delete_hostel', codenames)

    def test_staff_can_view_and_change_bookings(self):
        staff = Group.objects.get(name='Staff')
        codenames = set(staff.permissions.values_list('codename', flat=True))
        self.assertIn('view_booking', codenames)
        self.assertIn('change_booking', codenames)

    def test_student_has_no_admin_site_permissions(self):
        student = Group.objects.get(name='Student')
        self.assertEqual(student.permissions.count(), 0)

    def test_command_is_safe_to_run_twice(self):
        call_command('setup_roles')
        self.assertEqual(Group.objects.filter(name='Admin').count(), 1)
