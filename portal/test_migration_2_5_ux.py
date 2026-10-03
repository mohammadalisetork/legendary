from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class OnboardingTourMigrationTests(TransactionTestCase):
    reset_sequences = True
    serialized_rollback = True

    def test_existing_accounts_are_not_forced_into_the_first_run_tour(self):
        previous = [("portal", "0012_dynamic_radio_phone_fields_2_4")]
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        old_apps = executor.loader.project_state(previous).apps
        OldUser = old_apps.get_model("portal", "User")
        old_user = OldUser.objects.create(username="tour-existing-user", password="!", full_name="کاربر قدیمی", email="old@example.invalid")

        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        from .models import User

        old_user_now = User.objects.get(pk=old_user.pk)
        new_user = User.objects.create_user(username="tour-new-user", full_name="کاربر تازه", email="new@example.invalid")
        self.assertTrue(old_user_now.onboarding_tour_completed)
        self.assertFalse(new_user.onboarding_tour_completed)
