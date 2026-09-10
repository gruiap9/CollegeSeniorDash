import json
from datetime import timedelta

from morningbrief.db.models import Article, Assignment, Email
from morningbrief.db.repo import upsert_article, upsert_assignment, upsert_email
from morningbrief.services.brief_builder import build_brief, write_brief
from morningbrief.services.email_pipeline import process_unclassified
from morningbrief.services.change_detector import detect_changes
from morningbrief.utils.dates import now_local, to_utc_iso


def seed(db):
    now = now_local()
    upsert_assignment(db, Assignment("canvas", "CS461", "1", "Problem Set 2", due_date=to_utc_iso(now.replace(hour=23, minute=59)), status="unsubmitted", url="https://c/1"))
    upsert_assignment(db, Assignment("canvas", "CS520", "2", "Homework 1", due_date=to_utc_iso(now + timedelta(days=3)), status="unsubmitted", url="https://c/2"))
    upsert_assignment(db, Assignment("canvas", "CS461", "3", "Homework 1", due_date=to_utc_iso(now - timedelta(days=2)), status="graded", grade="94/100", url="https://c/3"))
    r = to_utc_iso(now - timedelta(hours=2))
    upsert_email(db, Email("m1", "gmail", "Amazon Recruiting", "no-reply@amazon.jobs", "Online Assessment Invitation", r, body="Please complete your online assessment on HackerRank.", url="https://g/1"))
    upsert_email(db, Email("m2", "gmail", "IBM", "talent@ibm.com", "Your application", r, body="Unfortunately we will not be moving forward.", url="https://g/2"))
    upsert_email(db, Email("m3", "outlook", "Yuriy Brun", "brun@cs.umass.edu", "CS520 office hours moved", r, body="Office hours moved to Thursday 2-4 PM.", url="https://o/3"))
    upsert_email(db, Email("m4", "outlook", "CICS News", "news-noreply@umass.edu", "This week at CICS", r, body="Events... unsubscribe", url="https://o/4"))
    upsert_email(db, Email("m5", "gmail", "Gradescope", "no-reply@gradescope.com", "Grades for Homework 1 in CS 461 have been released", r, body="Score: 94.0 / 100.0", url="https://g/5"))
    upsert_email(db, Email("m6", "gmail", "Piazza", "no-reply@piazza.com", "[CS 461] Instructor note: exam covers ch 1-4", r, body="An instructor posted. https://piazza.com/class/abc/post/7", url="https://g/6"))
    for i in range(3):
        upsert_article(db, Article(f"a{i}", "The Verge", f"OpenAI releases model {i}", f"https://v/{i}", r, "OpenAI today released a new model. It is fast."))
    upsert_article(db, Article("a9", "TechCrunch", "OpenAI launches model 0", "https://t/0", r, "OpenAI launched model 0."))


def test_build_brief(db, cfg, tmp_path):
    seed(db)
    process_unclassified(cfg, db)
    detect_changes(cfg, db)
    b = build_brief(cfg, db)
    assert b["job_search"]["counts_7d"]["OA"] == 1 and b["job_search"]["counts_7d"]["REJECTION"] == 1
    assert [j["event"] for j in b["job_search"]["items"]] == ["OA", "REJECTION"]
    assert b["important_email"][0]["sender"] == "Yuriy Brun"
    assert b["ignored_email_count"] >= 1
    assert b["school"]["today"][0]["title"] == "Problem Set 2" and b["school"]["today"][0]["due_label"].startswith("TODAY")
    assert b["school"]["next_3_days"][0]["course"] == "CS520"
    assert any(g["grade"] == "94/100" for g in b["school"]["new_grades"])
    assert b["piazza"][0]["course"] == "CS461" and b["piazza"][0]["new_count"] == 1
    assert b["news"] and b["news"][0]["rank"] == 1 and len(b["news"]) <= 5
    kinds = {e["kind"] for e in b["since_yesterday"]}
    assert {"job.oa", "job.rejection", "email.important", "grade.new", "piazza.instructor"} <= kinds
    p = write_brief(b, tmp_path / "brief.json")
    assert json.loads(p.read_text())["version"] == 1
