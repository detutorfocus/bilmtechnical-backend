"""
Bilm Technical Services — Database Seed
Run once after migrations: python -m app.seed

Seeds:
  1. Default company settings
  2. Default admin user
  3. All email templates (Jinja2 HTML, editable from dashboard)
"""
import asyncio
from app.database import AsyncSessionLocal, create_all_tables
from app.models import CompanySettings, EmailTemplate, User, UserRole
from app.core.auth import hash_password

# ─── Logo URL (update to your CDN/static URL after deploy) ───────────────────
LOGO_URL = "https://bilmtechnical.com/static/logo.png"

# ─── Shared HTML components ──────────────────────────────────────────────────

EMAIL_HEADER = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{margin:0;padding:0;background:#f0f4f8;font-family:'Segoe UI',Arial,sans-serif;}
  .wrapper{max-width:620px;margin:32px auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);}
  .header{background:#0a1628;padding:28px 36px;text-align:center;}
  .header img{height:64px;max-width:260px;object-fit:contain;}
  .tagline{color:#22c55e;font-size:11px;letter-spacing:2px;margin-top:6px;font-weight:600;}
  .accent-bar{height:4px;background:linear-gradient(90deg,#0a1628,#22c55e,#0a1628);}
  .body{padding:36px 40px;}
  .greeting{font-size:17px;font-weight:700;color:#0a1628;margin-bottom:8px;}
  p{color:#374151;font-size:14px;line-height:1.7;margin:0 0 16px;}
  .highlight-box{background:#f0fdf4;border-left:4px solid #22c55e;padding:16px 20px;border-radius:4px;margin:20px 0;}
  .highlight-box p{margin:4px 0;color:#166534;font-size:13px;}
  .highlight-box .label{font-weight:700;color:#0a1628;font-size:11px;letter-spacing:1px;text-transform:uppercase;}
  .cta-btn{display:inline-block;background:#22c55e;color:#0a1628 !important;font-weight:700;font-size:13px;
           letter-spacing:1px;padding:12px 28px;border-radius:4px;text-decoration:none;margin:8px 0;}
  .divider{border:none;border-top:1px solid #e5e7eb;margin:28px 0;}
  .signature{color:#374151;font-size:13px;line-height:1.6;}
  .signature strong{color:#0a1628;}
  .footer{background:#0a1628;padding:20px 36px;text-align:center;}
  .footer p{color:#6b7280;font-size:11px;margin:4px 0;letter-spacing:0.5px;}
  .footer a{color:#22c55e;text-decoration:none;}
  @media(max-width:600px){.body{padding:24px 20px;}.header{padding:20px 24px;}}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <img src="{{ logo_url }}" alt="{{ company_name }}">
    <div class="tagline">POWERING OPERATIONS. DELIVERING RELIABILITY.</div>
  </div>
  <div class="accent-bar"></div>
  <div class="body">
"""

EMAIL_FOOTER = """
  </div>
  <div class="footer">
    <p>{{ company_name }} &nbsp;|&nbsp; Ref: {{ company_ref }}</p>
    <p>{{ company_address }}</p>
    <p><a href="tel:{{ company_phone }}">{{ company_phone }}</a> &nbsp;|&nbsp; <a href="mailto:{{ company_email }}">{{ company_email }}</a></p>
    <p><a href="{{ company_website }}">{{ company_website }}</a></p>
    <p style="margin-top:12px;color:#4b5563;font-size:10px;">
      This email was sent by {{ company_name }}. Please do not reply to automated emails.<br>
      &copy; {{ company_name }} — All rights reserved.
    </p>
  </div>
</div>
</body>
</html>
"""

SIGNATURE = """
<div class="signature">
  Best regards,<br>
  <strong>Biali Uchenna Kandi</strong><br>
  {{ company_name }}<br>
  {{ company_phone }} &nbsp;|&nbsp; {{ company_email }}
</div>
"""

# ─── Template definitions ─────────────────────────────────────────────────────

TEMPLATES = [
    # ── 1. Lead Welcome ──────────────────────────────────────────────────────
    {
        "slug":      "lead_welcome",
        "name":      "Lead Welcome — New Inquiry Confirmation",
        "subject":   "Thank You for Contacting {{ company_name }} — Ref: {{ ref_code }}",
        "variables": ["lead_company","lead_contact","service_type","equipment","ref_code",
                      "company_name","company_phone","company_email","logo_url"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">Dear {{ lead_contact }},</p>
<p>Thank you for reaching out to <strong>{{ company_name }}</strong>. We have received your inquiry and are pleased to assist you with your industrial equipment and technical service needs.</p>

<div class="highlight-box">
  <p class="label">Your Inquiry Summary</p>
  <p><strong>Company:</strong> {{ lead_company }}</p>
  <p><strong>Service Required:</strong> {{ service_type }}</p>
  {% if equipment %}<p><strong>Equipment:</strong> {{ equipment }}</p>{% endif %}
  <p><strong>Reference Number:</strong> {{ ref_code }}</p>
</div>

<p>Our technical team will review your requirements and respond with a detailed proposal within <strong>24 hours</strong> during business hours.</p>
<p>In the meantime, please feel free to explore our equipment catalog and company profile below:</p>
<p style="text-align:center;">
  <a href="{{ company_website }}" class="cta-btn">VISIT OUR WEBSITE</a>
</p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
        "body_text": "Dear {{ lead_contact }},\n\nThank you for contacting {{ company_name }}.\nRef: {{ ref_code }}\nService: {{ service_type }}\n\nWe will respond within 24 hours.\n\n{{ company_name }}\n{{ company_phone }}"
    },

    # ── 2. Admin Lead Notification ────────────────────────────────────────────
    {
        "slug":      "admin_lead_notification",
        "name":      "Admin — New Lead Notification",
        "subject":   "🔔 New Lead: {{ lead_company }} — {{ service_type }} | {{ ref_code }}",
        "variables": ["lead_company","lead_contact","lead_email","lead_phone","service_type",
                      "equipment","duration","description","ref_code","submitted_at","dashboard_url"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">New Lead Received</p>
<p>A new inquiry has been submitted via the website. Details below:</p>

<div class="highlight-box">
  <p class="label">Lead Details</p>
  <p><strong>Company:</strong> {{ lead_company }}</p>
  <p><strong>Contact:</strong> {{ lead_contact }}</p>
  <p><strong>Email:</strong> {{ lead_email }}</p>
  <p><strong>Phone:</strong> {{ lead_phone }}</p>
  <p><strong>Service Type:</strong> {{ service_type }}</p>
  <p><strong>Equipment:</strong> {{ equipment }}</p>
  <p><strong>Duration:</strong> {{ duration }}</p>
  <p><strong>Reference:</strong> {{ ref_code }}</p>
  <p><strong>Submitted:</strong> {{ submitted_at }}</p>
</div>

{% if description %}
<p><strong>Project Description:</strong></p>
<p style="background:#f9fafb;padding:12px 16px;border-radius:4px;font-size:13px;">{{ description }}</p>
{% endif %}

<p style="text-align:center;">
  <a href="{{ dashboard_url }}" class="cta-btn">VIEW IN DASHBOARD</a>
</p>
<p><em>Automated follow-up emails have been scheduled: 24h, 3 days, 7 days.</em></p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
    },

    # ── 3. Lead Follow-up 24h ────────────────────────────────────────────────
    {
        "slug":      "lead_followup_24h",
        "name":      "Lead Follow-Up — 24 Hours",
        "subject":   "Following Up: Your {{ service_type }} Inquiry — {{ company_name }}",
        "variables": ["lead_company","lead_contact","service_type","ref_code","company_name","company_phone"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">Dear {{ lead_contact }},</p>
<p>I hope this message finds you well. I wanted to personally follow up on the inquiry you submitted to <strong>{{ company_name }}</strong> regarding <strong>{{ service_type }}</strong> (Ref: {{ ref_code }}).</p>
<p>We are currently preparing a tailored proposal for your requirements. If you have any additional details or questions in the meantime, please do not hesitate to reach out directly:</p>

<div class="highlight-box">
  <p class="label">Contact Us Directly</p>
  <p>📞 <strong>{{ company_phone }}</strong></p>
  <p>✉️ <strong>{{ company_email }}</strong></p>
</div>

<p>We look forward to the opportunity of serving <strong>{{ lead_company }}</strong> and delivering the industrial solutions your operations require.</p>
<p style="text-align:center;">
  <a href="{{ company_website }}" class="cta-btn">EXPLORE OUR SERVICES</a>
</p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
    },

    # ── 4. Lead Follow-up 3 Days ─────────────────────────────────────────────
    {
        "slug":      "lead_followup_3d",
        "name":      "Lead Follow-Up — 3 Days",
        "subject":   "{{ lead_company }} — Your {{ service_type }} Proposal Is Being Finalized",
        "variables": ["lead_company","lead_contact","service_type","ref_code"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">Dear {{ lead_contact }},</p>
<p>We are reaching out once more regarding your <strong>{{ service_type }}</strong> inquiry (Ref: <strong>{{ ref_code }}</strong>) for <strong>{{ lead_company }}</strong>.</p>
<p>At <strong>{{ company_name }}</strong>, we have been delivering reliable industrial equipment and technical services across Nigeria since 2001. Our clients trust us for:</p>

<div class="highlight-box">
  <p>✅ Industrial-grade, well-maintained equipment</p>
  <p>✅ Certified and experienced technical team</p>
  <p>✅ 24/7 support and fast response times</p>
  <p>✅ Competitive rates without compromise on quality</p>
  <p>✅ Genuine Caterpillar and Perkins spare parts</p>
</div>

<p>We are finalizing your proposal and will have it ready shortly. If you have any urgent requirements or wish to discuss your project directly, please contact us at <strong>{{ company_phone }}</strong>.</p>
<p style="text-align:center;">
  <a href="{{ company_website }}" class="cta-btn">VIEW EQUIPMENT CATALOG</a>
</p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
    },

    # ── 5. Lead Proposal 7 Days ───────────────────────────────────────────────
    {
        "slug":      "lead_proposal_7d",
        "name":      "Lead Proposal — 7 Days",
        "subject":   "Formal Proposal from {{ company_name }} — {{ lead_company }} | {{ ref_code }}",
        "variables": ["lead_company","lead_contact","service_type","ref_code","quote_url","profile_url"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">Dear {{ lead_contact }},</p>
<p>Please find attached our formal proposal for <strong>{{ lead_company }}</strong> regarding your <strong>{{ service_type }}</strong> requirements (Ref: {{ ref_code }}).</p>
<p>We are confident that <strong>{{ company_name }}</strong> is the ideal partner for your industrial operations. Our proposal outlines our service offering, equipment specifications, pricing, and terms.</p>

<div class="highlight-box">
  <p class="label">Proposal Summary</p>
  <p><strong>Service:</strong> {{ service_type }}</p>
  <p><strong>Reference:</strong> {{ ref_code }}</p>
  <p><strong>Prepared by:</strong> {{ company_name }}</p>
</div>

<p style="text-align:center;">
  <a href="{{ quote_url }}" class="cta-btn">VIEW FULL PROPOSAL</a>
</p>
{% if profile_url %}
<p style="text-align:center;margin-top:8px;">
  <a href="{{ profile_url }}" style="color:#22c55e;font-size:13px;">📄 Download Company Profile PDF</a>
</p>
{% endif %}
<p>We look forward to building a long-term business relationship with <strong>{{ lead_company }}</strong>. Please do not hesitate to contact us to discuss the proposal or arrange a site visit.</p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
    },

    # ── 6. Quote Sent ─────────────────────────────────────────────────────────
    {
        "slug":      "quote_sent",
        "name":      "Quotation Sent to Client",
        "subject":   "Quotation {{ quote_number }} from {{ company_name }} — {{ client_company }}",
        "variables": ["client_company","client_contact","quote_number","service_desc","amount","valid_until","quote_url"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">Dear {{ client_contact }},</p>
<p>Please find your official quotation from <strong>{{ company_name }}</strong>. We are pleased to present our competitive proposal for your review.</p>

<div class="highlight-box">
  <p class="label">Quotation Details</p>
  <p><strong>Quote Number:</strong> {{ quote_number }}</p>
  <p><strong>Service:</strong> {{ service_desc }}</p>
  <p><strong>Amount:</strong> {{ amount }}</p>
  <p><strong>Valid Until:</strong> {{ valid_until }}</p>
</div>

<p>Please review the quotation and do not hesitate to contact us with any questions or requests for adjustments.</p>
<p style="text-align:center;">
  <a href="{{ quote_url }}" class="cta-btn">VIEW & ACCEPT QUOTATION</a>
</p>
<p>This quotation is valid until <strong>{{ valid_until }}</strong>. To proceed, please confirm your acceptance via the link above or contact us directly.</p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
    },

    # ── 7. Quote Follow-up ────────────────────────────────────────────────────
    {
        "slug":      "quote_followup",
        "name":      "Quotation Follow-Up — 3 Days",
        "subject":   "Following Up: Quotation {{ quote_number }} — Action Required",
        "variables": ["client_company","client_contact","quote_number","amount","valid_until","quote_url"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">Dear {{ client_contact }},</p>
<p>We hope this message finds you well. We are following up on <strong>Quotation {{ quote_number }}</strong> sent to <strong>{{ client_company }}</strong>.</p>

<div class="highlight-box">
  <p class="label">Quotation Status</p>
  <p><strong>Quote:</strong> {{ quote_number }}</p>
  <p><strong>Amount:</strong> {{ amount }}</p>
  <p><strong>Expires:</strong> {{ valid_until }}</p>
</div>

<p>If you have any questions, require amendments, or wish to discuss the terms, our team is available to assist.</p>
<p style="text-align:center;">
  <a href="{{ quote_url }}" class="cta-btn">REVIEW QUOTATION</a>
</p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
    },

    # ── 8. Rental Expiry Reminder ─────────────────────────────────────────────
    {
        "slug":      "rental_expiry_reminder",
        "name":      "Rental Expiry Reminder — 14 Days",
        "subject":   "Rental Expiry Notice: {{ rental_code }} — {{ equipment_name }} | {{ end_date }}",
        "variables": ["client_company","rental_code","equipment_name","end_date","renewal_url"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">Dear {{ recipient_name }},</p>
<p>This is a courtesy reminder that your equipment rental with <strong>{{ company_name }}</strong> is due to expire in <strong>14 days</strong>.</p>

<div class="highlight-box">
  <p class="label">Rental Details</p>
  <p><strong>Client:</strong> {{ client_company }}</p>
  <p><strong>Rental Code:</strong> {{ rental_code }}</p>
  <p><strong>Equipment:</strong> {{ equipment_name }}</p>
  <p><strong>Expiry Date:</strong> {{ end_date }}</p>
</div>

<p>If you wish to <strong>extend your rental</strong>, please contact us before the expiry date to ensure continuity of service and equipment availability.</p>
<p style="text-align:center;">
  <a href="{{ renewal_url }}" class="cta-btn">REQUEST RENEWAL</a>
</p>
<p>If you no longer require the equipment, please arrange a return schedule with our team at least 5 days before the expiry date.</p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
    },

    # ── 9. Maintenance Reminder — Admin ──────────────────────────────────────
    {
        "slug":      "maintenance_reminder_admin",
        "name":      "Maintenance Reminder — Admin Notification",
        "subject":   "🔧 Maintenance Due in 7 Days: {{ maint_code }} — {{ equipment_name }}",
        "variables": ["maint_code","equipment_name","maint_type","scheduled_date","technician","dashboard_url"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">Maintenance Due in 7 Days</p>
<p>The following maintenance activity is scheduled in <strong>7 days</strong>. Please ensure all preparations are in order.</p>

<div class="highlight-box">
  <p class="label">Maintenance Details</p>
  <p><strong>Code:</strong> {{ maint_code }}</p>
  <p><strong>Equipment:</strong> {{ equipment_name }}</p>
  <p><strong>Type:</strong> {{ maint_type }}</p>
  <p><strong>Scheduled Date:</strong> {{ scheduled_date }}</p>
  <p><strong>Assigned Technician:</strong> {{ technician }}</p>
</div>

<p style="text-align:center;">
  <a href="{{ dashboard_url }}" class="cta-btn">MANAGE IN DASHBOARD</a>
</p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
    },

    # ── 10. Maintenance Reminder — Client ─────────────────────────────────────
    {
        "slug":      "maintenance_reminder_client",
        "name":      "Maintenance Reminder — Client Notification",
        "subject":   "Scheduled Maintenance Notice: {{ equipment_name }} — {{ scheduled_date }}",
        "variables": ["client_company","maint_code","equipment_name","maint_type","scheduled_date","technician"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">Dear {{ recipient_name }},</p>
<p>This is an advance notice that <strong>{{ company_name }}</strong> will be conducting scheduled maintenance on your equipment in <strong>7 days</strong>.</p>

<div class="highlight-box">
  <p class="label">Maintenance Schedule</p>
  <p><strong>Client:</strong> {{ client_company }}</p>
  <p><strong>Equipment:</strong> {{ equipment_name }}</p>
  <p><strong>Service Type:</strong> {{ maint_type }}</p>
  <p><strong>Scheduled Date:</strong> {{ scheduled_date }}</p>
  <p><strong>Technician:</strong> {{ technician }}</p>
</div>

<p>Our certified technician will attend your site on the scheduled date. Please ensure the equipment is accessible and a representative is available on-site.</p>
<p>If the scheduled date is inconvenient, please contact us at least 3 days in advance to reschedule.</p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
    },

    # ── 11. Invoice Reminder ──────────────────────────────────────────────────
    {
        "slug":      "invoice_reminder",
        "name":      "Invoice Payment Reminder — 7 Days",
        "subject":   "Payment Due in 7 Days: {{ rental_code }} — {{ company_name }}",
        "variables": ["client_company","rental_code","equipment_name","amount","due_date","portal_url"],
        "body_html": EMAIL_HEADER + """
<p class="greeting">Dear {{ recipient_name }},</p>
<p>This is a friendly reminder that a rental payment for your equipment with <strong>{{ company_name }}</strong> is due in <strong>7 days</strong>.</p>

<div class="highlight-box">
  <p class="label">Payment Details</p>
  <p><strong>Client:</strong> {{ client_company }}</p>
  <p><strong>Rental Code:</strong> {{ rental_code }}</p>
  <p><strong>Equipment:</strong> {{ equipment_name }}</p>
  <p><strong>Amount Due:</strong> {{ amount }}</p>
  <p><strong>Due Date:</strong> {{ due_date }}</p>
</div>

<p>Please ensure timely payment to avoid any interruption to your rental service. For payment inquiries or to request an official invoice, please contact our accounts team.</p>
<p style="text-align:center;">
  <a href="{{ portal_url }}" class="cta-btn">VIEW PORTAL</a>
</p>
<hr class="divider">
""" + SIGNATURE + EMAIL_FOOTER,
    },
]

# ─── Default company settings ─────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "company_name":       "Bilm Technical Services",
    "company_ref":        "BTS/IL/0069",
    "company_tagline":    "Powering Operations. Delivering Reliability.",
    "company_phone":      "08037815188",
    "company_email":      "Biali.kandi@gmail.com",
    "company_address":    "23 Chief Nwuke Street, Trans Amadi Industrial Layout, Port Harcourt, Rivers State",
    "company_website":    "https://bilmtechnical.com",
    "established_year":   "2001",
    "years_experience":   "20+",
    "projects_completed": "500+",
    "fleet_size":         "80+",
    "staff_count":        "45+",
    "logo_url":           LOGO_URL,
}

# ─── Seed runner ─────────────────────────────────────────────────────────────

async def seed():
    await create_all_tables()
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        # Company settings
        for key, value in DEFAULT_SETTINGS.items():
            existing = (await db.execute(
                select(CompanySettings).where(CompanySettings.key == key)
            )).scalar_one_or_none()
            if not existing:
                db.add(CompanySettings(key=key, value=value))
        print("✅  Company settings seeded")

        # Email templates
        for t in TEMPLATES:
            existing = (await db.execute(
                select(EmailTemplate).where(EmailTemplate.slug == t["slug"])
            )).scalar_one_or_none()
            if not existing:
                db.add(EmailTemplate(
                    slug=t["slug"],
                    name=t["name"],
                    subject=t["subject"],
                    body_html=t["body_html"],
                    body_text=t.get("body_text"),
                    variables=t.get("variables"),
                ))
        print(f"✅  {len(TEMPLATES)} email templates seeded")

        # Default admin user
        existing_admin = (await db.execute(
            select(User).where(User.email == "admin@bilmtechnical.com")
        )).scalar_one_or_none()
        if not existing_admin:
            db.add(User(
                email="admin@bilmtechnical.com",
                hashed_password=hash_password("ChangeMe2025!"),
                full_name="Biali Uchenna Kandi",
                role=UserRole.admin,
            ))
            print("✅  Default admin user created: admin@bilmtechnical.com / ChangeMe2025!")
        else:
            print("ℹ️   Admin user already exists")

        await db.commit()
    print("\n🎉  Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
