from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CatalogueScalingUpgradeTests(TransactionTestCase):
    reset_sequences=True
    serialized_rollback=True

    def test_0010_preserves_populated_23_catalogue_governance_and_backfills_snapshots(self):
        target=[("portal","0009_priority_capacity_approval_engine")]
        executor=MigrationExecutor(connection);executor.migrate(target)
        apps=executor.loader.project_state(target).apps
        User=apps.get_model("portal","User");Department=apps.get_model("portal","Department")
        Category=apps.get_model("portal","Category");Service=apps.get_model("portal","Service")
        FormField=apps.get_model("portal","ServiceFormField");Request=apps.get_model("portal","Request")
        Program=apps.get_model("portal","Program");Project=apps.get_model("portal","Project")
        actor=User.objects.create(username="upgrade-24",password="!",full_name="Legacy",email="legacy@example.invalid")
        department=Department.objects.create(code="legacy24",name="Historical Department",status="PUBLISHED")
        category=Category.objects.create(name="Historical Family",slug="legacy24",department=department)
        inactive_category=Category.objects.create(name="Disabled Family",slug="disabled24",department=department,active=False)
        service=Service.objects.create(code="L24",name="Historical Service",category=category,domain="test",full_description="Original",initial_response_days=2,delivery_min_days=4,delivery_max_days=8)
        inactive_service=Service.objects.create(code="L24D",name="Disabled Service",category=inactive_category,domain="test",full_description="Disabled",active=False)
        FormField.objects.create(service=service,key="historic",label="Historic label",field_type="text",required=True)
        program=Program.objects.create(code="legacy-plan24",name="Legacy Program",status="ACTIVE")
        project=Project.objects.create(code="legacy-project24",name="Legacy Project",program=program,status="ACTIVE")
        legacy=Request.objects.create(requester=actor,department=department,service=service,requesting_unit="Legacy",project="free-text",title="Preserve me",public_id="MKT-LEGACY-24",priority="VERY_URGENT",status="SUBMITTED",request_data={"historic":"value"},program=program,project_entity=project)
        inactive_id=inactive_service.pk
        executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
        from .models import Category as CurrentCategory, Project as CurrentProject, Request as CurrentRequest, Service as CurrentService
        current=CurrentRequest.objects.get(pk=legacy.pk)
        self.assertEqual((current.public_id,current.title,current.project,current.priority,current.status),("MKT-LEGACY-24","Preserve me","free-text","VERY_URGENT","SUBMITTED"))
        self.assertEqual(current.request_data,{"historic":"value"})
        self.assertEqual((current.program.code,current.project_entity.code),("legacy-plan24","legacy-project24"))
        self.assertEqual(current.catalogue_snapshot["form_fields"][0]["label"],"Historic label")
        self.assertEqual(current.catalogue_snapshot["service"]["delivery_max_days"],8)
        self.assertEqual(CurrentCategory.objects.get(pk=inactive_category.pk).lifecycle_status,"DISABLED")
        self.assertEqual(CurrentService.objects.get(pk=inactive_id).lifecycle_status,"DISABLED")
