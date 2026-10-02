from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Attachment, InternalNote, Program, Project, Request, RoleAssignment, ServiceFormField, User
from .policies import Action, can, program_request_scope, request_scope


class ProgramProjectGovernanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command("seed_catalog", verbosity=0)
        cls.service = __import__("portal.models", fromlist=["Service"]).Service.objects.first()
        cls.admin = User.objects.create_user(username="v22admin", role=User.Role.ADMIN, must_change_password=False)
        cls.provider = User.objects.create_user(username="v22provider", role=User.Role.REQUEST_MANAGER, must_change_password=False)
        cls.pm = User.objects.create_user(username="v22pm", role=User.Role.USER, must_change_password=False)
        cls.pjm = User.objects.create_user(username="v22pjm", role=User.Role.USER, must_change_password=False)
        cls.other = User.objects.create_user(username="v22other", role=User.Role.USER, must_change_password=False)
        cls.program = Program.objects.create(code="health-plan", name="Health Plan")
        cls.program.status = Program.Status.ACTIVE; cls.program.save()
        cls.program2 = Program.objects.create(code="other-plan", name="Other Plan")
        cls.program2.status = Program.Status.ACTIVE; cls.program2.save()
        cls.project = Project.objects.create(code="health-project", name="Health Project", program=cls.program)
        cls.project.status = Project.Status.ACTIVE; cls.project.save()
        cls.project2 = Project.objects.create(code="other-project", name="Other Project", program=cls.program2)
        cls.project2.status = Project.Status.ACTIVE; cls.project2.save()
        RoleAssignment.objects.create(user=cls.pm, role=RoleAssignment.Role.PROGRAM_MANAGER, scope_type=RoleAssignment.ScopeType.PROGRAM, program=cls.program, assigned_by=cls.admin)
        RoleAssignment.objects.create(user=cls.pjm, role=RoleAssignment.Role.PROJECT_MANAGER, scope_type=RoleAssignment.ScopeType.PROJECT, program=cls.program, project=cls.project, assigned_by=cls.admin)
        cls.data = {}
        for field in cls.service.form_fields.filter(active=True, required=True):
            if field.field_type == ServiceFormField.FieldType.FILE:
                continue
            if field.field_type == ServiceFormField.FieldType.SELECT:
                value = field.options[0] if field.options else "گزینه"
            elif field.field_type == ServiceFormField.FieldType.MULTISELECT:
                value = field.options[:1]
            elif field.field_type == ServiceFormField.FieldType.CHECKBOX:
                value = True
            elif field.field_type == ServiceFormField.FieldType.DATE:
                value = timezone.localdate().isoformat()
            elif field.field_type == ServiceFormField.FieldType.NUMBER:
                value = 1
            elif field.field_type == ServiceFormField.FieldType.EMAIL:
                value = "test@example.invalid"
            else:
                value = "مقدار آزمون"
            cls.data[field.key] = value

    def make_request(self, *, requester=None, service=None, program=None, project=None, status=Request.Status.SUBMITTED, title="Test request"):
        return Request.objects.create(
            requester=requester or self.other, requesting_unit="واحد آزمون", service=service or self.service,
            project="متن قدیمی", title=title, request_data=self.data, program=program,
            project_entity=project, status=status,
        )

    def assign_provider_department(self, user, department=None):
        from .models import Department
        department = department or self.service.department
        RoleAssignment.objects.create(user=user, role=RoleAssignment.Role.REQUEST_MANAGER,
            scope_type=RoleAssignment.ScopeType.DEPARTMENT, department=department, assigned_by=self.admin)

    def test_model_lifecycle_and_project_parent_are_guarded(self):
        with self.assertRaises(ValidationError):
            Program.objects.create(code="bad-plan", name="Bad", status=Program.Status.ARCHIVED)
        project = self.project
        project.program = self.program2
        with self.assertRaises(ValidationError):
            project.save()
        self.program.status = Program.Status.ARCHIVED
        with self.assertRaises(ValidationError):
            self.program.save()

    def test_role_scope_rejects_project_program_mismatch(self):
        with self.assertRaises(ValidationError):
            RoleAssignment.objects.create(user=self.other, role=RoleAssignment.Role.PROJECT_MANAGER,
                scope_type=RoleAssignment.ScopeType.PROJECT, program=self.program2, project=self.project)

    def test_program_manager_sees_submitted_requests_across_provider_departments_read_only(self):
        req = self.make_request(program=self.program, project=self.project)
        self.client.force_login(self.pm)
        self.assertEqual(self.client.get(reverse("request_detail", args=[req.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("demand_requests")).status_code, 200)
        self.assertEqual(self.client.get(reverse("control_request_detail", args=[req.pk])).status_code, 404)
        self.assertFalse(can(self.pm, Action.REQUEST_RESPOND, resource=req))
        self.assertFalse(can(self.pm, Action.REQUEST_INTERNAL_NOTE, resource=req))
        response = self.client.post(reverse("control_action", args=[req.pk]), {"kind":"note", "body":"secret"})
        self.assertIn(response.status_code, (404, 403))

    def test_project_manager_scope_is_limited_to_assigned_project(self):
        visible = self.make_request(program=self.program, project=self.project)
        hidden = self.make_request(program=self.program2, project=self.project2)
        self.client.force_login(self.pjm)
        self.assertEqual(self.client.get(reverse("project_requests")).status_code, 200)
        self.assertEqual(self.client.get(reverse("request_detail", args=[visible.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("request_detail", args=[hidden.pk])).status_code, 404)

    def test_internal_notes_are_hidden_from_demand_manager(self):
        req = self.make_request(program=self.program, project=self.project)
        InternalNote.objects.create(request=req, author=self.provider, body="محرمانه برای تیم رسیدگی")
        self.client.force_login(self.pm)
        self.assertNotContains(self.client.get(reverse("request_detail", args=[req.pk])), "محرمانه برای تیم رسیدگی")

    def test_program_manager_can_download_authorized_request_attachment(self):
        req = self.make_request(program=self.program, project=self.project)
        upload = SimpleUploadedFile("proof.txt", b"safe test", content_type="text/plain")
        attachment = Attachment.objects.create(request=req, uploaded_by=req.requester, file=upload,
            original_name="proof.txt", size=9, content_type="text/plain")
        self.client.force_login(self.pm)
        response = self.client.get(reverse("attachment_download", args=[attachment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"safe test")

    def test_drafts_are_not_visible_to_other_demand_managers(self):
        req = self.make_request(program=self.program, project=self.project, status=Request.Status.DRAFT)
        self.assertFalse(program_request_scope(self.pm).filter(pk=req.pk).exists())
        self.client.force_login(self.pm)
        self.assertEqual(self.client.get(reverse("request_detail", args=[req.pk])).status_code, 404)

    def test_provider_scope_does_not_expand_to_program_scope(self):
        from .models import Category, Department, Service
        external_department = Department.objects.create(code="other-department", name="ادارهٔ دیگر", short_name="دیگر", status=Department.Status.PUBLISHED)
        category = Category.objects.create(name="خانواده دیگر", slug="other-family", department=external_department)
        external_service = Service.objects.create(code="ZZ-22", name="خدمت دیگر", category=category, domain="آزمون", full_description="آزمون")
        req = self.make_request(service=external_service, program=self.program, project=self.project)
        self.assign_provider_department(self.provider)
        self.client.force_login(self.provider)
        self.assertNotIn(req.pk, request_scope(self.provider).values_list("pk", flat=True))
        self.assertEqual(self.client.get(reverse("control_dashboard")).status_code, 200)

    def test_submission_stores_immutable_context_snapshots_and_audit(self):
        req = self.make_request(requester=self.pm, program=self.program, project=self.project, status=Request.Status.DRAFT)
        req.requester_role_context = RoleAssignment.Role.PROGRAM_MANAGER
        req.save()
        self.client.force_login(self.pm)
        response = self.client.post(reverse("submit_request", args=[req.pk]))
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, Request.Status.SUBMITTED)
        self.assertEqual((req.program_name_snapshot, req.project_name_snapshot), ("Health Plan", "Health Project"))
        self.assertEqual(req.requester_role_at_submission, RoleAssignment.Role.PROGRAM_MANAGER)
        self.assertTrue(req.history.filter(action="REQUEST_SUBMITTED", metadata__program="health-plan").exists())
        self.program.name = "Renamed Plan"
        self.program.save()
        req.refresh_from_db()
        self.assertEqual(req.program_name_snapshot, "Health Plan")

    def test_inactive_assignment_or_program_blocks_final_submit(self):
        req = self.make_request(requester=self.pm, program=self.program, project=self.project, status=Request.Status.DRAFT)
        req.requester_role_context = RoleAssignment.Role.PROGRAM_MANAGER
        req.save()
        assignment = RoleAssignment.objects.get(user=self.pm, program=self.program)
        assignment.is_active = False
        assignment.save()
        self.client.force_login(self.pm)
        self.client.post(reverse("submit_request", args=[req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, Request.Status.DRAFT)

    def test_request_form_limits_program_and_project_choices(self):
        from .forms import RequestBaseForm
        form = RequestBaseForm(service=self.service, user=self.pm)
        self.assertEqual(set(form.fields["program"].queryset.values_list("pk", flat=True)), {self.program.pk})
        self.assertEqual(set(form.fields["project_entity"].queryset.values_list("pk", flat=True)), {self.project.pk})
        self.client.force_login(self.pm)
        page = self.client.get(reverse("request_create", args=[self.service.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "مدیر طرح")

    def test_project_manager_project_options_are_assignment_scoped(self):
        from .forms import RequestBaseForm
        form = RequestBaseForm(service=self.service, user=self.pjm)
        self.assertNotIn("program", form.fields)
        self.assertEqual(set(form.fields["project_entity"].queryset.values_list("pk", flat=True)), {self.project.pk})

    def test_admin_can_create_program_project_assign_and_deactivate_manager(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("manage_program_create"), {"code":"new-plan", "name":"New Plan", "description":"", "status":"DRAFT"})
        self.assertEqual(response.status_code, 302)
        program = Program.objects.get(code="new-plan")
        program.status = Program.Status.ACTIVE
        program.save()
        response = self.client.post(reverse("manage_project_create"), {"code":"new-project", "name":"New Project", "program":program.pk, "description":"", "status":"DRAFT"})
        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(code="new-project")
        user = User.objects.create_user(username="assignedpm", role=User.Role.USER, must_change_password=False)
        response = self.client.post(reverse("manage_program_assignment", args=[program.pk]), {"user":user.pk})
        self.assertEqual(response.status_code, 302)
        assignment = RoleAssignment.objects.get(user=user, program=program)
        self.assertTrue(assignment.is_active)
        self.client.post(reverse("manage_program_assignment", args=[program.pk]), {"deactivate":assignment.pk})
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertIsNotNone(assignment.deactivated_at)

    def test_mixed_demand_assignments_switch_project_options_by_role(self):
        from .forms import RequestBaseForm
        RoleAssignment.objects.create(user=self.pjm, role=RoleAssignment.Role.PROGRAM_MANAGER,
            scope_type=RoleAssignment.ScopeType.PROGRAM, program=self.program2, assigned_by=self.admin)
        form = RequestBaseForm(service=self.service, user=self.pjm)
        self.assertEqual(set(form.fields["requester_role_context"].choices and [x[0] for x in form.fields["requester_role_context"].choices]),
            {Rol