from django.db.models import Exists, OuterRef, Q

from .models import Department, Request, RoleAssignment, User


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
        or has_department_role(user, RoleAssignment.Role.REQUEST_MANAGER, department)
        or has_department_role(user, RoleAssignment.Role.DEPARTMENT_LEAD, department)
    )


def eligible_owners(department):
    scoped_ids = RoleAssignment.objects.filter(
        department=department,
        scope_type=RoleAssignment.ScopeType.DEPARTMENT,
        role__in=DEPARTMENT_OPERATIONAL_ROLES,
        is_active=True,
        user__is_active=True,
    ).values_list("user_id", flat=True)
    query = Q(pk__in=scoped_ids) | Q(role=User.Role.ADMIN)
    if department.code == MARKET_DEVELOPMENT_CODE:
        scoped = RoleAssignment.objects.filter(
            user_id=OuterRef("pk"),
            scope_type=RoleAssignment.ScopeType.DEPARTMENT,
            role__in=DEPARTMENT_OPERATIONAL_ROLES,
            is_active=True,
        )
        legacy_ids = User.objects.filter(role=User.Role.REQUEST_MANAGER, is_active=True).annotate(
            has_scoped=Exists(scoped)
        ).filter(has_scoped=False).values_list("pk", flat=True)
        query |= Q(pk__in=legacy_ids)
    return User.objects.filter(query, is_active=True).distinct()
