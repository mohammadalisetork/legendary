from django.contrib import admin
from django.urls import include, path
from portal import views

admin.site.site_header = "مدیریت کاتالوگ خدمات"
admin.site.site_title = "مدیریت خدمات"
admin.site.index_title = "تنظیمات سامانه"
urlpatterns = [
    path("health", views.health, name="health"),
    path("django-admin/", admin.site.urls),
    path("", include("portal.urls")),
]
