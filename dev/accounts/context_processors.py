def user_role(request):
    is_student = request.user.is_authenticated and request.user.groups.filter(name='Student').exists()
    return {'is_student': is_student}
