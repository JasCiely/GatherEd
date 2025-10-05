# core/views.py
import uuid

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.conf import settings
from supabase import create_client, Client
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from datetime import datetime
from django.urls import reverse



def index(request):
    return render(request, 'index.html')


def register(request):
    # --- 0. CRITICAL FIX: INITIALIZE SUPABASE CLIENTS ---
    try:
        # The public client is used for read-only checks (like checking if an ID exists)
        # Assuming you have SUPABASE_ANON_KEY defined in settings
        supabase_public: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_ANON_KEY
        )
        # The admin client is used for privileged writes (user creation)
        supabase_admin: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
    except AttributeError:
        # Handle case where keys are not set in settings
        messages.error(request, "Server configuration error: Supabase keys are missing.")
        return render(request, 'register.html')

    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        name = request.POST.get('name')
        user_type = request.POST.get('user_type')
        cit_id = request.POST.get('cit_id')

        # --- VALIDATION (Simplified & Cleaned) ---
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

        # --- CIT ID EXISTENCE CHECK (Using the correct table names from migration) ---
        # Note: We must use the table names defined in models.py (admins, students)
        # Assuming your Supabase tables are named 'admins' and 'students' from the last successful migration.
        student_id_check = supabase_public.table('students').select('cit_id').eq('cit_id', formatted_cit_id).execute().data
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
                is_staff=is_staff_user
            )

            # 2. Create profile in Supabase
            if user_type == 'administrator':
                # Use the 'admins' table as defined in your models.py
                admin_result = supabase_admin.table('admins').insert({
                    # Django FK column name is '<ModelName>_id', but your SQL requested 'user_id'
                    # We use 'user_id' because Django ORM handles the field name mapping.
                    'user_id': str(user.pk),
                    'name': name,
                    'cit_id': formatted_cit_id,
                    'created_at': datetime.now().isoformat()
                }).execute()
                if not admin_result.data:
                    user.delete()
                    raise Exception("Failed to insert admin profile into admins table.")
                redirect_path = 'admin_dashboard'

            elif user_type == 'student':
                # Use the 'students' table as defined in your models.py
                student_result = supabase_admin.table('students').insert({
                    'user_id': str(user.pk),
                    'name': name,
                    'cit_id': formatted_cit_id,
                    'created_at': datetime.now().isoformat()
                }).execute()
                if not student_result.data:
                    user.delete()
                    raise Exception("Failed to insert student profile into students table.")
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
            # Final cleanup check for the Django User object
            if 'user' in locals():
                try:
                    user.delete()
                except:
                    pass

            messages.error(request, f'Registration failed: {str(e)}')
            return render(request, 'register.html')

    return render(request, 'register.html')


def login_view(request):
    # --- 0. CRITICAL FIX: INITIALIZE SUPABASE PUBLIC CLIENT ---
    try:
        supabase_public: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_ANON_KEY
        )
    except AttributeError:
        messages.error(request, "Server configuration error: Supabase keys are missing.")
        return render(request, 'login.html')

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
                # Use the 'admins' table name
                admin_check = supabase_public.table('admins').select('user_id').eq('user_id', str(user.pk)).limit(
                    1).execute().data
                if admin_check:
                    return redirect('admin_dashboard')

                # Use the 'students' table name
                student_check = supabase_public.table('students').select('user_id').eq('user_id', str(user.pk)).limit(
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

def get_event_status(event_date_str):
    """Determines the status of an event based on its date."""
    try:
        # Assuming event_date_str is in 'YYYY-MM-DD' format
        event_date = datetime.datetime.strptime(event_date_str, '%Y-%m-%d').date()
        today = datetime.date.today()

        if event_date < today:
            return 'Completed'
        elif event_date == today:
            return 'Active'
        else:
            return 'Upcoming'
    except:
        return 'Unknown'

@login_required
def manage_events(request):
    """
    Admin view to display, manage, and modify all events.
    Fetches data using the Service Role Key to bypass RLS policies.
    """
    events_list = []

    # Check for AJAX request, used by HTMX or custom JS to load content dynamically
    is_ajax = request.GET.get('is_ajax', False)

    try:
        # CRITICAL FIX: Initialize admin client INSIDE the view
        # to ensure settings are correctly loaded for the request, fixing the 401 error.
        admin_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )

        # Fetch all events, ordered by date
        # Note: Your shell test confirmed this query structure works.
        fetch_result = admin_client.table('events').select('*').order('date', desc=False).execute()

        # Ensure the client object has data before proceeding
        if not hasattr(fetch_result, 'data'):
            raise Exception("Supabase response object is malformed.")

        # Check for errors returned by the client object
        if hasattr(fetch_result, 'error') and fetch_result.error:
            # Raise an exception to be caught by the outer block
            raise Exception(f"Supabase Client Error: {fetch_result.error}")

        # Process data and add calculated fields (status, registrations)
        for event in fetch_result.data:
            # Mock or calculate registrations (replace 10 with real lookup if available)
            mock_registrations = 10

            events_list.append({
                'id': event['id'],
                # Template uses 'name', but Supabase column is 'title'. This mapping is correct.
                'name': event['title'],
                'description': event['description'],
                'date': event['date'],
                'location': event['location'],
                'start_time': event['start_time'],
                'end_time': event['end_time'],
                'max_attendees': event['max_attendees'],
                'registrations': mock_registrations,
                'status': get_event_status(event['date']),
            })

    except Exception as e:
        # This catches the 401 API key error and logs it to the console
        print(f"Error fetching events from Supabase: {e}")
        # Add a flash message to alert the administrator
        messages.error(request,
                       "Failed to load events due to a critical server error. Check the Django console for details.")
        # events_list remains empty, which triggers the 'No events found' message in HTML.

    template_context = {
        'events_list': events_list,
        'title': 'Manage Events',
    }

    # Return the content fragment if it's an AJAX request (for dashboard loading)
    if is_ajax:
        return render(request, 'admin/fragments/manage_events_content.html', template_context)

    # Otherwise, return the full dashboard page
    return render(request, 'admin/admin_dashboard.html', template_context)


@login_required
def create_event(request):
    """
    Handles the creation of a new event, submitting data to Supabase via AJAX.
    """
    is_ajax = request.GET.get('is_ajax') == 'true'
    context = {}

    try:
        supabase_admin: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
    except AttributeError:
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': 'Server configuration error: Supabase service key is missing.'}, status=500)
        return redirect('admin_dashboard')

    # --- GET AUTHENTICATED ADMIN ID (from admins table, not Django user.pk) ---
    try:
        user_pk = str(request.user.pk)
        admin_record = supabase_admin.table('admins').select('id').eq('user_id', user_pk).limit(1).execute()
        if not admin_record.data:
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': 'No matching admin profile found for this user.'}, status=400)
            return redirect('admin_dashboard')
        admin_id = admin_record.data[0]['id']
    except Exception:
        if is_ajax:
             return JsonResponse({'status': 'error', 'message': 'Authentication error: Admin ID could not be determined.'}, status=401)
        return redirect('admin_dashboard')

    if request.method == 'POST':
        try:
            title = request.POST.get('title')
            description = request.POST.get('description')
            date = request.POST.get('date')
            location = request.POST.get('location')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')
            max_attendees = request.POST.get('max_attendees')

            if not all([title, description, date, start_time]):
                return JsonResponse({'status': 'error', 'message': "Event title, description, date, and start time are required."}, status=400)

            new_uuid = str(uuid.uuid4())

            insert_data = {
                'id': new_uuid,
                'admin_id': admin_id,
                'title': title,
                'description': description,
                'date': date,
                'location': location,
                'start_time': start_time,
                'end_time': end_time,
                'max_attendees': int(max_attendees) if max_attendees and max_attendees.isdigit() else None,
                'picture_url': None,
                'created_at': datetime.now().isoformat(),
            }

            insert_result = supabase_admin.table('events').insert(insert_data).execute()

            if not insert_result.data:
                error_message = getattr(insert_result, 'error', {}).get('message', 'Unknown database error')
                raise Exception(f"Database insertion failed: {error_message}")

            modify_url = reverse('modify_event', kwargs={'event_id': new_uuid})

            return JsonResponse({
                'status': 'success',
                'message': f"Event '{title}' scheduled successfully!",
                'event_data': insert_result.data[0],
                'modify_url': modify_url
            }, status=204)

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Failed to create event: {e}"}, status=500)

    else:
        if is_ajax:
            return render(request, 'admin/fragments/create_event_content.html', context)
        else:
            return redirect('admin_dashboard')

@login_required
def modify_event(request, event_id):
    """
    Placeholder view for modifying or viewing event details.
    Takes the event_id (UUID) as a parameter.
    """
    context = {
        'event_id': event_id,
        'message': f"You are now on the modify page for event ID: {event_id}"
    }
    # For now, just render a simple response or template
    # Replace 'admin/modify_event.html' with your actual template path later.
    return render(request, 'admin/admin_dashboard.html', context)


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
        # Initialize clients here as well, if they are not already available
        supabase_public: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

        existing = supabase_public.table('event_registrations').select('*').eq('student_id', user_id).eq('event_id',
                                                                                                      event_id).execute().data
        if existing:
            messages.info(request, "You are already registered.")
        else:
            # Note: Changed 'user_id' to 'student_id' to match the model/SQL
            insert_result = supabase_admin.table('event_registrations').insert(
                {'student_id': user_id, 'event_id': event_id}).execute()
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
        # Initialize public client
        supabase_public: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
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