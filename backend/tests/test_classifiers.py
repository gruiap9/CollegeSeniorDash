from morningbrief.classifiers import job_email, school_email
from morningbrief.classifiers.gradescope_email import parse_gradescope_email
from morningbrief.classifiers.importance import route
from morningbrief.classifiers.piazza_email import parse_piazza_email


def test_job_oa():
    r = job_email.rules("Amazon Recruiting", "no-reply@amazon.jobs", "Amazon SDE Intern: Online Assessment Invitation",
                        "Please complete your online assessment on HackerRank within 5 days.")
    assert r.job_related and r.event == "OA" and r.confidence >= 0.8
    assert r.company and "Amazon" in r.company


def test_job_rejection():
    r = job_email.rules("IBM Talent", "talent@ibm.com", "Update on your application to IBM",
                        "Thank you for your interest. Unfortunately, we will not be moving forward with your application.")
    assert r.event == "REJECTION"


def test_job_received():
    r = job_email.rules("Palantir", "no-reply@lever.co", "Thank you for applying to Palantir",
                        "We have received your application for Software Engineer, New Grad.")
    assert r.event == "APPLICATION_RECEIVED"


def test_job_interview_vs_rejection():
    r = job_email.rules("Google", "recruiting@google.com", "Your interview with Google",
                        "Unfortunately we will not be moving forward after your interview.")
    assert r.event == "REJECTION"


def test_newsletter_not_job():
    r = job_email.rules("LinkedIn Job Alerts", "jobalerts-noreply@linkedin.com", "5 new jobs for you",
                        "Recommended jobs based on your profile. Unsubscribe.")
    assert not r.job_related


def test_non_job():
    r = job_email.rules("Mom", "mom@example.com", "dinner", "Coming home this weekend?")
    assert not r.job_related


def test_school_professor():
    r = school_email.rules("Yuriy Brun", "brun@cs.umass.edu", "CS520 office hours moved",
                           "Office hours are moved to Thursday 2-4 PM this week.")
    assert r.school_related and r.role == "professor" and r.importance == 3 and r.course == "CS520"


def test_school_newsletter_ignored():
    r = school_email.rules("CICS News", "cics-news@umass.edu", "This week at CICS", "Events this week... Unsubscribe")
    assert r.importance == 0


def test_school_advisor():
    r = school_email.rules("CS Advising", "advising@cs.umass.edu", "Spring registration appointment",
                           "Your advising appointment for registration opens Friday.")
    assert r.role in ("advisor", "registrar") and r.importance >= 2


def test_route():
    assert route("no-reply@gradescope.com", "x") == "gradescope"
    assert route("no-reply@piazza.com", "x") == "piazza"
    assert route("brun@cs.umass.edu", "x") == "school"
    assert route("a@b.com", "x") == "job_or_other"


def test_gradescope_grade():
    g = parse_gradescope_email("Grades for Homework 1 in CS 461 have been released",
                               "Your score: 94.0 / 100.0 points. View: https://www.gradescope.com/courses/1388267/assignments/55/submissions/9")
    assert g.kind == "grade_published" and g.course == "CS461" and g.assignment == "Homework 1" and g.grade == "94.0/100.0"
    assert g.url.endswith("/submissions/9")


def test_gradescope_submitted_no_grade():
    g = parse_gradescope_email("Your submission to Problem Set 2 in COMPSCI 520 was received", "Thank you for submitting.")
    assert g.kind == "submitted" and g.course == "CS520" and g.grade is None


def test_piazza_instructor():
    p = parse_piazza_email("[CS 461] Instructor note: Exam covers chapters 1-4",
                           "An instructor posted a new note. https://piazza.com/class/mtqi57hoc4tmg/post/42")
    assert p.course == "CS461" and p.author_role == "instructor" and p.post_id == "42" and p.weight == 1.0
