import uuid
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

class User(AbstractUser):
    class Role(models.TextChoices): USER="USER","کاربر"; REQUEST_MANAGER="REQUEST_MANAGER","مدیر درخواست"; ADMIN="ADMIN","مدیر سامانه"
    full_name=models.CharField("نام و نام خانوادگی",max_length=160)
    email=models.EmailField("ایمیل سازمانی")
    mobile=models.CharField("شماره همراه",max_length=20,blank=True)
    organizational_unit=models.CharField("واحد سازمانی",max_length=160,blank=True)
    job_title=models.CharField("عنوان شغلی",max_length=160,blank=True)
    role=models.CharField("نقش",max_length=24,choices=Role.choices,default=Role.USER,db_index=True)
    must_change_password=models.BooleanField("تغییر اجباری رمز",default=True)
    last_activity_at=models.DateTimeField(null=True,blank=True)
    def save(self,*a,**kw):
        self.is_staff=self.role in {self.Role.ADMIN,self.Role.REQUEST_MANAGER}
        self.is_superuser=self.role==self.Role.ADMIN
        super().save(*a,**kw)
    def __str__(self): return self.full_name or self.username

class Timestamped(models.Model):
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: abstract=True

class Category(Timestamped):
    name=models.CharField(max_length=160,unique=True); slug=models.SlugField(max_length=180,unique=True,allow_unicode=True)
    description=models.TextField(blank=True); active=models.BooleanField(default=True); display_order=models.PositiveIntegerField(default=0)
    class Meta: ordering=["display_order","name"]; verbose_name_plural="دسته‌بندی‌ها"
    def __str__(self): return self.name

class Service(Timestamped):
    code=models.CharField(max_length=20,unique=True); name=models.CharField(max_length=200); category=models.ForeignKey(Category,on_delete=models.PROTECT,related_name="services")
    domain=models.CharField(max_length=160); short_description=models.TextField(blank=True); full_description=models.TextField()
    purpose=models.TextField(blank=True); scope=models.TextField(blank=True); deliverables=models.TextField(blank=True); required_inputs=models.TextField(blank=True)
    request_requirements=models.TextField(blank=True); process_information=models.TextField(blank=True); excluded=models.TextField(blank=True)
    service_role=models.CharField(max_length=160,blank=True); acceptance_criteria=models.TextField(blank=True); legacy_sla=models.CharField(max_length=250,blank=True)
    default_owner=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="owned_services")
    initial_response_days=models.PositiveSmallIntegerField(default=2,validators=[MinValueValidator(1)])
    review_target_days=models.PositiveSmallIntegerField(null=True,blank=True)
    delivery_min_days=models.PositiveSmallIntegerField(default=5); delivery_max_days=models.PositiveSmallIntegerField(default=10)
    maximum_duration_days=models.PositiveSmallIntegerField(null=True,blank=True)
    supports_desired_date=models.BooleanField(default=True); active=models.BooleanField(default=True); display_order=models.PositiveIntegerField(default=0)
    class Meta: ordering=["category__display_order","display_order","code"]; indexes=[models.Index(fields=["active","category"])]
    def __str__(self): return f"{self.code} · {self.name}"

class ServiceFormField(Timestamped):
    class FieldType(models.TextChoices): TEXT="text","متن کوتاه"; TEXTAREA="textarea","متن بلند"; NUMBER="number","عدد"; DATE="date","تاریخ"; SELECT="select","انتخاب"; MULTISELECT="multiselect","چندانتخابی"; CHECKBOX="checkbox","تأیید"; EMAIL="email","ایمیل"; FILE="file","فایل"
    service=models.ForeignKey(Service,on_delete=models.CASCADE,related_name="form_fields"); key=models.SlugField(max_length=80,allow_unicode=False)
    label=models.CharField(max_length=200); field_type=models.CharField(max_length=20,choices=FieldType.choices); required=models.BooleanField(default=False)
    placeholder=models.CharField(max_length=250,blank=True); help_text=models.CharField(max_length=500,blank=True); options=models.JSONField(default=list,blank=True); display_order=models.PositiveIntegerField(default=0); active=models.BooleanField(default=True)
    class Meta: ordering=["display_order","id"]; constraints=[models.UniqueConstraint(fields=["service","key"],name="unique_service_field")]
    def __str__(self): return f"{self.service.code} · {self.label}"

class WorkingCalendar(Timestamped):
    name=models.CharField(max_length=100,default="تقویم کاری اصلی"); weekend_days=models.JSONField(default=list,help_text="شماره روزهای تعطیل پایتون؛ دوشنبه ۰ و جمعه ۴")
    workday_start=models.TimeField(default="08:00"); workday_end=models.TimeField(default="16:00"); active=models.BooleanField(default=True)
    def __str__(self): return self.name

class NonWorkingDate(Timestamped):
    calendar=models.ForeignKey(WorkingCalendar,on_delete=models.CASCADE,related_name="non_working_dates"); date=models.DateField(); title=models.CharField(max_length=200)
    class Meta: constraints=[models.UniqueConstraint(fields=["calendar","date"],name="unique_non_working_date")]
    def __str__(self): return f"{self.date}: {self.title}"

class Request(Timestamped):
    class Status(models.TextChoices): DRAFT="DRAFT","پیش‌نویس"; SUBMITTED="SUBMITTED","ثبت‌شده"; UNDER_REVIEW="UNDER_REVIEW","در حال بررسی"; NEED_INFO="NEED_INFO","نیازمند اطلاعات تکمیلی"; ACCEPTED="ACCEPTED","پذیرفته‌شده"; IN_PROGRESS="IN_PROGRESS","در حال انجام"; ON_HOLD="ON_HOLD","متوقف‌شده"; COMPLETED="COMPLETED","تکمیل‌شده"; REJECTED="REJECTED","ردشده"; CANCELLED="CANCELLED","لغوشده"
    class Priority(models.TextChoices): LOW="LOW","کم"; NORMAL="NORMAL","عادی"; HIGH="HIGH","زیاد"; URGENT="URGENT","فوری"
    TRANSITIONS={
        Status.SUBMITTED:{Status.UNDER_REVIEW,Status.NEED_INFO,Status.ACCEPTED,Status.ON_HOLD,Status.REJECTED,Status.CANCELLED},
        Status.UNDER_REVIEW:{Status.NEED_INFO,Status.ACCEPTED,Status.IN_PROGRESS,Status.ON_HOLD,Status.REJECTED,Status.CANCELLED},
        Status.NEED_INFO:{Status.UNDER_REVIEW,Status.ON_HOLD,Status.CANCELLED},
        Status.ACCEPTED:{Status.NEED_INFO,Status.IN_PROGRESS,Status.ON_HOLD,Status.CANCELLED},
        Status.IN_PROGRESS:{Status.NEED_INFO,Status.ON_HOLD,Status.COMPLETED,Status.CANCELLED},
        Status.ON_HOLD:{Status.UNDER_REVIEW,Status.ACCEPTED,Status.IN_PROGRESS,Status.REJECTED,Status.CANCELLED},
    }
    public_id=models.CharField(max_length=32,unique=True,editable=False,db_index=True); requester=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="requests")
    requesting_unit=models.CharField(max_length=160); service=models.ForeignKey(Service,on_delete=models.PROTECT,related_name="requests"); project=models.CharField(max_length=200)
    title=models.CharField(max_length=250); request_data=models.JSONField(default=dict); desired_delivery_date=models.DateField(null=True,blank=True)
    priority=models.CharField(max_length=12,choices=Priority.choices,default=Priority.NORMAL); status=models.CharField(max_length=20,choices=Status.choices,default=Status.DRAFT,db_index=True)
    assigned_owner=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="assigned_requests")
    submitted_at=models.DateTimeField(null=True,blank=True); first_response_at=models.DateTimeField(null=True,blank=True); current_stage_started_at=models.DateTimeField(default=timezone.now); completed_at=models.DateTimeField(null=True,blank=True)
    expected_initial_response_at=models.DateTimeField(null=True,blank=True); estimated_delivery_min=models.DateField(null=True,blank=True); estimated_delivery_max=models.DateField(null=True,blank=True)
    operational_paused_at=models.DateTimeField(null=True,blank=True); paused_seconds=models.PositiveBigIntegerField(default=0); needs_user_action=models.BooleanField(default=False,db_index=True)
    class Meta: ordering=["-updated_at"]; indexes=[models.Index(fields=["requester","status"]),models.Index(fields=["assigned_owner","status"])]
    def save(self,*a,**kw):
        if not self.public_id:
            today=timezone.localdate().strftime("%Y%m%d")
            self.public_id=f"MKT-{today}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*a,**kw)
    @property
    def is_overdue(self):
        if self.status in {self.Status.COMPLETED,self.Status.REJECTED,self.Status.CANCELLED,self.Status.DRAFT}: return False
        if self.operational_paused_at: return False
        if not self.first_response_at: return bool(self.expected_initial_response_at and timezone.now()>self.expected_initial_response_at)
        return bool(self.estimated_delivery_max and timezone.localdate()>self.estimated_delivery_max)
    @property
    def operational_elapsed_seconds(self):
        if not self.submitted_at:return 0
        end=self.completed_at or timezone.now(); cal=WorkingCalendar.objects.filter(active=True).first()
        if not cal:return max(0,int((end-self.submitted_at).total_seconds())-self.paused_seconds)
        blocked=set(cal.non_working_dates.values_list("date",flat=True))
        def working_seconds(start,finish):
            if not start or finish<=start:return 0
            start=timezone.localtime(start); finish=timezone.localtime(finish); current=start.date(); total=0
            while current<=finish.date():
                if current.weekday() not in cal.weekend_days and current not in blocked:
                    day_start=timezone.make_aware(datetime.combine(current,cal.workday_start)); day_end=timezone.make_aware(datetime.combine(current,cal.workday_end))
                    total+=max(0,int((min(finish,day_end)-max(start,day_start)).total_seconds()))
                current+=timedelta(days=1)
            return total
        total=working_seconds(self.submitted_at,end); pause_start=None; paused=0
        for event in self.history.filter(action__in=["CLOCK_PAUSED","CLOCK_RESUMED"]).order_by("created_at"):
            if event.action=="CLOCK_PAUSED" and pause_start is None: pause_start=event.created_at
            elif event.action=="CLOCK_RESUMED" and pause_start is not None: paused+=working_seconds(pause_start,event.created_at); pause_start=None
        if pause_start is not None: paused+=working_seconds(pause_start,end)
        return max(0,total-paused)
    @property
    def brief_items(self):
        labels={f.key:f.label for f in self.service.form_fields.all()}
        return [(labels.get(k,k), "، ".join(v) if isinstance(v,list) else ("بله" if v is True else "خیر" if v is False else v)) for k,v in self.request_data.items()]
    def __str__(self): return self.public_id
    def allowed_transitions(self): return self.TRANSITIONS.get(self.status,set())

class RequestResponse(Timestamped):
    request=models.ForeignKey(Request,on_delete=models.CASCADE,related_name="responses"); author=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); body=models.TextField(); requests_information=models.BooleanField(default=False)
    class Meta: ordering=["created_at"]

def upload_path(instance,filename): return f"requests/{instance.request.public_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
class Attachment(Timestamped):
    request=models.ForeignKey(Request,on_delete=models.CASCADE,related_name="attachments"); uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); file=models.FileField(upload_to=upload_path); original_name=models.CharField(max_length=255); size=models.PositiveBigIntegerField(); content_type=models.CharField(max_length=120); response=models.ForeignKey(RequestResponse,null=True,blank=True,on_delete=models.CASCADE,related_name="attachments")

class InternalNote(Timestamped):
    request=models.ForeignKey(Request,on_delete=models.CASCADE,related_name="internal_notes"); author=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); body=models.TextField()
    class Meta: ordering=["created_at"]

class RequestHistory(models.Model):
    request=models.ForeignKey(Request,on_delete=models.CASCADE,related_name="history"); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL); action=models.CharField(max_length=80); from_status=models.CharField(max_length=20,blank=True); to_status=models.CharField(max_length=20,blank=True); metadata=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["created_at"]

class ActivityLog(models.Model):
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL); action=models.CharField(max_length=100); target_type=models.CharField(max_length=60); target_id=models.CharField(max_length=80); metadata=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at"]

class Notification(Timestamped):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="notifications"); title=models.CharField(max_length=200); body=models.CharField(max_length=500,blank=True); request=models.ForeignKey(Request,null=True,blank=True,on_delete=models.CASCADE); read_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=["-created_at"]

class AppSetting(Timestamped):
    key=models.CharField(max_length=100,unique=True); value=models.JSONField(default=dict)
    def __str__(self): return self.key

class LoginThrottle(models.Model):
    key=models.CharField(max_length=64,unique=True); failures=models.PositiveSmallIntegerField(default=0); locked_until=models.DateTimeField(null=True,blank=True); updated_at=models.DateTimeField(auto_now=True)
