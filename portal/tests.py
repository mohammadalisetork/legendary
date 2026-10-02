import tempfile
from datetime import date, datetime, timedelta
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from unittest.mock import patch
from .models import ActivityLog, Category, InternalNote, LoginThrottle, NonWorkingDate, Notification, Request, RequestHistory, Service, ServiceFormField, User, WorkingCalendar
from .utils import add_working_days, apply_submission_timing, transition
from .templatetags.portal_tags import jdate

TEST_PASSWORD=get_random_string(32)

class PortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog",verbosity=0)
        cls.service=Service.objects.first()
        cls.user=User.objects.create_user(username="user",password=TEST_PASSWORD,full_name="کاربر آزمون",organizational_unit="طرح سلامت",role=User.Role.USER,must_change_password=False)
        cls.other=User.objects.create_user(username="other",password=TEST_PASSWORD,full_name="کاربر دیگر",role=User.Role.USER,must_change_password=False)
        cls.manager=User.objects.create_user(username="manager",password=TEST_PASSWORD,full_name="مدیر درخواست",role=User.Role.REQUEST_MANAGER,must_change_password=False)
        cls.admin=User.objects.create_user(username="admin",password=TEST_PASSWORD,full_name="مدیر سامانه",role=User.Role.ADMIN,must_change_password=False)
        data={f.key:"مقدار آزمون" for f in cls.service.form_fields.filter(active=True,required=True) if f.field_type!=ServiceFormField.FieldType.FILE}
        cls.request=Request.objects.create(requester=cls.user,requesting_unit="طرح سلامت",service=cls.service,project="پروژه الف",title="درخواست آزمون",request_data=data,assigned_owner=cls.manager)

    def test_catalog_seed_from_source(self):
        self.assertEqual(Service.objects.count(),65); self.assertEqual(Category.objects.count(),8)
        self.assertTrue(all(s.form_fields.exists() for s in Service.objects.all()))
        mr1=Service.objects.get(code="MR-01"); self.assertEqual((mr1.initial_response_days,mr1.delivery_min_days,mr1.delivery_max_days),(3,7,10))

    def test_login_and_protected_page(self):
        self.assertEqual(self.client.get(reverse("home")).status_code,302)
        response=self.client.post(reverse("login"),{"username":"user","password":TEST_PASSWORD}); self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get(reverse("catalog")).status_code,200)
        self.assertEqual(self.client.post(reverse("logout")).status_code,302); self.assertEqual(self.client.get(reverse("home")).status_code,302)

    def test_user_cannot_view_another_request_or_control(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("request_detail",args=[self.request.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse("control_dashboard")).status_code,404)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code,302)

    def test_internal_notes_are_not_in_user_response(self):
        InternalNote.objects.create(request=self.request,author=self.manager,body="محرمانه داخلی")
        self.client.force_login(self.user); response=self.client.get(reverse("request_detail",args=[self.request.pk]))
        self.assertNotContains(response,"محرمانه داخلی")

    def test_manager_scope_and_admin_scope(self):
        self.request.status=Request.Status.SUBMITTED; self.request.save(update_fields=["status"])
        unassigned=Request.objects.create(requester=self.other,requesting_unit="طرح",service=self.service,project="ب",title="بدون مسئول",status=Request.Status.SUBMITTED)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("control_request_detail",args=[self.request.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse("control_request_detail",args=[unassigned.pk])).status_code,200)
        other_manager=User.objects.create_user(username="manager2",password=TEST_PASSWORD,full_name="مدیر دوم",role=User.Role.REQUEST_MANAGER,must_change_password=False)
        assigned_elsewhere=Request.objects.create(requester=self.other,requesting_unit="طرح",service=self.service,project="ج",title="تخصیص دیگر",assigned_owner=other_manager,status=Request.Status.SUBMITTED)
        self.assertEqual(self.client.get(reverse("control_request_detail",args=[assigned_elsewhere.pk])).status_code,404)
        private_draft=Request.objects.create(requester=self.other,requesting_unit="طرح",service=self.service,project="د",title="پیش‌نویس خصوصی")
        self.assertEqual(self.client.get(reverse("control_request_detail",args=[private_draft.pk])).status_code,404)
        self.client.force_login(self.admin); self.assertEqual(self.client.get(reverse("control_dashboard")).status_code,200)

    def test_submit_creates_timing_and_unique_public_id(self):
        self.client.force_login(self.user)
        response=self.client.post(reverse("submit_request",args=[self.request.pk]))
        self.assertEqual(response.status_code,302); self.request.refresh_from_db()
        self.assertEqual(self.request.status,Request.Status.SUBMITTED); self.assertTrue(self.request.public_id.startswith("MKT-")); self.assertIsNotNone(self.request.expected_initial_response_at)

    def test_pause_and_resume_clock(self):
        self.request.status=Request.Status.UNDER_REVIEW; self.request.save(update_fields=["status"])
        transition(self.request,Request.Status.NEED_INFO,self.manager); self.request.refresh_from_db(); self.assertTrue(self.request.needs_user_action); self.assertIsNotNone(self.request.operational_paused_at)
        self.request.operational_paused_at=timezone.now()-timedelta(hours=2); self.request.save(update_fields=["operational_paused_at"])
        transition(self.request,Request.Status.UNDER_REVIEW,self.user); self.request.refresh_from_db(); self.assertFalse(self.request.needs_user_action); self.assertGreaterEqual(self.request.paused_seconds,7199)

    def test_manager_can_hold_resume_cancel_and_reason_is_audited(self):
        self.request.status=Request.Status.IN_PROGRESS; self.request.save(update_fields=["status"]); self.client.force_login(self.manager)
        url=reverse("control_action",args=[self.request.pk])
        self.client.post(url,{"kind":"action","owner":self.manager.pk,"status":Request.Status.ON_HOLD,"reason":"توقف به علت وابستگی بیرونی"})
        self.request.refresh_from_db(); self.assertEqual(self.request.status,Request.Status.ON_HOLD); self.assertIsNotNone(self.request.operational_paused_at)
        self.request.expected_initial_response_at=timezone.now()-timedelta(days=1); self.request.save(update_fields=["expected_initial_response_at"]); self.assertFalse(self.request.is_overdue)
        self.assertTrue(self.request.history.filter(action="STATUS_CHANGED",metadata__reason="توقف به علت وابستگی بیرونی").exists())
        self.client.post(url,{"kind":"action","owner":self.manager.pk,"status":Request.Status.IN_PROGRESS})
        self.request.refresh_from_db(); self.assertEqual(self.request.status,Request.Status.IN_PROGRESS); self.assertIsNone(self.request.operational_paused_at)
        self.client.post(url,{"kind":"action","owner":self.manager.pk,"status":Request.Status.CANCELLED,"reason":"لغو با درخواست واحد متقاضی"})
        self.request.refresh_from_db(); self.assertEqual(self.request.status,Request.Status.CANCELLED)

    def test_hold_reject_and_cancel_require_reason(self):
        self.request.status=Request.Status.UNDER_REVIEW; self.request.save(update_fields=["status"]); self.client.force_login(self.manager)
        response=self.client.post(reverse("control_action",args=[self.request.pk]),{"kind":"action","owner":self.manager.pk,"status":Request.Status.REJECTED},follow=True)
        self.request.refresh_from_db(); self.assertEqual(self.request.status,Request.Status.UNDER_REVIEW)
        self.assertContains(response,"ثبت دلیل برای این تغییر وضعیت الزامی است")

    def test_operational_elapsed_excludes_pause_and_off_hours(self):
        cal=WorkingCalendar.objects.first(); cal.weekend_days=[4]; cal.workday_start=datetime.min.time().replace(hour=8); cal.workday_end=datetime.min.time().replace(hour=16); cal.save()
        start=timezone.make_aware(datetime(2026,9,28,10)); end=timezone.make_aware(datetime(2026,9,28,14)); self.request.submitted_at=start; self.request.completed_at=end; self.request.status=Request.Status.COMPLETED; self.request.save()
        pause=RequestHistory.objects.create(request=self.request,actor=self.manager,action="CLOCK_PAUSED"); resume=RequestHistory.objects.create(request=self.request,actor=self.manager,action="CLOCK_RESUMED")
        RequestHistory.objects.filter(pk=pause.pk).update(created_at=timezone.make_aware(datetime(2026,9,28,11))); RequestHistory.objects.filter(pk=resume.pk).update(created_at=timezone.make_aware(datetime(2026,9,28,12)))
        self.assertEqual(self.request.operational_elapsed_seconds,3*3600)

    def test_working_days_skip_weekend_and_exception(self):
        cal=WorkingCalendar.objects.first(); cal.weekend_days=[4]; cal.save()
        start=date(2026,9,24) # Thursday
        self.assertEqual(add_working_days(start,1),date(2026,9,26))
        NonWorkingDate.objects.create(calendar=cal,date=date(2026,9,26),title="تعطیلی آزمون")
        self.assertEqual(add_working_days(start,1),date(2026,9,27))

    def test_invalid_past_desired_date_rejected(self):
        self.client.force_login(self.user)
        data={"project":"پروژه","title":"عنوان","priority":"NORMAL","desired_delivery_date":"2020-01-01"}
        for field in self.service.form_fields.filter(active=True,required=True): data[f"data_{field.key}"]="پاسخ"
        response=self.client.post(reverse("request_create",args=[self.service.pk]),data)
        self.assertContains(response,"نمی‌تواند در گذشته باشد")

    def test_health(self): self.assertEqual(self.client.get("/health").json()["status"],"ok")

    def test_password_hash_and_login_throttle(self):
        self.assertTrue(self.user.password.startswith("argon2$"))
        for _ in range(5): self.client.post(reverse("login"),{"username":"user","password":"wrong"})
        self.assertEqual(self.client.post(reverse("login"),{"username":"user","password":"wrong"}).status_code,429)
        self.assertEqual(LoginThrottle.objects.count(),1)

    def test_expected_response_uses_working_calendar_end(self):
        cal=WorkingCalendar.objects.first(); cal.workday_end=timezone.datetime.min.time().replace(hour=15,minute=30); cal.save()
        apply_submission_timing(self.request); local=timezone.localtime(self.request.expected_initial_response_at)
        self.assertEqual((local.hour,local.minute),(15,30))

    def test_jalali_display_known_date(self): self.assertEqual(jdate(date(2026,10,7)),"۱۴۰۵/۰۷/۱۵")

    def test_admin_can_create_user_and_edit_catalogue(self):
        self.client.force_login(self.admin)
        panel_password=get_random_string(32)
        response=self.client.post(reverse("admin:portal_user_add"),{"username":"panel-user","full_name":"کاربر پنل","email":"panel@example.com","organizational_unit":"طرح سلامت","job_title":"مدیر پروژه","role":"USER","password1":panel_password,"password2":panel_password,"must_change_password":"on","is_active":"on","_save":"Save"})
        self.assertEqual(response.status_code,302); self.assertTrue(User.objects.filter(username="panel-user",must_change_password=True).exists())
        service=Service.objects.create(code="AUD-01",name="خدمت ممیزی",category=Category.objects.first(),domain="توسعه بازار",full_description="تعریف",initial_response_days=2,delivery_min_days=3,delivery_max_days=5)
        url=reverse("admin:portal_service_change",args=[service.pk]); get_response=self.client.get(url); self.assertEqual(get_response.status_code,200)
        prefix=get_response.context["inline_admin_formsets"][0].formset.prefix
        data={"code":"AUD-01","name":"خدمت ممیزی ویرایش‌شده","category":service.category_id,"domain":"توسعه بازار","short_description":"","full_description":"تعریف ویرایش‌شده","purpose":"","scope":"","deliverables":"","required_inputs":"","request_requirements":"","process_information":"","excluded":"","service_role":"","acceptance_criteria":"","legacy_sla":"","default_owner":"","initial_response_days":2,"review_target_days":"","delivery_min_days":3,"delivery_max_days":5,"maximum_duration_days":"","supports_desired_date":"on","active":"on","display_order":0,"_save":"Save",f"{prefix}-TOTAL_FORMS":0,f"{prefix}-INITIAL_FORMS":0,f"{prefix}-MIN_NUM_FORMS":0,f"{prefix}-MAX_NUM_FORMS":1000}
        response=self.client.post(url,data)
        self.assertEqual(response.status_code,302); service.refresh_from_db(); self.assertEqual(service.name,"خدمت ممیزی ویرایش‌شده"); self.assertTrue(ActivityLog.objects.filter(actor=self.admin,action="ADMIN_UPDATED",target_id=str(service.pk)).exists())
        call_command("seed_catalog",verbosity=0); service.refresh_from_db(); self.assertEqual(service.name,"خدمت ممیزی ویرایش‌شده")
        calendar_response=self.client.get(reverse("admin:portal_nonworkingdate_add")); self.assertContains(calendar_response,"date-trigger"); self.assertContains(calendar_response,"jalali.js")

    def test_admin_can_edit_role_and_deactivate_user(self):
        target=User.objects.create_user(username="managed-user",password=TEST_PASSWORD,full_name="کاربر قابل مدیریت",email="managed@example.com",role=User.Role.USER,must_change_password=False)
        self.client.force_login(self.admin)
        response=self.client.post(reverse("admin:portal_user_change",args=[target.pk]),{
            "username":target.username,"full_name":target.full_name,"email":target.email,"mobile":"","organizational_unit":"طرح سلامت","job_title":"مدیر پروژه",
            "role":User.Role.REQUEST_MANAGER,"must_change_password":"on","_save":"Save",
        })
        self.assertEqual(response.status_code,302)
        target.refresh_from_db()
        self.assertEqual(target.role,User.Role.REQUEST_MANAGER)
        self.assertTrue(target.is_staff)
        self.assertFalse(target.is_active)
        self.assertTrue(target.must_change_password)

    def test_incomplete_draft_persists_but_cannot_submit(self):
        self.client.force_login(self.user)
        response=self.client.post(reverse("request_create",args=[self.service.pk]),{"action":"draft","project":"","title":"","priority":"NORMAL","desired_delivery_date":""}); self.assertEqual(response.status_code,302)
        draft=Request.objects.filter(requester=self.user,status=Request.Status.DRAFT).latest("created_at"); self.assertEqual(draft.title,"")
        response=self.client.post(reverse("submit_request",args=[draft.pk])); draft.refresh_from_db(); self.assertEqual(draft.status,Request.Status.DRAFT); self.assertRedirects(response,reverse("request_edit",args=[draft.pk]))

    def test_dynamic_date_number_and_multiselect_are_json_safe(self):
        service=Service.objects.create(code="FORM-01",name="فرم پویا",category=Category.objects.first(),domain="توسعه بازار",full_description="فرم")
        ServiceFormField.objects.create(service=service,key="event_date",label="تاریخ رویداد",field_type="date",required=True)
        ServiceFormField.objects.create(service=service,key="budget",label="بودجه",field_type="number",required=True,display_order=1)
        ServiceFormField.objects.create(service=service,key="channels",label="کانال‌ها",field_type="multiselect",required=True,options=["وب","رویداد"],display_order=2)
        self.client.force_login(self.user); payload={"action":"submit","project":"پروژه","title":"فرم پویا","priority":"NORMAL","desired_delivery_date":str(timezone.localdate()+timedelta(days=20)),"data_event_date":"2026-10-07","data_budget":"125.50","data_channels":["وب","رویداد"]}
        response=self.client.post(reverse("request_create",args=[service.pk]),payload); self.assertEqual(response.status_code,302)
        item=Request.objects.get(title="فرم پویا"); self.assertEqual(item.status,Request.Status.SUBMITTED); self.assertEqual(item.request_data["event_date"],"2026-10-07"); self.assertEqual(item.request_data["budget"],"125.50"); self.assertEqual(item.request_data["channels"],["وب","رویداد"])

    def test_weak_initial_admin_password_is_rejected(self):
        with patch.dict("os.environ",{"INITIAL_ADMIN_USERNAME":"weak-admin","INITIAL_ADMIN_PASSWORD":"1234567890"},clear=False):
            with self.assertRaises(CommandError): call_command("create_initial_admin")

class EndToEndFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog",verbosity=0); cls.service=Service.objects.first(); cls.service.default_owner=None; cls.service.save()
        cls.user=User.objects.create_user(username="flow-user",password=TEST_PASSWORD,full_name="درخواست‌دهنده",organizational_unit="طرح کشاورزی",role=User.Role.USER,must_change_password=False)
        cls.manager=User.objects.create_user(username="flow-manager",password=TEST_PASSWORD,full_name="رسیدگی‌کننده",role=User.Role.REQUEST_MANAGER,must_change_password=False)
    def payload(self):
        data={"project":"پروژه جریان کامل","title":"درخواست جریان کامل","priority":"HIGH","desired_delivery_date":str(timezone.localdate()+timedelta(days=30))}
        for f in self.service.form_fields.filter(active=True,required=True): data[f"data_{f.key}"]="اطلاعات آزمون"
        return data
    def test_complete_user_and_manager_flow(self):
        self.assertTrue(self.client.login(username="flow-user",password=TEST_PASSWORD))
        self.assertEqual(self.client.get(reverse("catalog")+"?q="+self.service.code).status_code,200)
        response=self.client.post(reverse("request_create",args=[self.service.pk]),self.payload()|{"action":"draft"}); self.assertEqual(response.status_code,302)
        item=Request.objects.get(title="درخواست جریان کامل"); self.client.logout(); self.client.login(username="flow-user",password=TEST_PASSWORD)
        self.assertContains(self.client.get(reverse("request_detail",args=[item.pk])),"درخواست جریان کامل")
        self.client.post(reverse("submit_request",args=[item.pk])); item.refresh_from_db(); self.assertEqual(item.status,Request.Status.SUBMITTED)
        self.client.logout(); self.client.login(username="flow-manager",password=TEST_PASSWORD)
        self.client.post(reverse("control_action",args=[item.pk]),{"kind":"action","owner":self.manager.pk,"status":"UNDER_REVIEW"})
        self.client.post(reverse("control_action",args=[item.pk]),{"kind":"message","body":"مدرک زمان‌بندی را ارسال کنید.","request_info":"1"}); item.refresh_from_db(); self.assertTrue(item.needs_user_action)
        self.assertTrue(Notification.objects.filter(user=self.user,request=item,read_at__isnull=True).exists())
        self.client.logout(); self.client.login(username="flow-user",password=TEST_PASSWORD)
        upload=SimpleUploadedFile("plan.pdf",b"test-pdf",content_type="application/pdf")
        self.client.post(reverse("add_message",args=[item.pk]),{"body":"مدرک پیوست شد.","file":upload}); item.refresh_from_db(); self.assertEqual(item.status,Request.Status.UNDER_REVIEW); self.assertFalse(item.needs_user_action); self.assertEqual(item.attachments.count(),1)
        self.client.logout(); self.client.login(username="flow-manager",password=TEST_PASSWORD)
        self.client.post(reverse("control_action",args=[item.pk]),{"kind":"action","owner":self.manager.pk,"status":"IN_PROGRESS"})
        self.client.post(reverse("control_action",args=[item.pk]),{"kind":"action","owner":self.manager.pk,"status":"COMPLETED"}); item.refresh_from_db(); self.assertEqual(item.status,Request.Status.COMPLETED); self.assertIsNotNone(item.completed_at); self.assertGreater(item.history.count(),5); self.assertTrue(ActivityLog.objects.filter(target_id=str(item.pk),action="STATUS_CHANGED").exists())

    def test_requester_comment_attachment_manager_round_trip(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.service.default_owner=self.manager; self.service.save(update_fields=["default_owner"])
            self.client.force_login(self.user)
            self.client.post(reverse("request_create",args=[self.service.pk]),self.payload()|{"action":"submit"})
            item=Request.objects.get(title="درخواست جریان کامل")
            upload=SimpleUploadedFile("requester-evidence.png",b"image-bytes",content_type="image/png")
            response=self.client.post(reverse("add_message",args=[item.pk]),{"body":"توضیح و تصویر درخواست‌دهنده","file":upload})
            self.assertRedirects(response,reverse("request_detail",args=[item.pk]))
            attachment=item.attachments.get(original_name="requester-evidence.png")
            self.assertEqual(attachment.response.author,self.user)

            self.client.force_login(self.manager)
            manager_detail=self.client.get(reverse("control_request_detail",args=[item.pk]))
            self.assertEqual(manager_detail.status_code,200)
            self.assertContains(manager_detail,"توضیح و تصویر درخواست‌دهنده")
            self.assertContains(manager_detail,"requester-evidence.png")
            download=self.client.get(reverse("attachment_download",args=[attachment.pk]))
            self.assertEqual(download.status_code,200)
            self.assertEqual(b"".join(download.streaming_content),b"image-bytes")
            self.client.post(reverse("control_action",args=[item.pk]),{"kind":"message","body":"پاسخ مدیر درخواست"})
            self.client.post(reverse("control_action",args=[item.pk]),{"kind":"note","body":"یادداشت محرمانه مدیر"})

            self.client.force_login(self.user)
            requester_detail=self.client.get(reverse("request_detail",args=[item.pk]))
            self.assertContains(requester_detail,"پاسخ مدیر درخواست")
            self.assertContains(requester_detail,"توضیح و تصویر درخواست‌دهنده")
            self.assertContains(requester_detail,"requester-evidence.png")
            self.assertNotContains(requester_detail,"یادداشت محرمانه مدیر")

    def test_request_form_uses_proportional_action_buttons(self):
        self.client.force_login(self.user)
        response=self.client.get(reverse("request_create",args=[self.service.pk]))
        self.assertContains(response,'class="btn btn-md btn-tertiary"')
        self.assertContains(response,'name="action" value="draft" class="btn btn-md secondary"')
        self.assertContains(response,'name="action" value="submit" class="btn btn-lg primary"')
