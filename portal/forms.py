from pathlib import Path
from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone
from .models import AppearanceSetting, Attachment, Category, Department, Request, RoleAssignment, Service, ServiceFormField, User

class LoginForm(AuthenticationForm):
    username=forms.CharField(label="نام کاربری",widget=forms.TextInput(attrs={"autofocus":True,"autocomplete":"username"}))
    password=forms.CharField(label="رمز عبور",strip=False,widget=forms.PasswordInput(attrs={"autocomplete":"current-password"}))

class AppearanceForm(forms.ModelForm):
    class Meta:
        model=AppearanceSetting
        fields=["app_name","logo","primary_color","accent_color","base_font_size","font_family"]
        labels={"app_name":"نام سامانه","logo":"لوگو (PNG، حداکثر ۱ مگابایت)","primary_color":"رنگ اصلی","accent_color":"رنگ تأکیدی","base_font_size":"اندازه پایه قلم","font_family":"قلم"}
        widgets={"primary_color":forms.TextInput(attrs={"type":"color"}),"accent_color":forms.TextInput(attrs={"type":"color"})}

class RequestBaseForm(forms.ModelForm):
    class Meta:
        model=Request; fields=["project","title","priority","desired_delivery_date"]
        labels={"project":"نام طرح یا پروژه","title":"عنوان درخواست","priority":"اولویت","desired_delivery_date":"تاریخ مورد انتظار درخواست‌دهنده"}
        widgets={"desired_delivery_date":forms.HiddenInput(attrs={"class":"jalali-iso","data-min-today":"true"})}
    def __init__(self,*a,service=None,allow_incomplete=False,**kw):
        super().__init__(*a,**kw); self.service=service; self.allow_incomplete=allow_incomplete
        if not service.supports_desired_date: self.fields.pop("desired_delivery_date",None)
        if allow_incomplete:
            for name in ("project","title","priority","desired_delivery_date"):
                if name in self.fields: self.fields[name].required=False
        for f in service.form_fields.filter(active=True):
            required=f.required and not allow_incomplete; attrs={"placeholder":f.placeholder,"data-help":f.help_text}
            if f.field_type==ServiceFormField.FieldType.FILE and self.instance.pk and self.instance.attachments.exists(): required=False
            if f.field_type==ServiceFormField.FieldType.TEXTAREA: field=forms.CharField(widget=forms.Textarea(attrs=attrs),required=required)
            elif f.field_type==ServiceFormField.FieldType.NUMBER: field=forms.DecimalField(widget=forms.NumberInput(attrs=attrs),required=required)
            elif f.field_type==ServiceFormField.FieldType.DATE: field=forms.DateField(widget=forms.HiddenInput(attrs={"class":"jalali-iso dynamic-date"}),required=required)
            elif f.field_type==ServiceFormField.FieldType.SELECT: field=forms.ChoiceField(choices=[("","انتخاب کنید")]+[(x,x) for x in f.options],required=required)
            elif f.field_type==ServiceFormField.FieldType.MULTISELECT: field=forms.MultipleChoiceField(choices=[(x,x) for x in f.options],widget=forms.CheckboxSelectMultiple,required=required)
            elif f.field_type==ServiceFormField.FieldType.CHECKBOX: field=forms.BooleanField(required=required)
            elif f.field_type==ServiceFormField.FieldType.EMAIL: field=forms.EmailField(widget=forms.EmailInput(attrs=attrs),required=required)
            elif f.field_type==ServiceFormField.FieldType.FILE: field=forms.FileField(required=required)
            else: field=forms.CharField(widget=forms.TextInput(attrs=attrs),required=required)
            field.label=f.label; field.help_text=f.help_text; self.fields[f"data_{f.key}"]=field
            if f.field_type==ServiceFormField.FieldType.FILE:
                field.widget.attrs.update({"data-file-preview":"true","data-max-size":str(settings.MAX_UPLOAD_SIZE),"accept":",".join("."+extension for extension in sorted(settings.ALLOWED_UPLOAD_EXTENSIONS))})
            if self.instance.pk and f.key in self.instance.request_data: self.initial[f"data_{f.key}"]=self.instance.request_data[f.key]
    def clean_desired_delivery_date(self):
        value=self.cleaned_data.get("desired_delivery_date")
        if value and value<timezone.localdate(): raise forms.ValidationError("تاریخ مورد انتظار نمی‌تواند در گذشته باشد.")
        return value
    def save(self,commit=True):
        obj=super().save(False); obj.service=self.service
        def serializable(value):
            if hasattr(value,"isoformat"): return value.isoformat()
            return str(value) if value.__class__.__name__=="Decimal" else value
        obj.request_data={k[5:]:serializable(v) for k,v in self.cleaned_data.items() if k.startswith("data_") and not hasattr(v,"read") and v not in (None,"")}
        if commit: obj.save()
        return obj
    def clean(self):
        cleaned=super().clean()
        for key,value in cleaned.items():
            if key.startswith("data_") and hasattr(value,"size"):
                if value.size>settings.MAX_UPLOAD_SIZE: self.add_error(key,"حجم فایل بیشتر از حد مجاز است.")
                if Path(value.name).suffix.lower().lstrip(".") not in settings.ALLOWED_UPLOAD_EXTENSIONS: self.add_error(key,"نوع فایل مجاز نیست.")
        return cleaned
    def dynamic_files(self): return [v for k,v in self.cleaned_data.items() if k.startswith("data_") and hasattr(v,"read")]

    def mark_errors_for_accessibility(self):
        for name in self.errors:
            if name in self.fields:
                widget=self.fields[name].widget
                widget.attrs["aria-invalid"]="true"
                error_id=f"id_{name}_error"
                widget.attrs["aria-describedby"]=" ".join(filter(None,(widget.attrs.get("aria-describedby"),error_id)))

def request_readiness_errors(obj):
    errors=[]
    if not obj.project.strip(): errors.append("نام طرح یا پروژه")
    if not obj.title.strip(): errors.append("عنوان درخواست")
    if obj.service.supports_desired_date and obj.desired_delivery_date and obj.desired_delivery_date < timezone.localdate(): errors.append("تاریخ مورد انتظار معتبر")
    for field in obj.service.form_fields.filter(active=True,required=True):
        if field.field_type==ServiceFormField.FieldType.FILE:
            if not obj.attachments.exists(): errors.append(field.label)
        elif obj.request_data.get(field.key) in (None,"",[]): errors.append(field.label)
    return errors

class MessageForm(forms.Form):
    body=forms.CharField(label="پیام",widget=forms.Textarea(attrs={"rows":4}),required=True)
    file=forms.FileField(label="پیوست",required=False)
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["file"].widget.attrs.update({"data-file-preview":"true","data-max-size":str(settings.MAX_UPLOAD_SIZE),"accept":",".join("."+extension for extension in sorted(settings.ALLOWED_UPLOAD_EXTENSIONS))})
    def clean_file(self):
        f=self.cleaned_data.get("file")
        if not f:return f
        if f.size>settings.MAX_UPLOAD_SIZE: raise forms.ValidationError("حجم فایل بیشتر از حد مجاز است.")
        if Path(f.name).suffix.lower().lstrip(".") not in settings.ALLOWED_UPLOAD_EXTENSIONS: raise forms.ValidationError("نوع فایل مجاز نیست.")
        return f

class InternalNoteForm(forms.Form): body=forms.CharField(label="یادداشت داخلی",widget=forms.Textarea(attrs={"rows":3}))
class ManagerActionForm(forms.Form):
    status=forms.ChoiceField(label="وضعیت",choices=Request.Status.choices,required=False)
    owner=forms.ModelChoiceField(label="مسئول رسیدگی",queryset=None,required=False)
    reason=forms.CharField(label="دلیل تغییر وضعیت",required=False,widget=forms.Textarea(attrs={"rows":3,"placeholder":"برای توقف، درخواست اطلاعات، رد یا لغو الزامی است."}))
    def __init__(self,*a,request_obj=None,**kw):
        from .models import User
        from .policies import eligible_owners
        super().__init__(*a,**kw); self.fields["owner"].queryset=User.objects.none()
        if request_obj:
            self.fields["owner"].queryset=eligible_owners(request_obj.department)
            allowed={request_obj.status,*request_obj.allowed_transitions()}; self.fields["status"].choices=[x for x in Request.Status.choices if x[0] in allowed]
            self.request_obj=request_obj
    def clean(self):
        cleaned=super().clean(); status=cleaned.get("status"); reason=(cleaned.get("reason") or "").strip()
        needs_reason={Request.Status.NEED_INFO,Request.Status.ON_HOLD,Request.Status.REJECTED,Request.Status.CANCELLED}
        current_status=getattr(getattr(self,"request_obj",None),"status",None)
        if status and status!=current_status and status in needs_reason and not reason:
            self.add_error("reason","ثبت دلیل برای این تغییر وضعیت الزامی است.")
        cleaned["reason"]=reason; return cleaned

def save_upload(req,user,file,response=None):
    if not file:return None
    return Attachment.objects.create(request=req,uploaded_by=user,file=file,original_name=file.name,size=file.size,content_type=getattr(file,"content_type","")[:120],response=response)


class DepartmentForm(forms.ModelForm):
    class Meta:
        model=Department
        fields=["code","name","short_name","description","intro_text","display_order"]
        labels={"code":"کد پایدار","name":"نام اداره","short_name":"نام کوتاه","description":"توضیح کوتاه","intro_text":"متن معرفی","display_order":"ترتیب نمایش"}
        widgets={"description":forms.Textarea(attrs={"rows":3}),"intro_text":forms.Textarea(attrs={"rows":4})}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.instance.pk:
            self.fields["code"].disabled=True


class DepartmentLifecycleForm(forms.Form):
    status=forms.ChoiceField(label="وضعیت مقصد",choices=Department.Status.choices)

    def __init__(self,*args,department=None,actor=None,**kwargs):
        from .policies import is_super_admin
        super().__init__(*args,**kwargs)
        allowed={
            Department.Status.DRAFT:{Department.Status.PUBLISHED},
            Department.Status.PUBLISHED:{Department.Status.DISABLED,Department.Status.ARCHIVED},
            Department.Status.DISABLED:{Department.Status.PUBLISHED,Department.Status.ARCHIVED},
            Department.Status.ARCHIVED:set(),
        }.get(department.status,set())
        if not is_super_admin(actor): allowed.discard(Department.Status.ARCHIVED)
        self.fields["status"].choices=[item for item in Department.Status.choices if item[0] in allowed]
        self.department=department

    def clean_status(self):
        status=self.cleaned_data["status"]
        if status==Department.Status.PUBLISHED and not self.department.service_families.filter(active=True,services__active=True).exists():
            raise forms.ValidationError("برای انتشار، حداقل یک خانواده و خدمت فعال لازم است.")
        return status


class DepartmentMembershipForm(forms.Form):
    user=forms.ModelChoiceField(label="کاربر",queryset=User.objects.none())
    role=forms.ChoiceField(label="نقش",choices=())

    def __init__(self,*args,actor=None,**kwargs):
        from .policies import is_super_admin
        super().__init__(*args,**kwargs)
        self.fields["user"].queryset=User.objects.filter(is_active=True).order_by("full_name","username")
        roles=[RoleAssignment.Role.REQUEST_MANAGER]
        if is_super_admin(actor): roles.append(RoleAssignment.Role.DEPARTMENT_LEAD)
        self.fields["role"].choices=[item for item in RoleAssignment.Role.choices if item[0] in roles]


class ServiceFamilyForm(forms.ModelForm):
    class Meta:
        model=Category
        fields=["name","slug","description","display_order","active"]
        labels={"name":"نام خانواده خدمت","slug":"شناسه نشانی","description":"توضیح","display_order":"ترتیب نمایش","active":"فعال"}
        widgets={"description":forms.Textarea(attrs={"rows":3})}


class ServiceManagementForm(forms.ModelForm):
    class Meta:
        model=Service
        fields=["code","name","category","domain","short_description","full_description","purpose","scope","deliverables","required_inputs","default_owner","initial_response_days","delivery_min_days","delivery_max_days","supports_desired_date","active","display_order"]
        labels={"category":"خانواده خدمت","active":"فعال","display_order":"ترتیب نمایش"}
        widgets={name:forms.Textarea(attrs={"rows":3}) for name in ["short_description","full_description","purpose","scope","deliverables","required_inputs"]}

    def __init__(self,*args,department=None,**kwargs):
        from .policies import eligible_owners
        super().__init__(*args,**kwargs)
        self.department=department
        self.fields["category"].queryset=department.service_families.all()
        self.fields["default_owner"].queryset=eligible_owners(department)

    def clean_category(self):
        category=self.cleaned_data["category"]
        if category.department_id!=self.department.pk:
            raise forms.ValidationError("خانواده خدمت باید متعلق به همین اداره باشد.")
        return category
