import unittest

from scripts import delivery


class DeliveryTests(unittest.TestCase):
    def test_telegram_alert_text_excludes_raw_message_text(self):
        text = delivery.build_telegram_alert_text(
            item={
                "topic": "Exchange outage",
                "rating": "high",
                "why": "Decision-relevant market signal.",
                "text": "RAW TELEGRAM BODY SHOULD NOT BE SENT",
                "decision_state": {"status": "new"},
                "source_message_refs": [{"channel": "cointelegraph", "id": 123}],
            },
            card={"card_id": "card_123"},
            report_url="output/runs/run/report.html",
            dashboard_url="http://127.0.0.1:8765",
        )

        self.assertIn("Exchange outage", text)
        self.assertIn("cointelegraph#123", text)
        self.assertNotIn("RAW TELEGRAM BODY", text)

    def test_telegram_alert_title_uses_role_when_company_is_placeholder(self):
        text = delivery.build_telegram_alert_text(
            item={
                "company": "Unknown",
                "role": "AI Engineer",
                "rating": "high",
                "why": "Strong fit.",
                "decision_state": {"status": "new"},
                "source_message_refs": [{"channel": "jobs", "id": 42}],
            },
            card={"card_id": "card_123"},
        )

        self.assertIn("TGCS alert: AI Engineer", text)
        self.assertNotIn("TGCS alert: Unknown", text)

    def test_dry_run_telegram_delivery_does_not_require_token(self):
        attempt = delivery.send_telegram_bot_message(
            target_id="telegram-bot-default",
            chat_id="12345",
            text="hello",
            mode="dry-run",
        )

        self.assertTrue(attempt.ok)
        self.assertEqual(attempt.status, "dry_run")


if __name__ == "__main__":
    unittest.main()
