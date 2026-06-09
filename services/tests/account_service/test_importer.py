from account_service.importer import AccountImporter


def test_parse_txt():
    content = "a@test.com----pass1----rt1----c1\nb@test.com----pass2"
    result = AccountImporter.parse_txt(content, "outlook")
    assert len(result) == 2
    assert result[0]["email"] == "a@test.com"
    assert result[0]["tokens"]["refresh_token"] == "rt1"
    assert result[1]["platform"] == "outlook"


def test_parse_txt_empty_lines():
    content = "a@test.com----pass1\n\n\nb@test.com----pass2\n"
    result = AccountImporter.parse_txt(content, "google")
    assert len(result) == 2


def test_parse_json():
    content = '[{"email": "a@test.com", "password": "p1"}]'
    result = AccountImporter.parse_json(content, "outlook")
    assert len(result) == 1
    assert result[0]["platform"] == "outlook"


def test_parse_dispatcher():
    txt = "a@test.com----pass1"
    result = AccountImporter.parse(txt, "txt", "outlook")
    assert len(result) == 1
