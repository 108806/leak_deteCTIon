from django.urls import path
from .views import (
    BreachedCredentialListView,
    BreachedCredentialCreateView,
    BreachedCredentialUpdateView,
    BreachedCredentialDeleteView,
    BreachedCredentialDetailView,
    search_credentials,
)

app_name = "webui"

urlpatterns = [
    path("", BreachedCredentialListView.as_view(), name="list"),
    path("create/", BreachedCredentialCreateView.as_view(), name="create"),
    path("<int:pk>/", BreachedCredentialDetailView.as_view(), name="detail"),
    path("<int:pk>/update/", BreachedCredentialUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", BreachedCredentialDeleteView.as_view(), name="delete"),
    path("search/", search_credentials, name="search"),
]
