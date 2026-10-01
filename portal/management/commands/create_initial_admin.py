import os
from django.core.management.base import BaseCommand, CommandError
from portal.models import RoleAssignment, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
class Command(BaseCommand):
    help="Create the initial administrator from environment variables"
    def handle(self,*args,**opts):
        username=os.getenv("INITIAL_ADMIN_USERNAME"); password=os.getenv("INITIAL_ADMIN_PASSWORD"); email=os.getenv("INITIAL_ADMIN_EMAIL",""); full_name=os.getenv("INITIAL_ADMIN_FULL_NAME","مدیر سامانه")
        if not username or not password: raise CommandError("INITIAL_ADMIN_USERNAME and INITIAL_ADMIN_PASSWORD are required")
        existing=User.objects.filter(username=username).first()
        if existing:
            if existing.role==User.Role.ADMIN:
                RoleAssignment.objects.get_or_create(user=existing,role=RoleAssignment.Role.SUPER_ADMIN,scope_type=RoleAssignment.ScopeType.GLOBAL,department=None,defaults={"is_active":existing.is_active})
            self.stdout.write("Initial admin already exists"); return
        user=User(username=username,email=email,full_name=full_name,role=User.Role.ADMIN,must_change_password=True,is_active=True)
        try: validate_password(password,user)
        except ValidationError as exc: raise CommandError("Initial admin password is not acceptable: "+"; ".join(exc.messages))
        user.set_password(password); user.save()
        RoleAssignment.objects.get_or_create(user=user,role=RoleAssignment.Role.SUPER_ADMIN,scope_type=RoleAssignment.ScopeType.GLOBAL,department=None)
        self.stdout.write(self.style.SUCCESS("Initial admin created"))
