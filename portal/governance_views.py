"""V2.3 scoped credit administration and approval workspaces."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import (AllocationPeriodForm, ApprovalPolicyForm, CreditAllocationForm, MessageForm,
                    PriorityPolicyForm, ProviderApprovalForm, SeniorApprovalConfigurationForm)
from .governance import (GovernanceError, capacity_for, decide_step, may_clarify, may_decide,
                         may_view_case, provide_clarification, request_provider_approval, cancel_pending_approval, wallet_balance)
from .models import (AllocationPeriod, ApprovalAttachment, ApprovalCase,
                     ApprovalPolicy, ApprovalStep, CreditAllocation, PriorityPolicy,
                     Request, RoleAssignment, SeniorApprovalConfiguration, User)
from .policies import (Action, can, is_program_manager, is_project_manager,
                       is_super_admin, program_ids_for_role, project_ids_for_role,
                       request_scope)
from .utils import audit


def _admin(user):
    if not is_super_admin(user):raise Http404


@login_required
@require_GET
def capacity_balance(request):
    priority=get_object_or_404(PriorityPolicy,code=request.GET.get('priority'),is_active=True)
    service_id=request.GET.get('service','')
    from .models import Service
    service=get_object_or_404(Service.objects.select_related('category__department'),pk=service_id) if service_id.isdigit() else None
    if not service:raise Http404
    if not priority.requires_credit:return JsonResponse({'requires_credit':False})
    role=request.GET.get('role','')
    raw_program=request.GET.get('program','')
    raw_project=request.GET.get('project','')
    if role==RoleAssignment.Role.PROJECT_MANAGER:
        if not raw_project.isdigit() or int(raw_project) not in project_ids_for_role(request.user):raise Http404
        from .models import Project
        project=get_object_or_404(Project,pk=raw_project)
        program_id=project.program_id
    elif role==RoleAssignment.Role.PROGRAM_MANAGER:
        if not raw_program.isdigit() or int(raw_program) not in program_ids_for_role(request.user):raise Http404
        program_id=int(raw_program)
    else:raise Http404
    balance=capacity_for(program_id,service.department.pk,priority.code)
    return JsonResponse({'requires_credit':True,'remaining':balance,'available':balance is not None and balance>0,'last_credit':balance==1})


@login_required
def capacity_dashboard(request):
    if not (is_super_admin(request.user) or is_program_manager(request.user) or is_project_manager(request.user)):raise Http404
    if is_super_admin(request.user):wallets=CreditAllocation.objects.all()
    else:
        from .models import Project
        program_ids=program_ids_for_role(request.user)|set(Project.objects.filter(pk__in=project_ids_for_role(request.user)).values_list('program_id',flat=True))
        wallets=CreditAllocation.objects.filter(program_id__in=program_ids)
    wallets=wallets.select_related('program','department','priority','period').order_by('program__name','department__name','priority__display_order','-period__starts_on')
    rows=[{'wallet':w,'reserved':w.reservations.filter(status='RESERVED').count(),
           'consumed':w.reservations.filter(status='CONSUMED').count(),'remaining':wallet_balance(w)} for w in wallets]
    return render(request,'control/capacity.html',{'rows':rows,'can_manage':is_super_admin(request.user),
        'priorities':PriorityPolicy.objects.all(),'periods':AllocationPeriod.objects.all(),
        'policies':ApprovalPolicy.objects.select_related('priority').all(),
        'senior':SeniorApprovalConfiguration.objects.filter(pk=1).first(),
        'senior_assignments':RoleAssignment.objects.filter(role=RoleAssignment.Role.SENIOR_APPROVAL_AUTHORITY).select_related('user') if is_super_admin(request.user) else [],
        'active_users':User.objects.filter(is_active=True).order_by('full_name') if is_super_admin(request.user) else []})


@login_required
def manage_priority_policy(request,pk):
    _admin(request.user)
    obj=get_object_or_404(PriorityPolicy,pk=pk)
    form=PriorityPolicyForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        form.save();audit(request.user,'PRIORITY_POLICY_UPDATED',obj,{'fields':list(form.changed_data)});return redirect('capacity_dashboard')
    return render(request,'control/object_form.html',{'form':form,'title':'سیاست اولویت','back_url':reverse('capacity_dashboard')})


@login_required
def manage_allocation_period(request,pk=None):
    _admin(request.user)
    obj=get_object_or_404(AllocationPeriod,pk=pk) if pk else AllocationPeriod()
    form=AllocationPeriodForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        form.save();audit(request.user,'ALLOCATION_PERIOD_UPDATED',obj,{'fields':list(form.changed_data)});return redirect('capacity_dashboard')
    return render(request,'control/object_form.html',{'form':form,'title':'دورهٔ اعتبار','back_url':reverse('capacity_dashboard')})


@login_required
def manage_credit_allocation(request,pk=None):
    _admin(request.user)
    obj=get_object_or_404(CreditAllocation,pk=pk) if pk else CreditAllocation(created_by=request.user)
    form=CreditAllocationForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            obj=form.save(commit=False)
            if not obj.created_by_id:obj.created_by=request.user
            obj.save()
            audit(request.user,'CREDIT_ALLOCATION_UPDATED',obj,{'fields':list(form.changed_data),'quantity':obj.quantity})
        return redirect('capacity_dashboard')
    return render(request,'control/object_form.html',{'form':form,'title':'تخصیص اعتبار','back_url':reverse('capacity_dashboard')})


@login_required
def manage_approval_policy(request,pk=None):
    _admin(request.user)
    obj=get_object_or_404(ApprovalPolicy,pk=pk) if pk else ApprovalPolicy()
    form=ApprovalPolicyForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        form.save();audit(request.user,'APPROVAL_POLICY_UPDATED',obj,{'fields':list(form.changed_data)});return redirect('capacity_dashboard')
    return render(request,'control/object_form.html',{'form':form,'title':'سیاست تأیید','back_url':reverse('capacity_dashboard')})


@login_required
def manage_senior_authority(request):
    _admin(request.user)
    obj=SeniorApprovalConfiguration.objects.filter(pk=1).first() or SeniorApprovalConfiguration(pk=1)
    form=SeniorApprovalConfigurationForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        form.save();audit(request.user,'SENIOR_AUTHORITY_UPDATED',obj,{'fields':list(form.changed_data)});return redirect('capacity_dashboard')
    return render(request,'control/object_form.html',{'form':form,'title':'مرجع تأیید ارشد','back_url':reverse('capacity_dashboard')})


@login_required
@require_POST
def assign_senior_authority(request):
    _admin(request.user)
    if request.POST.get('deactivate','').isdigit():
        assignment=get_object_or_404(RoleAssignment,pk=request.POST['deactivate'],role=RoleAssignment.Role.SENIOR_APPROVAL_AUTHORITY)
        assignment.is_active=False;assignment.save();audit(request.user,'SENIOR_AUTHORITY_DEACTIVATED',assignment)
    else:
        user=get_object_or_404(User,pk=request.POST.get('user'),is_active=True)
        assignment,created=RoleAssignment.objects.get_or_create(user=user,role=RoleAssignment.Role.SENIOR_APPROVAL_AUTHORITY,scope_type=RoleAssignment.ScopeType.GLOBAL,
            defaults={'assigned_by':request.user})
        if not created:assignment.is_active=True;assignment.assigned_by=request.user;assignment.save()
        audit(request.user,'SENIOR_AUTHORITY_ASSIGNED',assignment)
    return redirect('capacity_dashboard')


@login_required
@require_POST
def provider_approval(request,pk):
    req=get_object_or_404(request_scope(request.user),pk=pk)
    form=ProviderApprovalForm(request.POST,request.FILES)
    if not form.is_valid():
        messages.error(request,'ارجاع ثبت نشد: '+'، '.join(str(e) for errors in form.errors.values() for e in errors))
        return redirect('control_request_detail',pk=pk)
    details={key:form.cleaned_data[key] for key in ('reason','assessment','estimated_time','estimated_cost','conditions','recommendation','risks')}
    try:case=request_provider_approval(pk,request.user,target=form.cleaned_data['target'],details=details,attachment=form.cleaned_data.get('file'))
    except GovernanceError as exc:
        messages.error(request,str(exc));return redirect('control_request_detail',pk=pk)
    messages.success(request,'درخواست تأیید ثبت شد.')
    return redirect('approval_detail',pk=case.pk)


@login_required
@require_POST
def cancel_priority_approval(request,pk):
    req=get_object_or_404(Request,pk=pk,requester=request.user)
    try:
        if not cancel_pending_approval(req.pk,request.user):raise GovernanceError('تأیید باز برای لغو وجود ندارد.')
    except GovernanceError as exc:messages.error(request,str(exc))
    else:messages.success(request,'درخواست و اعتبار رزروشده لغو شد.')
    return redirect('request_detail',pk=pk)


@login_required
def approval_inbox(request):
    if not request.user.is_active:raise Http404
    cases=ApprovalCase.objects.select_related('request__program','request__project_entity','request__department','request__service').prefetch_related('steps').order_by('-created_at')
    cases=[case for case in cases if any(may_decide(request.user,step) for step in case.steps.all())]
    status=request.GET.get('status','PENDING')
    if status not in {'PENDING','APPROVED','REJECTED'}:raise Http404
    if status=='PENDING':cases=[case for case in cases if case.status in {ApprovalCase.Status.PENDING,ApprovalCase.Status.CLARIFICATION_REQUESTED}]
    else:cases=[case for case in cases if case.status==status]
    return render(request,'portal/approval_inbox.html',{'cases':cases,'status':status})


@login_required
def approval_detail(request,pk):
    case=get_object_or_404(ApprovalCase.objects.select_related('request__requester','request__program','request__project_entity','request__department','request__service','requested_by').prefetch_related('steps__decisions','attachments','clarifications__author'),pk=pk)
    if not may_view_case(request.user,case):raise Http404
    pending_step=next((step for step in case.steps.all() if step.status in {ApprovalStep.Status.PENDING,ApprovalStep.Status.CLARIFICATION_REQUESTED} and may_decide(request.user,step)),None)
    return render(request,'portal/approval_detail.html',{'case':case,'item':case.request,'pending_step':pending_step,'can_clarify':may_clarify(request.user,case),'clarification_form':MessageForm()})


@login_required
@require_POST
def approval_clarify(request,pk):
    case=get_object_or_404(ApprovalCase,pk=pk)
    if not may_clarify(request.user,case):raise Http404
    form=MessageForm(request.POST,request.FILES)
    if not form.is_valid():messages.error(request,'توضیح یا پیوست معتبر نیست.');return redirect('approval_detail',pk=pk)
    try:provide_clarification(pk,request.user,form.cleaned_data['body'],form.cleaned_data.get('file'))
    except GovernanceError as exc:messages.error(request,str(exc))
    else:messages.success(request,'توضیح برای تصمیم‌گیرنده ارسال شد.')
    return redirect('approval_detail',pk=pk)


@login_required
@require_POST
def approval_decide(request,pk):
    step=get_object_or_404(ApprovalStep,pk=pk)
    if not may_decide(request.user,step):raise Http404
    try:case=decide_step(pk,request.user,request.POST.get('outcome'),request.POST.get('reason',''))
    except GovernanceError as exc:messages.error(request,str(exc));return redirect('approval_detail',pk=step.case_id)
    messages.success(request,'تصمیم ثبت شد.')
    return redirect('approval_detail',pk=case.pk)


@login_required
def approval_attachment_download(request,pk):
    attachment=get_object_or_404(ApprovalAttachment.objects.select_related('case__request'),pk=pk)
    if not may_view_case(request.user,attachment.case):raise Http404
    return FileResponse(attachment.file.open('rb'),as_attachment=True,filename=attachment.original_name)
