from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404, JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .appearance import DEFAULT_ACCENT, DEFAULT_NAME, DEFAULT_PRIMARY
from .forms import AppearanceForm, DepartmentForm, DepartmentLifecycleForm, DepartmentMembershipForm, InternalNoteForm, LoginForm, ManagerActionForm, MessageForm, RequestBaseForm, ServiceFamilyForm, ServiceManagementForm, request_readiness_errors, save_upload
from .models import AppearanceSetting, Attachment, Category, Department, InternalNote, LoginThrottle, Notification, Request, RequestResponse, RoleAssignment, Service, User
from .policies import Action, authorized_departments, can, can_access_control, department_ids_for_role, is_super_admin, request_scope
from .utils import apply_submission_timing, audit, history, notify, transition

class PortalLoginView(LoginView):
    template_name="registration/login.html"; authentication_form=LoginForm; redirect_authenticated_user=True
    def throttle_key(self):
        from django.utils.crypto import salted_hmac
        username=self.request.POST.get("username","").strip().casefold(); ip=self.request.META.get("HTTP_X_REAL_IP") or self.request.META.get("REMOTE_ADDR","")
        return salted_hmac("portal-login-throttle",f"{ip}|{username}").hexdigest()
    def dispatch(self,request,*args,**kwargs):
        if request.method=="POST" and LoginThrottle.objects.filter(key=self.throttle_key(),locked_until__gt=timezone.now()).exists():
            return render(request,self.template_name,{"form":self.get_form(),"throttled":True},status=429)
        return super().dispatch(request,*args,**kwargs)
    def form_invalid(self,form):
        from datetime import timedelta
        from django.conf import settings
        with transaction.atomic():
            row,_=LoginThrottle.objects.select_for_update().get_or_create(key=self.throttle_key()); row.failures+=1
            if row.failures>=settings.LOGIN_MAX_FAILURES: row.locked_until=timezone.now()+timedelta(minutes=settings.LOGIN_LOCK_MINUTES); row.failures=0
            row.save()
        return super().form_invalid(form)
    def form_valid(self,form):
        LoginThrottle.objects.filter(key=self.throttle_key()).delete(); return super().form_valid(form)

@login_required
def password_change(request):
    form=PasswordChangeForm(request.user,request.POST or None)
    if request.method=="POST" and form.is_valid():
        user=form.save(); user.must_change_password=False; user.save(update_fields=["must_change_password"]); update_session_auth_hash(request,user); audit(user,"PASSWORD_CHANGED",user); return redirect("password_change_done")
    return render(request,"registration/password_change.html",{"form":form})

def health(request):
    try:
        with connection.cursor() as c: c.execute("SELECT 1"); c.fetchone()
        return JsonResponse({"status":"ok","database":"ok"})
    except Exception: return JsonResponse({"status":"degraded","database":"unavailable"},status=503)

def brand_logo(request):
    appearance=AppearanceSetting.objects.filter(pk=1).first()
    if not appearance or not appearance.logo: raise Http404
    try: return FileResponse(appearance.logo.open("rb"),content_type="image/png")
    except (OSError,FileNotFoundError): raise Http404

@login_required
def appearance_settings(request):
    if not is_super_admin(request.user): raise PermissionDenied
    appearance=AppearanceSetting.objects.filter(pk=1).first() or AppearanceSetting()
    if request.method=="POST" and request.POST.get("reset"):
        appearance.app_name=DEFAULT_NAME; appearance.primary_color=DEFAULT_PRIMARY; appearance.accent_color=DEFAULT_ACCENT
        appearance.base_font_size=15; appearance.font_family="system"; appearance.logo=""; appearance.save()
        audit(request.user,"APPEARANCE_RESET",appearance); messages.success(request,"ظاهر پیش‌فرض بازگردانده شد.")
        return redirect("appearance_settings")
    form=AppearanceForm(request.POST or None,request.FILES or None,instance=appearance)
    if request.method=="POST" and form.is_valid():
        form.save(); audit(request.user,"APPEARANCE_UPDATED",appearance,{"fields":list(form.changed_data)})
        messages.success(request,"تنظیمات ظاهر ذخیره شد."); return redirect("appearance_settings")
    return render(request,"control/appearance.html",{"form":form,"current_appearance":appearance})

def fa_digits(v): return str(v).translate(str.maketrans("0123456789","۰۱۲۳۴۵۶۷۸۹"))

@login_required
def home(request):
    own=Request.objects.filter(requester=request.user).exclude(status=Request.Status.DRAFT)
    categories=Category.objects.filter(active=True,department__status=Department.Status.PUBLISHED).select_related("department").annotate(service_count=Count("services",filter=Q(services__active=True)))
    return render(request,"portal/home.html",{"recent":own[:5],"action_required":own.filter(needs_user_action=True)[:5],"categories":categories,"draft_count":Request.objects.filter(requester=request.user,status=Request.Status.DRAFT).count()})

@login_required
def service_hub(request):
    departments=Department.objects.filter(status=Department.Status.PUBLISHED).annotate(
        family_count=Count("service_families",filter=Q(service_families__active=True),distinct=True),
        service_count=Count("service_families__services",filter=Q(service_families__active=True,service_families__services__active=True),distinct=True),
    )
    q=request.GET.get("q","").strip()
    if q:
        departments=departments.filter(Q(name__icontains=q)|Q(short_name__icontains=q)|Q(description__icontains=q)|Q(service_families__services__name__icontains=q)|Q(service_families__services__code__icontains=q)).distinct()
    return render(request,"portal/service_hub.html",{"departments":departments,"q":q,"breadcrumbs":[{"label":"مرکز خدمات"}]})

@login_required
def department_landing(request,code):
    department=get_object_or_404(Department,code=code,status=Department.Status.PUBLISHED)
    families=department.service_families.filter(active=True).prefetch_related(Prefetch("services",queryset=Service.objects.filter(active=True).select_related("category")))
    q=request.GET.get("q","").strip()
    if q:
        families=families.filter(Q(name__icontains=q)|Q(description__icontains=q)|Q(services__active=True,services__name__icontains=q)|Q(services__active=True,services__code__icontains=q)).distinct()
    return render(request,"portal/department_landing.html",{"department":department,"families":families,"q":q,"breadcrumbs":[{"label":"مرکز خدمات","href":reverse("service_hub")},{"label":str(department)}]})

@login_required
def catalog(request):
    services=Service.objects.filter(active=True,category__active=True,category__department__status=Department.Status.PUBLISHED).select_related("category","category__department")
    q=request.GET.get("q","").strip(); category=request.GET.get("category","")
    if q: services=services.filter(Q(name__icontains=q)|Q(code__icontains=q)|Q(full_description__icontains=q)|Q(deliverables__icontains=q)|Q(purpose__icontains=q))
    if category: services=services.filter(category_id=category)
    return render(request,"portal/catalog.html",{"services":services,"categories":Category.objects.filter(active=True,department__status=Department.Status.PUBLISHED),"q":q,"selected_category":category})

@login_required
def service_detail(request,pk):
    service=get_object_or_404(Service.objects.select_related("category__department","default_owner"),pk=pk)
    if service.department.status==Department.Status.DRAFT and not can(request.user,Action.CATALOGUE_MANAGE,department=service.department): raise Http404
    available=service.is_requestable
    return render(request,"portal/service_detail.html",{"service":service,"available":available,"breadcrumbs":[{"label":"مرکز خدمات","href":reverse("service_hub")},{"label":service.department.name,"href":reverse("department_landing",args=[service.department.code])},{"label":service.category.name},{"label":service.name}]})

@login_required
def request_create(request,service_id):
    service=get_object_or_404(Service.objects.select_related("category__department"),pk=service_id,active=True,category__active=True,category__department__status=Department.Status.PUBLISHED)
    form=RequestBaseForm(request.POST or None,request.FILES or None,service=service,allow_incomplete=request.method=="POST" and request.POST.get("action")!="submit")
    if request.method=="POST" and form.is_valid():
        obj=form.save(False); obj.requester=request.user; obj.requesting_unit=request.user.organizational_unit; obj.assigned_owner=service.default_owner; obj.status=Request.Status.DRAFT; obj.save()
        for file in form.dynamic_files(): save_upload(obj,request.user,file)
        history(obj,request.user,"REQUEST_CREATED")
        if request.POST.get("action")=="submit": return submit_request(request,obj.pk)
        messages.success(request,"پیش‌نویس ذخیره شد."); return redirect("request_detail",pk=obj.pk)
    if request.method=="POST": form.mark_errors_for_accessibility()
    return render(request,"portal/request_form.html",{"service":service,"form":form,"form_base_fields":[form[name] for name in ("project","title","priority","desired_delivery_date") if name in form.fields],"form_dynamic_fields":[form[name] for name in form.fields if name.startswith("data_")],"breadcrumbs":[{"label":"مرکز خدمات","href":reverse("service_hub")},{"label":service.department.name,"href":reverse("department_landing",args=[service.department.code])},{"label":service.category.name},{"label":service.name,"href":reverse("service_detail",args=[service.pk])},{"label":"ثبت درخواست"}]})

def accessible_request(user,pk,manager=False):
    qs=Request.objects.select_related("department","service__category__department","requester","assigned_owner")
    if manager and can_access_control(user): return get_object_or_404(request_scope(user).prefetch_related("responses__attachments","internal_notes","history"),pk=pk)
    if is_super_admin(user): return get_object_or_404(qs,pk=pk)
    return get_object_or_404(qs,pk=pk,requester=user)

@login_required
def request_detail(request,pk):
    obj=accessible_request(request.user,pk)
    return render(request,"portal/request_detail.html",{"item":obj,"message_form":MessageForm(),"can_edit":obj.status==Request.Status.DRAFT,"public_history":obj.history.exclude(action="INTERNAL_NOTE_ADDED"),"can_view_attachments":True})

@login_required
def request_edit(request,pk):
    obj=accessible_request(request.user,pk)
    if obj.status!=Request.Status.DRAFT: messages.error(request,"فقط پیش‌نویس قابل ویرایش است."); return redirect("request_detail",pk=pk)
    form=RequestBaseForm(request.POST or None,request.FILES or None,instance=obj,service=obj.service,allow_incomplete=request.method=="POST" and request.POST.get("action")!="submit")
    if request.method=="POST" and form.is_valid():
        form.save()
        for file in form.dynamic_files(): save_upload(obj,request.user,file)
        history(obj,request.user,"DRAFT_UPDATED")
        if request.POST.get("action")=="submit": return submit_request(request,obj.pk)
        messages.success(request,"پیش‌نویس ذخیره شد."); return redirect("request_detail",pk=pk)
    if request.method=="POST": form.mark_errors_for_accessibility()
    return render(request,"portal/request_form.html",{"service":obj.service,"form":form,"item":obj,"form_base_fields":[form[name] for name in ("project","title","priority","desired_delivery_date") if name in form.fields],"form_dynamic_fields":[form[name] for name in form.fields if name.startswith("data_")]})

@login_required
@require_POST
def submit_request(request,pk):
    obj=accessible_request(request.user,pk)
    if obj.status!=Request.Status.DRAFT: return redirect("request_detail",pk=pk)
    if not obj.service.is_requestable or not can(request.user,Action.REQUEST_CREATE,department=obj.department):
        messages.error(request,"این خدمت در حال حاضر امکان ثبت درخواست جدید ندارد.")
        return redirect("request_detail",pk=pk)
    missing=request_readiness_errors(obj)
    if missing:
        messages.error(request,"برای ثبت نهایی این موارد را کامل کنید: "+"، ".join(missing))
        return redirect("request_edit",pk=pk)
    apply_submission_timing(obj); obj.status=Request.Status.SUBMITTED; obj.save()
    history(obj,request.user,"REQUEST_SUBMITTED","DRAFT","SUBMITTED")
    notify(obj.assigned_owner,"درخواست جدید",f"درخواست {obj.public_id} ثبت شد.",obj)
    messages.success(request,f"درخواست با شناسه {obj.public_id} ثبت شد."); return redirect("request_detail",pk=obj.pk)

@login_required
def my_requests(request):
    items=Request.objects.filter(requester=request.user).select_related("department","service","assigned_owner")
    drafts=request.path.endswith("drafts/")
    if drafts: items=items.filter(status=Request.Status.DRAFT)
    status=request.GET.get("status",""); q=request.GET.get("q","")
    if status: items=items.filter(status=status)
    if q: items=items.filter(Q(public_id__icontains=q)|Q(title__icontains=q)|Q(service__name__icontains=q))
    page=Paginator(items,25).get_page(request.GET.get("page"))
    return render(request,"portal/request_list.html",{"items":page,"page":page,"statuses":Request.Status.choices,"status":status,"q":q,"drafts":drafts})

@login_required
@require_POST
def add_message(request,pk):
    obj=accessible_request(request.user,pk); form=MessageForm(request.POST,request.FILES)
    if obj.status not in {Request.Status.SUBMITTED,Request.Status.UNDER_REVIEW,Request.Status.NEED_INFO,Request.Status.ACCEPTED,Request.Status.IN_PROGRESS}:
        messages.error(request,"در وضعیت فعلی امکان ارسال پاسخ وجود ندارد."); return redirect("request_detail",pk=pk)
    if form.is_valid():
        response=RequestResponse.objects.create(request=obj,author=request.user,body=form.cleaned_data["body"]); save_upload(obj,request.user,form.cleaned_data.get("file"),response)
        history(obj,request.user,"REQUESTER_RESPONDED")
        if obj.status==Request.Status.NEED_INFO: transition(obj,Request.Status.UNDER_REVIEW,request.user)
        notify(obj.assigned_owner,"پاسخ درخواست‌دهنده",f"برای {obj.public_id} پاسخ جدید ثبت شد.",obj); messages.success(request,"پاسخ ثبت شد.")
    else: messages.error(request,"پیام یا فایل معتبر نیست: "+" ".join(error for errors in form.errors.values() for error in errors))
    return redirect("request_detail",pk=pk)

@login_required
def attachment_download(request,pk):
    a=get_object_or_404(Attachment.objects.select_related("request__department","request__service"),pk=pk)
    if not can(request.user,Action.REQUEST_VIEW_ATTACHMENT,resource=a.request): raise Http404
    return FileResponse(a.file.open("rb"),as_attachment=True,filename=a.original_name)

@login_required
def brief_print(request,pk): return render(request,"portal/brief.html",{"item":accessible_request(request.user,pk,manager=True)},content_type="text/html")

@login_required
def notifications(request): return render(request,"portal/notifications.html",{"items":request.user.notifications.select_related("request__department")})
@login_required
@require_POST
def notification_read(request,pk):
    n=get_object_or_404(Notification,pk=pk,user=request.user); n.read_at=timezone.now(); n.save(update_fields=["read_at"]); return redirect(n.request and "request_detail" or "notifications",**({"pk":n.request_id} if n.request else {}))

def is_manager(user): return can_access_control(user)
@login_required
def control_dashboard(request):
    if not is_manager(request.user): raise Http404
    departments=authorized_departments(request.user,operational=True)
    selected=request.GET.get("department","")
    qs=manager_scope(request.user)
    if selected:
        department=get_object_or_404(departments,code=selected); qs=qs.filter(department=department)
    counts={k:qs.filter(status=k).count() for k,_ in Request.Status.choices}
    return render(request,"control/dashboard.html",{"counts":counts,"recent":qs.exclude(status=Request.Status.DRAFT)[:10],"unassigned":qs.filter(assigned_owner__isnull=True).count(),"overdue":sum(1 for x in qs if x.is_overdue),"departments":departments,"selected_department":selected})

def manager_scope(user):
    return request_scope(user)

@login_required
def control_requests(request):
    if not is_manager(request.user): raise Http404
    departments=authorized_departments(request.user,operational=True)
    qs=manager_scope(request.user).exclude(status=Request.Status.DRAFT); q=request.GET.get("q",""); status=request.GET.get("status",""); priority=request.GET.get("priority",""); owner=request.GET.get("owner","")
    selected_department=request.GET.get("department","")
    if selected_department:
        department=get_object_or_404(departments,code=selected_department); qs=qs.filter(department=department)
    if q: qs=qs.filter(Q(public_id__icontains=q)|Q(title__icontains=q)|Q(requester__full_name__icontains=q)|Q(service__name__icontains=q))
    if status: qs=qs.filter(status=status)
    if priority: qs=qs.filter(priority=priority)
    if owner=="none": qs=qs.filter(assigned_owner__isnull=True)
    elif owner.isdigit(): qs=qs.filter(assigned_owner_id=owner)
    if request.GET.get("service","").isdigit(): qs=qs.filter(service_id=request.GET["service"])
    if request.GET.get("category","").isdigit(): qs=qs.filter(service__category_id=request.GET["category"])
    if request.GET.get("unit"): qs=qs.filter(requesting_unit=request.GET["unit"])
    if request.GET.get("needs_action")=="1": qs=qs.filter(needs_user_action=True)
    start=request.GET.get("start"); end=request.GET.get("end")
    if start: qs=qs.filter(submitted_at__date__gte=start)
    if end: qs=qs.filter(submitted_at__date__lte=end)
    sort=request.GET.get("sort","-updated_at"); allowed={"submitted_at","-submitted_at","updated_at","-updated_at","priority","status"}; qs=qs.order_by(sort if sort in allowed else "-updated_at")
    if request.GET.get("overdue")=="1": qs=qs.filter(expected_initial_response_at__lt=timezone.now(),first_response_at__isnull=True)
    page=Paginator(qs,25).get_page(request.GET.get("page"))
    visible_departments=manager_scope(request.user).values_list("department_id",flat=True).distinct()
    owners=User.objects.filter(is_active=True).filter(Q(role__in=[User.Role.REQUEST_MANAGER,User.Role.ADMIN])|Q(role_assignments__department_id__in=visible_departments,role_assignments__role__in=[RoleAssignment.Role.REQUEST_MANAGER,RoleAssignment.Role.DEPARTMENT_LEAD],role_assignments__is_active=True)).distinct()
    return render(request,"control/requests.html",{"items":page,"page":page,"statuses":Request.Status.choices,"priorities":Request.Priority.choices,"services":Service.objects.filter(active=True,category__department_id__in=visible_departments),"categories":Category.objects.filter(active=True,department_id__in=visible_departments),"owners":owners,"units":User.objects.exclude(organizational_unit="").values_list("organizational_unit",flat=True).distinct(),"departments":departments,"selected_department":selected_department})

@login_required
def control_request_detail(request,pk):
    if not is_manager(request.user): raise Http404
    obj=accessible_request(request.user,pk,manager=True)
    can_mutate=can(request.user,Action.REQUEST_RESPOND,resource=obj)
    return render(request,"control/request_detail.html",{"item":obj,"message_form":MessageForm(),"note_form":InternalNoteForm(),"action_form":ManagerActionForm(request_obj=obj,initial={"status":obj.status,"owner":obj.assigned_owner}),"can_mutate":can_mutate,"can_internal_note":can(request.user,Action.REQUEST_INTERNAL_NOTE,resource=obj),"can_view_attachments":can(request.user,Action.REQUEST_VIEW_ATTACHMENT,resource=obj)})

@login_required
@require_POST
def control_action(request,pk):
    if not is_manager(request.user): raise Http404
    obj=accessible_request(request.user,pk,manager=True); kind=request.POST.get("kind")
    action={"action":Action.REQUEST_CHANGE_STATUS,"message":Action.REQUEST_RESPOND,"note":Action.REQUEST_INTERNAL_NOTE}.get(kind)
    if not action or not can(request.user,action,resource=obj): raise Http404
    if kind=="action":
        form=ManagerActionForm(request.POST,request_obj=obj)
        if form.is_valid():
            owner=form.cleaned_data.get("owner"); status=form.cleaned_data.get("status"); reason=form.cleaned_data.get("reason","")
            if owner!=obj.assigned_owner: old=obj.assigned_owner; obj.assigned_owner=owner; obj.save(update_fields=["assigned_owner","updated_at"]); history(obj,request.user,"OWNER_CHANGED",metadata={"from":str(old or ""),"to":str(owner or "")})
            if status and status!=obj.status: transition(obj,status,request.user,reason); notify(obj.requester,"تغییر وضعیت درخواست",f"وضعیت {obj.public_id} به «{obj.get_status_display()}» تغییر کرد."+(f" دلیل: {reason}" if reason else ""),obj)
        else:
            messages.error(request,"تغییر وضعیت ثبت نشد: "+" ".join(e for errors in form.errors.values() for e in errors))
    elif kind=="message":
        if obj.status in {Request.Status.DRAFT,Request.Status.COMPLETED,Request.Status.REJECTED,Request.Status.CANCELLED}:
            messages.error(request,"در وضعیت فعلی امکان ارسال پیام وجود ندارد."); return redirect("control_request_detail",pk=pk)
        form=MessageForm(request.POST,request.FILES)
        if form.is_valid():
            ask=request.POST.get("request_info")=="1"; response=RequestResponse.objects.create(request=obj,author=request.user,body=form.cleaned_data["body"],requests_information=ask); save_upload(obj,request.user,form.cleaned_data.get("file"),response)
            if ask: transition(obj,Request.Status.NEED_INFO,request.user,form.cleaned_data["body"])
            elif not obj.first_response_at: obj.first_response_at=timezone.now(); obj.save(update_fields=["first_response_at","updated_at"])
            history(obj,request.user,"INFORMATION_REQUESTED" if ask else "MANAGER_RESPONDED"); notify(obj.requester,"پیام جدید درباره درخواست",f"برای {obj.public_id} پیام جدید ثبت شد.",obj)
    elif kind=="note":
        form=InternalNoteForm(request.POST)
        if form.is_valid(): InternalNote.objects.create(request=obj,author=request.user,body=form.cleaned_data["body"]); history(obj,request.user,"INTERNAL_NOTE_ADDED")
    if kind in {"action","message","note"} and 'form' in locals() and not form.is_valid(): messages.error(request,"اطلاعات واردشده معتبر نیست.")
    else: messages.success(request,"تغییرات ثبت شد.")
    return redirect("control_request_detail",pk=pk)

@login_required
def profile(request): return render(request,"portal/profile.html")


def _managed_department(user,pk):
    department=get_object_or_404(Department,pk=pk)
    if not can(user,Action.DEPARTMENT_MANAGE,department=department): raise PermissionDenied
    return department


@login_required
def manage_departments(request):
    if is_super_admin(request.user): departments=Department.objects.all()
    else: departments=Department.objects.filter(pk__in=department_ids_for_role(request.user,RoleAssignment.Role.DEPARTMENT_LEAD))
    departments=departments.annotate(
        family_count=Count("service_families",distinct=True),service_count=Count("service_families__services",distinct=True),member_count=Count("role_assignments",filter=Q(role_assignments__is_active=True),distinct=True)
    )
    if not departments.exists() and not is_super_admin(request.user): raise PermissionDenied
    return render(request,"control/departments.html",{"departments":departments,"can_create":is_super_admin(request.user)})


@login_required
def manage_department_detail(request,pk):
    department=_managed_department(request.user,pk)
    families=department.service_families.prefetch_related("services__default_owner")
    members=department.role_assignments.filter(is_active=True).select_related("user")
    return render(request,"control/department_detail.html",{"department":department,"families":families,"members":members,"lifecycle_form":DepartmentLifecycleForm(department=department,actor=request.user),"membership_form":DepartmentMembershipForm(actor=request.user),"can_archive":is_super_admin(request.user)})


@login_required
def manage_department_edit(request,pk=None):
    if pk:
        department=_managed_department(request.user,pk)
    else:
        if not is_super_admin(request.user): raise PermissionDenied
        department=Department()
    form=DepartmentForm(request.POST or None,instance=department)
    if request.method=="POST" and form.is_valid():
        created=not department.pk; obj=form.save(); audit(request.user,"DEPARTMENT_CREATED" if created else "DEPARTMENT_UPDATED",obj,{"fields":list(form.changed_data)}); messages.success(request,"اطلاعات اداره ذخیره شد."); return redirect("manage_department_detail",pk=obj.pk)
    return render(request,"control/object_form.html",{"form":form,"title":"ایجاد اداره" if not pk else "ویرایش اداره","department":department if pk else None})


@login_required
@require_POST
def manage_department_status(request,pk):
    department=_managed_department(request.user,pk)
    form=DepartmentLifecycleForm(request.POST,department=department,actor=request.user)
    if form.is_valid():
        target=form.cleaned_data["status"]
        if target==Department.Status.ARCHIVED and not is_super_admin(request.user): raise PermissionDenied
        old=department.status; department.status=target; department.save(update_fields=["status","updated_at"]); audit(request.user,"DEPARTMENT_STATUS_CHANGED",department,{"from":old,"to":target}); messages.success(request,"وضعیت اداره تغییر کرد.")
    else: messages.error(request,"تغییر وضعیت انجام نشد: "+" ".join(e for errors in form.errors.values() for e in errors))
    return redirect("manage_department_detail",pk=pk)


@login_required
@require_POST
def manage_department_members(request,pk):
    department=_managed_department(request.user,pk)
    if not can(request.user,Action.ROLE_MANAGE,department=department): raise PermissionDenied
    if request.POST.get("remove"):
        assignment=get_object_or_404(RoleAssignment,pk=request.POST["remove"],department=department,is_active=True)
        if assignment.role==RoleAssignment.Role.DEPARTMENT_LEAD and not is_super_admin(request.user): raise PermissionDenied
        assignment.is_active=False; assignment.save(update_fields=["is_active","updated_at"]); audit(request.user,"DEPARTMENT_MEMBERSHIP_REMOVED",assignment,{"department":department.pk,"role":assignment.role}); messages.success(request,"عضویت غیرفعال شد.")
    else:
        form=DepartmentMembershipForm(request.POST,actor=request.user)
        if form.is_valid():
            assignment,created=RoleAssignment.objects.update_or_create(user=form.cleaned_data["user"],department=department,role=form.cleaned_data["role"],defaults={"scope_type":RoleAssignment.ScopeType.DEPARTMENT,"is_active":True,"assigned_by":request.user})
            audit(request.user,"DEPARTMENT_MEMBERSHIP_ADDED" if created else "DEPARTMENT_ROLE_CHANGED",assignment,{"department":department.pk,"role":assignment.role}); messages.success(request,"عضویت اداره ذخیره شد.")
        else: messages.error(request,"عضویت ذخیره نشد.")
    return redirect("manage_department_detail",pk=pk)


@login_required
def manage_family_edit(request,department_pk=None,pk=None):
    family=get_object_or_404(Category,pk=pk) if pk else None
    department=_managed_department(request.user,family.department_id if family else department_pk)
    if not can(request.user,Action.CATALOGUE_MANAGE,department=department): raise PermissionDenied
    form=ServiceFamilyForm(request.POST or None,instance=family)
    if request.method=="POST" and form.is_valid():
        obj=form.save(False); obj.department=department; obj.save(); audit(request.user,"SERVICE_FAMILY_CREATED" if not family else "SERVICE_FAMILY_UPDATED",obj,{"department":department.pk,"fields":list(form.changed_data)}); messages.success(request,"خانواده خدمت ذخیره شد."); return redirect("manage_department_detail",pk=department.pk)
    return render(request,"control/object_form.html",{"form":form,"title":"ایجاد خانواده خدمت" if not family else "ویرایش خانواده خدمت","department":department})


@login_required
def manage_service_edit(request,department_pk=None,pk=None):
    service=get_object_or_404(Service.objects.select_related("category__department"),pk=pk) if pk else None
    department=_managed_department(request.user,service.department.pk if service else department_pk)
    if not can(request.user,Action.CATALOGUE_MANAGE,department=department): raise PermissionDenied
    form=ServiceManagementForm(request.POST or None,instance=service,department=department)
    if request.method=="POST" and form.is_valid():
        obj=form.save(); audit(request.user,"SERVICE_CREATED" if not service else "SERVICE_UPDATED",obj,{"department":department.pk,"fields":list(form.changed_data)}); messages.success(request,"خدمت ذخیره شد."); return redirect("manage_department_detail",pk=department.pk)
    return render(request,"control/object_form.html",{"form":form,"title":"ایجاد خدمت" if not service else "ویرایش خدمت","department":department})
