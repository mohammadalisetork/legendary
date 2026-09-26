import time
from django.core.management.base import BaseCommand
from django.db import connections
class Command(BaseCommand):
    def handle(self,*args,**opts):
        for _ in range(30):
            try: connections["default"].cursor().execute("SELECT 1"); self.stdout.write("Database ready"); return
            except Exception: time.sleep(2)
        raise RuntimeError("Database unavailable")
