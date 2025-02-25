from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from .models import BreachedCredential


# List View
class BreachedCredentialListView(ListView):
    model = BreachedCredential
    template_name = "webui/list.html"
    context_object_name = "credentials"


# Create View
class BreachedCredentialCreateView(CreateView):
    model = BreachedCredential
    fields = ["STRING", "source"]
    template_name = "webui/form.html"
    success_url = reverse_lazy("webui:list")


# Update View
class BreachedCredentialUpdateView(UpdateView):
    model = BreachedCredential
    fields = ["STRING", "source"]
    template_name = "webui/form.html"
    success_url = reverse_lazy("webui:list")


# Delete View
class BreachedCredentialDeleteView(DeleteView):
    model = BreachedCredential
    template_name = "webui/confirm_delete.html"
    success_url = reverse_lazy("webui:list")
