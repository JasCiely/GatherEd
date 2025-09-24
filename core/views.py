from urllib.parse import parse_qs, urlparse

from django.shortcuts import render, redirect
from django.conf import settings
from supabase import create_client, Client
from supabase_auth.errors import AuthApiError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from supabase_auth.errors import AuthApiError


# Initialize both Supabase clients
supabase_public: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def index(request):
    return render(request, 'index.html')


def register(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        name = request.POST.get('name')
        user_type = request.POST.get('user_type')
        school_id = request.POST.get('school_id')
        new_school_name = request.POST.get('new_school_name')

        if not email or not password:
            messages.error(request, 'Email and password are required.')
            return render(request, 'register.html')

        if user_type == 'student' and not school_id:
            messages.error(request, 'Student registration requires a school.')
            return render(request, 'register.html')
        elif user_type == 'administrator' and not new_school_name:
            messages.error(request, 'Administrator registration requires a new school name.')
            return render(request, 'register.html')

        try:
            # Redirect back to Django after email confirmation
            redirect_url = request.build_absolute_uri('/auth/callback')

            res = supabase_public.auth.sign_up(
                {"email": email, "password": password},
                options={"email_redirect_to": redirect_url}
            )

            user_id = res.user.id if res.user else None

            # Store in DB immediately (instead of only session)
            supabase_admin.table("pending_users").insert({
                "id": user_id,
                "name": name,
                "user_type": user_type,
                "school_id": school_id,
                "new_school_name": new_school_name
            }).execute()

            messages.success(request, 'Registration successful! Please check your email to confirm your account.')
            return redirect('email_confirmation_sent')

        except AuthApiError as e:
            messages.error(request, e.message)
            return render(request, 'register.html')
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            messages.error(request, 'An unexpected error occurred. Please try again.')
            return render(request, 'register.html')

    schools_response = supabase_public.table('schools').select('*').execute().data
    return render(request, 'register.html', {'schools': schools_response})


def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        if not email or not password:
            messages.error(request, 'Email and password are required.')
            return render(request, 'login.html')

        try:
            res = supabase_public.auth.sign_in_with_password({"email": email, "password": password})
            request.session['access_token'] = res.session.access_token
            user_id = res.user.id
            request.session['user_id'] = user_id

            admin_check = supabase_public.table('admins').select('id').eq('id', user_id).limit(1).execute().data
            if admin_check:
                messages.success(request, 'You have been successfully logged in as an admin.')
                return redirect('admin_dashboard')

            student_check = supabase_public.table('students').select('id').eq('id', user_id).limit(1).execute().data
            if student_check:
                messages.success(request, 'You have been successfully logged in as a student.')
                return redirect('student_dashboard')
            else:
                messages.error(request, "User profile not found. Please contact support.")
                return redirect('login')

        except AuthApiError as e:
            messages.error(request, e.message)
            return render(request, 'login.html')
        except Exception as e:
            messages.error(request, f'An unexpected error occurred. Please try again. Error: {e}')
            return render(request, 'login.html')

    return render(request, 'login.html')


def logout_view(request):
    if 'access_token' in request.session:
        del request.session['access_token']
    if 'user_id' in request.session:
        del request.session['user_id']
    messages.success(request, "You have been logged out.")
    return redirect('index')


@login_required
def student_dashboard(request):
    user_id = request.session.get('user_id')
    try:
        events_response = supabase_public.table('events').select('*').execute().data
        announcements_response = supabase_public.table('announcements').select('*').execute().data
        registrations_response = supabase_public.table('event_registrations').select('*, events(*)').eq('user_id',
                                                                                                        user_id).execute().data

        context = {
            'events': events_response,
            'announcements': announcements_response,
            'registered_events': [reg['events'] for reg in registrations_response]
        }
        return render(request, 'student_dashboard.html', context)
    except Exception as e:
        messages.error(request, f"Failed to load dashboard data: {e}.")
        return redirect('index')


@login_required
def admin_dashboard(request):
    user_id = request.session.get('user_id')
    try:
        admin_check = supabase_public.table('admins').select('id').eq('id', user_id).limit(1).execute().data
        if not admin_check:
            messages.error(request, "Access denied. You do not have permission to view this page.")
            return redirect('student_dashboard')

        schools_response = supabase_admin.table('schools').select('*').execute().data
        events_response = supabase_admin.table('events').select('*').execute().data
        announcements_response = supabase_admin.table('announcements').select('*').execute().data
        feedbacks_response = supabase_admin.table('feedbacks').select('*').execute().data

        context = {
            'schools': schools_response,
            'events': events_response,
            'announcements': announcements_response,
            'feedbacks': feedbacks_response
        }
        return render(request, 'admin_dashboard.html', context)
    except Exception as e:
        messages.error(request, f"Failed to load admin dashboard data: {e}.")
        return redirect('index')


@login_required
def event_register(request, event_id):
    user_id = request.session.get('user_id')
    try:
        existing_registration = supabase_public.table('event_registrations').select('*').eq('user_id', user_id).eq(
            'event_id', event_id).limit(1).execute().data
        if existing_registration:
            messages.info(request, "You are already registered for this event.")
            return redirect('student_dashboard')
        insert_data = {"user_id": user_id, "event_id": event_id}
        supabase_public.table('event_registrations').insert(insert_data).execute()
        messages.success(request, "You have successfully registered for the event!")
        return redirect('student_dashboard')
    except Exception as e:
        messages.error(request, f"Failed to register for the event: {e}.")
        return redirect('event_listing')


def email_confirmation_sent(request):
    return render(request, 'email_confirmation_sent.html')


@login_required
def event_listing(request):
    try:
        events_response = supabase_public.table('events').select('*').execute().data
        context = {'events': events_response}
        return render(request, 'event_listing.html', context)
    except Exception as e:
        messages.error(request, f"Failed to load event list: {e}.")
        return redirect('index')


def create_event(request):
    if request.method == 'POST':
        user_id = request.session.get('user_id')
        try:
            admin_school = supabase_public.table('admins').select('school_id').eq('id', user_id).single().execute().data
            if not admin_school:
                messages.error(request, "Admin school not found.")
                return redirect('admin_dashboard')

            title = request.POST.get('title')
            description = request.POST.get('description')
            date = request.POST.get('date')
            school_id = admin_school['school_id']

            supabase_admin.table('events').insert(
                {'title': title, 'description': description, 'date': date, 'school_id': school_id}).execute()
            messages.success(request, "Event created successfully!")
            return redirect('admin_dashboard')

        except Exception as e:
            messages.error(request, f"Failed to create event: {e}.")
            return redirect('admin_dashboard')

    return render(request, 'create_event.html')


def auth_callback(request):
    try:
        query_params = parse_qs(urlparse(request.get_full_path()).fragment)
        access_token = query_params.get('access_token', [None])[0]

        if not access_token:
            messages.error(request, "Authentication failed. No access token found.")
            return redirect('login')

        auth_response = supabase_public.auth.get_user(access_token)
        user_id = auth_response.user.id

        request.session['access_token'] = access_token
        request.session['user_id'] = user_id

        # --- Look up pending user in DB ---
        pending = supabase_admin.table("pending_users").select("*").eq("id", user_id).single().execute().data

        if pending:
            user_type = pending['user_type']
            name = pending['name']

            if user_type == 'administrator':
                new_school_name = pending['new_school_name']
                school_id = pending['school_id']

                if not school_id and new_school_name:
                    school_data = supabase_admin.table('schools').insert({'name': new_school_name}).execute().data
                    school_id = school_data[0]['id']

                supabase_admin.table('admins').insert({
                    'id': user_id,
                    'name': name,
                    'school_id': school_id
                }).execute()

            elif user_type == 'student':
                school_id = pending['school_id']
                supabase_admin.table('students').insert({
                    'id': user_id,
                    'name': name,
                    'school_id': school_id
                }).execute()

            # Clean up
            supabase_admin.table("pending_users").delete().eq("id", user_id).execute()

        # --- Redirect user to the right dashboard ---
        if supabase_public.table('admins').select('id').eq('id', user_id).limit(1).execute().data:
            messages.success(request, 'Email confirmed! You have been logged in as an admin.')
            return redirect('admin_dashboard')

        if supabase_public.table('students').select('id').eq('id', user_id).limit(1).execute().data:
            messages.success(request, 'Email confirmed! You have been logged in as a student.')
            return redirect('student_dashboard')

        messages.error(request, "User profile not found. Please contact support.")
        return redirect('login')

    except Exception as e:
        messages.error(request, f"Authentication callback error: {e}")
        return redirect('login')

