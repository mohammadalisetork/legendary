from datetime import datetime, timedelta
from django.utils import timezone
from .models import ActivityLog, Notification, Request, RequestHistory, WorkingCalendar

def calendar():
    existing=WorkingCalendar.objects.filter(active=True).first()
    if existing:return existing
    created=WorkingCalendar.objects.create(name="تقویم کاری اصلی",weekend_days=[4])
    created.refresh_from_db()
    return created

def add_working_days(start, days):
    cal=calendar(); blocked=set(cal.non_working_dates.values_list("date",flat=True)); current=start; added=0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() not in cal.weekend_days and current not in blocked: added += 1
    return current

def advance_working_seconds(start, seconds, cal=None):
    """Move a due timestamp through the configured working hours."""
    if not start or seconds<=0:return start
    cal=cal or WorkingCalendar.objects.filter(active=True).first()
    if not cal:return start+timedelta(seconds=seconds)
    blocked=set(cal.non_working_dates.values_list('date',flat=True))
    cursor=timezone.localtime(start)
    remaining=seconds
    while remaining>0:
        day=cursor.date()
        if day.weekday() not in cal.weekend_days and day not in blocked:
            opening=timezone.make_aware(datetime.combine(day,cal.workday_start))
            closing=timezone.make_aware(datetime.combine(day,cal.workday_end))
            cursor=max(cursor,opening)
            available=max(0,int((closing-cursor).total_seconds()))
            if available>=remaining:return cursor+timedelta(seconds=remaining)
            remaining-=available
        cursor=timezone.make_aware(datetime.combine(day+timedelta(days=1),cal.workday_start))
    return cursor

def audit(actor, action, target, metadata=None):
    ActivityLog.objects.create(actor=actor,action=action,target_type=target.__class__.__name__,target_id=str(target.pk),metadata=metadata or {})

def history(req, actor, action, from_status="", to_status="", metadata=None):
    RequestHistory.objects.create(request=req,actor=actor,action=action,from_status=from_status,to_status=to_status,metadata=metadata or {})
    audit(actor,action,req,metadata)

def notify(user,title,body,req=None):
    if user: Notification.objects.create(user=user,title=title,body=body,request=req)

def apply_submission_timing(req):
    now=timezone.now(); req.submitted_at=now; req.current_stage_started_at=now
    cal=calendar(); due_date=add_working_days(timezone.localdate(),req.service.initial_response_days)
    req.expected_initial_response_at=timezone.make_aware(timezone.datetime.combine(due_date,cal.workday_end))
    req.estimated_delivery_min=add_working_days(timezone.localdate(),req.service.delivery_min_days)
    req.estimated_delivery_max=add_working_days(timezone.localdate(),req.service.delivery_max_days)

def transition(req, status, actor, reason=""):
    old=req.status; now=timezone.now()
    if status!=old and status not in req.allowed_transitions(): raise ValueError("Invalid request status transition")
    paused_statuses={Request.Status.NEED_INFO,Request.Status.ON_HOLD}; metadata={"reason":reason} if reason else None
    if status in paused_statuses and old not in paused_statuses and not req.operational_paused_at:
        req.operational_paused_at=now; history(req,actor,"CLOCK_PAUSED",old,status,metadata)
    elif old in paused_statuses and status not in paused_statuses and req.operational_paused_at:
        req.paused_seconds += int((now-req.operational_paused_at).total_seconds()); req.operational_paused_at=None; history(req,actor,"CLOCK_RESUMED",old,status,metadata)
    req.needs_user_action=status==Request.Status.NEED_INFO
    req.status=status; req.current_stage_started_at=now
    if status==Request.Status.COMPLETED: req.completed_at=now
    if actor.role in {actor.Role.REQUEST_MANAGER,actor.Role.ADMIN} and not req.first_response_at: req.first_response_at=now
    req.save(); history(req,actor,"STATUS_CHANGED",old,status,metadata)
