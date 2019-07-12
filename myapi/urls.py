from django.conf.urls import url, include

from . import views

urlpatterns = [
    url(r'^lambda_handler/', views.lambda_handler)
]
