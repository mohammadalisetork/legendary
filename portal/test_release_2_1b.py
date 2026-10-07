from django.test import TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string

from .models import ActivityLog, Category, Department, Request, RoleAssignment, Service, User


def password():
    return f"{get_random_string(24)}aA9!"


class MultiDepartmentExperienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.requester=User.objects.create_user(username="requester-21b",password=password(),full_name="درخواست‌دهنده",must_change_password=False)
        cls.lead=User.objects.create_user(username="lead-21b",password=password(),full_name="مدیر اداره الف",must_change_password=False)
        cls.manager=User.objects.create_user(username="manager-21b",password=password(),full_name="مدیر درخواست الف",must_change_password=False)
        cls.outsider=User.objects.create_user(username="outsider-21b",password=password(),full_name="مدیر اداره ب",must_change_password=False)
        cls.supervisor=User.objects.create_user(username="supervisor-21b",password=password(),full_name="ناظر",must_change_password=False)
        cls.admin=User.objects.create_user(username="admin-21b",password=password(),full_name="مدیر ارشد",role=User.Role.ADMIN,must_change_password=False)
        cls.department_a=Department.objects.create(code="department-a",name="اداره الف",short_name="الف",status=Department.Status.PUBLISHED)
        cls.department_b=Department.objects.create(code="department-b",name="اداره ب",short_name="ب",status=Department.Status.DRAFT)
        cls.family_a=Category.objects.create(department=cls.department_a,name="خانواده الف",slug="family-a")
        cls.family_b=Category.objects.create(department=cls.department_b,name="خانواده ب",slug="family-b")
        cls.service_a=Service.objects.create(code="A-21B",name="خدمت فعال الف",category=cls.family_a,domain="الف",full_description="شرح",purpose="نیاز الف")
        cls.inactive=Service.objects.create(code="A-OFF",name="خدمت غیرفعال الف",category=cls.family_a,domain="الف",full_description="شرح",active=False)
        cls.service_b=Service.objects.create(code="B-21B",name="خدمت ب",category=cls.family_b,domain="ب",full_description="شرح")
        RoleAssignment.objects.create(user=cls.lead,role=RoleAssignment.Role.DEPARTMENT_LEAD,scope_type=RoleAssignment.ScopeType.DEPARTMENT,department=cls.department_a)
        RoleAssignment.objects.create(user=cls.manager,role=RoleAssignment.Role.REQUEST_MANAGER,scope_type=RoleAssignment.ScopeType.DEPARTMENT,department=cls.department_a)
        RoleAssignment.objects.create(user=cls.outsider,role=RoleAssignment.Role.DEPARTMENT_LEAD,scope_type=RoleAssignment.ScopeType.DEPARTMENT,department=cls.department_b)
        RoleAssignment.objects.create(user=cls.supervisor,role=RoleAssignment.Role.SUPERVISOR,scope_type=RoleAssignment.ScopeType.GLOBAL)
        cls.request_a=Request.objects.create(requester=cls.requester,requesting_unit="طرح",service=cls.service_a,project="پروژه",title="درخواست الف",status=Request.Status.SUBMITTED)
        cls.request_b=Request.objects.create(requester=cls.requester,requesting_unit="طرح",service=cls.service_b,project="پروژه",title="درخواست ب",status=Request.Status.SUBMITTED)

    def test_hub_lists_only_published_departments(self):
        self.client.force_login(self.requester)
        response=self.client.get(reverse("service_hub"))
        self.assertContains(response,"اداره الف")
        self.assertNotContains(response,"اداره ب")
        self.assertContains(response,"1 خانواده · 1 خدمت")

    def test_department_landing_and_existing_catalogue_url(self):
        self.client.force_login(self.requester)
        response=self.client.get(reverse("department_landing",args=[self.department_a.code]))
        self.assertContains(response,"خدمت فعال الف")
        self.assertNotContains(response,"خدمت غیرفعال الف")
        self.assertNotContains(response,"دسته‌بندی")
        self.assertEqual(self.client.get(reverse("catalog")).status_code,200)
        self.assertEqual(self.client.get(reverse("department_landing",args=[self.department_b.code])).status_code,404)

    def test_service_detail_has_hierarchy_and_inactive_state(self):
        self.client.force_login(self.requester)
        response=self.client.get(reverse("service_detail",args=[self.service_a.pk]))
        self.assertContains(response,"مرکز خدمات")
        self.assertContains(response,"اداره الف")
        self.assertContains(response,"خانواده الف")
        inactive=self.client.get(reverse("service_detail",args=[self.inactive.pk]))
        self.assertEqual(inactive.status_code,200)
        self.assertContains(inactive,"در حال حاضر غیرفعال است")
        self.assertEqual(self.client.get(reverse("request_create",args=[self.inactive.pk])).status_code,404)

    def test_permission_aware_navigation(self):
        self.client.force_login(self.requester)
        response=self.client.get(reverse("home"))
        self.assertNotContains(response,"داشبورد اداره")
        self.assertNotContains(response,"اداره‌ها و کاتالوگ")
        self.client.force_login(self.lead)
        response=self.client.get(reverse("home"))
        self.assertContains(response,"داشبورد اداره")
        self.assertContains(response,"اداره‌ها و کاتالوگ")

    def test_queue_department_scope_and_tamper_resistance(self):
        self.client.force_login(self.lead)
        response=self.client.get(reverse("control_requests")+"?department=department-a")
        self.assertContains(response,"درخواست الف")
        self.assertNotContains(response,"درخواست ب")
        self.assertEqual(self.client.get(reverse("control_requests")+"?department=department-b").status_code,404)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("control_requests")+"?department=department-b").status_code,200)

    def test_department_lead_management_is_scoped(self):
        self.client.force_login(self.lead)
        self.assertEqual(self.client.get(reverse("manage_department_detail",args=[self.department_a.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse("manage_department_detail",args=[self.department_b.pk])).status_code,403)
        self.assertEqual(self.client.get(reverse("manage_department_create")).status_code,403)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("manage_departments")).status_code,403)

    def test_department_lead_can_assign_manager_but_not_lead(self):
        target=User.objects.create_user(username="member-21b",password=password(),full_name="عضو جدید",must_change_password=False)
        self.client.force_login(self.lead)
        url=reverse("manage_department_members",args=[self.department_a.pk])
        self.client.post(url,{"user":target.pk,"role":RoleAssignment.Role.REQUEST_MANAGER})
        self.assertTrue(RoleAssignment.objects.filter(user=target,department=self.department_a,role=RoleAssignment.Role.REQUEST_MANAGER,is_active=True).exists())
        other=User.objects.create_user(username="member-lead-21b",password=password(),full_name="عضو دوم",must_change_password=False)
        self.client.post(url,{"user":other.pk,"role":RoleAssignment.Role.DEPARTMENT_LEAD})
        self.assertFalse(RoleAssignment.objects.filter(user=other,department=self.department_a,role=RoleAssignment.Role.DEPARTMENT_LEAD).exists())
        self.assertTrue(ActivityLog.objects.filter(action="DEPARTMENT_MEMBERSHIP_ADDED",target_id=str(RoleAssignment.objects.get(user=target,department=self.department_a).pk)).exists())

    def test_catalogue_management_is_scoped_and_audited(self):
        self.client.force_login(self.lead)
        response=self.client.post(reverse("manage_family_create",args=[self.department_a.pk]),{"name":"خانواده تازه","slug":"new-family","description":"شرح","display_order":2,"active":"on"})
        self.assertEqual(response.status_code,302)
        family=Category.objects.get(department=self.department_a,slug="new-family")
        self.assertTrue(ActivityLog.objects.filter(action="SERVICE_FAMILY_CREATED",target_id=str(family.pk)).exists())
        self.assertEqual(self.client.get(reverse("manage_family_edit",args=[self.family_b.pk])).status_code,403)

    def test_lifecycle_requires_catalogue_and_is_audited(self):
        empty=Department.objects.create(code="empty-department",name="اداره خالی")
        self.client.force_login(self.admin)
        response=self.client.post(reverse("manage_department_status",args=[empty.pk]),{"status":Department.Status.PUBLISHED},follow=True)
        empty.refresh_from_db()
        self.assertEqual(empty.status,Department.Status.DRAFT)
        self.assertContains(response,"حداقل یک خانواده و خدمت فعال")
        family=Category.objects.create(department=empty,name="خانواده",slug="empty-family")
        Service.objects.create(code="EMPTY-1",name="خدمت",category=family,domain="آزمون",full_description="شرح")
        self.client.post(reverse("manage_department_status",args=[empty.pk]),{"status":Department.Status.PUBLISHED})
        empty.refresh_from_db()
        self.assertEqual(empty.status,Department.Status.PUBLISHED)
        self.assertTrue(ActivityLog.objects.filter(action="DEPARTMENT_STATUS_CHANGED",target_id=str(empty.pk)).exists())
