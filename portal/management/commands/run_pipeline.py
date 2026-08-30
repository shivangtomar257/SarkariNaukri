from django.core.management.base import BaseCommand
from portal.models import Source
from portal.pipeline.scan import scan_source
class Command(BaseCommand):
    help="Run enabled source scans synchronously"
    def add_arguments(self,p): p.add_argument("--type",choices=["official","discovery"],default="official")
    def handle(self,*args,**o):
        for source in Source.objects.filter(enabled=True,source_type=o["type"]):
            run=scan_source(source); self.stdout.write(f"{source.name}: {run.status} ({run.discovered_count} candidates)")
