from django.urls import path

from . import views

app_name = "recruiting"

urlpatterns = [
    path("app/", views.dashboard, name="dashboard"),
    path("app/nouveau/", views.recruitment_edit, name="create"),
    path("app/<int:pk>/", views.recruitment_detail, name="detail"),
    path("app/<int:pk>/modifier/", views.recruitment_edit, name="edit"),
    path("app/<int:pk>/clore/", views.recruitment_toggle, name="toggle"),
    path("app/<int:pk>/supprimer/", views.recruitment_delete, name="delete"),
    path("app/<int:pk>/equipe/", views.team, name="team"),
    path("app/<int:pk>/candidats/<int:app_pk>/", views.application_detail, name="application"),
    path("app/notifications/", views.notifications, name="notifications"),
    path("app/invitations/<int:pk>/repondre/", views.invitation_respond, name="invitation_respond"),
    path("fichiers/<str:kind>/<int:pk>/", views.preview, name="preview"),
    path("fichiers/<str:kind>/<int:pk>/flux/", views.raw, name="raw"),
    path("r/<str:public_id>/", views.apply, name="apply"),
    path("r/<str:public_id>/merci/", views.thanks, name="thanks"),
    path("r/<str:public_id>/test/", views.submit_test, name="test"),
]
