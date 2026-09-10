from morningbrief.collectors.canvas import course_code, normalize_assignment


def test_course_code():
    assert course_code({"course_code": "COMPSCI 461 Fall 2026"}) == "CS461"
    assert course_code({"course_code": "CS-520-01"}) == "CS520"


def test_normalize_graded():
    a = normalize_assignment("CS461", {"id": 5, "name": "HW1", "due_at": "2026-09-12T03:59:00Z", "points_possible": 100,
                                       "html_url": "https://x/1", "submission": {"workflow_state": "graded", "score": 94.0},
                                       "submission_types": ["online_upload"]})
    assert a.status == "graded" and a.grade == "94.0/100" and a.due_date == "2026-09-12T03:59:00+00:00"


def test_normalize_unsubmitted():
    a = normalize_assignment("CS461", {"id": 6, "name": "HW2", "due_at": None, "submission": {"workflow_state": "unsubmitted"},
                                       "submission_types": ["online_upload"]})
    assert a.status == "unsubmitted" and a.due_date is None
