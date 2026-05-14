import unittest
from contextlib import contextmanager
from http import HTTPStatus
from unittest.mock import patch

from scripts import dashboard_server, desk_operation_routes


class DashboardOperationRouteTests(unittest.TestCase):
    def test_operation_route_owner_handles_desk_action_with_decoded_action_id(self):
        class FakeHandler:
            status = None
            payload = None

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        features = []
        body = {"confirm": True}

        handler = FakeHandler()
        handled = desk_operation_routes.handle_operation_post_route(
            handler,
            "/api/desk/actions/sources%3Aprobe/run",
            body,
            require_loopback_access=lambda value, feature: features.append((value, feature)),
            close_after_use=lambda conn: conn,
            monitor_state_module=dashboard_server.monitor_state,
            run_desk_action=lambda action_id, *, body=None: {"action_id": action_id, "body": dict(body or {})},
            git_update_status=lambda *, fetch: {},
            git_pull_latest=lambda: {},
            git_confirmation_error=dashboard_server.DashboardGitError,
            write_feedback_export=lambda conn: {},
        )

        self.assertTrue(handled)
        self.assertEqual(features, [(handler, "Desk actions")])
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload, {"ok": True, "result": {"action_id": "sources:probe", "body": body}})


    def test_operation_route_owner_handles_feedback_export_with_closed_connection(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        class FakeHandler:
            status = None
            payload = None
            conn = FakeConnection()

            def _connect(self):
                return self.conn

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        @contextmanager
        def close_after_use(conn):
            try:
                yield conn
            finally:
                conn.close()

        handler = FakeHandler()
        handled = desk_operation_routes.handle_operation_post_route(
            handler,
            "/api/feedback/export",
            {},
            require_loopback_access=lambda handler, feature: None,
            close_after_use=close_after_use,
            monitor_state_module=dashboard_server.monitor_state,
            run_desk_action=lambda action_id, *, body=None: {},
            git_update_status=lambda *, fetch: {},
            git_pull_latest=lambda: {},
            git_confirmation_error=dashboard_server.DashboardGitError,
            write_feedback_export=lambda conn: {"conn": conn is handler.conn},
        )

        self.assertTrue(handled)
        self.assertTrue(handler.conn.closed)
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload, {"ok": True, "export": {"conn": True}})


    def test_operation_route_owner_handles_review_card_action_with_decoded_card_id(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        class FakeMonitorState:
            @staticmethod
            def set_card_action(conn, *, card_id, action, note):
                return {"conn": conn is handler.conn, "card_id": card_id, "action": action, "note": note}

        class FakeHandler:
            status = None
            payload = None
            conn = FakeConnection()

            def _connect(self):
                return self.conn

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        @contextmanager
        def close_after_use(conn):
            try:
                yield conn
            finally:
                conn.close()

        handler = FakeHandler()
        handled = desk_operation_routes.handle_operation_post_route(
            handler,
            "/api/review-cards/card%3A123/action",
            {"action": "keep", "note": "follow up"},
            require_loopback_access=lambda handler, feature: None,
            close_after_use=close_after_use,
            monitor_state_module=FakeMonitorState,
            run_desk_action=lambda action_id, *, body=None: {},
            git_update_status=lambda *, fetch: {},
            git_pull_latest=lambda: {},
            git_confirmation_error=dashboard_server.DashboardGitError,
            write_feedback_export=lambda conn: {},
        )

        self.assertTrue(handled)
        self.assertTrue(handler.conn.closed)
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(
            handler.payload,
            {"ok": True, "card": {"conn": True, "card_id": "card:123", "action": "keep", "note": "follow up"}},
        )


    def test_operation_route_owner_rejects_git_pull_without_confirmation_before_pull(self):
        class FakeHandler:
            def _json(self, status, payload):
                raise AssertionError("unconfirmed pull should raise before JSON response")

        with self.assertRaisesRegex(dashboard_server.DashboardGitError, "explicit confirmation"):
            desk_operation_routes.handle_operation_post_route(
                FakeHandler(),
                "/api/git/pull-latest",
                {"confirm": False},
                require_loopback_access=lambda handler, feature: None,
                close_after_use=lambda conn: conn,
                monitor_state_module=dashboard_server.monitor_state,
                run_desk_action=lambda action_id, *, body=None: {},
                git_update_status=lambda *, fetch: {},
                git_pull_latest=lambda: (_ for _ in ()).throw(AssertionError("pull should not run")),
                git_confirmation_error=dashboard_server.DashboardGitError,
                write_feedback_export=lambda conn: {},
            )


    def test_operation_route_owner_returns_false_for_non_operation_path(self):
        handled = desk_operation_routes.handle_operation_post_route(
            object(),
            "/api/profiles/create",
            {},
            require_loopback_access=lambda handler, feature: None,
            close_after_use=lambda conn: conn,
            monitor_state_module=dashboard_server.monitor_state,
            run_desk_action=lambda action_id, *, body=None: {},
            git_update_status=lambda *, fetch: {},
            git_pull_latest=lambda: {},
            git_confirmation_error=dashboard_server.DashboardGitError,
            write_feedback_export=lambda conn: {},
        )

        self.assertFalse(handled)


    def test_dashboard_handler_post_uses_facade_injected_operation_helpers(self):
        class FakeHandler:
            status = None
            payload = None

            def __init__(self, path, body):
                self.path = path
                self.body = body

            def _read_json_body(self):
                return self.body

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        cases = [
            (
                "/api/desk/actions/monitor_jobs_dry_run/run",
                {"confirm": True},
                "run_desk_action",
                ("monitor_jobs_dry_run",),
                {"body": {"confirm": True}},
                "result",
            ),
            (
                "/api/git/check-updates",
                {},
                "_git_update_status",
                (),
                {"fetch": True},
                "git",
            ),
            (
                "/api/git/pull-latest",
                {"confirm": True},
                "_git_pull_latest",
                (),
                {},
                "git",
            ),
        ]
        for path, body, helper_name, expected_args, expected_kwargs, payload_key in cases:
            with self.subTest(path=path):
                result = {"schema_version": f"patched_{helper_name}_v1"}
                with patch.object(dashboard_server, helper_name, return_value=result) as helper_mock:
                    handler = FakeHandler(path, body)
                    dashboard_server.DashboardHandler.do_POST(handler)

                helper_mock.assert_called_once_with(*expected_args, **expected_kwargs)
                self.assertEqual(handler.status, HTTPStatus.OK)
                self.assertEqual(handler.payload, {"ok": True, payload_key: result})


if __name__ == "__main__":
    unittest.main()
