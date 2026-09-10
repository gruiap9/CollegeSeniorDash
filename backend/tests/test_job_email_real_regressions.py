"""Regression tests built directly from real emails that were misclassified
in production (see the job_email.py module docstring for the root causes).
These use the actual body text (trimmed/redacted of tracking junk only) so a
future change can't silently reopen the same bug.
"""

from morningbrief.classifiers.job_email import guess_company, rules

AMAZON_SUBJECT = "Thank you for Applying to Amazon!"
AMAZON_BODY = """Hi Stefan-Gruia,
Thanks for applying to Amazon! We've received your application for the Software Development Engineer (ID: 10489298) position.
What happens next?
If we decide to move forward with your application, the Amazon recruiting team will reach out to discuss next steps. Any updates to your application status will be reflected on your Application dashboard, so be sure to check back regularly.

Go to your application dashboard

Explore our interview resources for more information on the hiring process and how to prepare for interviews. To learn more about our peculiar culture, visit Amazon.jobs.
Best regards,
Amazon Recruiting Team"""

GM_SUBJECT = "Your application to Entry Level Software Engineer is in!"
GM_BODY = """Dear Stefan-Gruia ,

Thanks for applying to GM, where we are working to make our world better, safer and
more equitable for all.

We appreciate your interest and will review your application promptly.

If you are applying to a role that requires coding skills, you may receive an invitation
to take a coding assessment. You will receive a separate email within 24 hours providing
further instructions to complete the coding assessment."""

IBM_SUBJECT = "You have successfully submitted your IBM job application - Associate Data Scientist 2027"
IBM_BODY = """Dear Gruia,

Thank you for applying to the role of Associate Data Scientist 2027 - 129654 at IBM. We're excited that you're considering us as your next employer.

What to expect next:

- Depending on the role, you may be notified via email in the next 7 days to complete 1-2 assessments (some roles may not require assessments). Our Talent Acquisition team will review your application and any assessment results.

- Selected candidates will move forward to the interview stage.

- For this hiring cycle, interviews are planned to take place anywhere from 60 to 120 days after assessments are completed.

While you wait to hear from us:

- Visit our careers page to find tips on acing your interview and career advice from current IBMers.

Best regards,
IBM Talent Acquisition Team"""

IBM_REJECT_SUBJECT = "Your IBM Application Status"
IBM_REJECT_BODY = """Dear Gruia Pascale,

We regret to inform you that, after careful consideration, we have decided to move forward with other candidates whose applications more closely align with the specific requirements of the position.

Sincerely,
IBM Talent Acquisition Team"""

OSCAR_SUBJECT = "Thank you for applying to Oscar!"
OSCAR_BODY = """Hi Stefan-Gruia,

Thank you for your interest in Oscar. We appreciate you taking the time to complete your application for Data Scientist I.

What happens next?

If your skills and experience align well with the requirements of the role, a member of our team will reach out to schedule a conversation with you.

Due to the high volume of applications we receive, we may not be able to respond directly if there is not a match for this specific role.

Artificial Intelligence (AI) Guidelines: Please see our AI Guidelines for the acceptable use of artificial intelligence during the interview process at Oscar.

Oscar Talent Acquisition"""

VOLEON_SUBJECT = "Thank you for applying to The Voleon Group"
VOLEON_BODY = """Hi Stefan-Gruia,

Thank you for your interest in The Voleon Group! We have received your application for Data Scientist, and we are delighted that you would consider joining our team. Our team will review your application and will be in touch if your qualifications match our needs for the role. If you are not selected for this position, keep an eye on our jobs page as we're growing and adding openings.

All the best,
The Voleon Group"""

SALESFORCE_SUBJECT = "Great News! We’ve Received Your Application for the Software Engineering AMTS (College Grad) Position"
SALESFORCE_BODY = """Hi Stefan-Gruia,

You have officially applied for the Software Engineering AMTS (College Grad) opening at Salesforce, the world’s #1 agent-first enterprise.

So what’s next? We’ll review your application and reach out if you’re a potential match.

Thank you for exploring a future with Salesforce,
The Salesforce Recruiting Team"""

LINKEDIN_SUBJECT = "Sean Durkin recently posted"
LINKEDIN_BODY = """Sean Durkin shared a post: I’m thrilled to announce that I have accepted a job offer with Vi-Leon Life Sciences & Staffing Consulting, starting on September 14th.

I will be...
LIKE PRAISE EMPATHY 62, 22 Comments"""

SOUNDCLOUD_SUBJECT = "Sound Advice: AC Slater on His New Mixtape, Musical Evolution and More – Listen Now"
SOUNDCLOUD_BODY = """SoundCloud

Listen to an exclusive interview with the LA-based DJ, producer and Night Bass label boss on his new era. Hit play.

This week on Sound Advice, we're catching up with AC Slater. In our exclusive interview, AC talks about the making of his new mixtape.

Grow Your Music Career With Trackstack

Contact  Help  Terms  Privacy  Jobs"""


def test_amazon_application_received_not_interview():
    r = rules("Amazon.com", "noreply@mail.amazon.jobs", AMAZON_SUBJECT, AMAZON_BODY)
    assert r.job_related and r.event == "APPLICATION_RECEIVED"


def test_gm_workday_application_received_not_oa():
    r = rules("generalmotors@myworkday.com", "generalmotors@myworkday.com", GM_SUBJECT, GM_BODY)
    assert r.job_related and r.event == "APPLICATION_RECEIVED"
    assert r.company and r.company.lower() != "generalmotors@myworkday.com"


def test_ibm_application_received_not_interview():
    r = rules("IBM Talent Acquisition", "talent@ibm.com", IBM_SUBJECT, IBM_BODY)
    assert r.job_related and r.event == "APPLICATION_RECEIVED"
    assert r.company == "IBM"


def test_ibm_rejection_still_a_rejection():
    """Hedge-filtering must not break a genuine, unhedged rejection."""
    r = rules("IBM Talent Acquisition", "talent@ibm.com", IBM_REJECT_SUBJECT, IBM_REJECT_BODY)
    assert r.job_related and r.event == "REJECTION"


def test_oscar_greenhouse_application_received_not_interview():
    r = rules("no-reply@us.greenhouse-mail.io", "no-reply@us.greenhouse-mail.io", OSCAR_SUBJECT, OSCAR_BODY)
    assert r.job_related and r.event == "APPLICATION_RECEIVED"
    assert r.company == "Oscar"


def test_voleon_application_received_not_rejection():
    """The 'if you are not selected' boilerplate must not be read as a real rejection."""
    r = rules("Recruiting noreply", "recruiting-noreply@voleon.com", VOLEON_SUBJECT, VOLEON_BODY)
    assert r.job_related and r.event == "APPLICATION_RECEIVED"


def test_salesforce_curly_apostrophe_still_matches():
    """Real HTML email uses a curly apostrophe in \"We’ve Received\" — must still match."""
    r = rules("Salesforce", "salesforce@myworkday.com", SALESFORCE_SUBJECT, SALESFORCE_BODY)
    assert r.job_related and r.event == "APPLICATION_RECEIVED"
    assert r.company == "Salesforce"


def test_linkedin_social_digest_not_job_related():
    """Someone else's LinkedIn post about their own offer must not become the user's OFFER event."""
    r = rules("LinkedIn", "updates-noreply@linkedin.com", LINKEDIN_SUBJECT, LINKEDIN_BODY)
    assert not r.job_related


def test_soundcloud_newsletter_not_interview():
    r = rules("SoundCloud", "info@announcements.soundcloud.com", SOUNDCLOUD_SUBJECT, SOUNDCLOUD_BODY)
    assert r.event != "INTERVIEW"


def test_guess_company_word_boundary_not_substring():
    """'Great News!' must not extract 'News' from the 'at' inside 'Great'."""
    company = guess_company("Salesforce", "salesforce@myworkday.com", SALESFORCE_SUBJECT, SALESFORCE_BODY)
    assert company != "News"
    assert company == "Salesforce"


def test_guess_company_strips_whole_bad_phrase():
    company = guess_company("IBM Talent Acquisition", "talent@ibm.com", IBM_SUBJECT, IBM_BODY)
    assert company == "IBM"


def test_gm_company_not_garbled_by_role_title():
    """A prior version of the specific-pattern matcher grabbed the role title
    ('Entry Level Software Engineer is in') as if it were the company name."""
    company = guess_company("generalmotors@myworkday.com", "generalmotors@myworkday.com", GM_SUBJECT, GM_BODY)
    assert company == "GM"


def test_bare_hostname_sender_name_not_used_as_company():
    """A From: header with no friendly name can leave the raw hostname as the
    'display name' (e.g. 'mail.amazon.jobs') — that must not be shown as-is."""
    company = guess_company("mail.amazon.jobs", "account-update@mail.amazon.jobs", "Keep track of your application", "")
    assert company != "mail.amazon.jobs"


def test_fanduel_subject_pattern():
    company = guess_company("FanDuel", "no-reply@fanduel.com", "Thank you for applying to FanDuel", "")
    assert company == "FanDuel"


GARMIN_SUBJECT = "User account with Garmin International, Inc."
GARMIN_BODY = """Thank you for verifying your email with Garmin's career site.

Please start your job application below.

Start Your Application

If you didn't make this request, please ignore this message.

Thank you,
Human Resources
Garmin International"""

DELUXE_VERIFY_SUBJECT = "Verify your candidate account"
DELUXE_VERIFY_BODY = """Click this link to confirm your email address and complete setup for your candidate
account
https://deluxe.wd5.myworkdayjobs.com/USA_CAN/activate/...
The link will expire after 24 hours."""


def test_account_verification_not_application_received():
    """A verify-your-email / start-your-application template must not be
    read as a received/submitted confirmation — and must be confident enough
    (>=0.8) to skip the LLM fallback, which was observed getting this wrong."""
    r = rules("Garmin", "garmin+autoreply@talent.icims.com", GARMIN_SUBJECT, GARMIN_BODY)
    assert r.event == "JOB_OTHER"
    assert r.confidence >= 0.8

    r2 = rules("Deluxe", "deluxe@otp.workday.com", DELUXE_VERIFY_SUBJECT, DELUXE_VERIFY_BODY)
    assert r2.event == "JOB_OTHER"
    assert r2.confidence >= 0.8
