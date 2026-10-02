from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PriorityApprovalUpgradeTests(TransactionTestCase):
    reset_sequences=True
    serialized_rollback=True

    def test_0009_preserves_22_request_and_adds_default_policies(self):
        executor=MigrationExecutor(connection)
        old=[('portal','0008_program_project_governance')]
        executor.migrate(old)
        apps=executor.loader.project_state(old).apps
        User=apps.get_model('portal','User');Department=apps.get_model('portal','Department')
        Category=apps.get_model('portal','Category');Service=apps.get_model('portal','Service')
        Request=apps.get_model('portal','Request')
        actor=User.objects.create(username='upgrade-23',password='unusable',full_name='Legacy',email='legacy@example.invalid')
        department=Department.objects.create(code='legacy23',name='Historical Department',status='PUBLISHED')
        category=Category.objects.create(name='Historical Category',slug='legacy23',department=department)
        service=Service.objects.create(code='L23',name='Historical Service',category=category,domain='test',full_description='test')
        original=Request.objects.create(requester=actor,department=department,service=service,requesting_unit='Legacy',project='Unmapped',title='Old Request',public_id='MKT-LEGACY-23',priority='URGENT',status='SUBMITTED')
        executor=MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        from .models import CreditReservation, PriorityPolicy, Request as CurrentRequest
        current=CurrentRequest.objects.get(pk=original.pk)
        self.assertEqual((current.project,current.priority,current.status),('Unmapped','URGENT','SUBMITTED'))
        self.assertIsNone(current.program_id)
        self.assertFalse(current.provider_hold)
        self.assertFalse(CreditReservation.objects.filter(request=current).exists())
        self.assertEqual(set(PriorityPolicy.objects.values_list('code',flat=True)),{'NORMAL','HIGH','VERY_URGENT','EMERGENCY'})
