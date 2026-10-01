from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils.crypto import get_random_string
from unittest.mock import patch

from .models import (
    ActivityLog,
    Category,
    Department,
    InternalNote,
    Request,
    RoleAssignment,
    Service,
    User,
)
from .policies import Action, can


TEST_PASSWORD = get_random_string(32)


class DepartmentAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        cls.market = Department.objects.get(code="market-development")
        cls.other_department = Department.objects.get(code="technical-support")
        cls.other_department.status = Department.Status.PUBLISHED
        cls.other_department.save(update_fields=["status", "updated_at"])

        cls.service_a = Service.objects.first()
        family_b = Category.objects.create(
            department=cls.other_department,
            name="خانواده پشتیبانی آزمون",
            slug="support-test-family",
        )
        cls.service_b = Service.objects.create(
            code="SUP-TEST",
            name="خدمت پشتیبانی آزمون",
            category=family_b,
            domain="پشتیبانی فنی",
            full_description="خدمت تست دامنه اداره",
        )

        cls.requester_a = User.objects.create_user(username="requester-a", password=TEST_PASSWORD, full_name="درخواست‌دهنده الف", role=User.Role.USER, must_change_password=False)
        cls.requester_b = User.objects.create_user(username="requester-b", password=TEST_PASSWORD, full_name="درخواست‌دهنده ب", role=User.Role.USER, must_change_password=False)
        cls.manager_a = User.objects.create_user(username="manager-a", password=TEST_PASSWORD, full_name="مدیر الف", role=User.Role.USER, must_change_password=False)
        cls.manager_b = User.objects.create_user(username="manager-b", password=TEST_PASSWORD, full_name="مدیر ب", role=User.Role.USER, must_change_password=False)
        cls.lead_a = User.objects.create_user(username="lead-a", password=TEST_PASSWORD, full_name="مدیر اداره الف", role=User.Role.USER, must_change_password=False)
        cls.supervisor = User.objects.create_user(username="supervisor", password=TEST_PASSWORD, full_name="ناظر", role=User.Role.USER, must_change_password=False)
        cls.executive = User.objects.create_user(username="executive", password=TEST_PASSWORD, full_name="مشاهده‌گر ارشد", role=User.Role.USER, must_change_password=False)
        cls.super_admin = User.objects.create_user(username="scoped-admin", password=TEST_PASSWORD, full_name="مدیر ارشد", role=User.Role.USER, must_change_password=False)

        cls._assign(cls.manager_a, RoleAssignment.Role.REQUEST_MANAGER, cls.market)
        cls._assign(cls.manager_b, RoleAssignment.Role.REQUEST_MANAGER, cls.other_department)
        cls._assign(cls.lead_a, RoleAssignment.Role.DEPARTMENT_LEAD, cls.market)
        cls._assign(cls.supervisor, RoleAssignment.Role.SUPERVISOR)
        cls._assign(cls.executive, RoleAssignment.Role.EXECUTIVE_VIEWER)
        cls._assign(cls.super_admin, RoleAssignment.Role.SUPER_ADMIN)

        cls.request_a = Request.objects.create(
            requester=cls.requester_a,
            requesting_unit="واحد الف",
            service=cls.service_a,
            project="پروژه الف",
            title="درخواست اداره الف",
            status=Request.Status.SUBMITTED,
            assigned_owner=cls.manager_a,
        )
        cls.request_b = Request.objects.create(
            requester=cls.requester_b,
            requesting_unit="واحد ب",
            service=cls.service_b,
            project="پروژه ب",
            title="درخواست اداره ب",
            status=Request.Status.SUBMITTED,
            assigned_owner=cls.manager_b,
        )
        InternalNote.objects.create(request=cls.request_b, author=cls.manager_b, body="یادداشت محرمانه اداره ب")

    @classmethod
    def _assign(cls, user, role, department=None):
        return RoleAssignment.objects.create(
            user=user,
            role=role,
            scope_type=RoleAssignment.ScopeType.DEPARTMENT if department else RoleAssignment.ScopeType.GLOBAL,
            department=department,
        )

    def test_initial_departments_and_legacy_catalogue_mapping(self):
        self.assertEqual(Department.objects.count(), 6)
        self.assertEqual(Department.objects.filter(status=Department.Status.PUBLISHED).count(), 2)
        seeded = Service.objects.exclude(code="SUP-TEST")
        self.assertFalse(seeded.exclude(category__department=self.market).exists())

    def test_request_department_is_derived_and_remains_historical_snapshot(self):
        item = Request(
            requester=self.requester_a,
            requesting_unit="واحد",
            service=self.service_a,
            project="پروژه",
            title="آزمون snapshot",
            department=self.other_department,
        )
        item.save()
        self.assertEqual(item.department, self.market)
        family = self.service_a.category
        family.department = self.other_department
        family.save(update_fields=["department", "updated_at"])
        item.refresh_from_db()
        self.assertEqual(item.department, self.market)

    def test_default_owner_must_belong_to_service_department(self):
        self.service_a.default_owner = self.manager_b
        with self.assertRaises(ValidationError):
            self.service_a.full_clean()
        self.service_a.default_owner = self.manager_a
        self.service_a.full_clean()
        self.service_a.save(update_fields=["default_owner", "updated_at"])
        family = self.service_a.category
        family.department = self.other_department
        with self.assertRaises(ValidationError):
            family.save(update_fields=["department", "updated_at"])
        with self.assertRaises(ValidationError):
            Request.objects.create(requester=self.requester_a, requesting_unit="واحد", service=Service.objects.get(pk=self.service_a.pk), project="پروژه", title="مسئول نامعتبر", assigned_owner=self.manager_b)

    def test_manager_cannot_read_or_mutate_other_department(self):
        self.client.force_login(self.manager_a)
        self.assertEqual(self.client.get(reverse("control_request_detail", args=[self.request_a.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("control_request_detail", args=[self.request_b.pk])).status_code, 404)
        action_url = reverse("control_action", args=[self.request_b.pk])
        self.assertEqual(self.client.post(action_url, {"kind": "action", "status": Request.Status.UNDER_REVIEW}).status_code, 404)
        self.assertEqual(self.client.post(action_url, {"kind": "message", "body": "تلاش غیرمجاز"}).status_code, 404)
        self.assertEqual(self.client.post(action_url, {"kind": "note", "body": "یادداشت غیرمجاز"}).status_code, 404)
        self.request_b.refresh_from_db()
        self.assertEqual(self.request_b.status, Request.Status.SUBMITTED)
        self.assertFalse(self.request_b.responses.filter(body="تلاش غیرمجاز").exists())
        self.assertFalse(self.request_b.internal_notes.filter(body="یادداشت غیرمجاز").exists())

    def test_department_lead_is_scoped_to_own_department(self):
        self.client.force_login(self.lead_a)
        self.assertEqual(self.client.get(reverse("control_request_detail", args=[self.request_a.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("control_request_detail", args=[self.request_b.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("control_action", args=[self.request_b.pk]), {"kind": "message", "body": "غیرمجاز"}).status_code, 404)

    def test_supervisor_is_cross_department_read_only_without_internal_notes(self):
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse("control_request_detail", args=[self.request_b.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دسترسی شما به این درخواست فقط خواندنی است")
        self.assertNotContains(response, "یادداشت محرمانه اداره ب")
        self.assertNotContains(response, "ارسال پاسخ به درخواست‌دهنده")
        self.assertEqual(self.client.post(reverse("control_action", args=[self.request_b.pk]), {"kind": "message", "body": "غیرمجاز"}).status_code, 404)

    def test_executive_has_no_operational_access(self):
        self.client.force_login(self.executive)
        self.assertTrue(can(self.executive, Action.DASHBOARD_EXECUTIVE))
        self.assertEqual(self.client.get(reverse("control_dashboard")).status_code, 404)
        self.assertEqual(self.client.get(reverse("control_request_detail", args=[self.request_a.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("control_action", args=[self.request_a.pk]), {"kind": "message", "body": "غیرمجاز"}).status_code, 404)

    def test_super_admin_can_administer_both_departments(self):
        self.client.force_login(self.super_admin)
        self.assertTrue(self.super_admin.is_superuser)
        self.assertEqual(self.client.get(reverse("control_request_detail", args=[self.request_a.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("control_request_detail", args=[self.request_b.pk])).status_code, 200)
        response = self.client.post(reverse("control_action", args=[self.request_b.pk]), {"kind": "message", "body": "پاسخ مدیر ارشد"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.request_b.responses.filter(body="پاسخ مدیر ارشد").exists())

    def test_requester_isolation_and_internal_note_privacy(self):
        self.client.force_login(self.requester_a)
        self.assertEqual(self.client.get(reverse("request_detail", args=[self.request_b.pk])).status_code, 404)
        own = self.client.get(reverse("request_detail", args=[self.request_a.pk]))
        self.assertNotContains(own, "یادداشت محرمانه اداره ب")

    def test_disabled_department_blocks_new_requests_but_not_history(self):
        self.market.status = Department.Status.DISABLED
        self.market.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.requester_a)
        self.assertEqual(self.client.get(reverse("request_create", args=[self.service_a.pk])).status_code, 404)
        self.client.force_login(self.manager_a)
        self.assertEqual(self.client.get(reverse("control_request_detail", args=[self.request_a.pk])).status_code, 200)

    def test_archived_department_requests_are_read_only(self):
        self.other_department.status = Department.Status.ARCHIVED
        self.other_department.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.manager_b)
        detail = self.client.get(reverse("control_request_detail", args=[self.request_b.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "دسترسی شما به این درخواست فقط خواندنی است")
        self.assertEqual(self.client.post(reverse("control_action", args=[self.request_b.pk]), {"kind": "message", "body": "نباید ثبت شود"}).status_code, 404)

    def test_assignment_scope_validation(self):
        invalid = RoleAssignment(
            user=self.manager_a,
            role=RoleAssignment.Role.REQUEST_MANAGER,
            scope_type=RoleAssignment.ScopeType.DEPARTMENT,
            department=None,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_department_and_membership_admin_actions_are_audited(self):
        self.client.force_login(self.super_admin)
        response = self.client.post(reverse("admin:portal_department_add"), {
            "code": "audit-department",
            "name": "اداره ممیزی",
            "short_name": "ممیزی",
            "description": "",
            "intro_text": "",
            "status": Department.Status.DRAFT,
            "display_order": 90,
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        department = Department.objects.get(code="audit-department")
        self.assertTrue(ActivityLog.objects.filter(action="DEPARTMENT_CREATED", target_id=str(department.pk)).exists())
        target = User.objects.create_user(username="audit-manager", password=TEST_PASSWORD, full_name="مدیر ممیزی", role=User.Role.USER, must_change_password=False)
        response = self.client.post(reverse("admin:portal_roleassignment_add"), {
            "user": target.pk,
            "role": RoleAssignment.Role.REQUEST_MANAGER,
            "scope_type": RoleAssignment.ScopeType.DEPARTMENT,
            "department": department.pk,
            "is_active": "on",
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        assignment = RoleAssignment.objects.get(user=target, department=department)
        self.assertEqual(assignment.assigned_by, self.super_admin)
        self.assertTrue(ActivityLog.objects.filter(action="DEPARTMENT_MEMBERSHIP_ADDED", target_id=str(assignment.pk)).exists())

    def test_initial_admin_receives_super_admin_assignment(self):
        with patch.dict("os.environ", {
            "INITIAL_ADMIN_USERNAME": "release-admin",
            "INITIAL_ADMIN_PASSWORD": TEST_PASSWORD,
            "INITIAL_ADMIN_EMAIL": "release-admin@example.test",
        }, clear=False):
            call_command("create_initial_admin", verbosity=0)
        user = User.objects.get(username="release-admin")
        self.assertTrue(RoleAssignment.objects.filter(user=user, role=RoleAssignment.Role.SUPER_ADMIN, scope_type=RoleAssignment.ScopeType.GLOBAL, is_active=True).exists())


class LegacyDepartmentMigrationTests(TransactionTestCase):
    serialized_rollback = True
    migrate_from = ("portal", "0003_alter_request_status")
    migrate_to = ("portal", "0006_department_constraints")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps

        UserV1 = old_apps.get_model("portal", "User")
        CategoryV1 = old_apps.get_model("portal", "Category")
        ServiceV1 = old_apps.get_model("portal", "Service")
        RequestV1 = old_apps.get_model("portal", "Request")
        ResponseV1 = old_apps.get_model("portal", "RequestResponse")
        AttachmentV1 = old_apps.get_model("portal", "Attachment")
        InternalNoteV1 = old_apps.get_model("portal", "InternalNote")
        HistoryV1 = old_apps.get_model("portal", "RequestHistory")

        encoded_password = make_password(TEST_PASSWORD)
        requester = UserV1.objects.create(username="legacy-user", password=encoded_password, full_name="کاربر قدیمی", email="legacy-user@example.com", role="USER")
        manager = UserV1.objects.create(username="legacy-manager", password=encoded_password, full_name="مدیر قدیمی", email="legacy-manager@example.com", role="REQUEST_MANAGER", is_active=True)
        admin = UserV1.objects.create(username="legacy-admin", password=encoded_password, full_name="ادمین قدیمی", email="legacy-admin@example.com", role="ADMIN", is_active=True)
        category = CategoryV1.objects.create(name="خانواده قدیمی", slug="legacy-family")
        service = ServiceV1.objects.create(code="LEG-01", name="خدمت قدیمی", category=category, domain="توسعه بازار", full_description="تعریف قدیمی")
        request = RequestV1.objects.create(public_id="MKT-LEGACY-001", requester=requester, requesting_unit="واحد قدیمی", service=service, project="پروژه قدیمی", title="درخواست قدیمی", status="ON_HOLD", assigned_owner=manager)
        response = ResponseV1.objects.create(request=request, author=requester, body="گفت‌وگوی قدیمی")
        AttachmentV1.objects.create(request=request, response=response, uploaded_by=requester, file="requests/MKT-LEGACY-001/legacy.pdf", original_name="legacy.pdf", size=123, content_type="application/pdf")
        InternalNoteV1.objects.create(request=request, author=manager, body="یادداشت قدیمی")
        HistoryV1.objects.create(request=request, actor=manager, action="STATUS_CHANGED", from_status="IN_PROGRESS", to_status="ON_HOLD")
        self.legacy_ids = {"request": request.pk, "manager": manager.pk, "admin": admin.pk}

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_populated_v1_database_is_preserved_and_scoped(self):
        DepartmentV2 = self.apps.get_model("portal", "Department")
        CategoryV2 = self.apps.get_model("portal", "Category")
        RequestV2 = self.apps.get_model("portal", "Request")
        RoleAssignmentV2 = self.apps.get_model("portal", "RoleAssignment")
        AttachmentV2 = self.apps.get_model("portal", "Attachment")
        ResponseV2 = self.apps.get_model("portal", "RequestResponse")
        InternalNoteV2 = self.apps.get_model("portal", "InternalNote")
        HistoryV2 = self.apps.get_model("portal", "RequestHistory")

        market = DepartmentV2.objects.get(code="market-development")
        self.assertEqual(DepartmentV2.objects.count(), 6)
        self.assertFalse(CategoryV2.objects.exclude(department=market).exists())
        request = RequestV2.objects.get(pk=self.legacy_ids["request"])
        self.assertEqual(request.public_id, "MKT-LEGACY-001")
        self.assertEqual(request.department_id, market.pk)
        self.assertEqual(request.status, "ON_HOLD")
        self.assertEqual(ResponseV2.objects.filter(request=request, body="گفت‌وگوی قدیمی").count(), 1)
        self.assertEqual(AttachmentV2.objects.filter(request=request, original_name="legacy.pdf").count(), 1)
        self.assertEqual(InternalNoteV2.objects.filter(request=request, body="یادداشت قدیمی").count(), 1)
        self.assertEqual(HistoryV2.objects.filter(request=request, action="STATUS_CHANGED").count(), 1)
        self.assertTrue(RoleAssignmentV2.objects.filter(user_id=self.legacy_ids["manager"], department=market, role="REQUEST_MANAGER", is_active=True).exists())
        self.assertTrue(RoleAssignmentV2.objects.filter(user_id=self.legacy_ids["admin"], role="SUPER_ADMIN", scope_type="GLOBAL", is_active=True).exists())
