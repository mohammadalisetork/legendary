from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django import forms
import jdatetime
from .models import ActivityLog, AppSetting, Category, NonWorkingDate, Request, Service, ServiceFormField, User, WorkingCalendar
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
    list_display=("code","name","category","domain","initial_response_days","delivery_min_days","delivery_max_days","default_owner","active")
    list_filter=("active","domain","category"); search_fields=("code","name","full_description"); ordering=("category","display_order"); inlines=(ServiceFieldInline,)
    actions=("duplicate_services",)
    @admin.action(description="تکثیر خدمت انتخاب‌شده")
    def duplicate_services(self,request,queryset):
        for service in queryset:
            fields=list(service.form_fields.all()); service.pk=None; service.code=f"COPY-{service.code}"[:20]; service.name=f"کپی {service.name}"; service.active=False; service.save()
            for f in fields: f.pk=None; f.service=service; f.save()

@admin.register(Category)
class CategoryAdmin(AuditAdminMixin,admin.ModelAdmin): list_display=("name","display_order","active"); list_editable=("display_order","active"); prepopulated_fields={"slug":("name",)}
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
    list_display=("public_id","title","requester","service","status","priority","assigned_owner","submitted_at"); list_filter=("status","priority","service__category"); search_fields=("public_id","title","requester__full_name"); readonly_fields=("public_id","submitted_at","first_response_at","completed_at","paused_seconds")
@admin.register(ActivityLog)
class ActivityAdmin(admin.ModelAdmin):
    list_display=("created_at","actor","action","target_type","target_id")
    list_filter=("action","target_type")
    readonly_fields=("actor","action","target_type","target_id","metadata","created_at")
    def has_add_permission(self,request): return False
admin.site.register([AppSetting])
