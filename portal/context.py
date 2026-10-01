from .models import RoleAssignment
from .policies import can_access_control, department_ids_for_role, is_super_admin


def portal_context(request):
    if not request.user.is_authenticated:return {}
    return {"unread_notifications":request.user.notifications.filter(read_at__isnull=True).count(),"is_request_manager":can_access_control(request.user),"can_manage_departments":is_super_admin(request.user) or bool(department_ids_for_role(request.user,RoleAssignment.Role.DEPARTMENT_LEAD)),"is_super_admin":is_super_admin(request.user)}
