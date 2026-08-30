import json
from pathlib import Path
from django.core.management.base import BaseCommand
from portal.models import Source
class Command(BaseCommand):
    help="Load initial source registry"
    def handle(self,*args,**opts):
        path=Path(__file__).resolve().parents[3]/"config"/"sources.json"
        data=json.loads(path.read_text())
        for row in data:
            obj,_=Source.objects.update_or_create(name=row["name"],defaults=row)
            self.stdout.write(self.style.SUCCESS(f"Loaded {obj.name}"))
