import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("portal", "0005_department_legacy_data")]
    operations = [
        migrations.AddConstraint(model_name="department", constraint=models.CheckConstraint(condition=models.Q(("status__in", ["DRAFT", "PUBLISHED", "DISABLED", "ARCHIVED"])), name="valid_department_status")),
        migrations.AlterField(
            model_name="category",
            name="department",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="service_families", to="portal.department"),
        ),
        migrations.AlterField(
            model_name="request",
            name="department",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requests", to="portal.department"),
        ),
        migrations.AddConstraint(model_name="category", constraint=models.UniqueConstraint(fields=("department", "name"), name="unique_department_category_name")),
        migrations.AddConstraint(model_name="category", constraint=models.UniqueConstraint(fields=("department", "slug"), name="unique_department_category_slug")),
    ]
