"""Industry automation pack definitions — one-click install."""

INDUSTRY_PACKS = [
    {
        "id": "pest_control",
        "name": "Pest Control Pack",
        "industry": "pest_control",
        "icon": "bug",
        "description": "Complete automation for pest control businesses",
        "flows": [
            {"title": "Lead Collection Flow", "trigger": "hi", "steps": ["location", "pest_type", "property_size", "lead_capture"]},
            {"title": "Site Visit Flow", "trigger": "visit", "steps": ["date_pick", "address", "confirm"]},
            {"title": "AMC Flow", "trigger": "amc", "steps": ["plan_select", "duration", "quote"]},
            {"title": "Quotation Flow", "trigger": "quote", "steps": ["service", "area", "send_quote"]},
        ],
        "templates": [
            {"name": "pest_inspection_booking", "category": "utility", "body": "Hi {{1}}, your pest inspection is confirmed for {{2}} at {{3}}."},
            {"name": "pest_treatment_reminder", "category": "utility", "body": "Reminder: Your {{1}} treatment is scheduled for tomorrow at {{2}}."},
            {"name": "pest_monsoon_offer", "category": "marketing", "body": "Monsoon Special! Get 20% off on termite treatment. Reply YES to book."},
        ],
        "pipeline_stages": ["New Lead", "Qualified", "Site Visit Scheduled", "Quotation Sent", "Negotiation", "Won", "Lost"],
        "tags": ["residential", "commercial", "termite", "rodent", "cockroach"],
        "welcome_message": "Welcome to our Pest Control service! How can we help you today? Reply HI to get started.",
    },
    {
        "id": "driver_service",
        "name": "Driver Service Pack",
        "industry": "driver_service",
        "icon": "car",
        "description": "Booking flows for driver and cab services",
        "flows": [
            {"title": "Driver Booking Flow", "trigger": "book", "steps": ["pickup", "drop", "datetime", "confirm"]},
            {"title": "Airport Transfer Flow", "trigger": "airport", "steps": ["flight_details", "pickup_time", "confirm"]},
            {"title": "Outstation Booking Flow", "trigger": "outstation", "steps": ["destination", "dates", "vehicle_type", "quote"]},
        ],
        "templates": [
            {"name": "driver_booking_confirm", "category": "utility", "body": "Your ride is confirmed! Driver {{1}} will arrive at {{2}}."},
            {"name": "driver_arriving", "category": "utility", "body": "Your driver is 5 minutes away. Vehicle: {{1}}, Contact: {{2}}."},
        ],
        "pipeline_stages": ["New Lead", "Qualified", "Booking Confirmed", "In Progress", "Completed", "Lost"],
        "tags": ["airport", "outstation", "hourly", "corporate"],
        "welcome_message": "Welcome! Book a driver instantly. Reply BOOK to start.",
    },
    {
        "id": "real_estate",
        "name": "Real Estate Pack",
        "industry": "real_estate",
        "icon": "building",
        "description": "Property inquiry and site visit automation",
        "flows": [
            {"title": "Property Inquiry Flow", "trigger": "property", "steps": ["budget", "location", "bhk", "lead_capture"]},
            {"title": "Site Visit Flow", "trigger": "visit", "steps": ["property_select", "datetime", "confirm"]},
            {"title": "Lead Nurturing Flow", "trigger": "nurture", "steps": ["follow_up", "new_listings", "callback"]},
        ],
        "templates": [
            {"name": "property_site_visit", "category": "utility", "body": "Site visit confirmed for {{1}} on {{2}}. Our agent {{3}} will meet you."},
            {"name": "new_property_alert", "category": "marketing", "body": "New listing in {{1}}! {{2}} BHK starting at {{3}}. Reply INTERESTED for details."},
        ],
        "pipeline_stages": ["New Lead", "Qualified", "Site Visit", "Quotation Sent", "Negotiation", "Won", "Lost"],
        "tags": ["residential", "commercial", "rental", "sale"],
        "welcome_message": "Looking for your dream property? Reply PROPERTY to explore listings.",
    },
    {
        "id": "clinic",
        "name": "Clinic Pack",
        "industry": "clinic",
        "icon": "heart",
        "description": "Appointment booking and patient follow-up",
        "flows": [
            {"title": "Appointment Booking", "trigger": "appointment", "steps": ["department", "doctor", "datetime", "confirm"]},
            {"title": "Follow-Up Flow", "trigger": "followup", "steps": ["health_check", "next_visit", "feedback"]},
            {"title": "Prescription Reminder", "trigger": "medicine", "steps": ["medicine_list", "reminder_time", "confirm"]},
        ],
        "templates": [
            {"name": "appointment_confirm", "category": "utility", "body": "Appointment confirmed with Dr. {{1}} on {{2}} at {{3}}."},
            {"name": "prescription_reminder", "category": "utility", "body": "Reminder: Take your {{1}} medication. Next dose at {{2}}."},
        ],
        "pipeline_stages": ["New Patient", "Appointment Booked", "Visited", "Follow-up", "Completed"],
        "tags": ["general", "dental", "pediatric", "emergency"],
        "welcome_message": "Welcome to our clinic! Reply APPOINTMENT to book a visit.",
    },
    {
        "id": "resort",
        "name": "Resort Pack",
        "industry": "resort",
        "icon": "palmtree",
        "description": "Booking inquiry and guest communication",
        "flows": [
            {"title": "Booking Inquiry", "trigger": "book", "steps": ["dates", "guests", "room_type", "quote"]},
            {"title": "Availability Check", "trigger": "available", "steps": ["dates", "room_type", "show_options"]},
            {"title": "Payment Reminder", "trigger": "payment", "steps": ["booking_ref", "amount", "payment_link"]},
        ],
        "templates": [
            {"name": "booking_confirmation", "category": "utility", "body": "Booking confirmed! Ref: {{1}}. Check-in: {{2}}. Total: {{3}}."},
            {"name": "payment_reminder_resort", "category": "utility", "body": "Payment of {{1}} due for booking {{2}}. Pay here: {{3}}."},
        ],
        "pipeline_stages": ["Inquiry", "Quoted", "Booked", "Checked In", "Completed", "Cancelled"],
        "tags": ["deluxe", "suite", "villa", "conference"],
        "welcome_message": "Welcome to paradise! Reply BOOK to check availability.",
    },
    {
        "id": "education",
        "name": "Education Pack",
        "industry": "education",
        "icon": "graduation",
        "description": "Student inquiry and enrollment automation",
        "flows": [
            {"title": "Course Inquiry Flow", "trigger": "course", "steps": ["course_select", "eligibility", "counselor"]},
            {"title": "Admission Flow", "trigger": "admission", "steps": ["documents", "fee", "confirm"]},
        ],
        "templates": [
            {"name": "admission_confirm", "category": "utility", "body": "Admission confirmed for {{1}}. Classes start {{2}}."},
        ],
        "pipeline_stages": ["Inquiry", "Counseling", "Applied", "Enrolled", "Lost"],
        "tags": ["undergraduate", "postgraduate", "certification"],
        "welcome_message": "Welcome! Reply COURSE to explore our programs.",
    },
]

INDUSTRY_AI_PROFILES = {
    "pest_control": {
        "welcome_message": "Hi! Welcome to our Pest Control service. I'm here to help you with termite, rodent, or/cockroach treatment. What pest problem are you facing?",
        "qualification_questions": ["What type of pest?", "Property location?", "Property size (BHK)?", "Preferred visit date?"],
        "pipeline_stages": ["New Lead", "Qualified", "Site Visit Scheduled", "Quotation Sent", "Negotiation", "Won", "Lost"],
        "tags": ["termite", "rodent", "cockroach", "residential", "commercial"],
        "follow_up_days": [1, 3, 7],
    },
    "driver_service": {
        "welcome_message": "Hello! Need a driver? I can help you book airport transfers, outstation trips, or hourly drivers. Where do you need to go?",
        "qualification_questions": ["Pickup location?", "Drop location?", "Date and time?", "One-way or round trip?"],
        "pipeline_stages": ["New Lead", "Qualified", "Booking Confirmed", "In Progress", "Completed", "Lost"],
        "tags": ["airport", "outstation", "hourly", "corporate"],
        "follow_up_days": [1, 2],
    },
    "real_estate": {
        "welcome_message": "Welcome! Looking to buy or rent? Tell me your preferred location and budget, and I'll find the perfect property for you.",
        "qualification_questions": ["Buy or rent?", "Preferred location?", "Budget range?", "BHK requirement?"],
        "pipeline_stages": ["New Lead", "Qualified", "Site Visit", "Quotation Sent", "Negotiation", "Won", "Lost"],
        "tags": ["residential", "commercial", "rental", "sale"],
        "follow_up_days": [1, 3, 5, 14],
    },
    "clinic": {
        "welcome_message": "Welcome to our clinic! I can help you book an appointment, check doctor availability, or answer health queries. How can I assist?",
        "qualification_questions": ["Which department?", "Preferred doctor?", "Symptoms?", "Preferred date/time?"],
        "pipeline_stages": ["New Patient", "Appointment Booked", "Visited", "Follow-up", "Completed"],
        "tags": ["general", "dental", "pediatric"],
        "follow_up_days": [1, 7, 30],
    },
    "resort": {
        "welcome_message": "Welcome to our resort! I can check room availability, share packages, or help with your booking. What dates are you planning?",
        "qualification_questions": ["Check-in date?", "Number of guests?", "Room preference?", "Special requirements?"],
        "pipeline_stages": ["Inquiry", "Quoted", "Booked", "Checked In", "Completed", "Cancelled"],
        "tags": ["deluxe", "suite", "villa"],
        "follow_up_days": [1, 3],
    },
    "education": {
        "welcome_message": "Welcome! Explore our courses and programs. I can help with admissions, fees, and course details. Which program interests you?",
        "qualification_questions": ["Course of interest?", "Educational background?", "Preferred batch?", "Contact number?"],
        "pipeline_stages": ["Inquiry", "Counseling", "Applied", "Enrolled", "Lost"],
        "tags": ["undergraduate", "postgraduate", "certification"],
        "follow_up_days": [1, 3, 7],
    },
}

DEFAULT_PIPELINE = [
    {"name": "New Lead", "color": "#6366f1", "order": 0},
    {"name": "Qualified", "color": "#8b5cf6", "order": 1},
    {"name": "Follow-up", "color": "#a855f7", "order": 2},
    {"name": "Quotation Sent", "color": "#d946ef", "order": 3},
    {"name": "Negotiation", "color": "#ec4899", "order": 4},
    {"name": "Won", "color": "#22c55e", "order": 5, "is_won": True},
    {"name": "Lost", "color": "#ef4444", "order": 6, "is_lost": True},
]
