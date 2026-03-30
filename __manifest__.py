# -*- coding: utf-8 -*-
{
    "name": "Intelligent Applicant Tracking System (IATS)",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Recruitment",
    "summary": "Advanced applicant intelligence, resume parsing, and shortlist scoring for Odoo 19",
    "description": """
Intelligent Applicant Tracking System (IATS) is a fresh Odoo 19 recruitment addon
focused on reliable, explainable applicant screening.

Key capabilities:
- Resume ingestion from applicant attachments and direct uploads
- Safe resume parsing state tracking for PDF, DOCX, TXT, RTF, ODT, and images
- Weighted applicant scoring across keywords, skills, experience, education, and profile completeness
- Job-specific screening profiles with shortlist and review thresholds
- Recruiter-facing actions to screen, explain, and rank applicants
- Automatic screening cron for enabled job profiles
    """,
    "author": "Aayush Acharya & Nilima Shrestha",
    "license": "LGPL-3",
    "depends": [
        "hr_recruitment",
        "hr_recruitment_skills",
        "mail",
        "website_hr_recruitment",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/iats_job_profile_views.xml",
        "views/hr_job_views.xml",
        "views/hr_applicant_views.xml",
        "data/iats_cron_data.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
