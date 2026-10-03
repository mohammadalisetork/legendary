from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("portal", "0012_dynamic_radio_phone_fields_2_4")]

    operations = [
        # Existing accounts have already learned the current UI; do not interrupt
        # them with a first-run overlay. New accounts use the model default False.
        migrations.AddField(
            model_name="user",
            name="onboarding_tour_completed",
            field=models.BooleanField(default=True, verbose_name="راهنمای آغاز دیده شده"),
        ),
        migrations.AlterField(
            model_name="user",
            name="onboarding_tour_completed",
            field=models.BooleanField(default=False, verbose_name="راهنمای آغاز دیده شده"),
        ),
    ]
