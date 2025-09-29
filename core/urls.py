from django.urls import path
from . import views

urlpatterns = [
    # General Routes
    path('', views.index, name='index'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboards
    path('student_dashboard/', views.student_dashboard, name='student_dashboard'),
    path('admin_dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # --- ADMIN MANAGEMENT ROUTES (Custom Admin) ---

    # Other Admin Tools/Features
    path('events/', views.manage_events, name='manage_events'),
    path('events/create/', views.create_event, name='create_event'),
    path('events/attendance/', views.track_attendance, name='track_attendance'),
    path('events/feedback/', views.manage_feedback, name='manage_feedback'),

    # --- STUDENT MANAGEMENT ROUTES (Custom STUDENT) ---

    # Other Student Tools/Features
    path('events/list/', views.event_list, name='event_list'),
    path('events/my/', views.my_events, name='my_events'),
    path('feedback/submit/', views.submit_feedback, name='submit_feedback'),
    path('notifications/', views.get_notifications, name='get_notifications'),
    path('events/register/<int:event_id>/', views.event_register, name='event_register'),
]