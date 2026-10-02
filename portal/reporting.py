"""Scoped, live request facts and deterministic management measures."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from statistics import mean, median

import jdatetime
from django.conf import settings
from django.db.models import Prefetch, Q
from django.http import Http404
from django.utils import timezone

from .models import ApprovalCase, ApprovalStep, CreditAllocation, CreditReservation, Department, Project, Request, RequestHistory, RoleAssignment, WorkingCalendar
from .policies import department_ids_for_role, has_global_role, is_super_admin, program_ids_for_role, project_ids_for_role

FINAL = {Request.Status.COMPLETED, Request.Status.REJECTED, Request.Status.CANCELLED}
OPEN = set(Request.Status.values) - FINAL - {Request.Status.DRAFT}
DIMENSIONS = ("department", "program", "project", "family", "service", "status", "priority", "requester", "unit", "owner")
SNAPSHOT_FILTERS = ("snapshot_department", "snapshot_program", "snapshot_project", "snapshot_family", "snapshot_service")
PERIODS = ("today", "7d", "30d", "month", "quarter", "6m", "ytd", "year", "custom")


def month_start(day, offset=0):
    j = jdatetime.date.fromgregorian(date=day)
    n = j.year * 12 + j.month - 1 + offset
    return jdatetime.date(n // 12, n % 12 + 1, 1).togregorian()


def year_start(day, offset=0):
    j = jdatetime.date.fromgregorian(date=day)
    return jdatetime.date(j.year + offset, 1, 1).togregorian()


@dataclass(frozen=True)
class Window:
    start: date
    end: date
    preset: str

    def previous(self):
        if self.preset in ("month", "quarter", "ytd"):
            start = month_start(self.start, -1 if self.preset == "month" else -3) if self.preset != "ytd" else year_start(self.start, -1)
            return Window(start, min(start + (self.end - self.start), self.start - timedelta(days=1)), "custom")
        if self.preset == "year":
            return Window(year_start(self.start, -1), self.start - timedelta(days=1), "custom")
        length = (self.end - self.start).days + 1
        return Window(self.start - timedelta(days=length), self.start - timedelta(days=1), "custom")

    def timestamps(self):
        return (timezone.make_aware(datetime.combine(self.start, time.min)), timezone.make_aware(datetime.combine(self.end + timedelta(days=1), time.min)))


def window_from_params(params, today=None):
    today = today or timezone.localdate()
    preset = params.get("period", "30d")
    if preset not in PERIODS: raise Http404
    if preset == "custom":
        try: start, end = date.fromisoformat(params["start"]), date.fromisoformat(params["end"])
        except (KeyError, ValueError): raise Http404 from None
        if start > end: raise Http404
    elif preset == "today": start = end = today
    elif preset == "7d": start, end = today - timedelta(days=6), today
    elif preset == "30d": start, end = today - timedelta(days=29), today
    elif preset == "month": start, end = month_start(today), today
    elif preset == "quarter":
        j = jdatetime.date.fromgregorian(date=today)
        start, end = month_start(today, -((j.month - 1) % 3)), today
    elif preset == "6m": start, end = month_start(today, -5), today
    elif preset == "ytd": start, end = year_start(today), today
    else: start, end = year_start(today), year_start(today, 1) - timedelta(days=1)
    return Window(start, end, preset)


def global_access(user):
    return is_super_admin(user) or has_global_role(user, RoleAssignment.Role.SUPERVISOR) or has_global_role(user, RoleAssignment.Role.EXECUTIVE_VIEWER)


def analytics_allowed(user):
    return bool(getattr(user, "is_authenticated", False) and user.is_active and (global_access(user) or
        department_ids_for_role(user, RoleAssignment.Role.DEPARTMENT_LEAD) or department_ids_for_role(user, RoleAssignment.Role.REQUEST_MANAGER) or
        program_ids_for_role(user) or project_ids_for_role(user)))


def analytics_scope(user):
    if not analytics_allowed(user): raise Http404
    qs = Request.objects.exclude(status=Request.Status.DRAFT).filter(submitted_at__isnull=False)
    if global_access(user): return qs
    leads = department_ids_for_role(user, RoleAssignment.Role.DEPARTMENT_LEAD)
    managers = department_ids_for_role(user, RoleAssignment.Role.REQUEST_MANAGER)
    programs, projects = program_ids_for_role(user), project_ids_for_role(user)
    rule = Q(pk__in=[])
    if leads: rule |= Q(department_id__in=leads)
    if managers:
        rule |= Q(department_id__in=managers, provider_hold=False) & (Q(assigned_owner=user) | Q(assigned_owner__isnull=True) | Q(service__default_owner=user))
    if programs: rule |= Q(program_id__in=programs)
    if projects: rule |= Q(project_entity_id__in=projects)
    return qs.filter(rule).distinct()


def report_filters(user, params, forced=None):
    result = {}
    for key in DIMENSIONS:
        raw = params.get(key, "").strip()[:160]
        if not raw: continue
        if key == "department":
            obj = Department.objects.filter(code=raw).first()
            if not obj: raise Http404
            if not global_access(user) and obj.pk not in (department_ids_for_role(user, RoleAssignment.Role.DEPARTMENT_LEAD) | department_ids_for_role(user, RoleAssignment.Role.REQUEST_MANAGER)) and not (program_ids_for_role(user) or project_ids_for_role(user)): raise Http404
            result[key] = obj.pk
        elif key in {"program", "project", "family", "service", "requester", "owner"}:
            if not raw.isdigit(): raise Http404
            result[key] = int(raw)
            if key == "program" and not global_access(user) and not (department_ids_for_role(user, RoleAssignment.Role.DEPARTMENT_LEAD) or department_ids_for_role(user, RoleAssignment.Role.REQUEST_MANAGER)):
                permitted = program_ids_for_role(user) | set(Project.objects.filter(pk__in=project_ids_for_role(user)).values_list("program_id", flat=True))
                if result[key] not in permitted: raise Http404
            if key == "project" and not global_access(user) and not (department_ids_for_role(user, RoleAssignment.Role.DEPARTMENT_LEAD) or department_ids_for_role(user, RoleAssignment.Role.REQUEST_MANAGER) or program_ids_for_role(user)) and result[key] not in project_ids_for_role(user): raise Http404
        elif key == "status":
            if raw not in Request.Status.values[1:]: raise Http404
            result[key] = raw
        elif key == "priority":
            if raw not in Request.Priority.values: raise Http404
            result[key] = raw
        else: result[key] = raw
    for key in SNAPSHOT_FILTERS:
        raw = params.get(key, "").strip()[:200]
        if raw: result[key] = raw
    for key, value in (forced or {}).items():
        if key in result and result[key] != value: raise Http404
        result[key] = value
    return result


def dimension_queryset(scope, filters):
    columns = {"department":"department_id", "program":"program_id", "project":"project_entity_id", "family":"service__category_id", "service":"service_id", "status":"status", "priority":"priority", "requester":"requester_id", "unit":"requesting_unit", "owner":"assigned_owner_id"}
    for key, value in filters.items():
        if key in columns: scope = scope.filter(**{columns[key]:value})
    return scope


def calendar_data():
    cal = WorkingCalendar.objects.filter(active=True).prefetch_related("non_working_dates").first()
    return cal, {row.date for row in cal.non_working_dates.all()} if cal else set()


def working_seconds(start, end, cal, holidays):
    if not start or not end or end <= start: return 0
    if not cal: return int((end-start).total_seconds())
    start, end = timezone.localtime(start), timezone.localtime(end)
    day, total = start.date(), 0
    while day <= end.date():
        if day.weekday() not in cal.weekend_days and day not in holidays:
            opening = timezone.make_aware(datetime.combine(day, cal.workday_start))
            closing = timezone.make_aware(datetime.combine(day, cal.workday_end))
            total += max(0, int((min(end, closing) - max(start, opening)).total_seconds()))
        day += timedelta(days=1)
    return total


def pauses(req, end):
    intervals, opened = [], None
    for event in req.report_history:
        if event.action == "CLOCK_PAUSED" and opened is None: opened = event.created_at
        elif event.action == "CLOCK_RESUMED" and opened is not None:
            intervals.append((opened, event.created_at)); opened = None
    if opened: intervals.append((opened, end))
    intervals.extend((step.started_at, step.decided_at or end) for step in req.report_steps if step.pauses_sla and step.started_at)
    clipped = sorted((max(a, req.submitted_at), min(b,end)) for a,b in intervals if a and b and b>req.submitted_at and a<end)
    result = []
    for a,b in clipped:
        if result and a<=result[-1][1]: result[-1]=(result[-1][0],max(b,result[-1][1]))
        else: result.append((a,b))
    return result


def operational_seconds(req, end, cal, holidays):
    total = working_seconds(req.submitted_at,end,cal,holidays)
    return max(0,total-sum(working_seconds(a,b,cal,holidays) for a,b in pauses(req,end)))


@dataclass
class Fact:
    request: Request
    department: str
    program: str
    project: str
    family: str
    service: str
    first_seconds: int|None
    resolution_seconds: int|None
    operational_seconds: int
    first_sla: bool|None
    completion_sla: bool|None
    overdue: bool
    at_risk: bool
    aging_days: int
    requester_wait: int
    program_wait: int
    senior_wait: int

    @property
    def status(self): return self.request.status


def names_for(req):
    snap=req.catalogue_snapshot or {}
    unknown="قدیمی / نگاشت‌نشده"
    return dict(department=snap.get("department_name") or req.department.name,
                program=req.program_name_snapshot or (req.program.name if req.program_id else unknown),
                project=req.project_name_snapshot or (req.project_entity.name if req.project_entity_id else unknown),
                family=snap.get("family_name") or req.service.category.name,
                service=snap.get("service_name") or req.service.name)


def facts_for(scope, window, filters, *, now=None):
    now=now or timezone.now()
    start,end=window.timestamps()
    qs=dimension_queryset(scope,filters).filter(submitted_at__gte=start,submitted_at__lt=end).select_related("department","program","project_entity","service__category","requester","assigned_owner").prefetch_related(
        Prefetch("history",queryset=RequestHistory.objects.filter(action__in=["CLOCK_PAUSED","CLOCK_RESUMED"]).order_by("created_at"),to_attr="report_history"),
        Prefetch("approval_steps",queryset=ApprovalStep.objects.all(),to_attr="report_steps"),
        Prefetch("approval_cases",queryset=ApprovalCase.objects.all(),to_attr="report_cases"))
    cal,holidays=calendar_data(); threshold=settings.REPORT_AT_RISK_RATIO
    facts=[]
    for req in qs.iterator(chunk_size=500):
        names=names_for(req)
        if any(names[key.removeprefix("snapshot_")]!=value for key,value in filters.items() if key in SNAPSHOT_FILTERS): continue
        finish=min(req.completed_at or now,now); first_finish=min(req.first_response_at or now,now)
        elapsed=operational_seconds(req,finish,cal,holidays); first_elapsed=operational_seconds(req,first_finish,cal,holidays)
        initial=working_seconds(req.submitted_at,req.expected_initial_response_at,cal,holidays)
        delivery=timezone.make_aware(datetime.combine(req.estimated_delivery_max,cal.workday_end if cal else time.max)) if req.estimated_delivery_max else None
        budget=working_seconds(req.submitted_at,delivery,cal,holidays)
        eligible=req.status not in {Request.Status.REJECTED,Request.Status.CANCELLED}
        first_sla=(first_elapsed<=initial) if eligible and initial and (req.first_response_at or now>=req.expected_initial_response_at) else None
        completion_sla=(elapsed<=budget) if eligible and budget and (req.completed_at or now>=delivery) else None
        due=initial if not req.first_response_at else budget; consumed=first_elapsed if not req.first_response_at else elapsed
        overdue=bool(req.status in OPEN and due and consumed>due)
        at_risk=bool(req.status in OPEN and due and not overdue and consumed>=threshold*due)
        requester_wait,opened=0,None
        for event in req.report_history:
            if event.action=="CLOCK_PAUSED" and event.to_status==Request.Status.NEED_INFO: opened=event.created_at
            elif event.action=="CLOCK_RESUMED" and opened:
                requester_wait+=working_seconds(opened,min(event.created_at,finish),cal,holidays);opened=None
        if opened: requester_wait+=working_seconds(opened,finish,cal,holidays)
        def approval_wait(target): return sum(max(0,int((min(step.decided_at or now,now)-step.started_at).total_seconds())) for step in req.report_steps if step.started_at and step.target==target)
        facts.append(Fact(req,**names,first_seconds=first_elapsed if req.first_response_at else None,
            resolution_seconds=max(0,int((req.completed_at-req.submitted_at).total_seconds())) if req.completed_at else None,
            operational_seconds=elapsed,first_sla=first_sla,completion_sla=completion_sla,overdue=overdue,at_risk=at_risk,
            aging_days=max(0,(timezone.localdate(finish)-timezone.localdate(req.submitted_at)).days),
            requester_wait=requester_wait,program_wait=approval_wait("PROGRAM_MANAGER"),senior_wait=approval_wait("SENIOR")))
    return facts


def percentile(values,p):
    if len(values)<5:return None
    values=sorted(values);position=(len(values)-1)*p;low=int(position)
    return values[low]+(values[min(low+1,len(values)-1)]-values[low])*(position-low)


def average(values):return round(mean(values)) if values else None


def metrics(facts):
    completed=[f for f in facts if f.status==Request.Status.COMPLETED]; opened=[f for f in facts if f.status in OPEN]
    first=[f.first_seconds for f in facts if f.first_seconds is not None]
    resolution=[f.resolution_seconds for f in completed if f.resolution_seconds is not None]
    f_sla=[f.first_sla for f in facts if f.first_sla is not None];c_sla=[f.completion_sla for f in facts if f.completion_sla is not None]
    rate=lambda n,d:round(n*100/d,1) if d else None
    return dict(total=len(facts),new=len(facts),open=len(opened),backlog=len(opened),completed=len(completed),
        in_progress=sum(f.status==Request.Status.IN_PROGRESS for f in facts),pending=sum(f.request.provider_hold for f in facts),
        emergency=sum(f.request.priority==Request.Priority.EMERGENCY for f in facts),very_urgent=sum(f.request.priority==Request.Priority.VERY_URGENT for f in facts),
        completion_rate=rate(len(completed),sum(f.status not in {Request.Status.REJECTED,Request.Status.CANCELLED} for f in facts)),
        overdue=sum(f.overdue for f in opened),at_risk=sum(f.at_risk for f in opened),
        first_avg=average(first),first_median=round(median(first)) if first else None,first_p75=percentile(first,.75),first_p90=percentile(first,.9),
        resolution_avg=average(resolution),resolution_median=round(median(resolution)) if resolution else None,resolution_p75=percentile(resolution,.75),resolution_p90=percentile(resolution,.9),
        provider_avg=average([f.operational_seconds for f in completed]),requester_wait_avg=average([f.requester_wait for f in facts if f.requester_wait]),
        program_wait_avg=average([f.program_wait for f in facts if f.program_wait]),senior_wait_avg=average([f.senior_wait for f in facts if f.senior_wait]),
        first_sla=rate(sum(f_sla),len(f_sla)),first_sla_count=len(f_sla),completion_sla=rate(sum(c_sla),len(c_sla)),completion_sla_count=len(c_sla))


def group(facts, dimension):
    def key(f):
        req=f.request
        return {"department":(req.department_id,f.department),"program":(req.program_id or 0,f.program),"project":(req.project_entity_id or 0,f.project),
            "family":(req.service.category_id,f.family),"service":(req.service_id,f.service),
            "owner":(req.assigned_owner_id or 0,(req.assigned_owner.full_name or req.assigned_owner.username) if req.assigned_owner_id else "بدون مسئول"),
            "status":(req.status,req.get_status_display()),"priority":(req.priority,req.get_priority_display())}[dimension]
    buckets=defaultdict(list)
    for f in facts:buckets[key(f)].append(f)
    result=[]
    for (identifier,name),items in sorted(buckets.items(),key=lambda pair:(-len(pair[1]),pair[0][1])):
        m=metrics(items)
        result.append(dict(id=identifier,name=name,total=m["total"],open=m["open"],completed=m["completed"],overdue=m["overdue"],sla=m["completion_sla"],resolution_avg=m["resolution_avg"],resolution_median=m["resolution_median"],resolution_p90=m["resolution_p90"]))
    return result


def matrix(facts):
    buckets=defaultdict(list)
    for f in facts:buckets[(f.request.program_id or 0,f.program,f.request.department_id,f.department)].append(f)
    return [dict(program_id=p,program=pn,department_id=d,department=dn,total=len(items),open=metrics(items)["open"],overdue=metrics(items)["overdue"],sla=metrics(items)["completion_sla"],resolution_avg=metrics(items)["resolution_avg"]) for (p,pn,d,dn),items in sorted(buckets.items(),key=lambda pair:(pair[0][1],pair[0][3]))]


def aging(facts):
    return [dict(name=label,total=sum(f.status in OPEN and f.aging_days>=low and (high is None or f.aging_days<=high) for f in facts)) for label,low,high in (("۰ تا ۲",0,2),("۳ تا ۵",3,5),("۶ تا ۱۰",6,10),("۱۱ تا ۲۰",11,20),("۲۱ روز و بیشتر",21,None))]


def approval_metrics(facts):
    cases=[c for f in facts for c in f.request.report_cases]
    decided=[c for c in cases if c.status in {ApprovalCase.Status.APPROVED,ApprovalCase.Status.REJECTED}]
    wait=[f.program_wait+f.senior_wait for f in facts if f.program_wait or f.senior_wait]
    groups={key:defaultdict(int) for key in ("department","program")}
    for f in facts:
        for key in groups:groups[key][getattr(f,key)]+=len(f.request.report_cases)
    return dict(total=len(cases),pending=sum(c.status in {ApprovalCase.Status.PENDING,ApprovalCase.Status.CLARIFICATION_REQUESTED} for c in cases),
        approved=sum(c.status==ApprovalCase.Status.APPROVED for c in cases),rejected=sum(c.status==ApprovalCase.Status.REJECTED for c in cases),
        rate=round(100*sum(c.status==ApprovalCase.Status.APPROVED for c in decided)/len(decided),1) if decided else None,
        wait_avg=average(wait),program_wait_avg=average([f.program_wait for f in facts if f.program_wait]),senior_wait_avg=average([f.senior_wait for f in facts if f.senior_wait]),
        by_type=[dict(name=next(c.get_trigger_display() for c in cases if c.trigger==value),total=sum(c.trigger==value for c in cases)) for value in sorted({c.trigger for c in cases})],
        by_department=[dict(name=name,total=count) for name,count in sorted(groups["department"].items()) if count],
        by_program=[dict(name=name,total=count) for name,count in sorted(groups["program"].items()) if count])


def credit_metrics(user,filters,window):
    qs=CreditAllocation.objects.select_related("program","department","period","priority").prefetch_related("reservations")
    if not global_access(user):
        departments=department_ids_for_role(user,RoleAssignment.Role.DEPARTMENT_LEAD)|department_ids_for_role(user,RoleAssignment.Role.REQUEST_MANAGER)
        programs=program_ids_for_role(user)|set(Project.objects.filter(pk__in=project_ids_for_role(user)).values_list("program_id",flat=True))
        rule=Q(pk__in=[])
        if departments:rule|=Q(department_id__in=departments)
        if programs:rule|=Q(program_id__in=programs)
        qs=qs.filter(rule)
    for key,field in (("department","department_id"),("program","program_id"),("priority","priority__code")):
        if key in filters:qs=qs.filter(**{field:filters[key]})
    qs=qs.filter(period__starts_on__lte=window.end,period__ends_on__gte=window.start)
    rows=[]
    for w in qs:
        status=[r.status for r in w.reservations.all()]
        reserved,consumed,released=(status.count(s) for s in (CreditReservation.Status.RESERVED,CreditReservation.Status.CONSUMED,CreditReservation.Status.RELEASED))
        rows.append(dict(program=w.program.name,department=w.department.name,period=w.period.name,priority=w.priority.name,quantity=w.quantity,reserved=reserved,consumed=consumed,released=released,remaining=max(0,w.quantity-reserved-consumed),utilization=round(100*(reserved+consumed)/w.quantity,1) if w.quantity else None))
    return rows


def trend(facts,window):
    span=(window.end-window.start).days+1;interval=1 if span<=45 else 7 if span<=180 else 30
    counts=defaultdict(int)
    for f in facts:
        day=timezone.localdate(f.request.submitted_at)
        bucket=window.start+timedelta(days=((day-window.start).days//interval)*interval)
        counts[bucket]+=1
    return [dict(date=(window.start+timedelta(days=n)).isoformat(),new=counts[window.start+timedelta(days=n)],completed=0) for n in range(0,span,interval)]


def completed_during(scope,window,filters):
    start,end=window.timestamps()
    qs=dimension_queryset(scope,filters).filter(status=Request.Status.COMPLETED,completed_at__gte=start,completed_at__lt=end).select_related("department","program","project_entity","service__category")
    counts=defaultdict(int)
    for req in qs.iterator(chunk_size=500):
        names=names_for(req)
        if any(names[key.removeprefix("snapshot_")]!=value for key,value in filters.items() if key in SNAPSHOT_FILTERS):continue
        counts[timezone.localdate(req.completed_at)]+=1
    return counts
