import pytest
from django.urls import reverse
@pytest.mark.django_db
def test_home(client):
    r=client.get(reverse("home")); assert r.status_code==200; assert b"SarkariNaukri" in r.content
@pytest.mark.django_db
def test_health(client):
    assert client.get(reverse("health")).status_code==200
