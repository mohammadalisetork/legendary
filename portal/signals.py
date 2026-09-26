from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone
from .models import ActivityLog
@receiver(user_logged_in)
def logged_in(sender,request,user,**kwargs):
    user.last_activity_at=timezone.now(); user.save(update_fields=["last_activity_at"])
    ActivityLog.objects.create(actor=user,action="USER_LOGIN",target_type="User",target_id=str(user.pk))
