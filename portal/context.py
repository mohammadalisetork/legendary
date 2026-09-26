def portal_context(request):
    if not request.user.is_authenticated:return {}
    return {"unread_notifications":request.user.notifications.filter(read_at__isnull=True).count(),"is_request_manager":request.user.role in {request.user.Role.REQUEST_MANAGER,request.user.Role.ADMIN}}
