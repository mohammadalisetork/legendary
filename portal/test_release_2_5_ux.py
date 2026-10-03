from django.test import TestCase
from django.urls import reverse

from .models import Category, Department, RoleAssignment, Service, User


class CanonicalLandingAndOnboardingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.requester = User.objects.create_user(username="ux-requester", full_name="درخواست‌دهنده", must_change_password=False)
        cls.manager = User.objects.create_user(username="ux-manager", full_name="مدیر درخواست", must_change_password=False)
        cls.department = Department.objects.create(code="ux-dept", name="اداره نمونه", status=Department.Status.PUBLISHED)
        cls.family = Category.objects.create(department=cls.department, name="خانواده نمونه", slug="ux-family")
        Service.objects.create(code="UX-1", name="خدمت نمونه", category=cls.family, domain="نمونه", full_description="شرح")
        cls.hidden = Department.objects.create(code="ux-hidden", name="اداره پیش‌نویس")
        RoleAssignment.objects.create(
            user=cls.manager, role=RoleAssignment.Role.REQUEST_MANAGER,
            scope_type=RoleAssignment.ScopeType.DEPARTMENT, department=cls.department,
        )

    def test_home_is_department_first_and_legacy_service_url_reuses_it(self):
        self.client.force_login(self.requester)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اداره نمونه")
        self.assertNotContains(response, "اداره پیش‌نویس")
        self.assertContains(response, 'data-tour-step="departments"')
        self.assertNotContains(response, "خانواده‌های خدمت</h2>")
        legacy = self.client.get(reverse("service_hub") + "?q=نمونه")
        self.assertEqual(legacy.status_code, 200)
        self.assertContains(legacy, "اداره نمونه")
        self.assertContains(legacy, 'action="/"')

    def test_first_run_tour_can_be_skipped_and_is_saved_server_side(self):
        self.client.force_login(self.requester)
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'data-manual="0"')
        self.assertContains(response, 'data-tour-step="find-service"')
        result = self.client.post(reverse("onboarding_tour_state"), {"action": "skip", "manual": "0"})
        self.assertEqual(result.status_code, 200)
        self.requester.refresh_from_db()
        self.assertTrue(self.requester.onboarding_tour_completed)
        self.assertNotContains(self.client.get(reverse("home")), "data-onboarding-tour")

    def test_manual_replay_does_not_change_automatic_state(self):
        self.client.force_login(self.requester)
        profile = self.client.get(reverse("profile"))
        self.assertContains(profile, "tour=replay")
        response = self.client.get(reverse("home") + "?tour=replay")
        self.assertContains(response, 'data-manual="1"')
        result = self.client.post(reverse("onboarding_tour_state"), {"action": "finish", "manual": "1"})
        self.assertEqual(result.status_code, 200)
        self.requester.refresh_from_db()
        self.assertFalse(self.requester.onboarding_tour_completed)
        self.assertContains(self.client.get(reverse("home")), "data-onboarding-tour")

    def test_role_workspace_tour_step_uses_existing_authorized_navigation(self):
        self.client.force_login(self.requester)
        basic = self.client.get(reverse("home"))
        self.assertNotContains(basic, 'data-tour-title="فضای کاری اداره"')
        self.client.force_login(self.manager)
        manager_page = self.client.get(reverse("home"))
        self.assertContains(manager_page, 'data-tour-title="فضای کاری اداره"')
        self.assertContains(manager_page, reverse("control_dashboard"))
