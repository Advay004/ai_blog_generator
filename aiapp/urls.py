# urls.py (in your app directory)
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.u_login, name='login'),
    path('signup/', views.u_signup, name='signup'),
    path('logout/', views.u_logout, name='logout'),
    path('generate-blog/', views.generate_blog, name='generate_blog'),
    #path('blog-history/', views.blog_history, name='blog_history'),
    #path('health/', views.health_check, name='health_check'),
]