from django.contrib import admin
from django.urls import include, path
from django.contrib.sitemaps.views import sitemap
from portal.views import JobSitemap, LandingSitemap, StaticSitemap

admin.site.site_header = "SarkariNaukri Administration"
admin.site.site_title = "SarkariNaukri Admin"
admin.site.index_title = "Publishing & Automation"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", sitemap, {"sitemaps": {"jobs": JobSitemap, "landings": LandingSitemap, "static": StaticSitemap}}, name="sitemap"),
    path("", include("portal.urls")),
]
