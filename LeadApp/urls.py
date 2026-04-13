from django.urls import path
from . import views  
from django.contrib.auth import views as auth_views

urlpatterns = [
path('', views.index, name='index'),
 path('login/', views.login_view, name='login'),
path('logout/', views.logout_view, name='logout'),
path('dashboard', views.dashboard, name='dashboard'),
path('icon', views.DashboardIcon, name='icon'),


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
path("installment/<int:installment_id>/edit/",views.EditInstallment,name="EditInstallment"),

path("commission-ledger/", views.CommissionLedger, name="commission-ledger"),
path("commission-paid/<int:pk>/", views.mark_commission_paid, name="mark_commission_paid"),
path("commission-rollback/<int:pk>/", views.commission_rollback, name="commission-rollback"),
path("AddSalesTarget/<int:userId>/", views.AddSalesTarget, name="AddSalesTarget"),
path("SalesLeaderBoard", views.SalesLeaderBoard, name="SalesLeaderBoard"),

path("add-call-log/<int:lead_id>/", views.add_call_log, name="add-call-log"),

path("ViewExpenses", views.ViewExpenses, name="ViewExpenses"),
path("AddEditExpense", views.AddEditExpense, name="AddExpense"),
path("AddEditExpense/edit/<int:id>/",views.AddEditExpense, name="AddEditExpense"),
path("expense/delete/<int:id>/", views.DeleteExpense, name="expense_delete"),

path("sales-chart-data/", views.sales_chart_data, name="sales_chart_data"),
path("multi-sales-chart/", views.multi_user_sales_chart, name="multi_sales_chart"),

path("layout/", views.layout, name="layout"),

   path('dashboard/salesman/', views.salesman_dashboard, name='salesman_dashboard'),
    path('dashboard/lgs/', views.lgs_dashboard, name='lgs_dashboard'),

]
