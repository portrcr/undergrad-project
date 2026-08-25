from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

# codename prefixes per model, e.g. 'add_hostel', 'change_hostel', 'view_hostel', 'delete_hostel'
ADMIN_MODELS = ['hostel', 'room', 'term', 'profile', 'studentpreference', 'booking', 'recommendation']
STAFF_VIEW_MODELS = ['hostel', 'room', 'term', 'studentpreference']
STAFF_CHANGE_MODELS = ['booking']


def perms_for(models, actions):
    codenames = [f'{action}_{model}' for model in models for action in actions]
    return Permission.objects.filter(codename__in=codenames)


class Command(BaseCommand):
    help = 'Create the Admin, Staff and Student groups with their base permissions.'

    def handle(self, *args, **options):
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        staff_group, _ = Group.objects.get_or_create(name='Staff')
        student_group, _ = Group.objects.get_or_create(name='Student')

        admin_group.permissions.set(perms_for(ADMIN_MODELS, ['add', 'change', 'delete', 'view']))
        staff_group.permissions.set(
            list(perms_for(STAFF_VIEW_MODELS, ['view']))
            + list(perms_for(STAFF_CHANGE_MODELS, ['view', 'change']))
        )
        student_group.permissions.clear()  # students act through the app views, not the Django admin

        self.stdout.write(self.style.SUCCESS('Admin, Staff and Student groups are set up.'))
