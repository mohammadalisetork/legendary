from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
urlpatterns=[
 path("login/",views.PortalLoginView.as_view(),name="login"),path("logout/",auth_views.LogoutView.as_view(),name="logout"),
 path("password/",views.password_change,name="password_change"),
 path("password/done/",auth_views.PasswordChangeDoneView.as_view(template_name="registration/password_change_done.html"),name="password_change_done"),
 path("",views.home,name="home"),path("catalog/",views.catalog,name="catalog"),path("catalog/<int:pk>/",views.service_detail,name="service_detail"),
 path("requests/new/<int:service_id>/",views.request_create,name="request_create"),path("requests/",views.my_requests,name="my_requests"),path("drafts/",views.my_requests,name="drafts"),
 path("requests/<int:pk>/",views.request_detail,name="request_detail"),path("requests/<int:pk>/edit/",views.request_edit,name="request_edit"),path("requests/<int:pk>/submit/",views.submit_request,name="submit_request"),path("requests/<int:pk>/message/",views.add_message,name="add_message"),path("requests/<int:pk>/brief/",views.brief_print,name="brief_print"),
 path("attachments/<int:pk>/",views.attachment_download,name="attachment_download"),path("notifications/",views.notifications,name="notifications"),path("notifications/<int:pk>/read/",views.notification_read,name="notification_read"),path("profile/",views.profile,name="profile"),
 path("control/",views.control_dashboard,name="control_dashboard"),path("control/requests/",views.control_requests,name="control_requests"),path("control/requests/<int:pk>/",views.control_request_detail,name="control_request_detail"),path("control/requests/<int:pk>/action/",views.control_action,name="control_action"),
]
