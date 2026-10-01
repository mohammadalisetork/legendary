from .policies import can_access_control


def portal_context(request):
    if not request.user.is_authenticated:return {}
    return {"unread_notifications":request.user.notifications.filter(read_at__isnull=True).count(),"is_request_manager":can_access_control(request.user)}
