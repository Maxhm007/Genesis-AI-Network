from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY = ROOT / "mobile/app/src/main/java/org/genesisai/mobile/MainActivity.java"


def test_android_api_url_is_parsed_as_credential_free_https_origin():
    source = ACTIVITY.read_text(encoding="utf-8")
    assert "new URI(value)" in source
    assert '"https".equalsIgnoreCase(uri.getScheme())' in source
    assert "uri.getHost() != null" in source
    assert "uri.getUserInfo() == null" in source
    assert "uri.getQuery() == null" in source
    assert "uri.getFragment() == null" in source
    assert "Bearer token (not stored)" in source
    assert 'putString("base_url", value)' in source
    assert 'putString("token"' not in source
