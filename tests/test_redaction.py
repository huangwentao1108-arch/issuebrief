import unittest

from issuebrief.redaction import redact_text


class RedactionTests(unittest.TestCase):
    def test_redacts_supported_secret_types_without_leaking_values(self):
        fake_github = "ghp_" + "abcdefghijklmno12345"
        fake_openai = "sk-" + "exampleFakeToken123"
        fake_slack = "xoxb-" + "1234567890-abcdefghij"
        fake_jwt = "eyJ" + "hbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.signature12345"
        source = "\n".join(
            (
                f"Authorization: Bearer {fake_github}",
                f"openai={fake_openai} slack={fake_slack}",
                f"jwt={fake_jwt} password='not-a-real-password'",  # pragma: allowlist secret
                "api_key: example-api-value-12345",
                "https://user:example-password@example.test/path",  # pragma: allowlist secret
                "operator@example.test from 10.20.30.40 and 127.0.0.1",
                "-----BEGIN PRIVATE KEY-----\npretend-key-material\n-----END PRIVATE KEY-----",  # pragma: allowlist secret
            )
        )
        result = redact_text(source, home="/home/operator")

        for value in (
            fake_github,
            fake_openai,
            fake_slack,
            fake_jwt,
            "not-a-real-password",
            "example-password",
            "operator@example.test",
        ):
            self.assertNotIn(value, result.text)
        self.assertIn("127.0.0.1", result.text)
        self.assertEqual(1, result.counts["PEM_PRIVATE_KEY"])
        self.assertIn("[REDACTED:", result.text)

    def test_is_idempotent_and_keeps_normal_text_and_newlines(self):
        source = "A normal sentence.\r\napi_key=example-api-value-12345\r\n"
        first = redact_text(source)
        second = redact_text(first.text)
        self.assertEqual(first.text, second.text)
        self.assertEqual(2, first.text.count("\r\n"))
        self.assertIn("A normal sentence.", first.text)
        self.assertEqual({}, second.counts)

    def test_home_paths_extra_rules_and_false_positives(self):
        source = "C:\\Users\\Alice\\code C:/Users/Alice/other /home/alice/code localhost 127.0.0.1 version 1.2.3.4"
        result = redact_text(
            source, home="C:\\Users\\Alice", extra_patterns=(r"/home/alice",)
        )
        self.assertNotIn("C:\\Users\\Alice", result.text)
        self.assertNotIn("C:/Users/Alice", result.text)
        self.assertNotIn("/home/alice", result.text)
        self.assertIn("localhost 127.0.0.1", result.text)
        self.assertIn("[REDACTED:IPV4]", result.text)
        self.assertEqual(2, result.counts["HOME_PATH"])
        self.assertEqual(1, result.counts["EXTRA_PATTERN"])

    def test_github_prefix_variants_and_key_names_are_redacted(self):
        variants = " ".join(
            f"{prefix}_abcdefghijklmno12345"
            for prefix in ("ghp", "gho", "ghu", "ghs", "ghr")
        )
        result = redact_text(
            f"{variants}\ntoken: value-123456789\npassword: [REDACTED:CREDENTIAL_VALUE]"
        )
        self.assertEqual(5, result.text.count("[REDACTED:GITHUB_TOKEN]"))
        self.assertEqual(5, result.counts["GITHUB_TOKEN"])
        self.assertEqual(1, result.counts["CREDENTIAL_VALUE"])

    def test_redacts_quoted_bearer_and_common_service_credentials(self):
        values = {
            "GITHUB_PAT": "github_pat_"
            + "abcdefghijklmnopqrstuvwx",  # pragma: allowlist secret
            "AWS_ACCESS_KEY": "AKIA" + "ABCDEFGHIJKLMNOP",  # pragma: allowlist secret
            "AWS_SESSION_KEY": "ASIA" + "ABCDEFGHIJKLMNOP",  # pragma: allowlist secret
            "GITLAB_TOKEN": "glpat-"
            + "abcdefghijklmnopqrst",  # pragma: allowlist secret
            "GOOGLE_API_KEY": "AIza"  # pragma: allowlist secret
            + "abcdefghijklmnopqrstuvwxyz123456789",  # pragma: allowlist secret
            "NPM_TOKEN": "npm_"
            + "abcdefghijklmnopqrstuvwxyz123456",  # pragma: allowlist secret
            "STRIPE_LIVE_KEY": "sk_live_"
            + "abcdefghijklmnop",  # pragma: allowlist secret
            "STRIPE_RESTRICTED_KEY": "rk_live_"
            + "abcdefghijklmnop",  # pragma: allowlist secret
            "QUOTED_BEARER": "fake-bearer-token-123",
        }
        source = "\n".join(
            (
                values["GITHUB_PAT"],
                values["AWS_ACCESS_KEY"],
                values["AWS_SESSION_KEY"],
                values["GITLAB_TOKEN"],
                values["GOOGLE_API_KEY"],
                values["NPM_TOKEN"],
                values["STRIPE_LIVE_KEY"],
                values["STRIPE_RESTRICTED_KEY"],
                f"Authorization: Bearer '{values['QUOTED_BEARER']}'",
                f'authorization: bearer "{values["QUOTED_BEARER"]}"',
            )
        )
        first = redact_text(source)
        second = redact_text(first.text)

        for value in values.values():
            self.assertNotIn(value, first.text)
        self.assertIn("Bearer '[REDACTED:BEARER_TOKEN]'", first.text)
        self.assertIn('bearer "[REDACTED:BEARER_TOKEN]"', first.text)
        self.assertEqual(1, first.counts["GITHUB_PAT"])
        self.assertEqual(2, first.counts["AWS_ACCESS_KEY"])
        self.assertEqual(1, first.counts["GITLAB_TOKEN"])
        self.assertEqual(1, first.counts["GOOGLE_API_KEY"])
        self.assertEqual(1, first.counts["NPM_TOKEN"])
        self.assertEqual(2, first.counts["STRIPE_LIVE_KEY"])
        self.assertEqual(2, first.counts["BEARER_TOKEN"])
        self.assertEqual(first.text, second.text)
        self.assertEqual({}, second.counts)

    def test_redacts_sensitive_headers_and_ipv6_but_keeps_loopback(self):
        source = "\n".join(
            (
                "Authorization: Basic dXNlcjpwYXNz",
                "X-Api-Key: synthetic-header-secret",
                "Cookie: session=synthetic-cookie; theme=dark",
                "Set-Cookie: session=synthetic-cookie; HttpOnly",
                "remote=2001:db8::dead:beef loopback=::1",
            )
        )

        result = redact_text(source)

        for sensitive in (
            "dXNlcjpwYXNz",
            "synthetic-header-secret",
            "synthetic-cookie",
            "2001:db8::dead:beef",
        ):
            self.assertNotIn(sensitive, result.text)
        self.assertIn("Authorization: Basic [REDACTED:BASIC_AUTH]", result.text)
        self.assertIn("Cookie: [REDACTED:COOKIE_HEADER]", result.text)
        self.assertIn("loopback=::1", result.text)
        self.assertEqual(2, result.counts["COOKIE_HEADER"])
        self.assertEqual(1, result.counts["IPV6"])

    def test_sensitive_header_redaction_preserves_crlf(self):
        source = (
            "Cookie: session=synthetic-cookie\r\n"
            "Authorization: Basic dXNlcjpwYXNz\r\n"
            "ordinary line\r\n"
        )

        result = redact_text(source)

        self.assertEqual(3, result.text.count("\r\n"))
        self.assertIn("ordinary line\r\n", result.text)
