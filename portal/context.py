from .appearance import FONT_STACKS, darker
from .models import AppearanceSetting, RoleAssignment
from .policies import can_access_control, department_ids_for_role, is_program_manager, is_project_manager, is_super_admin
from .reporting import analytics_allowed


def portal_context(request):
    appearance=AppearanceSetting.objects.filter(pk=1).first() or AppearanceSetting()
    result={"appearance":appearance,"appearance_font_stack":FONT_STACKS[appearance.font_family],"appearance_primary_hover":darker(appearance.primary_color,.88),"appearance_primary_active":darker(appearance.primary_color,.76)}
    if not request.user.is_authenticated:return result
    super_admin=is_super_admin(request.user)
    assignment=request.user.role_assignments.filter(is_active=True).select_related("department","program","project").first()
    context_label=("مدیر ارشد سامانه" if super_admin else f"{assignment.get_role_display()} · {assignment.department}" if assignment and assignment.department else f"{assignment.get_role_display()} · {assignment.project.name}" if assignment and assignment.project else f"{assignment.get_role_display()} · {assignment.program.name}" if assignment and assignment.program else assignment.get_role_display() if assignment else request.user.get_role_display())
    result.update({"unread_notifications":request.user.notifications.filter(read_at__isnull=True).count(),"is_request_manager":can_access_control(request.user),"is_program_manager":is_program_manager(request.user),"is_project_manager":is_project_manager(request.user),"can_view_approval_inbox":is_program_manager(request.user) or request.user.role_assignments.filter(role=RoleAssignment.Role.SENIOR_APPROVAL_AUTHORITY,is_active=True).exists(),"can_manage_departments":super_admin or bool(department_ids_for_role(request.user,RoleAssignment.Role.DEPARTMENT_LEAD)),"is_super_admin":super_admin,"user_context_label":context_label,"can_view_analytics":analytics_allowed(request.user)})
    return result
