from django.urls import path
from . import views  
from django.contrib.auth import views as auth_views

urlpatterns = [
path('', views.index, name='index'),
 path('login/', views.login_view, name='login'),
path('logout/', views.logout_view, name='logout'),
path('dashboard/', views.dashboard, name='dashboard'),


path("AddEditLead/", views.AddEditLead, name="AddLead"),
path("AddEditLead/<int:leadId>/", views.AddEditLead, name="EditLead"),

path('ViewLead/', views.ViewLead, name='ViewLead'),

path('AddEditFollowup/<int:lead_id>/', views.AddEditFollowup, name='AddEditFollowup'),
path('AddEditFollowup/<int:lead_id>/<int:followup_id>/', views.AddEditFollowup, name='EditFollowup'),

path('viewusers/', views.view_user, name='viewusers'),
path('AddEditUser/', views.AddEditUser, name='AddEditUser'),

path("deal/create/<int:lead_id>/", views.CreateDeal, name="CreateDeal"),
path("deal/<int:deal_id>/installment/", views.AddInstallment, name="AddInstallment"),
path("installment/delete/<int:installment_id>/",views.DeleteInstallment,name="DeleteInstallment"),


]
