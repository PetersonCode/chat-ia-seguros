from django.http import JsonResponse
from django.urls import include, path

urlpatterns = [
    path("healthz/", lambda request: JsonResponse({"estado": "ok"})),
    path("", include("api.urls")),
]
