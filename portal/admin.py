from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django import forms
import jdatetime
from .models import ActivityLog, AppSetting, ApprovalCase, ApprovalDecision, ApprovalStep, Category, CreditLedgerEntry, CreditReservation, Department, NonWorkingDate, Program, Project, Request, RoleAssignment, Service, ServiceFormField, User, WorkingCalendar
from .utils import audit

class AuditAdminMixin:
    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change); audit(request.user,"ADMIN_UPDATED" if change else "ADMIN_CREATED",obj,{"fields":list(form.changed_data)})
    def delete_model(self,request,obj):
        audit(request.user,"ADMIN_DELETED",obj); super().delete_model(request,obj)

class JalaliDateWidget(forms.DateInput):
    input_type="hidden"; template_name="widgets/jalali_date.html"
    class Media: js=("jalali.js",)

class NonWorkingDateForm(forms.ModelForm):
    class Meta: model=NonWorkingDate; fields="__all__"; widgets={"date":JalaliDateWidget()}

class WorkingCalendarForm(forms.ModelForm):
    weekend_days=forms.MultipleChoiceField(label="روزهای تعطیل هفتگی",choices=[("5","شنبه"),("6","یکشنبه"),("0","دوشنبه"),("1","سه‌شنبه"),("2","چهارشنبه"),("3","پنجشنبه"),("4","جمعه")],widget=forms.CheckboxSelectMultiple)
    class Meta: model=WorkingCalendar; fields="__all__"
    def clean_weekend_days(self): return [int(x) for x in self.cleaned_data["weekend_days"]]

@admin.register(User)
class PortalUserAdmin(AuditAdminMixin,UserAdmin):
    add_form=UserCreationForm; form=UserChangeForm
    list_display=("username","full_name","organizational_unit","role","is_active","last_login")
    list_filter=("role","is_active","organizational_unit"); search_fields=("username","full_name","email")
    fieldsets=(("ورود",{"fields":("username","password")}), ("مشخصات",{"fields":("full_name","email","mobile","organizational_unit","job_title")}), ("دسترسی",{"fields":("role","is_active","must_change_password")}), ("زمان‌ها",{"fields":("last_login","date_joined","last_activity_at")}))
    add_fieldsets=((None,{"classes":("wide",),"fields":("username","full_name","email","organizational_unit","job_title","role","password1","password2","must_change_password","is_active")}),)
    readonly_fields=("last_login","date_joined","last_activity_at")

class ServiceFieldInline(admin.TabularInline): model=ServiceFormField; extra=1
@admin.register(Service)
class ServiceAdmin(AuditAdminMixin,admin.ModelAdmin):
    list_display=("code","name","category","provider_department","domain","initial_response_days","delivery_min_days","delivery_max_days","default_owner","active")
    list_filter=("active","domain","category__department","category"); search_fields=("code","name","full_description"); ordering=("category","display_order"); inlines=(ServiceFieldInline,)
    actions=("duplicate_services",)
    @admin.display(description="اداره ارائه‌دهنده",ordering="category__department")
    def provider_department(self,obj): return obj.category.department
    @admin.action(description="تکثیر خدمت انتخاب‌شده")
    def duplicate_services(self,request,queryset):
        for service in queryset:
            fields=list(service.form_fields.all()); service.pk=None; service.code=f"COPY-{service.code}"[:20]; service.name=f"کپی {service.name}"; service.active=False; service.save()
            for f in fields: f.pk=None; f.service=service; f.save()

@admin.register(Category)
class CategoryAdmin(AuditAdminMixin,admin.ModelAdmin): list_display=("name","department","display_order","active"); list_filter=("department","active"); list_editable=("display_order","active"); prepopulated_fields={"slug":("name",)}
@admin.register(ServiceFormField)
class ServiceFormFieldAdmin(AuditAdminMixin,admin.ModelAdmin): list_display=("label","service","field_type","required","display_order","active"); list_filter=("field_type","required","active","service")
@admin.register(WorkingCalendar)
class WorkingCalendarAdmin(AuditAdminMixin,admin.ModelAdmin):
    form=WorkingCalendarForm; list_display=("name","weekend_days","workday_start","workday_end","active")
@admin.register(NonWorkingDate)
class NonWorkingDateAdmin(AuditAdminMixin,admin.ModelAdmin):
    form=NonWorkingDateForm; list_display=("jalali_date","title","calendar"); list_filter=("calendar",)
    @admin.display(description="تاریخ")
    def jalali_date(self,obj): return jdatetime.date.fromgregorian(date=obj.date).strftime("%Y/%m/%d").translate(str.maketrans("0123456789","۰۱۲۳۴۵۶۷۸۹"))
@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display=("public_id","title","department","requester","service","status","priority","assigned_owner","submitted_at"); list_filter=("department","status","priority","service__category"); search_fields=("public_id","title","requester__full_name"); readonly_fields=("public_id","department","submitted_at","first_response_at","completed_at","paused_seconds","provider_hold")
    def get_readonly_fields(self,request,obj=None):
        fields=super().get_readonly_fields(request,obj)
        return (*fields,"priority","status","program","project_entity") if obj and obj.status!=Request.Status.DRAFT else fields

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display=("code","name","short_name","status","display_order","created_at","updated_at")
    list_filter=("status",); list_editable=("status","display_order"); search_fields=("code","name","short_name")
    readonly_fields=("created_at","updated_at")
    def save_model(self,request,obj,form,change):
        old_status=Department.objects.filter(pk=obj.pk).values_list("status",flat=True).first() if change else None
        super().save_model(request,obj,form,change)
        audit(request.user,"DEPARTMENT_UPDATED" if change else "DEPARTMENT_CREATED",obj,{"fields":list(form.changed_data)})
        if change and old_status!=obj.status: audit(request.user,"DEPARTMENT_STATUS_CHANGED",obj,{"from":old_status,"to":obj.status})
    def has_delete_permission(self,request,obj=None): return False

@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display=("user","role","scope_type","department","program","project","is_active","assigned_by","created_at","deactivated_at")
    list_filter=("role","scope_type","department","program","project","is_active"); search_fields=("user__username","user__full_name","department__name","program__name","project__name")
    readonly_fields=("created_at","updated_at","assigned_by","deactivated_at")
    def save_model(self,request,obj,form,change):
        previous=RoleAssignment.objects.filter(pk=obj.pk).values("role","department_id","is_active").first() if change else None
        if not obj.assigned_by_id: obj.assigned_by=request.user
        super().save_model(request,obj,form,change)
        action="DEPARTMENT_MEMBERSHIP_ADDED" if not change else "DEPARTMENT_ROLE_CHANGED"
        if previous and previous["is_active"] and not obj.is_active: action="DEPARTMENT_MEMBERSHIP_REMOVED"
        audit(request.user,action,obj,{"fields":list(form.changed_data),"department":obj.department_id,"program":obj.program_id,"project":obj.project_id,"role":obj.role})
    def delete_model(self,request,obj):
        audit(request.user,"DEPARTMENT_MEMBERSHIP_REMOVED",obj,{"department":obj.department_id,"role":obj.role})
        super().delete_model(request,obj)
@admin.register(ActivityLog)
class ActivityAdmin(admin.ModelAdmin):
    list_display=("created_at","actor","action","target_type","target_id")
    list_filter=("action","target_type")
    readonly_fields=("actor","action","target_type","target_id","metadata","created_at")
    def has_add_permission(self,request): return False
admin.site.register([AppSetting])

class GovernanceAuditAdmin(admin.ModelAdmin):
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False

for model in (CreditReservation,CreditLedgerEntry,ApprovalCase,ApprovalStep,ApprovalDecision):
    admin.site.register(model,GovernanceAuditAdmin)

@admin.register(Program)
class ProgramAdmin(AuditAdminMixin,admin.ModelAdmin):
    list_display=("code","name","status","created_at","updated_at")
    list_filter=("status",);search_fields=("code","name")
    readonly_fields=("created_at","updated_at")
    def has_delete_permission(self,request,obj=None):return False

@admin.register(Project)
class ProjectAdmin(AuditAdminMixin,admin.ModelAdmin):
    list_display=("code","name","program","status","created_at","updated_at")
    list_filter=("status","program");search_fields=("code","name","program__name")
    readonly_fields=("created_at","updated_at")
    def has_delete_permission(self,request,obj=None):return False
