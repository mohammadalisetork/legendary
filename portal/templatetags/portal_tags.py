import jdatetime
from django import template
from django.utils import timezone
register=template.Library()
def digits(value): return str(value).translate(str.maketrans("0123456789","۰۱۲۳۴۵۶۷۸۹"))
@register.filter
def jdate(value):
    if not value:return ""
    try:
        if hasattr(value,"hour"):
            if timezone.is_aware(value): value=timezone.localtime(value)
            result=jdatetime.datetime.fromgregorian(datetime=value).strftime("%Y/%m/%d %H:%M")
        else: result=jdatetime.date.fromgregorian(date=value).strftime("%Y/%m/%d")
        return digits(result)
    except Exception:return value
@register.filter
def duration_fa(value):
    try:
        seconds=max(0,int(value)); days,seconds=divmod(seconds,86400); hours,minutes=divmod(seconds,3600); minutes//=60
        parts=[]
        if days: parts.append(f"{digits(days)} روز")
        if hours: parts.append(f"{digits(hours)} ساعت")
        if minutes or not parts: parts.append(f"{digits(minutes)} دقیقه")
        return " و ".join(parts[:2])
    except Exception:return ""
