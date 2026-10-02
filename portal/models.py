import uuid
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.utils import OperationalError, ProgrammingError
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
        scoped_super_admin=False
        if self.pk:
            try:
                scoped_super_admin=self.role_assignments.filter(role="SUPER_ADMIN",scope_type="GLOBAL",is_active=True).exists()
            except (OperationalError,ProgrammingError):
                pass
        self.is_staff=self.role in {self.Role.ADMIN,self.Role.REQUEST_MANAGER} or scoped_super_admin
        self.is_superuser=self.role==self.Role.ADMIN or scoped_super_admin
        super().save(*a,**kw)
    def __str__(self): return self.full_name or self.username

class Timestamped(models.Model):
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: abstract=True

class Department(Timestamped):
    class Status(models.TextChoices):
        DRAFT="DRAFT","پیش‌نویس"
        PUBLISHED="PUBLISHED","منتشرشده"
        DISABLED="DISABLED","غیرفعال"
        TEMPORARILY_DISABLED="TEMPORARILY_DISABLED","موقتاً غیرفعال"
        ARCHIVED="ARCHIVED","بایگانی‌شده"
    code=models.SlugField(max_length=64,unique=True)
    name=models.CharField(max_length=200)
    short_name=models.CharField(max_length=100,blank=True)
    description=models.TextField(blank=True)
    intro_text=models.TextField(blank=True)
    icon_name=models.CharField(max_length=40,blank=True)
    cover_image=models.FileField(upload_to="departments/covers/",blank=True)
    status=models.CharField(max_length=24,choices=Status.choices,default=Status.DRAFT,db_index=True)
    display_order=models.PositiveIntegerField(default=0)
    class Meta:
        ordering=["display_order","name"]
        constraints=[models.CheckConstraint(condition=models.Q(status__in=["DRAFT","PUBLISHED","DISABLED","TEMPORARILY_DISABLED","ARCHIVED"]),name="valid_department_status")]
    @property
    def is_requestable(self): return self.status==self.Status.PUBLISHED
    def __str__(self): return self.short_name or self.name

class Program(Timestamped):
    class Status(models.TextChoices):
        DRAFT="DRAFT","پیش‌نویس"
        ACTIVE="ACTIVE","فعال"
        DISABLED="DISABLED","غیرفعال"
        ARCHIVED="ARCHIVED","بایگانی‌شده"
    code=models.SlugField(max_length=64,unique=True)
    name=models.CharField(max_length=200)
    description=models.TextField(blank=True)
    status=models.CharField(max_length=16,choices=Status.choices,default=Status.DRAFT,db_index=True)
    class Meta:
        ordering=["name"]
        constraints=[models.CheckConstraint(condition=models.Q(status__in=["DRAFT","ACTIVE","DISABLED","ARCHIVED"]),name="valid_program_status")]
        indexes=[models.Index(fields=["status","code"],name="portal_prog_status_code_idx")]
    def clean(self):
        super().clean()
        if not self.pk and self.status != self.Status.DRAFT:
            raise ValidationError({"status":"طرح جدید باید ابتدا در وضعیت پیش‌نویس ایجاد شود."})
        if self.pk:
            old=Program.objects.filter(pk=self.pk).values_list("status",flat=True).first()
            allowed={self.Status.DRAFT:{self.Status.ACTIVE},self.Status.ACTIVE:{self.Status.DISABLED,self.Status.ARCHIVED},self.Status.DISABLED:{self.Status.ACTIVE,self.Status.ARCHIVED},self.Status.ARCHIVED:set()}
            if old and self.status!=old and self.status not in allowed[old]:
                raise ValidationError({"status":"تغییر وضعیت طرح با چرخهٔ عمر آن سازگار نیست."})
        if self.status==self.Status.ARCHIVED and self.pk and self.projects.filter(status=Project.Status.ACTIVE).exists():
            raise ValidationError({"status":"ابتدا پروژه‌های فعال را غیرفعال یا بایگانی کنید."})
    def save(self,*args,**kwargs):
        self.full_clean()
        return super().save(*args,**kwargs)
    def __str__(self): return self.name

class Project(Timestamped):
    class Status(models.TextChoices):
        DRAFT="DRAFT","پیش‌نویس"
        ACTIVE="ACTIVE","فعال"
        DISABLED="DISABLED","غیرفعال"
        ARCHIVED="ARCHIVED","بایگانی‌شده"
    code=models.SlugField(max_length=64,unique=True)
    name=models.CharField(max_length=200)
    program=models.ForeignKey(Program,on_delete=models.PROTECT,related_name="projects")
    description=models.TextField(blank=True)
    status=models.CharField(max_length=16,choices=Status.choices,default=Status.DRAFT,db_index=True)
    class Meta:
        ordering=["program__name","name"]
        constraints=[models.CheckConstraint(condition=models.Q(status__in=["DRAFT","ACTIVE","DISABLED","ARCHIVED"]),name="valid_project_status")]
        indexes=[models.Index(fields=["program","status"],name="portal_proj_prog_status_idx")]
    @property
    def is_requestable(self):
        return self.status==self.Status.ACTIVE and self.program.status==Program.Status.ACTIVE
    def clean(self):
        super().clean()
        if not self.pk and self.status != self.Status.DRAFT:
            raise ValidationError({"status":"پروژهٔ جدید باید ابتدا در وضعیت پیش‌نویس ایجاد شود."})
        if self.pk:
            old=Project.objects.filter(pk=self.pk).values("status","program_id").first()
            allowed={self.Status.DRAFT:{self.Status.ACTIVE},self.Status.ACTIVE:{self.Status.DISABLED,self.Status.ARCHIVED},self.Status.DISABLED:{self.Status.ACTIVE,self.Status.ARCHIVED},self.Status.ARCHIVED:set()}
            if old and self.status!=old["status"] and self.status not in allowed[old["status"]]:
                raise ValidationError({"status":"تغییر وضعیت پروژه با چرخهٔ عمر آن سازگار نیست."})
            if old and self.program_id!=old["program_id"]:
                raise ValidationError({"program":"طرح والد پروژه پس از ایجاد قابل تغییر نیست."})
        if self.status==self.Status.ACTIVE and self.program_id and self.program.status!=Program.Status.ACTIVE:
            raise ValidationError({"status":"پروژه فقط زیر یک طرح فعال می‌تواند فعال شود."})
    def save(self,*args,**kwargs):
        self.full_clean()
        return super().save(*args,**kwargs)
    def __str__(self): return f"{self.program.name} · {self.name}"

class RoleAssignment(Timestamped):
    class Role(models.TextChoices):
        REQUESTER="REQUESTER","درخواست‌دهنده"
        REQUEST_MANAGER="REQUEST_MANAGER","مدیر درخواست"
        DEPARTMENT_LEAD="DEPARTMENT_LEAD","مدیر اداره"
        SUPERVISOR="SUPERVISOR","ناظر"
        EXECUTIVE_VIEWER="EXECUTIVE_VIEWER","مشاهده‌گر ارشد"
        SUPER_ADMIN="SUPER_ADMIN","مدیر ارشد سامانه"
        PROGRAM_MANAGER="PROGRAM_MANAGER","مدیر طرح"
        PROJECT_MANAGER="PROJECT_MANAGER","مدیر پروژه"
        SENIOR_APPROVAL_AUTHORITY="SENIOR_APPROVAL_AUTHORITY","مرجع تأیید ارشد"
    class ScopeType(models.TextChoices):
        GLOBAL="GLOBAL","سراسری"
        DEPARTMENT="DEPARTMENT","اداره"
        PROGRAM="PROGRAM","طرح"
        PROJECT="PROJECT","پروژه"
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="role_assignments")
    role=models.CharField(max_length=32,choices=Role.choices,db_index=True)
    scope_type=models.CharField(max_length=16,choices=ScopeType.choices,db_index=True)
    department=models.ForeignKey(Department,null=True,blank=True,on_delete=models.PROTECT,related_name="role_assignments")
    program=models.ForeignKey(Program,null=True,blank=True,on_delete=models.PROTECT,related_name="role_assignments")
    project=models.ForeignKey(Project,null=True,blank=True,on_delete=models.PROTECT,related_name="role_assignments")
    is_active=models.BooleanField(default=True,db_index=True)
    deactivated_at=models.DateTimeField(null=True,blank=True)
    assigned_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="assigned_roles")
    class Meta:
        ordering=["user__username","role"]
        constraints=[
            models.CheckConstraint(condition=(models.Q(scope_type="GLOBAL",department__isnull=True,program__isnull=True,project__isnull=True)|models.Q(scope_type="DEPARTMENT",department__isnull=False,program__isnull=True,project__isnull=True)|models.Q(scope_type="PROGRAM",department__isnull=True,program__isnull=False,project__isnull=True)|models.Q(scope_type="PROJECT",department__isnull=True,program__isnull=False,project__isnull=False)),name="role_assignment_scope_target"),
            models.CheckConstraint(condition=(models.Q(scope_type="GLOBAL",role__in=["REQUESTER","SUPERVISOR","EXECUTIVE_VIEWER","SUPER_ADMIN","SENIOR_APPROVAL_AUTHORITY"])|models.Q(scope_type="DEPARTMENT",role__in=["REQUEST_MANAGER","DEPARTMENT_LEAD"])|models.Q(scope_type="PROGRAM",role="PROGRAM_MANAGER")|models.Q(scope_type="PROJECT",role="PROJECT_MANAGER")),name="role_assignment_role_scope"),
            models.UniqueConstraint(fields=["user","role","scope_type"],condition=models.Q(scope_type="GLOBAL"),name="unique_global_role_assignment"),
            models.UniqueConstraint(fields=["user","role","department"],condition=models.Q(scope_type="DEPARTMENT"),name="unique_department_role_assignment"),
            models.UniqueConstraint(fields=["user","role","program"],condition=models.Q(scope_type="PROGRAM"),name="unique_program_role_assignment"),
            models.UniqueConstraint(fields=["user","role","project"],condition=models.Q(scope_type="PROJECT"),name="unique_project_role_assignment"),
        ]
        indexes=[models.Index(fields=["department","role","is_active"],name="portal_role_departm_a46b0d_idx"),models.Index(fields=["user","scope_type","is_active"],name="portal_role_user_id_9e7628_idx"),models.Index(fields=["user","role","program","is_active"],name="portal_role_prog_active_idx"),models.Index(fields=["user","role","project","is_active"],name="portal_role_proj_active_idx")]
    def clean(self):
        super().clean()
        if self.scope_type==self.ScopeType.GLOBAL and self.department_id:
            raise ValidationError({"department":"نقش سراسری نباید اداره داشته باشد."})
        if self.scope_type==self.ScopeType.DEPARTMENT and not self.department_id:
            raise ValidationError({"department":"برای نقش اداره‌ای انتخاب اداره الزامی است."})
        if self.scope_type in {self.ScopeType.GLOBAL,self.ScopeType.DEPARTMENT} and (self.program_id or self.project_id):
            raise ValidationError("نقش و محدودهٔ سازمانی با هم سازگار نیستند.")
        if self.scope_type==self.ScopeType.PROGRAM and (not self.program_id or self.project_id or self.department_id or self.role!=self.Role.PROGRAM_MANAGER):
            raise ValidationError("مدیر طرح باید دقیقاً در محدودهٔ یک طرح تعریف شود.")
        if self.scope_type==self.ScopeType.PROJECT:
            if not self.project_id or not self.program_id or self.department_id or self.role!=self.Role.PROJECT_MANAGER:
                raise ValidationError("مدیر پروژه باید به پروژه و طرح همان پروژه متصل باشد.")
            if self.project.program_id!=self.program_id:
                raise ValidationError({"program":"طرح انتخاب‌شده با پروژه هم‌خوانی ندارد."})
    def save(self,*a,**kw):
        if self.is_active:self.deactivated_at=None
        elif not self.deactivated_at:self.deactivated_at=timezone.now()
        self.full_clean()
        super().save(*a,**kw)
        self.user.save(update_fields=["is_staff","is_superuser"])
    def delete(self,*a,**kw):
        user=self.user
        result=super().delete(*a,**kw)
        user.save(update_fields=["is_staff","is_superuser"])
        return result
    def __str__(self):
        scope=self.department if self.department_id else self.get_scope_type_display()
        return f"{self.user} · {self.get_role_display()} · {scope}"

class Category(Timestamped):
    class Status(models.TextChoices): ACTIVE="ACTIVE","فعال"; DISABLED="DISABLED","غیرفعال"; ARCHIVED="ARCHIVED","بایگانی‌شده"
    name=models.CharField(max_length=160); slug=models.SlugField(max_length=180,allow_unicode=True)
    department=models.ForeignKey(Department,on_delete=models.PROTECT,related_name="service_families")
    description=models.TextField(blank=True); active=models.BooleanField(default=True); lifecycle_status=models.CharField(max_length=12,choices=Status.choices,default=Status.ACTIVE); display_order=models.PositiveIntegerField(default=0)
    class Meta:
        ordering=["department__display_order","display_order","name"]
        verbose_name="خانواده خدمت"
        verbose_name_plural="خانواده‌های خدمت"
        constraints=[models.UniqueConstraint(fields=["department","name"],name="unique_department_category_name"),models.UniqueConstraint(fields=["department","slug"],name="unique_department_category_slug"),models.CheckConstraint(condition=models.Q(lifecycle_status__in=["ACTIVE","DISABLED","ARCHIVED"]),name="valid_category_lifecycle")]
        indexes=[models.Index(fields=["department","active"],name="portal_cate_departm_762dfa_idx")]
    def clean(self):
        super().clean()
        if not self.pk and self.lifecycle_status==self.Status.ARCHIVED:raise ValidationError({"lifecycle_status":"خانوادهٔ جدید را نمی‌توان بایگانی‌شده ساخت."})
        if self.pk and self.department_id:
            old_status=Category.objects.filter(pk=self.pk).values_list("lifecycle_status",flat=True).first()
            allowed={self.Status.ACTIVE:{self.Status.DISABLED,self.Status.ARCHIVED},self.Status.DISABLED:{self.Status.ACTIVE,self.Status.ARCHIVED},self.Status.ARCHIVED:set()}
            if old_status and self.lifecycle_status!=old_status and self.lifecycle_status not in allowed[old_status]:raise ValidationError({"lifecycle_status":"تغییر وضعیت خانواده مجاز نیست."})
            from .policies import can_be_default_owner
            for service in self.services.select_related("default_owner").exclude(default_owner=None):
                if not can_be_default_owner(service.default_owner,self.department):
                    raise ValidationError({"department":f"مسئول پیش‌فرض خدمت {service.code} عضو اداره مقصد نیست."})
    def save(self,*a,**kw):
        if self.lifecycle_status!=self.Status.ACTIVE:self.active=False
        elif not self.active:self.lifecycle_status=self.Status.DISABLED
        self.full_clean()
        super().save(*a,**kw)
    def __str__(self): return self.name

class Service(Timestamped):
    class Status(models.TextChoices): ACTIVE="ACTIVE","فعال"; DISABLED="DISABLED","غیرفعال"; ARCHIVED="ARCHIVED","بایگانی‌شده"
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
    supports_desired_date=models.BooleanField(default=True); active=models.BooleanField(default=True); lifecycle_status=models.CharField(max_length=12,choices=Status.choices,default=Status.ACTIVE); display_order=models.PositiveIntegerField(default=0)
    class Meta: ordering=["category__display_order","display_order","code"]; indexes=[models.Index(fields=["active","category"])]; constraints=[models.CheckConstraint(condition=models.Q(lifecycle_status__in=["ACTIVE","DISABLED","ARCHIVED"]),name="valid_service_lifecycle")]
    @property
    def department(self): return self.category.department
    @property
    def is_requestable(self): return self.active and self.lifecycle_status==self.Status.ACTIVE and self.category.active and self.category.lifecycle_status==Category.Status.ACTIVE and self.category.department.is_requestable
    def clean(self):
        super().clean()
        if not self.pk and self.lifecycle_status==self.Status.ARCHIVED:raise ValidationError({"lifecycle_status":"خدمت جدید را نمی‌توان بایگانی‌شده ساخت."})
        if self.pk:
            old_status=Service.objects.filter(pk=self.pk).values_list("lifecycle_status",flat=True).first()
            allowed={self.Status.ACTIVE:{self.Status.DISABLED,self.Status.ARCHIVED},self.Status.DISABLED:{self.Status.ACTIVE,self.Status.ARCHIVED},self.Status.ARCHIVED:set()}
            if old_status and self.lifecycle_status!=old_status and self.lifecycle_status not in allowed[old_status]:raise ValidationError({"lifecycle_status":"تغییر وضعیت خدمت مجاز نیست."})
        if self.delivery_min_days and self.delivery_max_days and self.delivery_max_days<self.delivery_min_days:
            raise ValidationError({"delivery_max_days":"حداکثر زمان انجام باید برابر یا بیشتر از حداقل باشد."})
        if self.default_owner_id:
            from .policies import can_be_default_owner
            if not can_be_default_owner(self.default_owner,self.category.department):
                raise ValidationError({"default_owner":"مسئول پیش‌فرض باید مدیر درخواست یا مدیر همین اداره باشد."})
    def save(self,*a,**kw):
        if self.lifecycle_status!=self.Status.ACTIVE:self.active=False
        elif not self.active:self.lifecycle_status=self.Status.DISABLED
        self.full_clean()
        super().save(*a,**kw)
    def __str__(self): return f"{self.code} · {self.name}"

class ServiceFormField(Timestamped):
    class FieldType(models.TextChoices): TEXT="text","متن کوتاه"; TEXTAREA="textarea","متن بلند"; NUMBER="number","عدد"; DATE="date","تاریخ"; SELECT="select","انتخاب"; RADIO="radio","گزینه‌های رادیویی"; MULTISELECT="multiselect","چندانتخابی"; CHECKBOX="checkbox","تأیید"; EMAIL="email","ایمیل"; PHONE="phone","تلفن"; FILE="file","فایل"
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
    class Priority(models.TextChoices): LOW="LOW","کم"; NORMAL="NORMAL","عادی"; HIGH="HIGH","زیاد"; URGENT="URGENT","فوری"; VERY_URGENT="VERY_URGENT","خیلی فوری"; EMERGENCY="EMERGENCY","اضطراری"
    TRANSITIONS={
        Status.SUBMITTED:{Status.UNDER_REVIEW,Status.NEED_INFO,Status.ACCEPTED,Status.ON_HOLD,Status.REJECTED,Status.CANCELLED},
        Status.UNDER_REVIEW:{Status.NEED_INFO,Status.ACCEPTED,Status.IN_PROGRESS,Status.ON_HOLD,Status.REJECTED,Status.CANCELLED},
        Status.NEED_INFO:{Status.UNDER_REVIEW,Status.ON_HOLD,Status.CANCELLED},
        Status.ACCEPTED:{Status.NEED_INFO,Status.IN_PROGRESS,Status.ON_HOLD,Status.CANCELLED},
        Status.IN_PROGRESS:{Status.NEED_INFO,Status.ON_HOLD,Status.COMPLETED,Status.CANCELLED},
        Status.ON_HOLD:{Status.UNDER_REVIEW,Status.ACCEPTED,Status.IN_PROGRESS,Status.REJECTED,Status.CANCELLED},
    }
    public_id=models.CharField(max_length=32,unique=True,editable=False,db_index=True); requester=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="requests")
    department=models.ForeignKey(Department,on_delete=models.PROTECT,related_name="requests")
    program=models.ForeignKey(Program,null=True,blank=True,on_delete=models.PROTECT,related_name="requests")
    project_entity=models.ForeignKey(Project,null=True,blank=True,on_delete=models.PROTECT,related_name="requests")
    requester_role_context=models.CharField(max_length=32,blank=True,default="")
    requester_role_at_submission=models.CharField(max_length=32,blank=True,default="")
    program_name_snapshot=models.CharField(max_length=200,blank=True,default="")
    program_code_snapshot=models.CharField(max_length=64,blank=True,default="")
    project_name_snapshot=models.CharField(max_length=200,blank=True,default="")
    project_code_snapshot=models.CharField(max_length=64,blank=True,default="")
    requesting_unit=models.CharField(max_length=160); service=models.ForeignKey(Service,on_delete=models.PROTECT,related_name="requests"); project=models.CharField(max_length=200)
    title=models.CharField(max_length=250); request_data=models.JSONField(default=dict); catalogue_snapshot=models.JSONField(default=dict,blank=True); desired_delivery_date=models.DateField(null=True,blank=True)
    priority=models.CharField(max_length=16,choices=Priority.choices,default=Priority.NORMAL); status=models.CharField(max_length=20,choices=Status.choices,default=Status.DRAFT,db_index=True)
    provider_hold=models.BooleanField(default=False,db_index=True)
    assigned_owner=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="assigned_requests")
    submitted_at=models.DateTimeField(null=True,blank=True); first_response_at=models.DateTimeField(null=True,blank=True); current_stage_started_at=models.DateTimeField(default=timezone.now); completed_at=models.DateTimeField(null=True,blank=True)
    expected_initial_response_at=models.DateTimeField(null=True,blank=True); estimated_delivery_min=models.DateField(null=True,blank=True); estimated_delivery_max=models.DateField(null=True,blank=True)
    operational_paused_at=models.DateTimeField(null=True,blank=True); paused_seconds=models.PositiveBigIntegerField(default=0); needs_user_action=models.BooleanField(default=False,db_index=True)
    class Meta: ordering=["-updated_at"]; indexes=[models.Index(fields=["requester","status"]),models.Index(fields=["assigned_owner","status"]),models.Index(fields=["department","status"],name="portal_requ_departm_9bda87_idx"),models.Index(fields=["program","status"],name="portal_requ_program_status_idx"),models.Index(fields=["project_entity","status"],name="portal_requ_project_status_idx")]
    def save(self,*a,**kw):
        if self.project_entity_id and self.program_id != self.project_entity.program_id:
            raise ValidationError({"project_entity":"پروژه باید متعلق به طرح انتخاب‌شده باشد."})
        if self._state.adding:
            self.department=self.service.category.department
            if self.assigned_owner_id:
                from .policies import can_be_default_owner
                if not can_be_default_owner(self.assigned_owner,self.department):
                    raise ValidationError({"assigned_owner":"مسئول رسیدگی باید مدیر درخواست یا مدیر اداره ارائه‌دهنده باشد."})
        if not self.public_id:
            today=timezone.localdate().strftime("%Y%m%d")
            self.public_id=f"MKT-{today}-{uuid.uuid4().hex[:6].upper()}"
        if not self.catalogue_snapshot and self.service_id:
            self.catalogue_snapshot={"service_code":self.service.code,"service_name":self.service.name,"department_code":self.service.department.code,"department_name":self.service.department.name,"family_name":self.service.category.name,
                "service":{key:getattr(self.service,key) for key in ("domain","short_description","full_description","purpose","scope","deliverables","required_inputs","request_requirements","process_information","excluded","service_role","acceptance_criteria","legacy_sla","initial_response_days","review_target_days","delivery_min_days","delivery_max_days","maximum_duration_days","supports_desired_date")},
                "form_fields":[{"key":f.key,"label":f.label,"field_type":f.field_type,"required":f.required,"options":f.options,"placeholder":f.placeholder,"help_text":f.help_text,"display_order":f.display_order} for f in self.service.form_fields.all()]}
        super().save(*a,**kw)
    @property
    def is_overdue(self):
        if self.status in {self.Status.COMPLETED,self.Status.REJECTED,self.Status.CANCELLED,self.Status.DRAFT}: return False
        if self.operational_paused_at or self.approval_steps.filter(status__in=["PENDING","CLARIFICATION_REQUESTED"],pauses_sla=True).exists(): return False
        if not self.first_response_at: return bool(self.effective_initial_response_at and timezone.now()>self.effective_initial_response_at)
        return bool(self.effective_delivery_max and timezone.localdate()>self.effective_delivery_max)
    @property
    def approval_paused_working_seconds(self):
        cal=WorkingCalendar.objects.filter(active=True).first()
        end=self.completed_at or timezone.now()
        blocked=set(cal.non_working_dates.values_list('date',flat=True)) if cal else set()
        total=0
        for step in self.approval_steps.filter(pauses_sla=True,started_at__isnull=False):
            start=step.started_at;finish=min(step.decided_at or end,end)
            if finish<=start:continue
            if not cal:total+=int((finish-start).total_seconds());continue
            start=timezone.localtime(start);finish=timezone.localtime(finish);day=start.date()
            while day<=finish.date():
                if day.weekday() not in cal.weekend_days and day not in blocked:
                    opening=timezone.make_aware(datetime.combine(day,cal.workday_start))
                    closing=timezone.make_aware(datetime.combine(day,cal.workday_end))
                    total+=max(0,int((min(finish,closing)-max(start,opening)).total_seconds()))
                day+=timedelta(days=1)
        return total
    @property
    def effective_initial_response_at(self):
        if not self.expected_initial_response_at:return None
        from .utils import advance_working_seconds
        return advance_working_seconds(self.expected_initial_response_at,self.approval_paused_working_seconds)
    @property
    def effective_delivery_max(self):
        if not self.estimated_delivery_max:return None
        cal=WorkingCalendar.objects.filter(active=True).first()
        if not cal:return self.estimated_delivery_max+timedelta(seconds=self.approval_paused_working_seconds)
        from .utils import advance_working_seconds
        baseline=timezone.make_aware(datetime.combine(self.estimated_delivery_max,cal.workday_end))
        return timezone.localtime(advance_working_seconds(baseline,self.approval_paused_working_seconds,cal)).date()
    @property
    def operational_elapsed_seconds(self):
        if not self.submitted_at:return 0
        end=self.completed_at or timezone.now(); cal=WorkingCalendar.objects.filter(active=True).first()
        blocked=set(cal.non_working_dates.values_list("date",flat=True)) if cal else set()
        def working_seconds(start,finish):
            if not start or finish<=start:return 0
            if not cal:return int((finish-start).total_seconds())
            start=timezone.localtime(start); finish=timezone.localtime(finish); current=start.date(); total=0
            while current<=finish.date():
                if current.weekday() not in cal.weekend_days and current not in blocked:
                    day_start=timezone.make_aware(datetime.combine(current,cal.workday_start)); day_end=timezone.make_aware(datetime.combine(current,cal.workday_end))
                    total+=max(0,int((min(finish,day_end)-max(start,day_start)).total_seconds()))
                current+=timedelta(days=1)
            return total
        total=working_seconds(self.submitted_at,end); pause_start=None; intervals=[]
        for event in self.history.filter(action__in=["CLOCK_PAUSED","CLOCK_RESUMED"]).order_by("created_at"):
            if event.action=="CLOCK_PAUSED" and pause_start is None: pause_start=event.created_at
            elif event.action=="CLOCK_RESUMED" and pause_start is not None: intervals.append((pause_start,event.created_at)); pause_start=None
        if pause_start is not None: intervals.append((pause_start,end))
        intervals.extend((step.started_at,step.decided_at or end) for step in self.approval_steps.filter(pauses_sla=True,started_at__isnull=False))
        intervals=sorted((max(start,self.submitted_at),min(finish,end)) for start,finish in intervals if start and finish and finish>self.submitted_at)
        merged=[]
        for start,finish in intervals:
            if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(merged[-1][1],finish))
            else:merged.append((start,finish))
        paused=sum(working_seconds(start,finish) for start,finish in merged)
        return max(0,total-paused)
    @property
    def end_to_end_elapsed_seconds(self):
        return max(0,int(((self.completed_at or timezone.now())-self.submitted_at).total_seconds())) if self.submitted_at else 0
    def approval_wait_seconds(self,target=None):
        end=self.completed_at or timezone.now()
        steps=self.approval_steps.exclude(started_at=None)
        if target:steps=steps.filter(target=target)
        return sum(max(0,int((min(step.decided_at or end,end)-step.started_at).total_seconds())) for step in steps)
    @property
    def program_approval_wait_seconds(self):return self.approval_wait_seconds('PROGRAM_MANAGER')
    @property
    def senior_approval_wait_seconds(self):return self.approval_wait_seconds('SENIOR')
    @property
    def total_approval_wait_seconds(self):return self.approval_wait_seconds()
    @property
    def brief_items(self):
        labels={row.get("key"):row.get("label") for row in self.catalogue_snapshot.get("form_fields",[])} or {f.key:f.label for f in self.service.form_fields.all()}
        return [(labels.get(k,k), "، ".join(v) if isinstance(v,list) else ("بله" if v is True else "خیر" if v is False else v)) for k,v in self.request_data.items()]
    @property
    def catalogue_service_name(self):return self.catalogue_snapshot.get("service_name") or self.service.name
    @property
    def catalogue_department_name(self):return self.catalogue_snapshot.get("department_name") or self.department.name
    def __str__(self): return self.public_id
    def allowed_transitions(self): return self.TRANSITIONS.get(self.status,set())

class RequestResponse(Timestamped):
    request=models.ForeignKey(Request,on_delete=models.CASCADE,related_name="responses"); author=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); body=models.TextField(); requests_information=models.BooleanField(default=False)
    class Meta: ordering=["created_at"]

class PriorityPolicy(Timestamped):
    code=models.CharField(max_length=16,unique=True,choices=Request.Priority.choices)
    name=models.CharField(max_length=100)
    display_order=models.PositiveSmallIntegerField(default=0)
    is_active=models.BooleanField(default=True)
    requires_credit=models.BooleanField(default=False)
    requires_approval=models.BooleanField(default=False)
    semantic_tone=models.CharField(max_length=16,choices=[("neutral","عادی"),("warning","هشدار"),("critical","بحرانی")],default="neutral")
    class Meta: ordering=["display_order","id"]
    def __str__(self):return self.name

class AllocationPeriod(Timestamped):
    class Kind(models.TextChoices): MONTH="MONTH","ماهانه"; QUARTER="QUARTER","فصلی"; HALF_YEAR="HALF_YEAR","شش‌ماهه"; YEAR="YEAR","سالانه"; CUSTOM="CUSTOM","سفارشی"
    name=models.CharField(max_length=120)
    kind=models.CharField(max_length=12,choices=Kind.choices)
    starts_on=models.DateField()
    ends_on=models.DateField()
    is_active=models.BooleanField(default=True)
    class Meta: ordering=["-starts_on"]
    def clean(self):
        if self.starts_on and self.ends_on and self.ends_on<self.starts_on:raise ValidationError({"ends_on":"پایان دوره باید بعد از آغاز باشد."})
        if self.pk and self.is_active and self.starts_on and self.ends_on:
            for allocation in self.allocations.filter(is_active=True):
                if CreditAllocation.objects.filter(program=allocation.program,department=allocation.department,priority=allocation.priority,
                    is_active=True,period__is_active=True,period__starts_on__lte=self.ends_on,period__ends_on__gte=self.starts_on).exclude(period=self).exists():
                    raise ValidationError("تغییر این دوره باعث هم‌پوشانی کیف اعتبار فعال می‌شود.")
    def save(self,*args,**kwargs):
        with transaction.atomic():
            if self.pk:
                list(Program.objects.select_for_update().filter(pk__in=self.allocations.values_list('program_id',flat=True).distinct()).order_by('pk'))
            self.full_clean()
            return super().save(*args,**kwargs)
    def __str__(self):return self.name

class CreditAllocation(Timestamped):
    program=models.ForeignKey(Program,on_delete=models.PROTECT,related_name="credit_allocations")
    department=models.ForeignKey(Department,on_delete=models.PROTECT,related_name="credit_allocations")
    priority=models.ForeignKey(PriorityPolicy,on_delete=models.PROTECT,related_name="allocations")
    period=models.ForeignKey(AllocationPeriod,on_delete=models.PROTECT,related_name="allocations")
    quantity=models.PositiveIntegerField(default=0)
    is_active=models.BooleanField(default=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="created_allocations")
    class Meta:
        constraints=[models.UniqueConstraint(fields=["program","department","priority","period"],name="unique_credit_wallet")]
        indexes=[models.Index(fields=["program","department","priority","is_active"],name="credit_wallet_lookup_idx")]
    def clean(self):
        if self.pk:
            old=CreditAllocation.objects.filter(pk=self.pk).values('program_id','department_id','priority_id','period_id').first()
            if old and any(old[key]!=getattr(self,key) for key in old) and self.reservations.exists():
                raise ValidationError("ابعاد تخصیص دارای سابقهٔ اعتبار قابل تغییر نیست.")
            committed=self.reservations.exclude(status="RELEASED").count()
            if self.quantity<committed:raise ValidationError({"quantity":"سقف تخصیص کمتر از اعتبارات مصرف‌شده یا رزروشده است."})
        if not self.is_active or not self.period_id:return
        period=self.period
        if not period.is_active:raise ValidationError({"period":"دورهٔ تخصیص باید فعال باشد."})
        overlap=CreditAllocation.objects.filter(program_id=self.program_id,department_id=self.department_id,priority_id=self.priority_id,is_active=True,period__is_active=True,period__starts_on__lte=period.ends_on,period__ends_on__gte=period.starts_on).exclude(pk=self.pk)
        if overlap.exists():raise ValidationError("دورهٔ فعال هم‌پوشان برای این طرح، اداره و اولویت وجود دارد.")
    def save(self,*args,**kwargs):
        with transaction.atomic():
            if self.program_id:Program.objects.select_for_update().get(pk=self.program_id)
            if self.pk:CreditAllocation.objects.select_for_update().get(pk=self.pk)
            self.full_clean()
            return super().save(*args,**kwargs)
    def __str__(self):return f"{self.program} · {self.department} · {self.priority} · {self.period}"

class CreditReservation(Timestamped):
    class Status(models.TextChoices): RESERVED="RESERVED","رزروشده"; CONSUMED="CONSUMED","مصرف‌شده"; RELEASED="RELEASED","آزادشده"
    request=models.OneToOneField(Request,on_delete=models.PROTECT,related_name="credit_reservation")
    allocation=models.ForeignKey(CreditAllocation,on_delete=models.PROTECT,related_name="reservations")
    status=models.CharField(max_length=10,choices=Status.choices,default=Status.RESERVED)
    reserved_at=models.DateTimeField(default=timezone.now)
    resolved_at=models.DateTimeField(null=True,blank=True)
    def __str__(self):return f"{self.request.public_id} · {self.status}"

class CreditLedgerEntry(models.Model):
    class Event(models.TextChoices): RESERVE="RESERVE","رزرو"; CONSUME="CONSUME","مصرف"; RELEASE="RELEASE","آزادسازی"
    reservation=models.ForeignKey(CreditReservation,on_delete=models.PROTECT,related_name="ledger_entries")
    event=models.CharField(max_length=8,choices=Event.choices)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL)
    created_at=models.DateTimeField(auto_now_add=True)
    metadata=models.JSONField(default=dict,blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["reservation","event"],name="unique_credit_transition")]

class ApprovalPolicy(Timestamped):
    class Trigger(models.TextChoices): PRIORITY="PRIORITY","اولویت درخواست"; PROVIDER="PROVIDER","ارجاع ارائه‌دهنده"
    class Target(models.TextChoices): PROGRAM_MANAGER="PROGRAM_MANAGER","مدیر طرح"; SENIOR="SENIOR","مرجع ارشد"
    name=models.CharField(max_length=160)
    trigger=models.CharField(max_length=12,choices=Trigger.choices)
    priority=models.ForeignKey(PriorityPolicy,null=True,blank=True,on_delete=models.PROTECT)
    requester_role=models.CharField(max_length=32,blank=True,default="")
    target=models.CharField(max_length=20,choices=Target.choices)
    sequence=models.PositiveSmallIntegerField(default=1)
    is_active=models.BooleanField(default=True)
    pauses_sla=models.BooleanField(default=True)
    class Meta: ordering=["sequence","id"]
    def clean(self):
        if self.trigger==self.Trigger.PRIORITY and not self.priority_id:raise ValidationError({"priority":"اولویت برای این سیاست الزامی است."})
        if self.trigger==self.Trigger.PROVIDER and self.priority_id:raise ValidationError({"priority":"سیاست ارجاع ارائه‌دهنده مستقل از اولویت است."})
    def save(self,*args,**kwargs):self.full_clean();return super().save(*args,**kwargs)

class SeniorApprovalConfiguration(Timestamped):
    title=models.CharField(max_length=120,default="مرجع تأیید ارشد")
    is_active=models.BooleanField(default=True)
    def save(self,*args,**kwargs):
        if self.pk not in (None,1):raise ValidationError("فقط یک تنظیم مرجع ارشد مجاز است.")
        self.pk=1;self.full_clean();return super().save(*args,**kwargs)

class ApprovalCase(Timestamped):
    class Status(models.TextChoices): PENDING="PENDING","در انتظار"; APPROVED="APPROVED","تأییدشده"; REJECTED="REJECTED","ردشده"; CLARIFICATION_REQUESTED="CLARIFICATION_REQUESTED","نیازمند توضیح"; CANCELLED="CANCELLED","لغوشده"
    request=models.ForeignKey(Request,on_delete=models.PROTECT,related_name="approval_cases")
    trigger=models.CharField(max_length=12,choices=ApprovalPolicy.Trigger.choices)
    status=models.CharField(max_length=24,choices=Status.choices,default=Status.PENDING,db_index=True)
    requested_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="requested_approvals")
    reason=models.TextField(blank=True)
    assessment=models.TextField(blank=True)
    estimated_time=models.CharField(max_length=120,blank=True)
    estimated_cost=models.CharField(max_length=120,blank=True)
    conditions=models.TextField(blank=True)
    recommendation=models.TextField(blank=True)
    risks=models.TextField(blank=True)
    context_snapshot=models.JSONField(default=dict)
    decided_at=models.DateTimeField(null=True,blank=True)
    class Meta: indexes=[models.Index(fields=["request","trigger","status"],name="approval_case_lookup_idx")]

class ApprovalStep(Timestamped):
    class Status(models.TextChoices): BLOCKED="BLOCKED","در صف"; PENDING="PENDING","در انتظار"; APPROVED="APPROVED","تأییدشده"; REJECTED="REJECTED","ردشده"; CLARIFICATION_REQUESTED="CLARIFICATION_REQUESTED","نیازمند توضیح"; CANCELLED="CANCELLED","لغوشده"
    case=models.ForeignKey(ApprovalCase,on_delete=models.PROTECT,related_name="steps")
    request=models.ForeignKey(Request,on_delete=models.PROTECT,related_name="approval_steps")
    policy=models.ForeignKey(ApprovalPolicy,null=True,on_delete=models.SET_NULL)
    sequence=models.PositiveSmallIntegerField()
    target=models.CharField(max_length=20,choices=ApprovalPolicy.Target.choices)
    status=models.CharField(max_length=24,choices=Status.choices,default=Status.BLOCKED,db_index=True)
    pauses_sla=models.BooleanField(default=True)
    started_at=models.DateTimeField(null=True,blank=True)
    decided_at=models.DateTimeField(null=True,blank=True)
    decided_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL,related_name="approval_decisions")
    decision_reason=models.TextField(blank=True)
    target_snapshot=models.JSONField(default=dict)
    class Meta:
        ordering=["sequence","id"]
        constraints=[models.UniqueConstraint(fields=["case","sequence"],name="unique_approval_case_step")]

class ApprovalDecision(models.Model):
    step=models.ForeignKey(ApprovalStep,on_delete=models.PROTECT,related_name="decisions")
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    outcome=models.CharField(max_length=24,choices=[("APPROVED","تأیید"),("REJECTED","رد"),("CLARIFICATION_REQUESTED","درخواست توضیح"),("AUTO_APPROVED","تأیید خودکار")])
    reason=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

class ApprovalClarification(models.Model):
    case=models.ForeignKey(ApprovalCase,on_delete=models.PROTECT,related_name="clarifications")
    author=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    body=models.TextField()
    created_at=models.DateTimeField(auto_now_add=True)

def approval_upload_path(instance,filename):return f"approvals/{instance.case.request.public_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"

class ApprovalAttachment(Timestamped):
    case=models.ForeignKey(ApprovalCase,on_delete=models.PROTECT,related_name="attachments")
    uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    file=models.FileField(upload_to=approval_upload_path)
    original_name=models.CharField(max_length=255)
    size=models.PositiveBigIntegerField()
    content_type=models.CharField(max_length=120)

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

class CatalogueImportBatch(models.Model):
    class Status(models.TextChoices): PREVIEWED="PREVIEWED","پیش‌نمایش"; CONFIRMED="CONFIRMED","تأییدشده"; FAILED="FAILED","ناموفق"
    department=models.ForeignKey(Department,on_delete=models.PROTECT,related_name="catalogue_imports")
    uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL,related_name="catalogue_imports")
    confirmed_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="confirmed_catalogue_imports")
    original_filename=models.CharField(max_length=255)
    file_size=models.PositiveBigIntegerField(default=0)
    file_sha256=models.CharField(max_length=64,blank=True)
    status=models.CharField(max_length=12,choices=Status.choices,default=Status.PREVIEWED)
    validation_result=models.JSONField(default=dict,blank=True)
    created_count=models.PositiveIntegerField(default=0)
    updated_count=models.PositiveIntegerField(default=0)
    skipped_count=models.PositiveIntegerField(default=0)
    confirmed_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at"]

class Notification(Timestamped):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="notifications"); title=models.CharField(max_length=200); body=models.CharField(max_length=500,blank=True); request=models.ForeignKey(Request,null=True,blank=True,on_delete=models.CASCADE); read_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=["-created_at"]

class AppSetting(Timestamped):
    key=models.CharField(max_length=100,unique=True); value=models.JSONField(default=dict)
    def __str__(self): return self.key

class AppearanceSetting(Timestamped):
    """Single row (pk=1); defaults apply without seeding during an upgrade."""
    from .appearance import DEFAULT_ACCENT, DEFAULT_NAME, DEFAULT_PRIMARY, FONT_CHOICES, brand_logo_path, validate_brand_color, validate_png_logo
    app_name=models.CharField(max_length=100,default=DEFAULT_NAME)
    primary_color=models.CharField(max_length=7,default=DEFAULT_PRIMARY,validators=[validate_brand_color])
    accent_color=models.CharField(max_length=7,default=DEFAULT_ACCENT,validators=[validate_brand_color])
    base_font_size=models.PositiveSmallIntegerField(default=15,choices=[(x,str(x)) for x in range(14,19)])
    font_family=models.CharField(max_length=16,default="system",choices=FONT_CHOICES)
    logo=models.FileField(upload_to=brand_logo_path,blank=True,validators=[validate_png_logo])

    def save(self,*args,**kwargs):
        if self.pk not in (None,1): raise ValidationError("فقط یک تنظیم ظاهر مجاز است.")
        self.pk=1
        self.full_clean()
        return super().save(*args,**kwargs)

    def __str__(self): return self.app_name

class LoginThrottle(models.Model):
    key=models.CharField(max_length=64,unique=True); failures=models.PositiveSmallIntegerField(default=0); locked_until=models.DateTimeField(null=True,blank=True); updated_at=models.DateTimeField(auto_now=True)
