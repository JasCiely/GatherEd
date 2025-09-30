function createEventRowHtml(eventData) {
    // 1. Determine Status (Simple client-side calculation, backend is more reliable)
    const eventDate = new Date(eventData.date);
    const today = new Date();
    today.setHours(0, 0, 0, 0); // Normalize time
    eventDate.setHours(0, 0, 0, 0);

    let status;
    if (eventDate.getTime() > today.getTime()) {
        status = 'Upcoming';
    } else if (eventDate.getTime() === today.getTime()) {
        status = 'Active';
    } else {
        status = 'Completed';
    }

    // 2. Format Date (Example: YYYY-MM-DD to DD Month YYYY or similar)
    // For simplicity, we'll keep the ISO format, but you can format it here.
    const displayDate = eventData.date;

    // 3. Generate HTML
    return `
        <tr data-event-id="${eventData.id}">
            <td data-label="Event Name">${eventData.title}</td>
            <td data-label="Date">${displayDate}</td>
            <td data-label="Registrations">N/A</td> 
            <td data-label="Status" class="status-${status.toLowerCase()}">${status}</td>
            <td data-label="Actions" class="action-buttons">
                <button class="btn-action edit" title="Edit Event"><i class="fas fa-edit"></i></button>
                <button class="btn-action delete" title="Delete Event"><i class="fas fa-trash"></i></button>
            </td>
        </tr>
    `;
}

// --- Main AJAX Logic ---
$(document).ready(function() {
    const form = $('#create-event-form');
    const modal = $('#event-success-modal');
    const modalTitleSpan = $('#event-modal-title');

    // Select the table body where new rows go
    const eventsTableBody = $('.events-table tbody');
    const emptyState = $('.empty-state');

    // --- A. Handle Form Submission via AJAX ---
    form.on('submit', function(e) {
        e.preventDefault();

        const formData = form.serialize();

        $.ajax({
            url: form.attr('action'),
            type: 'POST',
            data: formData,
            dataType: 'json',
            success: function(response) {
                // 1. Process the new event data
                const newEventData = response.event_data;
                const newRowHtml = createEventRowHtml(newEventData);

                // 2. Inject the new row into the manage events table
                if (eventsTableBody.length) {
                    // Check if the empty state is visible and hide it
                    if (emptyState.is(':visible')) {
                        emptyState.hide();
                        // IMPORTANT: You might need to make the events-table visible here if you hide it when empty.
                    }
                    // Prepend or Append the new row (Prepending shows it instantly at the top)
                    eventsTableBody.prepend(newRowHtml);
                } else {
                    // Fallback or full content reload (if table structure wasn't loaded)
                    console.warn("Could not find events table body. Reloading manage content.");
                    // You would place your full fragment reload logic here:
                    // Example: $('#main-content-area').load('{% url 'manage_events' %}?is_ajax=true');
                }

                // 3. Show the aesthetic success modal
                modalTitleSpan.text(newEventData.title);
                modal.addClass('active');

                // 4. Clear the form
                form[0].reset();
            },
            error: function(xhr) {
                const errorResponse = xhr.responseJSON;
                const errorMessage = errorResponse ? errorResponse.message : 'An unknown network error occurred.';
                alert('Event Creation Error: ' + errorMessage);
                console.error("Server Error:", errorMessage);
            }
        });
    });

    // --- B. Handle Modal Close Actions (as defined previously) ---
    $('#modal-close-btn, #event-success-modal').on('click', function(e) {
        if (e.target.id === 'modal-close-btn' || e.target.id === 'event-success-modal') {
            modal.removeClass('active');
        }
    });
});