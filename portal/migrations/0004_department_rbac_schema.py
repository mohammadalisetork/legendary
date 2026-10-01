# Generated for Release 2.1A: additive schema before legacy-data backfill.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0003_alter_request_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=200)),
                ("short_name", models.CharField(blank=True, max_length=100)),
                ("description", models.TextField(blank=True)),
                ("intro_text", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("DRAFT", "پیش‌نویس"), ("PUBLISHED", "منتشرشده"), ("DISABLED", "غیرفعال"), ("ARCHIVED", "بایگانی‌شده")], db_index=True, default="DRAFT", max_length=16)),
                ("display_order", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ["display_order", "name"]},
        ),
        migrations.AddField(
            model_name="category",
            name="department",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="service_families", to="portal.department"),
        ),
        migrations.AddField(
            model_name="request",
            name="department",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="requests", to="portal.department"),
        ),
        migrations.AlterField(model_name="category", name="name", field=models.CharField(max_length=160)),
        migrations.AlterField(model_name="category", name="slug", field=models.SlugField(allow_unicode=True, max_length=180)),
        migrations.AlterModelOptions(
            name="category",
            options={"ordering": ["department__display_order", "display_order", "name"], "verbose_name": "خانواده خدمت", "verbose_name_plural": "خانواده‌های خدمت"},
        ),
        migrations.CreateModel(
            name="RoleAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("role", models.CharField(choices=[("REQUESTER", "درخواست‌دهنده"), ("REQUEST_MANAGER", "مدیر درخواست"), ("DEPARTMENT_LEAD", "مدیر اداره"), ("SUPERVISOR", "ناظر"), ("EXECUTIVE_VIEWER", "مشاهده‌گر ارشد"), ("SUPER_ADMIN", "مدیر ارشد سامانه")], db_index=True, max_length=32)),
                ("scope_type", models.CharField(choices=[("GLOBAL", "سراسری"), ("DEPARTMENT", "اداره")], db_index=True, max_length=16)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("assigned_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_roles", to=settings.AUTH_USER_MODEL)),
                ("department", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="role_assignments", to="portal.department")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="role_assignments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["user__username", "role"],
                "indexes": [models.Index(fields=["department", "role", "is_active"], name="portal_role_departm_a46b0d_idx"), models.Index(fields=["user", "scope_type", "is_active"], name="portal_role_user_id_9e7628_idx")],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("department__isnull", True), ("scope_type", "GLOBAL"), _connector="AND") | models.Q(("department__isnull", False), ("scope_type", "DEPARTMENT"), _connector="AND"), name="role_assignment_scope_target"),
                    models.CheckConstraint(condition=models.Q(("role__in", ["REQUESTER", "SUPERVISOR", "EXECUTIVE_VIEWER", "SUPER_ADMIN"]), ("scope_type", "GLOBAL"), _connector="AND") | models.Q(("role__in", ["REQUEST_MANAGER", "DEPARTMENT_LEAD"]), ("scope_type", "DEPARTMENT"), _connector="AND"), name="role_assignment_role_scope"),
                    models.UniqueConstraint(condition=models.Q(("scope_type", "GLOBAL")), fields=("user", "role", "scope_type"), name="unique_global_role_assignment"),
                    models.UniqueConstraint(condition=models.Q(("scope_type", "DEPARTMENT")), fields=("user", "role", "department"), name="unique_department_role_assignment"),
                ],
            },
        ),
        migrations.AddIndex(model_name="category", index=models.Index(fields=["department", "active"], name="portal_cate_departm_762dfa_idx")),
        migrations.AddIndex(model_name="request", index=models.Index(fields=["department", "status"], name="portal_requ_departm_9bda87_idx")),
    ]
