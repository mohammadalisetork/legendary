from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ProgramProjectMigrationUpgradeTests(TransactionTestCase):
    """Exercise 0008 against a 2.1C schema with one legacy free-text request."""
    reset_sequences = True
    serialized_rollback = True

    def test_0008_preserves_legacy_request_without_guessing_context(self):
        executor = MigrationExecutor(connection)
        target_old = [('portal', '0007_appearancesetting')]
        executor.migrate(target_old)
        old_apps = executor.loader.project_state(target_old).apps
        User = old_apps.get_model('portal', 'User')
        Department = old_apps.get_model('portal', 'Department')
        Category = old_apps.get_model('portal', 'Category')
        Service = old_apps.get_model('portal', 'Service')
        Request = old_apps.get_model('portal', 'Request')
        user = User.objects.create(username='migration-user', password='not-a-login', full_name='Legacy', email='legacy@example.invalid')
        department = Department.objects.create(code='migration-dept', name='Migration Department', status='PUBLISHED')
        category = Category.objects.create(name='Migration Family', slug='migration-family', department=department)
        service = Service.objects.create(code='MG-01', name='Migration Service', domain='test', full_description='test', category=category)
        legacy = Request.objects.create(requester=user, department=department, service=service,
            requesting_unit='Legacy unit', project='legacy free-text project', title='Legacy request',
            public_id='MKT-20261002-LEGACY', status='SUBMITTED')

        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        from .models import Request as CurrentRequest
        upgraded = CurrentRequest.objects.get(pk=legacy.pk)
        self.assertEqual(upgraded.project, 'legacy free-text project')
        self.assertIsNone(upgraded.program_id)
        self.assertIsNone(upgraded.project_entity_id)
        self.assertEqual(upgraded.title, 'Legacy request')
