"""Create a small, repeatable Release 2.5 dataset for local browser UAT only."""
from datetime import date, timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from portal.models import (
    AllocationPeriod, ApprovalCase, ApprovalDecision, ApprovalPolicy, ApprovalStep,
    Category, CreditAllocation, CreditLedgerEntry, CreditReservation, Department,
    Program, Project, Request, RoleAssignment, SeniorApprovalConfiguration,
    PriorityPolicy, Service, ServiceFormField, User,
)


DEPARTMENTS = (
    ("market-development", "توسعه بازار", "بازار"),
    ("technical-support", "پشتیبانی فنی", "فنی"),
    ("data-bi", "داده و هوش تجاری", "داده"),
    ("strategy-architecture", "راهبرد و معماری", "راهبرد"),
    ("customer-experience", "تجربه مشتری", "تجربه مشتری"),
    ("deputy-coordination", "هماهنگی معاونت", "هماهنگی"),
)
DEMO_PASSWORD = "Local-UAT-Only-2026!"


class Command(BaseCommand):
    help = "Create deterministic LOCAL-ONLY UAT data (never use on production data)."

    def add_arguments(self, parser):
        parser.add_argument("--confirm-local-only", action="store_true",
                            help="Confirm that this is a disposable local/development database.")

    def handle(self, *args, **options):
        if not options["confirm_local_only"]:
            raise CommandError("Pass --confirm-local-only only for a local UAT database.")
        if not settings.DEBUG or settings.APP_ENV not in {"local", "development", "test"}:
            raise CommandError("seed_demo is disabled unless DEBUG is true and APP_ENV is local/development/test.")
        database = settings.DATABASES["default"]
        local_sqlite = database["ENGINE"] == "django.db.backends.sqlite3"
        local_postgres = (database["ENGINE"] == "django.db.backends.postgresql" and
                          database.get("HOST") in {"db", "localhost", "127.0.0.1", "::1"})
        if not (local_sqlite or local_postgres or settings.APP_ENV == "test"):
            raise CommandError("For safety, seed_demo requires local SQLite or a PostgreSQL host named db/localhost.")
        with transaction.atomic():
            call_command("seed_catalog", verbosity=0)
            self.seed()
        self.stdout.write(self.style.SUCCESS(
            f"Local UAT data ready: {Department.objects.count()} departments, "
            f"{Request.objects.filter(public_id__startswith='UAT-RQ-').count()} UAT requests."
        ))
        self.stdout.write(f"LOCAL-ONLY demo password: {DEMO_PASSWORD}")

    def seed(self):
        now = timezone.now()
        departments = {code: Department.objects.get(code=code) for code, _, _ in DEPARTMENTS}
        for index, (code, name, short) in enumerate(DEPARTMENTS):
            Department.objects.filter(pk=departments[code].pk).update(
                name=name, short_name=short, description=f"داده نمونه محلی برای {name}",
                intro_text=f"محیط UAT اداره {name}", icon_name="building",
                status=Department.Status.PUBLISHED, display_order=index,
            )
        departments = {code: Department.objects.get(code=code) for code, _, _ in DEPARTMENTS}

        users = self.seed_users(now)
        families, services = self.seed_catalogue(departments, users)
        programs, projects = self.seed_programs()
        requests = self.seed_requests(now, departments, services, programs, projects, users)
        self.seed_governance(now, departments, programs, requests, users)
        # A separate state is available for catalogue lifecycle review without
        # hiding the representative active service in each department.
        disabled = services["market-development"]
        disabled.lifecycle_status = Service.Status.DISABLED
        disabled.active = False
        disabled.save()

    def user(self, username, full_name, role, unit, now):
        user, _ = User.objects.get_or_create(username=username, defaults={
            "full_name": full_name, "email": f"{username}@example.test", "role": role,
            "organizational_unit": unit, "job_title": "حساب نمایشی محلی",
            "is_active": True, "must_change_password": False,
        })
        user.full_name, user.email = full_name, f"{username}@example.test"
        user.role, user.organizational_unit = role, unit
        user.job_title, user.is_active, user.must_change_password = "حساب نمایشی محلی", True, False
        user.set_password(DEMO_PASSWORD)
        user.save()
        return user

    def assign(self, user, role, scope, **target):
        RoleAssignment.objects.update_or_create(user=user, role=role, scope_type=scope, **target,
            defaults={"is_active": True, "department": None, "program": None, "project": None, **target})

    def seed_users(self, now):
        users = {
            "admin": self.user("uat-admin", "مدیر ارشد سامانه (UAT)", User.Role.ADMIN, "UAT", now),
            "executive": self.user("uat-executive", "مشاهده‌گر ارشد (UAT)", User.Role.USER, "UAT", now),
            "supervisor": self.user("uat-supervisor", "ناظر (UAT)", User.Role.USER, "UAT", now),
            "lead": self.user("uat-department-lead", "مدیر اداره (UAT)", User.Role.USER, "UAT", now),
            "manager": self.user("uat-request-manager", "مدیر درخواست (UAT)", User.Role.REQUEST_MANAGER, "UAT", now),
            "program": self.user("uat-program-manager", "مدیر طرح (UAT)", User.Role.USER, "UAT", now),
            "project": self.user("uat-project-manager", "مدیر پروژه (UAT)", User.Role.USER, "UAT", now),
            "requester": self.user("uat-requester", "درخواست‌دهنده (UAT)", User.Role.USER, "UAT", now),
            "senior": self.user("uat-senior-approver", "مرجع تأیید ارشد (UAT)", User.Role.USER, "UAT", now),
        }
        global_roles = (("admin", RoleAssignment.Role.SUPER_ADMIN),
                        ("executive", RoleAssignment.Role.EXECUTIVE_VIEWER),
                        ("supervisor", RoleAssignment.Role.SUPERVISOR),
                        ("requester", RoleAssignment.Role.REQUESTER),
                        ("senior", RoleAssignment.Role.SENIOR_APPROVAL_AUTHORITY))
        for key, role in global_roles:
            self.assign(users[key], role, RoleAssignment.ScopeType.GLOBAL)
        for code, _, _ in DEPARTMENTS:
            department = Department.objects.get(code=code)
            self.assign(users["lead"], RoleAssignment.Role.DEPARTMENT_LEAD,
                        RoleAssignment.ScopeType.DEPARTMENT, department=department)
            self.assign(users["manager"], RoleAssignment.Role.REQUEST_MANAGER,
                        RoleAssignment.ScopeType.DEPARTMENT, department=department)
        return users

    def seed_catalogue(self, departments, users):
        families, services = {}, {}
        for index, (code, _, _) in enumerate(DEPARTMENTS):
            family, _ = Category.objects.get_or_create(
                department=departments[code], slug=f"uat-{code}",
                defaults={"name": f"خانواده نمونه {index + 1}", "description": "خدمات نمونه برای مرور محلی.", "display_order": 90},
            )
            if not family.active:
                family.active, family.lifecycle_status = True, Category.Status.ACTIVE
                family.save()
            families[code] = family
            service, _ = Service.objects.get_or_create(code=f"UAT-{index + 1:02d}", defaults={
                "name": f"خدمت نمونه اداره {index + 1}", "category": family,
                "domain": "LOCAL UAT", "short_description": "خدمت نمونه برای مرور کاتالوگ و فرم.",
                "full_description": "داده نمایشی محلی؛ هیچ فرایند واقعی یا داده تولیدی را نمایش نمی‌دهد.",
                "purpose": "مرور تجربه ثبت درخواست", "scope": "محیط محلی", "deliverables": "خروجی نمونه",
                "required_inputs": "شرح نیاز", "request_requirements": "شرح نیاز و گزینه اولویت",
                "process_information": "مرور محلی", "service_role": "مدیر درخواست",
                "acceptance_criteria": "قابل مشاهده در UAT", "legacy_sla": "۲ روز کاری",
                "initial_response_days": 2, "delivery_min_days": 3, "delivery_max_days": 8,
                "default_owner": users["manager"], "display_order": 90,
            })
            service.category = family
            service.default_owner = users["manager"]
            service.active, service.lifecycle_status = True, Service.Status.ACTIVE
            service.save()
            ServiceFormField.objects.update_or_create(service=service, key="uat_context", defaults={
                "label": "زمینه درخواست", "field_type": ServiceFormField.FieldType.TEXTAREA,
                "required": True, "help_text": "اطلاعات نمونه برای مرور فرم پویا.", "display_order": 1, "active": True,
            })
            ServiceFormField.objects.update_or_create(service=service, key="uat_channel", defaults={
                "label": "نوع خروجی", "field_type": ServiceFormField.FieldType.SELECT,
                "required": True, "options": ["گزارش", "تحلیل", "پشتیبانی"], "display_order": 2, "active": True,
            })
            ServiceFormField.objects.update_or_create(service=service, key="uat_due_date", defaults={
                "label": "تاریخ موردنظر", "field_type": ServiceFormField.FieldType.DATE,
                "required": False, "display_order": 3, "active": True,
            })
            families[code], services[code] = family, service
        return families, services

    def seed_programs(self):
        programs, projects = [], []
        for index, name in enumerate(("بهبود خدمت‌رسانی", "توسعه بازار دیجیتال", "توانمندسازی داده"), 1):
            program, _ = Program.objects.get_or_create(code=f"uat-program-{index}", defaults={
                "name": name, "description": "طرح نمایشی محلی برای مرور تحلیل‌ها."})
            if program.status == Program.Status.DRAFT:
                program.status = Program.Status.ACTIVE
                program.save()
            programs.append(program)
            for suffix, project_name in (("a", "پروژه تحلیل نیاز"), ("b", "پروژه بهبود فرایند")):
                project, _ = Project.objects.get_or_create(code=f"uat-project-{index}-{suffix}", defaults={
                    "name": f"{project_name} {index}", "program": program,
                    "description": "پروژه نمایشی محلی."})
                if project.status == Project.Status.DRAFT:
                    project.status = Project.Status.ACTIVE
                    project.save()
                projects.append(project)
        return programs, projects

    def seed_requests(self, now, departments, services, programs, projects, users):
        definitions = [
            ("AT-RISK", 0, 0, Request.Status.SUBMITTED, Request.Priority.NORMAL, -2, None, 4),
            ("OVERDUE", 1, 1, Request.Status.SUBMITTED, Request.Priority.HIGH, -12, None, -7),
            ("PROGRAM-APPROVAL", 2, 2, Request.Status.SUBMITTED, Request.Priority.VERY_URGENT, -3, None, 6),
            ("SENIOR-APPROVAL", 3, 3, Request.Status.IN_PROGRESS, Request.Priority.HIGH, -16, 1, 8),
            ("EMERGENCY-CREDIT", 4, 4, Request.Status.IN_PROGRESS, Request.Priority.EMERGENCY, -11, 1, 6),
            ("COMPLETED", 5, 5, Request.Status.COMPLETED, Request.Priority.NORMAL, -32, 1, -20),
            ("CANCELLED", 0, 0, Request.Status.CANCELLED, Request.Priority.NORMAL, -48, 1, -35),
            ("REJECTED", 1, 1, Request.Status.REJECTED, Request.Priority.HIGH, -60, 1, -46),
            ("WAITING", 2, 2, Request.Status.NEED_INFO, Request.Priority.NORMAL, -9, 1, 5),
            ("IN-PROGRESS", 3, 3, Request.Status.IN_PROGRESS, Request.Priority.HIGH, -18, 1, 9),
            ("UNDER-REVIEW", 4, 4, Request.Status.UNDER_REVIEW, Request.Priority.NORMAL, -5, None, 4),
            ("NEW", 5, 5, Request.Status.SUBMITTED, Request.Priority.VERY_URGENT, -1, None, 2),
            ("RESERVED-CREDIT", 0, 1, Request.Status.UNDER_REVIEW, Request.Priority.VERY_URGENT, -7, 1, 8),
            ("RELEASED-CREDIT", 1, 2, Request.Status.CANCELLED, Request.Priority.EMERGENCY, -24, 1, -12),
            ("APPROVED", 2, 0, Request.Status.IN_PROGRESS, Request.Priority.EMERGENCY, -22, 1, 5),
            ("AGING-15", 3, 1, Request.Status.ACCEPTED, Request.Priority.NORMAL, -17, 1, 14),
            ("AGING-30", 4, 2, Request.Status.ON_HOLD, Request.Priority.HIGH, -35, 1, 23),
            ("AGING-60", 5, 0, Request.Status.IN_PROGRESS, Request.Priority.NORMAL, -67, 1, 38),
        ]
        result = {}
        for serial, (label, dept_index, program_index, status, priority, submitted_days, response_days, deadline_days) in enumerate(definitions, 1):
            dept_code = DEPARTMENTS[dept_index][0]
            program_index %= len(programs)
            department, service, program = departments[dept_code], services[dept_code], programs[program_index]
            project = projects[program_index * 2 + (serial % 2)]
            submitted = now + timedelta(days=submitted_days)
            first = now + timedelta(days=submitted_days + response_days) if response_days is not None else None
            completed = now + timedelta(days=deadline_days) if status == Request.Status.COMPLETED else None
            due = now + timedelta(hours=1) if label == "AT-RISK" else now + timedelta(days=deadline_days)
            # UAT cases are representative current states, rather than workflow events.
            item, _ = Request.objects.update_or_create(public_id=f"UAT-RQ-{serial:03d}", defaults={
                "requester": users["requester"], "department": department, "program": program,
                "project_entity": project, "requester_role_context": RoleAssignment.Role.PROJECT_MANAGER,
                "requester_role_at_submission": RoleAssignment.Role.PROJECT_MANAGER,
                "program_name_snapshot": program.name, "program_code_snapshot": program.code,
                "project_name_snapshot": project.name, "project_code_snapshot": project.code,
                "requesting_unit": "واحد نمونه UAT", "service": service, "project": project.name,
                "title": f"درخواست نمونه {label}", "priority": priority, "status": status,
                "request_data": {"uat_context": f"شرح نمونه {label}", "uat_channel": "گزارش"},
                "catalogue_snapshot": {"service_code": service.code, "service_name": service.name,
                    "department_code": department.code, "department_name": department.name,
                    "family_name": service.category.name, "form_fields": [
                        {"key": "uat_context", "label": "زمینه درخواست", "field_type": "textarea", "required": True},
                        {"key": "uat_channel", "label": "نوع خروجی", "field_type": "select", "required": True, "options": ["گزارش", "تحلیل", "پشتیبانی"]},
                        {"key": "uat_due_date", "label": "تاریخ موردنظر", "field_type": "date", "required": False}]},
                "provider_hold": label in {"PROGRAM-APPROVAL", "SENIOR-APPROVAL"},
                "assigned_owner": users["manager"], "submitted_at": submitted,
                "first_response_at": first, "completed_at": completed,
                "expected_initial_response_at": due,
                "estimated_delivery_min": (now + timedelta(days=deadline_days - 2)).date(),
                "estimated_delivery_max": (now + timedelta(days=deadline_days)).date(),
                "operational_paused_at": now - timedelta(days=1) if label == "WAITING" else None,
                "needs_user_action": label == "WAITING",
            })
            Request.objects.filter(pk=item.pk).update(
                submitted_at=submitted, first_response_at=first, completed_at=completed,
                expected_initial_response_at=due,
                estimated_delivery_min=(now + timedelta(days=deadline_days - 2)).date(),
                estimated_delivery_max=(now + timedelta(days=deadline_days)).date(),
                catalogue_snapshot=item.catalogue_snapshot or {},
            )
            item.refresh_from_db()
            result[label] = item
        return result

    def seed_governance(self, now, departments, programs, requests, users):
        for program in programs:
            self.assign(users["program"], RoleAssignment.Role.PROGRAM_MANAGER,
                        RoleAssignment.ScopeType.PROGRAM, program=program)
        for project in Project.objects.filter(code__startswith="uat-project-").select_related("program"):
            self.assign(users["project"], RoleAssignment.Role.PROJECT_MANAGER,
                        RoleAssignment.ScopeType.PROJECT, program=project.program, project=project)
        period, _ = AllocationPeriod.objects.get_or_create(name=f"LOCAL UAT {now.year}", defaults={
            "kind": AllocationPeriod.Kind.YEAR, "starts_on": date(now.year, 1, 1),
            "ends_on": date(now.year, 12, 31), "is_active": True})
        policies = {p.code: p for p in PriorityPolicy.objects.filter(code__in=["NORMAL", "HIGH", "VERY_URGENT", "EMERGENCY"])}
        wallets = {}
        for program in programs:
            for dept_index, (code, _, _) in enumerate(DEPARTMENTS):
                for priority_code in ("VERY_URGENT", "EMERGENCY"):
                    quantity = 6 + ((dept_index + program.pk) % 4)
                    wallet, _ = CreditAllocation.objects.update_or_create(
                        program=program, department=departments[code], priority=policies[priority_code], period=period,
                        defaults={"quantity": quantity, "is_active": True, "created_by": users["admin"]})
                    wallets[(program.pk, code, priority_code)] = wallet
        SeniorApprovalConfiguration.objects.update_or_create(pk=1, defaults={"title": "مرجع ارشد (محلی)", "is_active": True})
        policies_by_key = {(p.trigger, p.target, p.priority.code if p.priority_id else None): p
                          for p in ApprovalPolicy.objects.select_related("priority") if p.is_active}
        self.case(requests["PROGRAM-APPROVAL"], ApprovalPolicy.Trigger.PRIORITY,
                  ApprovalCase.Status.PENDING, users["requester"], users, policies_by_key,
                  ApprovalPolicy.Target.PROGRAM_MANAGER, now)
        self.case(requests["SENIOR-APPROVAL"], ApprovalPolicy.Trigger.PROVIDER,
                  ApprovalCase.Status.PENDING, users["manager"], users, policies_by_key,
                  ApprovalPolicy.Target.SENIOR, now)
        self.case(requests["APPROVED"], ApprovalPolicy.Trigger.PROVIDER,
                  ApprovalCase.Status.APPROVED, users["manager"], users, policies_by_key,
                  ApprovalPolicy.Target.PROGRAM_MANAGER, now)
        self.case(requests["REJECTED"], ApprovalPolicy.Trigger.PROVIDER,
                  ApprovalCase.Status.REJECTED, users["manager"], users, policies_by_key,
                  ApprovalPolicy.Target.SENIOR, now)
        reservations = (("EMERGENCY-CREDIT", "CONSUMED", "EMERGENCY"),
                        ("RESERVED-CREDIT", "RESERVED", "VERY_URGENT"),
                        ("RELEASED-CREDIT", "RELEASED", "EMERGENCY"))
        for label, status, priority in reservations:
            req = requests[label]
            wallet = wallets[(req.program_id, req.department.code, priority)]
            reservation, _ = CreditReservation.objects.update_or_create(request=req, defaults={
                "allocation": wallet, "status": status,
                "reserved_at": req.submitted_at, "resolved_at": None if status == "RESERVED" else now - timedelta(days=1)})
            events = {"RESERVED": [CreditLedgerEntry.Event.RESERVE],
                      "CONSUMED": [CreditLedgerEntry.Event.RESERVE, CreditLedgerEntry.Event.CONSUME],
                      "RELEASED": [CreditLedgerEntry.Event.RESERVE, CreditLedgerEntry.Event.RELEASE]}[status]
            for event in events:
                CreditLedgerEntry.objects.get_or_create(reservation=reservation, event=event, defaults={
                    "actor": users["manager"], "metadata": {"source": "local-uAT-seed"}})

    def case(self, req, trigger, status, requested_by, users, policies, target, now):
        policy = policies.get((trigger, target, req.priority if trigger == ApprovalPolicy.Trigger.PRIORITY else None))
        if policy is None and trigger == ApprovalPolicy.Trigger.PROVIDER:
            policy = policies.get((trigger, target, None))
        case, _ = ApprovalCase.objects.update_or_create(request=req, trigger=trigger, defaults={
            "status": status, "requested_by": requested_by,
            "reason": "نمونه محلی برای مرور گردش تأیید.",
            "assessment": "ارزیابی نمونه UAT", "estimated_time": "۳ روز کاری",
            "estimated_cost": "بدون هزینه واقعی", "recommendation": "ادامه در محیط نمونه",
            "context_snapshot": {"source": "local-uAT-seed", "request": req.public_id,
                                 "department": req.department.name, "program": req.program.name,
                                 "project": req.project_entity.name, "service": req.catalogue_service_name},
            "decided_at": None if status == ApprovalCase.Status.PENDING else now - timedelta(days=1),
        })
        step_status = {ApprovalCase.Status.PENDING: ApprovalStep.Status.PENDING,
                       ApprovalCase.Status.APPROVED: ApprovalStep.Status.APPROVED,
                       ApprovalCase.Status.REJECTED: ApprovalStep.Status.REJECTED}[status]
        step, _ = ApprovalStep.objects.update_or_create(case=case, sequence=1, defaults={
            "request": req, "policy": policy, "target": target, "status": step_status,
            "pauses_sla": True, "started_at": req.submitted_at,
            "decided_at": None if status == ApprovalCase.Status.PENDING else now - timedelta(days=1),
            "decided_by": None if status == ApprovalCase.Status.PENDING else (users["senior"] if target == ApprovalPolicy.Target.SENIOR else users["program"]),
            "decision_reason": "تصمیم نمونه UAT" if status != ApprovalCase.Status.PENDING else "",
            "target_snapshot": {"target": target, "source": "local-uAT-seed"},
        })
        if status in {ApprovalCase.Status.APPROVED, ApprovalCase.Status.REJECTED}:
            outcome = "APPROVED" if status == ApprovalCase.Status.APPROVED else "REJECTED"
            ApprovalDecision.objects.get_or_create(step=step, actor=step.decided_by, outcome=outcome,
                defaults={"reason": "تصمیم نمونه UAT"})
