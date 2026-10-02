from django.db.models import Exists, OuterRef, Q

from .models import Department, Program, Project, Request, RoleAssignment, User


MARKET_DEVELOPMENT_CODE = "market-development"


class Action:
    DEPARTMENT_VIEW = "department.view"
    DEPARTMENT_MANAGE = "department.manage"
    CATALOGUE_VIEW = "catalogue.view"
    CATALOGUE_MANAGE = "catalogue.manage"
    REQUEST_CREATE = "request.create"
    REQUEST_VIEW_OWN = "request.view_own"
    REQUEST_VIEW_DEPARTMENT = "request.view_department"
    REQUEST_VIEW_ALL = "request.view_all"
    REQUEST_VIEW_ATTACHMENT = "request.view_attachment"
    REQUEST_ASSIGN = "request.assign"
    REQUEST_RESPOND = "request.respond"
    REQUEST_CHANGE_STATUS = "request.change_status"
    REQUEST_INTERNAL_NOTE = "request.internal_note"
    DASHBOARD_DEPARTMENT = "dashboard.department"
    DASHBOARD_EXECUTIVE = "dashboard.executive"
    USER_MANAGE = "user.manage"
    ROLE_MANAGE = "role.manage"
    SETTINGS_MANAGE = "settings.manage"
    AUDIT_VIEW = "audit.view"
    PROGRAM_VIEW = "program.view"
    PROGRAM_MANAGE = "program.manage"
    PROJECT_VIEW = "project.view"
    PROJECT_MANAGE = "project.manage"
    PROGRAM_ASSIGNMENT_MANAGE = "program.assignment.manage"
    REQUEST_VIEW_PROGRAM = "request.view_program"
    REQUEST_VIEW_PROJECT = "request.view_project"
    DASHBOARD_PROGRAM = "dashboard.program"


DEPARTMENT_OPERATIONAL_ROLES = {
    RoleAssignment.Role.REQUEST_MANAGER,
    RoleAssignment.Role.DEPARTMENT_LEAD,
}


def _active_assignments(user):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return RoleAssignment.objects.none()
    return RoleAssignment.objects.filter(user=user, is_active=True)


def is_super_admin(user):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if user.role == User.Role.ADMIN:
        return True
    return _active_assignments(user).filter(
        scope_type=RoleAssignment.ScopeType.GLOBAL,
        role=RoleAssignment.Role.SUPER_ADMIN,
    ).exists()


def has_global_role(user, role):
    if is_super_admin(user):
        return role == RoleAssignment.Role.SUPER_ADMIN
    return _active_assignments(user).filter(
        scope_type=RoleAssignment.ScopeType.GLOBAL,
        role=role,
    ).exists()


def _has_scoped_operational_assignment(user):
    return _active_assignments(user).filter(
        scope_type=RoleAssignment.ScopeType.DEPARTMENT,
        role__in=DEPARTMENT_OPERATIONAL_ROLES,
    ).exists()


def has_department_role(user, role, department):
    if is_super_admin(user):
        return True
    department_id = getattr(department, "pk", department)
    if not department_id:
        return False
    if _active_assignments(user).filter(
        scope_type=RoleAssignment.ScopeType.DEPARTMENT,
        department_id=department_id,
        role=role,
    ).exists():
        return True
    if role == RoleAssignment.Role.REQUEST_MANAGER and user.role == User.Role.REQUEST_MANAGER and not _has_scoped_operational_assignment(user):
        return Department.objects.filter(pk=department_id, code=MARKET_DEVELOPMENT_CODE).exists()
    return False


def department_ids_for_role(user, role):
    ids = set(_active_assignments(user).filter(
        scope_type=RoleAssignment.ScopeType.DEPARTMENT,
        role=role,
    ).values_list("department_id", flat=True))
    if role == RoleAssignment.Role.REQUEST_MANAGER and user.role == User.Role.REQUEST_MANAGER and not _has_scoped_operational_assignment(user):
        legacy_id = Department.objects.filter(code=MARKET_DEVELOPMENT_CODE).values_list("id", flat=True).first()
        if legacy_id:
            ids.add(legacy_id)
    return ids


def program_ids_for_role(user, role=RoleAssignment.Role.PROGRAM_MANAGER):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return set()
    return set(_active_assignments(user).filter(
        scope_type=RoleAssignment.ScopeType.PROGRAM, role=role,
    ).values_list("program_id", flat=True))


def project_ids_for_role(user, role=RoleAssignment.Role.PROJECT_MANAGER):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return set()
    return set(_active_assignments(user).filter(
        scope_type=RoleAssignment.ScopeType.PROJECT, role=role,
    ).values_list("project_id", flat=True))


def is_program_manager(user):
    return bool(program_ids_for_role(user))


def is_project_manager(user):
    return bool(project_ids_for_role(user))


def authorized_programs(user, *, active_only=False):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Program.objects.none()
    if is_super_admin(user):
        qs=Program.objects.all()
    else:
        qs=Program.objects.filter(pk__in=program_ids_for_role(user))
    return qs.filter(status=Program.Status.ACTIVE) if active_only else qs


def authorized_projects(user, *, active_only=False):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Project.objects.none()
    if is_super_admin(user):
        qs=Project.objects.select_related("program")
    else:
        qs=Project.objects.select_related("program").filter(pk__in=project_ids_for_role(user))
    return qs.filter(status=Project.Status.ACTIVE,program__status=Program.Status.ACTIVE) if active_only else qs


def program_request_scope(user):
    """Requester-safe demand visibility; provider queue policy stays separate."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Request.objects.none()
    own=Q(requester=user)
    program_ids=program_ids_for_role(user)
    project_ids=project_ids_for_role(user)
    managed=Q(pk__in=[])
    if program_ids:
        managed|=Q(program_id__in=program_ids) & ~Q(status=Request.Status.DRAFT)
    if project_ids:
        managed|=Q(project_entity_id__in=project_ids) & ~Q(status=Request.Status.DRAFT)
    return Request.objects.select_related("program","project_entity","department","service__category__department","requester").prefetch_related("responses__attachments","attachments","history").filter(own|managed).distinct()


def can_use_request_context(user,request_obj):
    """Revalidate a draft's selected demand context at final submission."""
    role=request_obj.requester_role_context
    if not role and not request_obj.program_id and not request_obj.project_entity_id:
        return True
    if role==RoleAssignment.Role.PROGRAM_MANAGER:
        return bool(request_obj.program_id and request_obj.program.status==Program.Status.ACTIVE
            and program_ids_for_role(user,RoleAssignment.Role.PROGRAM_MANAGER).intersection({request_obj.program_id})
            and (not request_obj.project_entity_id or request_obj.project_entity.program_id==request_obj.program_id and request_obj.project_entity.is_requestable))
    if role==RoleAssignment.Role.PROJECT_MANAGER:
        return bool(request_obj.project_entity_id and request_obj.project_entity.is_requestable
            and request_obj.project_entity.program_id==request_obj.program_id
            and request_obj.project_entity_id in project_ids_for_role(user,RoleAssignment.Role.PROJECT_MANAGER))
    return False


def authorized_departments(user, *, operational=False):
    """Departments visible in a scoped workspace; never use this as the only mutation guard."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Department.objects.none()
    if is_super_admin(user) or has_global_role(user, RoleAssignment.Role.SUPERVISOR):
        queryset = Department.objects.all()
        return queryset.exclude(status=Department.Status.ARCHIVED) if operational else queryset
    ids = (
        department_ids_for_role(user, RoleAssignment.Role.REQUEST_MANAGER)
        | department_ids_for_role(user, RoleAssignment.Role.DEPARTMENT_LEAD)
    )
    queryset = Department.objects.filter(pk__in=ids)
    return queryset.exclude(status=Department.Status.ARCHIVED) if operational else queryset


def _manager_can_operate_request(user, request_obj):
    if not has_department_role(user, RoleAssignment.Role.REQUEST_MANAGER, request_obj.department_id):
        return False
    return request_obj.assigned_owner_id in (None, user.pk) or request_obj.service.default_owner_id == user.pk


def can(user, action, resource=None, department=None):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    mutation_actions = {
        Action.REQUEST_ASSIGN,
        Action.REQUEST_RESPOND,
        Action.REQUEST_CHANGE_STATUS,
        Action.REQUEST_INTERNAL_NOTE,
    }
    if resource and action in mutation_actions and resource.department.status == Department.Status.ARCHIVED:
        return False
    if is_super_admin(user):
        return True

    target_department = department or getattr(resource, "department", None)

    if action == Action.REQUEST_CREATE:
        return bool(target_department and target_department.status == Department.Status.PUBLISHED)
    if action == Action.REQUEST_VIEW_OWN:
        return bool(resource and resource.requester_id == user.pk)
    if action == Action.REQUEST_VIEW_ALL:
        return has_global_role(user, RoleAssignment.Role.SUPERVISOR)
    if action == Action.REQUEST_VIEW_ATTACHMENT:
        if resource and resource.requester_id == user.pk:
            return True
        if resource and (can(user,Action.REQUEST_VIEW_PROGRAM,resource=resource) or can(user,Action.REQUEST_VIEW_PROJECT,resource=resource)):
            return True
        return bool(resource and (
            has_department_role(user, RoleAssignment.Role.DEPARTMENT_LEAD, resource.department_id)
            or _manager_can_operate_request(user, resource)
        ))
    if action == Action.REQUEST_VIEW_DEPARTMENT:
        if not resource or resource.status == Request.Status.DRAFT:
            return False
        return (
            has_global_role(user, RoleAssignment.Role.SUPERVISOR)
            or has_department_role(user, RoleAssignment.Role.DEPARTMENT_LEAD, resource.department_id)
            or _manager_can_operate_request(user, resource)
        )
    if action == Action.REQUEST_VIEW_PROGRAM:
        return bool(resource and (
            resource.requester_id==user.pk
            or resource.status!=Request.Status.DRAFT and resource.program_id in program_ids_for_role(user)
        ))
    if action == Action.REQUEST_VIEW_PROJECT:
        return bool(resource and (
            resource.requester_id==user.pk
            or resource.status!=Request.Status.DRAFT and resource.project_entity_id in project_ids_for_role(user)
        ))
    if action in {Action.PROGRAM_VIEW,Action.PROJECT_VIEW}:
        target=getattr(resource,"pk",resource)
        return bool(target and (target in program_ids_for_role(user) if action==Action.PROGRAM_VIEW else target in project_ids_for_role(user)))
    if action==Action.DASHBOARD_PROGRAM:
        return is_program_manager(user) or is_project_manager(user)
    if action in mutation_actions:
        if not resource or resource.status == Request.Status.DRAFT:
            return False
        return (
            has_department_role(user, RoleAssignment.Role.DEPARTMENT_LEAD, resource.department_id)
            or _manager_can_operate_request(user, resource)
        )
    if action == Action.DASHBOARD_DEPARTMENT:
        return bool(
            department_ids_for_role(user, RoleAssignment.Role.REQUEST_MANAGER)
            or department_ids_for_role(user, RoleAssignment.Role.DEPARTMENT_LEAD)
            or has_global_role(user, RoleAssignment.Role.SUPERVISOR)
        )
    if action == Action.DASHBOARD_EXECUTIVE:
        return has_global_role(user, RoleAssignment.Role.EXECUTIVE_VIEWER)
    if action == Action.DEPARTMENT_MANAGE:
        return bool(target_department and has_department_role(
            user, RoleAssignment.Role.DEPARTMENT_LEAD, target_department
        ))
    if action == Action.CATALOGUE_MANAGE:
        return bool(target_department and has_department_role(
            user, RoleAssignment.Role.DEPARTMENT_LEAD, target_department
        ))
    if action == Action.ROLE_MANAGE:
        return bool(target_department and has_department_role(
            user, RoleAssignment.Role.DEPARTMENT_LEAD, target_department
        ))
    if action in {Action.DEPARTMENT_VIEW, Action.CATALOGUE_VIEW}:
        return True
    return False


def can_access_control(user):
    return can(user, Action.DASHBOARD_DEPARTMENT)


def request_scope(user):
    qs = Request.objects.select_related("department", "service__category__department", "requester", "assigned_owner")
    if is_super_admin(user):
        return qs
    if has_global_role(user, RoleAssignment.Role.SUPERVISOR):
        return qs.exclude(status=Request.Status.DRAFT)
    lead_ids = department_ids_for_role(user, RoleAssignment.Role.DEPARTMENT_LEAD)
    manager_ids = department_ids_for_role(user, RoleAssignment.Role.REQUEST_MANAGER)
    scope = Q(pk__in=[])
    if lead_ids:
        scope |= Q(department_id__in=lead_ids)
    if manager_ids:
        scope |= Q(department_id__in=manager_ids) & (
            Q(assigned_owner=user) | Q(assigned_owner__isnull=True) | Q(service__default_owner=user)
        )
    return qs.exclude(status=Request.Status.DRAFT).filter(scope).distinct()


def can_be_default_owner(user, department):
    if not user or not user.is_active:
        return False
    return (
        is_super_admin(user)
        or has_department_role(user, RoleAs