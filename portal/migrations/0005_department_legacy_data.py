from django.db import migrations


DEPARTMENTS = [
    ("market-development", "اداره توسعه بازار و مدیریت کانال‌های فروش", "توسعه بازار", "PUBLISHED", 10),
    ("technical-support", "اداره پشتیبانی فنی", "پشتیبانی فنی", "DRAFT", 20),
    ("data-bi", "اداره تحلیل داده و BI", "تحلیل داده و BI", "DRAFT", 30),
    ("strategy-architecture", "اداره راهبرد و معماری", "راهبرد و معماری", "DRAFT", 40),
    ("customer-experience", "اداره مدیریت و پایش تجربه مشتریان", "تجربه مشتریان", "DRAFT", 50),
    ("deputy-coordination", "اداره هماهنگی امور معاونت", "هماهنگی امور معاونت", "DRAFT", 60),
]


def forwards(apps, schema_editor):
    Department = apps.get_model("portal", "Department")
    Category = apps.get_model("portal", "Category")
    Request = apps.get_model("portal", "Request")
    User = apps.get_model("portal", "User")
    RoleAssignment = apps.get_model("portal", "RoleAssignment")

    departments = {}
    for code, name, short_name, status, order in DEPARTMENTS:
        department, _ = Department.objects.update_or_create(
            code=code,
            defaults={"name": name, "short_name": short_name, "status": status, "display_order": order},
        )
        departments[code] = department

    market = departments["market-development"]
    Category.objects.filter(department__isnull=True).update(department=market)

    for request in Request.objects.filter(department__isnull=True).select_related("service__category"):
        request.department_id = request.service.category.department_id or market.id
        request.save(update_fields=["department"])

    for user in User.objects.filter(role="REQUEST_MANAGER"):
        RoleAssignment.objects.get_or_create(
            user=user,
            role="REQUEST_MANAGER",
            scope_type="DEPARTMENT",
            department=market,
            defaults={"is_active": user.is_active},
        )
    for user in User.objects.filter(role="ADMIN"):
        RoleAssignment.objects.get_or_create(
            user=user,
            role="SUPER_ADMIN",
            scope_type="GLOBAL",
            department=None,
            defaults={"is_active": user.is_active},
        )


def backwards(apps, schema_editor):
    # Data remains valid if schema migration is rolled back and re-applied.
    RoleAssignment = apps.get_model("portal", "RoleAssignment")
    Department = apps.get_model("portal", "Department")
    Category = apps.get_model("portal", "Category")
    Request = apps.get_model("portal", "Request")
    RoleAssignment.objects.filter(
        department__code="market-development",
        role="REQUEST_MANAGER",
        scope_type="DEPARTMENT",
    ).delete()
    RoleAssignment.objects.filter(role="SUPER_ADMIN", scope_type="GLOBAL").delete()
    Category.objects.filter(department__code="market-development").update(department=None)
    Request.objects.filter(department__code="market-development").update(department=None)
    Department.objects.filter(code__in=[row[0] for row in DEPARTMENTS]).delete()


class Migration(migrations.Migration):
    dependencies = [("portal", "0004_department_rbac_schema")]
    operations = [migrations.RunPython(forwards, backwards)]
