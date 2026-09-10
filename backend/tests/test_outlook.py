from morningbrief.collectors.outlook import parse_message


def test_parse_graph_message():
    e = parse_message({
        "id": "AAMk1", "conversationId": "c1", "subject": "Office hours",
        "from": {"emailAddress": {"name": "Yuriy Brun", "address": "Brun@cs.umass.edu"}},
        "receivedDateTime": "2026-09-09T12:00:00Z", "bodyPreview": "Moved to Thu",
        "body": {"contentType": "html", "content": "<p>Moved to <b>Thursday</b></p>"},
        "webLink": "https://outlook.office.com/mail/x",
    })
    assert e.sender_email == "brun@cs.umass.edu" and e.body == "Moved to Thursday"
    assert e.received_at == "2026-09-09T12:00:00+00:00" and e.url.startswith("https://outlook")
