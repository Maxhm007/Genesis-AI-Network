from pathlib import Path

activity = Path("mobile/app/src/main/java/org/genesisai/mobile/MainActivity.java")
text = activity.read_text(encoding="utf-8")
text = text.replace("import java.net.HttpURLConnection;\nimport java.net.URL;\n", "import java.net.HttpURLConnection;\nimport java.net.URI;\nimport java.net.URL;\n", 1)
old = '''    private String normalizedBaseUrl() {\n        String value = baseUrl.getText().toString().trim();\n        while (value.endsWith("/")) value = value.substring(0, value.length() - 1);\n        if (!value.startsWith("https://")) throw new IllegalArgumentException("Use an HTTPS Genesis API URL");\n        getPreferences(MODE_PRIVATE).edit().putString("base_url", value).apply();\n        return value;\n    }\n'''
new = '''    private String normalizedBaseUrl() {\n        String value = baseUrl.getText().toString().trim();\n        while (value.endsWith("/")) value = value.substring(0, value.length() - 1);\n        try {\n            URI uri = new URI(value);\n            boolean secureOrigin = "https".equalsIgnoreCase(uri.getScheme())\n                    && uri.getHost() != null\n                    && !uri.getHost().isBlank()\n                    && uri.getUserInfo() == null\n                    && uri.getQuery() == null\n                    && uri.getFragment() == null;\n            if (!secureOrigin) {\n                throw new IllegalArgumentException("Use a credential-free HTTPS Genesis API origin");\n            }\n        } catch (java.net.URISyntaxException e) {\n            throw new IllegalArgumentException("Use a valid HTTPS Genesis API origin", e);\n        }\n        getPreferences(MODE_PRIVATE).edit().putString("base_url", value).apply();\n        return value;\n    }\n'''
if text.count(old) != 1:
    raise SystemExit("normalizedBaseUrl anchor mismatch")
activity.write_text(text.replace(old, new, 1), encoding="utf-8")


test = Path("tests/test_android_secure_api_config.py")
test.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\nACTIVITY = ROOT / "mobile/app/src/main/java/org/genesisai/mobile/MainActivity.java"\n\n\ndef test_android_api_url_is_parsed_as_credential_free_https_origin():\n    source = ACTIVITY.read_text(encoding="utf-8")\n    assert "new URI(value)" in source\n    assert '\"https\".equalsIgnoreCase(uri.getScheme())' in source\n    assert "uri.getHost() != null" in source\n    assert "uri.getUserInfo() == null" in source\n    assert "uri.getQuery() == null" in source\n    assert "uri.getFragment() == null" in source\n    assert "Bearer token (not stored)" in source\n    assert 'putString("base_url", value)' in source\n    assert 'putString("token"' not in source\n''', encoding="utf-8")
