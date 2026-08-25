def notifications(request):
    if not request.user.is_authenticated:
        return {'unread_notification_count': 0}
    count = request.user.notifications.filter(is_read=False).count()
    return {'unread_notification_count': count}
