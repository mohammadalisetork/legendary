from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.auth.forms import PasswordChangeForm
from django.db import connection, transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import InternalNoteForm, LoginForm, ManagerActionForm, MessageForm, RequestBaseForm, request_readiness_errors, save_upload
from .models import Attachment, Category, InternalNote, LoginThrottle, Notification, Request, RequestResponse, Service, User
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

def fa_digits(v): return str(v).translate(str.maketrans("0123456789","۰۱۲۳۴۵۶۷۸۹"))

@login_required
def home(request):
    own=Request.objects.filter(requester=request.user).exclude(status=Request.Status.DRAFT)
    return render(request,"portal/home.html",{"recent":own[:5],"action_required":own.filter(needs_user_action=True)[:5],"categories":Category.objects.filter(active=True).annotate(service_count=Count("services",filter=Q(services__active=True))),"draft_count":Request.objects.filter(requester=request.user,status=Request.Status.DRAFT).count()})

@login_required
def catalog(request):
    services=Service.objects.filter(active=True,category__active=True).select_related("category")
    q=request.GET.get("q","").strip(); category=request.GET.get("category","")
    if q: services=services.filter(Q(name__icontains=q)|Q(code__icontains=q)|Q(full_description__icontains=q)|Q(deliverables__icontains=q)|Q(purpose__icontains=q))
    if category: services=services.filter(category_id=category)
    return render(request,"portal/catalog.html",{"services":services,"categories":Category.objects.filter(active=True),"q":q,"selected_category":category})

@login_required
def service_detail(request,pk): return render(request,"portal/service_detail.html",{"service":get_object_or_404(Service.objects.select_related("category","default_owner"),pk=pk,active=True)})

@login_required
def request_create(request,service_id):
    service=get_object_or_404(Service,pk=service_id,active=True)
    form=RequestBaseForm(request.POST or None,request.FILES or None,service=service,allow_incomplete=request.method=="POST" and request.POST.get("action")!="submit")
    if request.method=="POST" and form.is_valid():
        obj=form.save(False); obj.requester=request.user; obj.requesting_unit=request.user.organizational_unit; obj.assigned_owner=service.default_owner; obj.status=Request.Status.DRAFT; obj.save()
        for file in form.dynamic_files(): save_upload(obj,request.user,file)
        history(obj,request.user,"REQUEST_CREATED")
        if request.POST.get("action")=="submit": return submit_request(request,obj.pk)
        messages.success(request,"پیش‌نویس ذخیره شد."); return redirect("request_detail",pk=obj.pk)
    return render(request,"portal/request_form.html",{"service":service,"form":form})

def accessible_request(user,pk,manager=False):
    qs=Request.objects.select_related("service","requester","assigned_owner")
    if user.role==User.Role.ADMIN: return get_object_or_404(qs,pk=pk)
    if manager and user.role==User.Role.REQUEST_MANAGER:
        return get_object_or_404(qs.exclude(status=Request.Status.DRAFT).filter(Q(assigned_owner=user)|Q(assigned_owner__isnull=True)|Q(service__default_owner=user)).distinct(),pk=pk)
    return get_object_or_404(qs,pk=pk,requester=user)

@login_required
def request_detail(request,pk):
    obj=accessible_request(request.user,pk)
    return render(request,"portal/request_detail.html",{"item":obj,"message_form":MessageForm(),"can_edit":obj.status==Request.Status.DRAFT})

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
    return render(request,"portal/request_form.html",{"service":obj.service,"form":form,"item":obj})

@login_required
@require_POST
def submit_request(request,pk):
    obj=accessible_request(request.user,pk)
    if obj.status!=Request.Status.DRAFT: return redirect("request_detail",pk=pk)
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
    items=Request.objects.filter(requester=request.user).select_related("service","assigned_owner")
    status=request.GET.get("status",""); q=request.GET.get("q","")
    if status: items=items.filter(status=status)
    if q: items=items.filter(Q(public_id__icontains=q)|Q(title__icontains=q)|Q(service__name__icontains=q))
    return render(request,"portal/request_list.html",{"items":items,"statuses":Request.Status.choices,"status":status,"q":q,"drafts":request.path.endswith("drafts/")})

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
    else: messages.error(request,"پیام یا فایل معتبر نیست.")
    return redirect("request_detail",pk=pk)

@login_required
def attachment_download(request,pk):
    a=get_object_or_404(Attachment.objects.select_related("request"),pk=pk); accessible_request(request.user,a.request_id,manager=True if request.user.role!=User.Role.USER else False)
    return FileResponse(a.file.open("rb"),as_attachment=True,filename=a.original_name)

@login_required
def brief_print(request,pk): return render(request,"portal/brief.html",{"item":accessible_request(request.user,pk,manager=True)},content_type="text/html")

@login_required
def notifications(request): return render(request,"portal/notifications.html",{"items":request.user.notifications.select_related("request")})
@login_required
@require_POST
def notification_read(request,pk):
    n=get_object_or_404(Notification,pk=pk,user=request.user); n.read_at=timezone.now(); n.save(update_fields=["read_at"]); return redirect(n.request and "request_detail" or "notifications",**({"pk":n.request_id} if n.request else {}))

def is_manager(user): return user.is_authenticated and user.role in {User.Role.REQUEST_MANAGER,User.Role.ADMIN}
@login_required
def control_dashboard(request):
    if not is_manager(request.user): raise Http404
    qs=manager_scope(request.user); counts={k:qs.filter(status=k).count() for k,_ in Request.Status.choices}
    return render(request,"control/dashboard.html",{"counts":counts,"recent":qs.exclude(status=Request.Status.DRAFT)[:10],"unassigned":qs.filter(assigned_owner__isnull=True).count(),"overdue":sum(1 for x in qs if x.is_overdue)})

def manager_scope(user):
    qs=Request.objects.select_related("service","requester","assigned_owner")
    return qs if user.role==User.Role.ADMIN else qs.exclude(status=Request.Status.DRAFT).filter(Q(assigned_owner=user)|Q(assigned_owner__isnull=True)|Q(service__default_owner=user)).distinct()

@login_required
def control_requests(request):
    if not is_manager(request.user): raise Http404
    qs=manager_scope(request.user).exclude(status=Request.Status.DRAFT); q=request.GET.get("q",""); status=request.GET.get("status",""); priority=request.GET.get("priority",""); owner=request.GET.get("owner","")
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
    return render(request,"control/requests.html",{"items":page,"page":page,"statuses":Request.Status.choices,"priorities":Request.Priority.choices,"services":Service.objects.filter(active=True),"categories":Category.objects.filter(active=True),"owners":User.objects.filter(is_active=True,role__in=[User.Role.REQUEST_MANAGER,User.Role.ADMIN]),"units":User.objects.exclude(organizational_unit="").values_list("organizational_unit",flat=True).distinct()})

@login_required
def control_request_detail(request,pk):
    if not is_manager(request.user): raise Http404
    obj=accessible_request(request.user,pk,manager=True)
    return render(request,"control/request_detail.html",{"item":obj,"message_form":MessageForm(),"note_form":InternalNoteForm(),"action_form":ManagerActionForm(request_obj=obj,initial={"status":obj.status,"owner":obj.assigned_owner})})

@login_required
@require_POST
def control_action(request,pk):
    if not is_manager(request.user): raise Http404
    obj=accessible_request(request.user,pk,manager=True); kind=request.POST.get("kind")
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
