from morningbrief.collectors.gmail import _secret_name, parse_message


def test_secret_name_is_per_account():
    assert _secret_name("Foo@Bar.com") == "gmail_token_json:foo@bar.com"
    assert _secret_name("a@b.com") != _secret_name("c@d.com")


def test_parse_message_tags_account():
    e = parse_message({
        "id": "m1", "threadId": "t1", "internalDate": "1700000000000",
        "payload": {"headers": [{"name": "From", "value": "Bob <bob@x.com>"}, {"name": "Subject", "value": "Hi"}],
                    "mimeType": "text/plain", "body": {"data": ""}},
        "snippet": "hi",
    }, account="gruia@pascale.ro")
    assert e.account == "gruia@pascale.ro"
    assert e.sender_email == "bob@x.com"


def test_collector_disabled_without_accounts(cfg):
    from morningbrief.collectors.gmail import GmailCollector

    c = GmailCollector()
    cfg.gmail_enabled = True
    cfg.gmail_accounts = []
    assert not c.enabled(cfg)
    cfg.gmail_accounts = ["a@b.com"]
    assert c.enabled(cfg)
    cfg.gmail_enabled = False
    assert not c.enabled(cfg)


def test_collect_isolates_failing_account_from_others(db, cfg, monkeypatch):
    """One account failing (e.g. not yet authorized) must not stop the others."""
    from morningbrief.collectors import gmail as gmail_mod

    cfg.gmail_accounts = ["broken@x.com", "ok@y.com"]

    def fake_collect_account(self, db, email):
        if email == "broken@x.com":
            raise RuntimeError("not authorized")
        return 3

    monkeypatch.setattr(gmail_mod.GmailCollector, "_collect_account", fake_collect_account)
    res = gmail_mod.GmailCollector().collect(cfg, db)
    assert res.new == 3
    assert any("broken@x.com" in n and "ERROR" in n for n in res.notes)
    assert any("ok@y.com:3" in n for n in res.notes)
