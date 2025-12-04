from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('article/<slug:slug>/', views.article_detail, name='article_detail'),
    path('archive/', views.archive, name='archive'),
    # BBC-style category URLs
    path('<str:category>/', views.category_view, name='category_view'),
]