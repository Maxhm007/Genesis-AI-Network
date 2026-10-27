from genesis.log_redaction import redact_secrets


def test_redacts_known_token_shapes():
    text = (
        "Authorization: Bearer abc.def.ghi\n"
        "token ghp_" + "a" * 36 + "\n"
        "OPENAI_API_KEY=sk-" + "b" * 24 + "\n"
        "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----\n"
    )
    out = redact_secrets(text, environ={})
    assert "abc.def.ghi" not in out
    assert "ghp_" not in out
    assert "sk-bbbb" not in out
    assert "MIIE" not in out


def test_redacts_live_secret_environment_values():
    out = redact_secrets("value is s3cr3t-value-123", environ={"DEEPSEEK_API_KEY": "s3cr3t-value-123", "HOME": "/home/x"})
    assert "s3cr3t-value-123" not in out


def test_keeps_ordinary_test_output():
    text = "1553 passed, 41 skipped in 30.1s"
    assert redact_secrets(text, environ={}) == text


def test_redacts_more_token_shapes_and_keeps_numeric_settings():
    from genesis.log_redaction import redact_secrets
    text = (
        "Bearer abcdefghijklmnop12 "
        '{"token": "s3cr3tvalue"} '
        "https://user:hunter2pass@example.com/x "
        "glpat-ABCDEFGHIJKLMNOPQRST xoxb-1234567890-abcdef "
        "AIzaSyA1234567890abcdefghijklmnopqrstu "
        "max_tokens=1000"
    )
    out = redact_secrets(text, environ={})
    for leaked in ("abcdefghijklmnop12", "s3cr3tvalue", "hunter2pass", "glpat-ABC", "xoxb-123", "AIzaSyA"):
        assert leaked not in out
    assert "max_tokens=1000" in out
