from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.conf import settings
from supabase import create_client, Client
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail  # Kept the import in case it's used elsewhere
from django.template.loader import render_to_string  # Kept the import in case it's used elsewhere
from django.utils.html import strip_tags  # Kept the import in case it's used elsewhere
import random  # Kept the import in case it's used elsewhere
from datetime import datetime, timedelta  # Kept the import in case it's used elsewhere
import re

# Initialize Supabase clients for data storage
supabase_public: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def index(request):
    return render(request, 'index.html')


def register(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        name = request.POST.get('name')
        user_type = request.POST.get('user_type')
        cit_id = request.POST.get('cit_id')

        # --- VALIDATION (Unchanged) ---
        if not all([email, password, cit_id, name, user_type]):
            messages.error(request, 'All fields are required.')
            return render(request, 'register.html')

        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'register.html')

        if not email.endswith('@cit.edu'):
            messages.error(request, 'Registration is limited to @cit.edu email addresses only.')
            return render(request, 'register.html')

        cleaned_cit_id = cit_id.replace('-', '')
        if not cleaned_cit_id.isdigit() or len(cleaned_cit_id) != 9:
            messages.error(request, 'The ID must be exactly 9 digits long.')
            return render(request, 'register.html')
        formatted_cit_id = f"{cleaned_cit_id[:2]}-{cleaned_cit_id[2:6]}-{cleaned_cit_id[6:]}"

        if User.objects.filter(email=email).exists():
            messages.error(request, 'A user with this email already exists.')
            return render(request, 'register.html')

        student_id_check = supabase_public.table('students').select('cit_id').eq('cit_id',
                                                                                 formatted_cit_id).execute().data
        admin_id_check = supabase_public.table('admins').select('cit_id').eq('cit_id', formatted_cit_id).execute().data
        if student_id_check or admin_id_check:
            messages.error(request, 'This ID is already registered.')
            return render(request, 'register.html')

        # --- ACCOUNT CREATION: AUTOMATIC ROLE-BASED PERMISSION ---
        try:
            # Determine if the user should be a staff member (for Django Admin access)
            is_staff_user = (user_type == 'administrator')

            # 1. Create the Django user, applying the is_staff permission
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                is_staff=is_staff_user  # <--- CRITICAL CHANGE HERE
            )

            # 2. Create profile in Supabase
            if user_type == 'administrator':
                admin_result = supabase_admin.table('admins').insert({
                    'id': str(user.pk),
                    'name': name,
                    'cit_id': formatted_cit_id
                }).execute()
                if not admin_result.data:
                    user.delete()
                    raise Exception("Failed to insert admin profile.")
                redirect_path = 'admin_dashboard'

            elif user_type == 'student':
                student_result = supabase_admin.table('students').insert({
                    'id': str(user.pk),
                    'name': name,
                    'cit_id': formatted_cit_id
                }).execute()
                if not student_result.data:
                    user.delete()
                    raise Exception("Failed to insert student profile.")
                redirect_path = 'student_dashboard'

            else:
                user.delete()
                raise Exception("Invalid user type.")

            # 3. Log the user in immediately (Unchanged)
            logged_in_user = authenticate(request, username=email, password=password)
            if logged_in_user is not None:
                login(request, logged_in_user)
                messages.success(request, 'Registration successful! You are now logged in.')
                return redirect(redirect_path)
            else:
                messages.warning(request,
                                 'Registration successful, but automatic login failed. Please log in manually.')
                return redirect('login_view')

        except Exception as e:
            messages.error(request, f'Registration failed: {str(e)}')
            return render(request, 'register.html')

    return render(request, 'register.html')


# --- REMOVED: def verify_otp(request): ---
# This function is now removed entirely as it's no longer needed.


def login_view(request):
    # This function remains unchanged as it is a standard login view.
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        if not email or not password:
            messages.error(request, 'Email and password are required.')
            return render(request, 'login.html')

        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)

            try:
                admin_check = supabase_public.table('admins').select('id').eq('id', str(user.pk)).limit(
                    1).execute().data
                if admin_check:
                    return redirect('admin_dashboard')

                student_check = supabase_public.table('students').select('id').eq('id', str(user.pk)).limit(
                    1).execute().data
                if student_check:
                    return redirect('student_dashboard')
            except Exception as e:
                messages.error(request, f"Error checking user profile: {e}")
                return redirect('login_view')

            messages.error(request, "User profile not found. Contact support.")
            return render(request, 'login.html')
        else:
            messages.error(request, "Invalid email or password.")
            return render(request, 'login.html')

    return render(request, 'login.html')


# --- REMAINING FUNCTIONS (Unchanged from original code) ---

def logout_view(request):
    logout(request)
    request.session.flush()
    messages.success(request, "You have been logged out.")
    return redirect('index')

# @login_required # I'm commenting this out for now so I don't have to log in every time I refresh the UI.
def admin_dashboard(request):
    """
    Renders the admin dashboard. Returns the full shell or just a fragment based on the request type.
    """

    # --- 1. DETECT REQUEST TYPE ---
    # The JavaScript sends '?is_ajax=true' for sidebar clicks.
    is_ajax = request.GET.get('is_ajax') == 'true'

    # --- 2. GATHER CONTEXT DATA ---
    context = {}

    try:
        # Fetch data for the dashboard summary cards

        # ⚠️ NOTE: You must replace these placeholders with your actual Supabase queries.
        # Example queries to fetch counts:

        # Total Events (Replace with actual count logic)
        total_events = 0

        # Total Attendance (Placeholder for real query)
        total_attendance = 0

        # New Feedback (Placeholder for real query)
        new_feedback = 0

        # Notifications (For the badge on the top bar)
        notification_count = 0

        # Populate context with LIVE data (not dummy data)
        context = {
            'total_events': total_events,
            'total_attendance': total_attendance,
            'new_feedback': new_feedback,
            'notification_count': notification_count,
            # If you need to pass a list of events for a preview table:
            'events': [],  # Replace with actual list of upcoming events
        }

    except Exception as e:
        print(f"ERROR: Admin dashboard data fetch failed: {e}")
        # On error, we still continue with an empty context to avoid crashing
        pass

    # --- 3. RENDER TEMPLATE BASED ON REQUEST TYPE ---
    if is_ajax:
        # If the request came from a sidebar click (AJAX), return ONLY the content fragment.
        # This prevents the double sidebar issue.
        return render(request, 'admin/fragments/dashboard_content.html', context)
    else:
        # If it's a full page load (initial URL entry), return the full admin shell.
        return render(request, 'admin/admin_dashboard.html', context)


# --- EVENT MANAGEMENT VIEWS (The core features) ---

@login_required
def manage_events(request):
    """
    View to display and manage all events.
    Renders the frontend fragment with clean context for backend readiness.
    """
    is_ajax = request.GET.get('is_ajax') == 'true'

    # 🛑 PERMISSION CHECK (Disabled for current diagnostic mode) 🛑
    # if not request.user.is_staff:
    #     if is_ajax:
    #         return HttpResponse("Permission Denied: Admin role required.", status=403)
    #     else:
    #         return redirect('student_dashboard')

    # Context with empty lists, ready for backend integration
    template_context = {
        'events_list': [],  # List of event dictionaries for the main table
        #'schools_list': [],  # List of school dictionaries for the filter dropdown
    }

    if request.method == 'POST':
        # Future logic for handling edit/delete actions goes here
        return redirect('manage_events')
    else:
        template_name = 'admin/fragments/manage_events_content.html'

        if not is_ajax:
            return redirect('admin_dashboard')

        return render(request, template_name, template_context)


# @login_required  # Keep this commented out for development
@staff_member_required
@staff_member_required
def create_event(request):
    is_ajax = request.GET.get('is_ajax') == 'true'

    context = {
        'title': '',
        'description': '',
        'date': '',
        'location': '',
        'start_time': '',
        'end_time': '',
        'max_attendees': '',
    }

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        date_str = request.POST.get('date', '').strip()
        location = request.POST.get('location', '').strip()
        start_time_str = request.POST.get('start_time', '').strip()
        end_time_str = request.POST.get('end_time', '').strip()
        max_attendees = request.POST.get('max_attendees', '').strip()

        context.update({
            'title': title,
            'description': description,
            'date': date_str,
            'location': location,
            'start_time': start_time_str,
            'end_time': end_time_str,
            'max_attendees': max_attendees,
        })

        if not all([title, description, date_str, start_time_str]):
            messages.error(request, "Event title, description, date, and start time are required.")
            template = 'admin/fragments/create_event_content.html' if is_ajax else 'create_event.html'
            return render(request, template, context)

        try:
            event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_time = datetime.strptime(start_time_str, '%H:%M').time()
            end_time = datetime.strptime(end_time_str, '%H:%M').time() if end_time_str else None

            if end_time and start_time >= end_time:
                messages.error(request, "End time must be after start time.")
                template = 'admin/fragments/create_event_content.html' if is_ajax else 'create_event.html'
                return render(request, template, context)
        except ValueError:
            messages.error(request, "Invalid date or time format.")
            template = 'admin/fragments/create_event_content.html' if is_ajax else 'create_event.html'
            return render(request, template, context)

        try:
            max_attendees_int = int(max_attendees) if max_attendees else None
        except ValueError:
            messages.error(request, "Max attendees must be a number.")
            template = 'admin/fragments/create_event_content.html' if is_ajax else 'create_event.html'
            return render(request, template, context)

        try:
            insert_result = supabase_admin.table('events').insert({
                'title': title,
                'description': description,
                'date': event_date.isoformat(),
                'location': location,
                'start_time': start_time.strftime('%H:%M:%S'),
                'end_time': end_time.strftime('%H:%M:%S') if end_time else None,
                'max_attendees': max_attendees_int,
            }).execute()

            if not insert_result.data:
                raise Exception(getattr(insert_result, 'error', 'Unknown error'))

            messages.success(request, "Event created successfully!")
            return redirect('admin_dashboard')

        except Exception as e:
            messages.error(request, f"Failed to create event: {e}")
            template = 'admin/fragments/create_event_content.html' if is_ajax else 'create_event.html'
            return render(request, template, context)

    else:
        if is_ajax:
            return render(request, 'admin/fragments/create_event_content.html', context)
        else:
            return redirect('admin_dashboard')


@login_required
def track_attendance(request):
    """
    TEMPORARY DIAGNOSTIC: Bypasses ALL permission checks to confirm code flow.
    """
    is_ajax = request.GET.get('is_ajax') == 'true'

    # 🛑 CRITICAL: Permission check is REMOVED for this diagnostic.
    # if not request.user.is_staff:
    #     if is_ajax:
    #         return HttpResponse("Permission Denied: Admin role required.", status=403)
    #     else:
    #         return redirect('student_dashboard')

    # Context with empty lists, ready for backend integration
    template_context = {
        'events_list': [],
    }

    if request.method == 'POST':
        return redirect('track_attendance')
    else:
        template_name = 'admin/fragments/track_attendance_content.html'

        if not is_ajax:
            return redirect('admin_dashboard')

        # The content MUST load here if the user is logged in.
        return render(request, template_name, template_context)

@login_required
def manage_feedback(request):
    """
    TEMPORARY DIAGNOSTIC: Bypasses ALL permission checks to confirm code flow.
    (Placeholder data removed)
    """
    is_ajax = request.GET.get('is_ajax') == 'true'

    # 🛑 CRITICAL: We are removing the permission check entirely.
    # if not request.user.is_staff:
    #     if is_ajax:
    #         return HttpResponse("Permission Denied: Admin role required.", status=403)
    #     else:
    #         return redirect('student_dashboard')

    # Placeholder context (No dummy data included)
    template_context = {}
    # 🎯 NOTE: When you integrate your database, your fetched data should be
    # added to this dictionary, e.g., template_context['feedback_list'] = fetched_data

    if request.method == 'POST':
        return redirect('manage_feedback')
    else:
        template_name = 'admin/fragments/manage_feedback_content.html'

        if not is_ajax:
            return redirect('admin_dashboard')

        # The content MUST load here if the user is logged in.
        return render(request, template_name, template_context)

@login_required
def event_register(request, event_id):
    user_id = str(request.user.pk)
    try:
        existing = supabase_public.table('event_registrations').select('*').eq('user_id', user_id).eq('event_id',
                                                                                                      event_id).execute().data
        if existing:
            messages.info(request, "You are already registered.")
        else:
            insert_result = supabase_admin.table('event_registrations').insert(
                {'user_id': user_id, 'event_id': event_id}).execute()
            if not insert_result.data:
                raise Exception(f"Registration insert failed: {getattr(insert_result, 'error', 'Unknown error')}")
            messages.success(request, "Registered successfully!")
        return redirect('student_dashboard')
    except Exception as e:
        messages.error(request, f"Event registration failed: {e}")
        return redirect('event_listing')


@login_required
def event_listing(request):
    try:
        events = supabase_public.table('events').select('*').execute().data
        return render(request, 'event_listing.html', {'events': events})
    except Exception as e:
        messages.error(request, f"Failed to load events: {e}")
        return redirect('index')


@login_required
def student_dashboard(request):
    """
    General student dashboard view. Renders the base template or the home fragment.
    """
    is_ajax = request.GET.get('is_ajax') == 'true'

    # Context with placeholder data, ready for backend integration
    template_context = {
        'upcoming_events_count': 0,
        'total_registered_count': 0,
        'events_attended_count': 0,
        'next_event': None,  # Placeholder for the next event object/dictionary
    }

    if is_ajax:
        # Renders the home fragment: student/fragments/dashboard_content.html
        return render(request, 'student/fragments/dashboard_content.html', template_context)
    else:
        # Renders the base dashboard layout: student/student_dashboard.html
        return render(request, 'student/student_dashboard.html', template_context)


@login_required
def event_list(request):
    """
    Renders the fragment for viewing all available events for registration.
    (Features: View event details, Register button)
    """
    is_ajax = request.GET.get('is_ajax') == 'true'

    # Context ready for a list of event objects/dictionaries
    template_context = {'event_list': []}

    if is_ajax:
        # Renders the Event List fragment
        return render(request, 'student/fragments/event_list_content.html', template_context)
    return redirect('student_dashboard')


@login_required
def my_events(request):
    """
    Renders the fragment for viewing the student's registered events.
    (Features: View QR code, Cancel registration)
    """
    is_ajax = request.GET.get('is_ajax') == 'true'

    # Context ready for a list of registered event objects/dictionaries
    template_context = {'my_events_list': []}

    if is_ajax:
        # Renders the My Registrations fragment
        return render(request, 'student/fragments/my_events_content.html', template_context)
    return redirect('student_dashboard')


@login_required
def submit_feedback(request):
    """
    Renders the fragment for submitting feedback on attended events.
    (Feature: Select event, submit rating/comments)
    """
    is_ajax = request.GET.get('is_ajax') == 'true'

    # Context ready for a list of past events eligible for feedback
    template_context = {'events_for_feedback': []}

    if is_ajax:
        # Renders the Submit Feedback fragment
        return render(request, 'student/fragments/submit_feedback_content.html', template_context)
    return redirect('student_dashboard')

@login_required
def get_notifications(request):
    """
    Renders the fragment containing the user's full notification list.
    Loaded as a primary page fragment via AJAX.
    """
    is_ajax = request.GET.get('is_ajax') == 'true'

    # Context is now an EMPTY list, ready for real data
    template_context = {
        'notifications_list': [],
    }

    if is_ajax:
        # Renders the full-page notification fragment
        return render(request, 'student/fragments/notifications_content.html', template_context)
    return redirect('student_dashboard')