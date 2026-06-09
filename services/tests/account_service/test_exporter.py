from account_service.exporter import ExporterFactory, TxtExporter, CsvExporter, JsonExporter


def test_txt_export():
    accounts = [
        {"email": "a@test.com", "password": "pass1", "tokens": {"refresh_token": "rt1", "client_id": "c1"}},
        {"email": "b@test.com", "password": "pass2", "tokens": None},
    ]
    result = TxtExporter().export(accounts)
    lines = result.strip().split("\n")
    assert len(lines) == 2
    assert "a@test.com----pass1----rt1----c1" in lines[0]


def test_csv_export():
    accounts = [{"email": "a@test.com", "password": "p", "platform": "outlook", "status": "success", "created_at": "2026-01-01"}]
    result = CsvExporter().export(accounts)
    assert "email,password,platform,status,created_at" in result
    assert "a@test.com" in result


def test_json_export():
    accounts = [{"email": "a@test.com"}]
    result = JsonExporter().export(accounts)
    assert '"email": "a@test.com"' in result


def test_factory_get():
    for fmt in ["txt", "csv", "json"]:
        exporter = ExporterFactory.get(fmt)
        assert exporter is not None


def test_factory_list_formats():
    formats = ExporterFactory.list_formats()
    assert "txt" in formats
    assert "csv" in formats
    assert "json" in formats
