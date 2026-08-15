#!/usr/bin/env python3
"""Public-command tests for Agent Attention runtime contracts."""

from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import unittest
from unittest import mock
from pathlib import Path
from typing import Any


RUNTIME = Path(
    os.environ.get("AGENT_ATTENTION_RUNTIME", Path(__file__).with_name("agent-attention.py"))
)
RUNTIME_SPEC = importlib.util.spec_from_file_location("agent_attention_runtime", RUNTIME)
assert RUNTIME_SPEC and RUNTIME_SPEC.loader
AGENT_ATTENTION = importlib.util.module_from_spec(RUNTIME_SPEC)
RUNTIME_SPEC.loader.exec_module(AGENT_ATTENTION)
LIST_ID = "32C46BA9-FE7A-4758-AA9E-4C4A249A5DF6"
REMINDER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_REMINDER_ID = "22222222-2222-4222-8222-222222222222"
NEW_REMINDER_ID = "33333333-3333-4333-8333-333333333333"
THREAD_ID = "019fc54e-ff95-7ca1-af49-5720c36fdc0d"
OTHER_THREAD_ID = "019fc54e-ff95-7ca1-af49-5720c36fdc0e"
APPROVAL_MEANING = "Approve the bounded outcome-receipt test only."
FINISHED_AT = "2026-08-10T05:45:00Z"


class AgentAttentionCommandTest(unittest.TestCase):
	"""Prove discovery and outcome behavior through the public CLI."""

	def setUp(self) -> None:
		self.temporary = tempfile.TemporaryDirectory()
		self.root = Path(self.temporary.name)
		self.state_dir = self.root / "state"
		self.bin_dir = self.root / "bin"
		self.inventory_path = self.root / "inventory.json"
		self.calls_path = self.root / "calls.jsonl"
		self.poll_count_path = self.root / "poll-count.txt"
		self.bin_dir.mkdir()
		self._write_fake_remindctl()
		self.env = {
			**os.environ,
			"PATH": f"{self.bin_dir}:{os.environ['PATH']}",
			"FAKE_REMINDERS_INVENTORY": str(self.inventory_path),
			"FAKE_REMINDERS_CALLS": str(self.calls_path),
			"FAKE_REMINDERS_POLL_COUNT": str(self.poll_count_path),
		}
		self.mapping = {
			"version": 1,
			"list": {"id": LIST_ID, "name": "Agent Attention"},
			"reminder_id": REMINDER_ID,
			"expected_title": "[APPROVE] Approve outcome receipt test",
			"required_notes_line": f"Approval meaning: {APPROVAL_MEANING}",
			"thread_id": THREAD_ID,
			"approval_meaning": APPROVAL_MEANING,
		}
		self.target = {
			"id": REMINDER_ID,
			"listID": LIST_ID,
			"listName": "Agent Attention",
			"title": self.mapping["expected_title"],
			"notes": (
				"Recommended: approve.\n\n"
				f"Approval meaning: {APPROVAL_MEANING}\n"
				"Tick = approve only this action.\n"
				"Discuss or disagree: open Codex.\n\n"
				f"remindctl URL (managed): agent-attention://threads/{THREAD_ID}"
			),
			"url": f"agent-attention://threads/{THREAD_ID}",
			"priority": "high",
			"isCompleted": True,
			"completionDate": "2026-08-10T05:40:00Z",
			"lastModifiedDate": "2026-08-10T05:40:00Z",
		}
		self.other = {
			"id": OTHER_REMINDER_ID,
			"listID": LIST_ID,
			"listName": "Agent Attention",
			"title": "[APPROVE] Other gate",
			"notes": "Unrelated sentinel",
			"priority": "low",
			"isCompleted": False,
			"lastModifiedDate": "2026-08-10T05:30:00Z",
		}
		self._write_state(delivery_receipt=True)
		self._write_inventory()

	def tearDown(self) -> None:
		self.temporary.cleanup()

	def _write_fake_remindctl(self) -> None:
		path = self.bin_dir / "remindctl"
		path.write_text(
			"""#!/usr/bin/env python3
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

inventory_path = Path(os.environ["FAKE_REMINDERS_INVENTORY"])
calls_path = Path(os.environ["FAKE_REMINDERS_CALLS"])
args = sys.argv[1:]
with calls_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\\n")
inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

if args[0] == "show":
    if os.environ.get("FAKE_REMINDERS_INVALID_SHOW_JSON") == "1":
        print("{")
        raise SystemExit(0)
    if os.environ.get("FAKE_REMINDERS_HANG_SHOW_SECONDS"):
        time.sleep(float(os.environ["FAKE_REMINDERS_HANG_SHOW_SECONDS"]))
    if args[1] == "all" and os.environ.get("FAKE_REMINDERS_COMPLETE_AFTER_POLLS"):
        poll_count_path = Path(os.environ["FAKE_REMINDERS_POLL_COUNT"])
        count = int(poll_count_path.read_text() if poll_count_path.exists() else "0") + 1
        poll_count_path.write_text(str(count))
        if count >= int(os.environ["FAKE_REMINDERS_COMPLETE_AFTER_POLLS"]):
            target = inventory[0]
            if not target.get("isCompleted"):
                target["isCompleted"] = True
                target["completionDate"] = datetime.now(timezone.utc).isoformat()
                inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    if args[1] == "completed":
        inventory = [item for item in inventory if item.get("isCompleted")]
        if os.environ.get("FAKE_REMINDERS_REMOVE_AFTER_COMPLETED") == "1":
            Path(sys.argv[0]).unlink()
    print(json.dumps(inventory))
elif args[0] == "add":
    reminder = {
        "id": os.environ.get("FAKE_REMINDERS_NEW_ID", "33333333-3333-4333-8333-333333333333"),
        "listID": args[args.index("--list-id") + 1],
        "listName": "Agent Attention",
        "title": args[args.index("--title") + 1],
        "notes": args[args.index("--notes") + 1],
        "url": args[args.index("--url") + 1],
        "priority": args[args.index("--priority") + 1],
        "alarm": args[args.index("--alarm") + 1],
        "isCompleted": False,
        "lastModifiedDate": datetime.now(timezone.utc).isoformat(),
    }
    if os.environ.get("FAKE_REMINDERS_NEW_NOTES_JSON"):
        reminder["notes"] = json.loads(os.environ["FAKE_REMINDERS_NEW_NOTES_JSON"])
    if os.environ.get("FAKE_REMINDERS_NEW_COMPLETION_JSON"):
        reminder["isCompleted"] = json.loads(os.environ["FAKE_REMINDERS_NEW_COMPLETION_JSON"])
    if os.environ.get("FAKE_REMINDERS_OMIT_NEW_COMPLETION") == "1":
        reminder.pop("isCompleted")
    inventory.append(reminder)
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    print(json.dumps(reminder))
elif args[0] == "edit":
    reminder_id = args[1]
    notes = args[args.index("--notes") + 1]
    matches = [item for item in inventory if item.get("id") == reminder_id]
    if len(matches) != 1:
        raise SystemExit(4)
    matches[0]["notes"] = notes
    matches[0]["lastModifiedDate"] = "2026-08-10T05:45:01Z"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    if os.environ.get("FAKE_REMINDERS_FAIL_AFTER_EDIT") == "1":
        print("unknown result after write", file=sys.stderr)
        raise SystemExit(5)
    print(json.dumps(matches[0]))
elif args[0] == "doctor":
    if os.environ.get("FAKE_REMINDERS_INVALID_UTF8") == "1":
        sys.stdout.buffer.write(b"\\xff")
        raise SystemExit(0)
    print(os.environ.get("FAKE_REMINDERS_DOCTOR_JSON", '{"authorization":{"authorized":true}}'))
else:
    print("unsupported remindctl subcommand: " + args[0], file=sys.stderr)
    raise SystemExit(2)
""",
			encoding="utf-8",
		)
		path.chmod(0o755)

	def _write_inventory(self) -> None:
		self.inventory_path.write_text(
			json.dumps([self.target, self.other]), encoding="utf-8"
		)

	def _write_state(self, *, delivery_receipt: bool) -> None:
		(self.state_dir / "gates").mkdir(parents=True)
		(self.state_dir / "config.json").write_text(
			json.dumps({"version": 1, "list": self.mapping["list"]}),
			encoding="utf-8",
		)
		(self.state_dir / "gates" / f"{REMINDER_ID}.json").write_text(
			json.dumps(self.mapping), encoding="utf-8"
		)
		if delivery_receipt:
			identifier = self._event_id()
			(self.state_dir / "receipts").mkdir()
			(self.state_dir / "receipts" / f"{identifier}.json").write_text(
				json.dumps(
					{
						"event_id": identifier,
						"reminder_id": REMINDER_ID,
						"thread_id": THREAD_ID,
						"approval_meaning": APPROVAL_MEANING,
						"delivered_at": "2026-08-10T05:41:00Z",
					}
				),
				encoding="utf-8",
			)

	def _event_id(self) -> str:
		import hashlib

		payload = {
			"approval_meaning": APPROVAL_MEANING,
			"reminder_id": REMINDER_ID,
			"thread_id": THREAD_ID,
		}
		encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
		return hashlib.sha256(encoded).hexdigest()

	def _outcome_id(self, outcome: str) -> str:
		import hashlib

		payload = {
			"event_id": self._event_id(),
			"finished_at": FINISHED_AT,
			"outcome": outcome,
		}
		encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
		return hashlib.sha256(encoded).hexdigest()

	def run_cli(
		self, *arguments: str, env_update: dict[str, str] | None = None
	) -> subprocess.CompletedProcess[str]:
		env = {**self.env, **(env_update or {})}
		return subprocess.run(
			[
				sys.executable,
				str(RUNTIME),
				"--state-dir",
				str(self.state_dir),
				*arguments,
			],
			capture_output=True,
			text=True,
			env=env,
		)

	def result(self, completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
		self.assertEqual(completed.returncode, 0, completed.stderr)
		return json.loads(completed.stdout)

	def calls(self) -> list[list[str]]:
		if not self.calls_path.exists():
			return []
		return [json.loads(line) for line in self.calls_path.read_text().splitlines()]

	def submit_arguments(self, **overrides: str | bool) -> tuple[str, ...]:
		values: dict[str, str | bool] = {
			"decision_type": "yes_no",
			"unblocks_paused_task": True,
			"action": "Approve local router test",
			"recommendation": "Approve the bounded local router test.",
			"consequence": "The paused task will resume and run its focused tests.",
			"discussion_link": f"agent-attention://threads/{THREAD_ID}",
			"continuation": "Run the focused tests, then record the terminal outcome.",
			"approval_meaning": "Approve the bounded local router test only.",
		}
		values.update(overrides)
		arguments = ["submit", "--thread-id", THREAD_ID]
		for field, value in values.items():
			flag = f"--{field.replace('_', '-')}"
			if isinstance(value, bool):
				if value:
					arguments.append(flag)
			else:
				arguments.extend([flag, value])
		return tuple(arguments)

	def test_command_discovery_help_and_parser_stay_aligned(self) -> None:
		discovery = self.result(self.run_cli("commands"))
		command_names = [item["name"] for item in discovery["commands"]]
		self.assertIn("record-outcome", command_names)
		self.assertNotIn("create", command_names)

		help_result = self.run_cli("--help")
		self.assertEqual(help_result.returncode, 0)
		for command_name in command_names:
			self.assertIn(command_name, help_result.stdout)
			self.assertEqual(self.run_cli(command_name, "--help").returncode, 0)
		self.assertNotEqual(self.run_cli("create", "--help").returncode, 0)
		submit_help = self.run_cli("submit", "--help").stdout
		for term in ("yes_no", "paused", "Approve", "one alert"):
			self.assertIn(term, submit_help)

	def test_parser_construction_errors_use_the_structured_error_boundary(self) -> None:
		completed = self.run_cli(
			"commands", env_update={"XDG_STATE_HOME": "relative-state"}
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("XDG_STATE_HOME must be an absolute path", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		result = json.loads(completed.stdout)
		self.assertEqual(result["status"], "error")
		self.assertEqual(result["error_category"], "contract_or_runtime")
		self.assertIs(result["changed"], False)
		self.assertIs(result["change_uncertain"], True)

	def test_non_object_config_uses_the_structured_error_boundary(self) -> None:
		(self.state_dir / "config.json").write_text("[]", encoding="utf-8")
		completed = self.run_cli("doctor")
		self.assertEqual(completed.returncode, 1)
		self.assertIn("config must be a JSON object", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)

	def test_invalid_utf8_uses_the_structured_error_boundary(self) -> None:
		(self.state_dir / "config.json").write_bytes(b"\xff")
		completed = self.run_cli("poll")
		self.assertEqual(completed.returncode, 1)
		self.assertIn("persisted JSON is not valid UTF-8", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(json.loads(completed.stdout)["status"], "error")

	def test_invalid_command_output_utf8_uses_the_structured_error_boundary(self) -> None:
		completed = self.run_cli(
			"doctor", env_update={"FAKE_REMINDERS_INVALID_UTF8": "1"}
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("command output is not valid UTF-8", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(json.loads(completed.stdout)["status"], "error")

	def test_argparse_usage_error_uses_the_structured_error_boundary(self) -> None:
		completed = self.run_cli("submit", "--bad")
		self.assertEqual(completed.returncode, 1)
		self.assertIn("invalid command arguments", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(json.loads(completed.stdout)["status"], "error")
		result = json.loads(completed.stdout)
		self.assertEqual(result["status"], "error")
		self.assertEqual(result["error_category"], "contract_or_runtime")

	def test_configure_rejects_empty_binding_before_overwriting_config(self) -> None:
		config_path = self.state_dir / "config.json"
		before = config_path.read_text()
		completed = self.run_cli(
			"configure", "--list-id", "", "--list-name", "Agent Attention"
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("list ID must be nonempty text", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(config_path.read_text(), before)

	def test_poll_rejects_non_object_gate_mapping_before_deriving_event_id(self) -> None:
		(self.state_dir / "gates" / f"{REMINDER_ID}.json").write_text(
			"[]", encoding="utf-8"
		)
		completed = self.run_cli("poll")
		self.assertEqual(completed.returncode, 1)
		self.assertIn("gate mapping must be a JSON object", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)

	def test_poll_rejects_incomplete_gate_mapping_before_deriving_event_id(self) -> None:
		mapping = {**self.mapping}
		mapping.pop("approval_meaning")
		(self.state_dir / "gates" / f"{REMINDER_ID}.json").write_text(
			json.dumps(mapping), encoding="utf-8"
		)
		completed = self.run_cli("poll")
		self.assertEqual(completed.returncode, 1)
		self.assertIn("gate mapping approval_meaning must be nonempty text", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)

	def test_poll_rejects_non_object_inventory_entry(self) -> None:
		self.inventory_path.write_text(json.dumps([self.target, []]), encoding="utf-8")
		completed = self.run_cli("poll")
		self.assertEqual(completed.returncode, 1)
		self.assertIn("inventory entries must be JSON objects", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)

	def test_poll_rejects_non_text_and_duplicate_inventory_ids(self) -> None:
		for invalid_id, expected in (
			([], "must be nonempty text"),
			({}, "must be nonempty text"),
		):
			with self.subTest(invalid_id=invalid_id):
				self.inventory_path.write_text(
					json.dumps([self.target, {**self.other, "id": invalid_id}]),
					encoding="utf-8",
				)
				completed = self.run_cli("poll")
				self.assertEqual(completed.returncode, 1)
				self.assertIn(expected, completed.stderr)
				self.assertNotIn("Traceback", completed.stderr)

		self.inventory_path.write_text(
			json.dumps([self.target, {**self.other, "id": REMINDER_ID}]),
			encoding="utf-8",
		)
		completed = self.run_cli("poll")
		self.assertEqual(completed.returncode, 1)
		self.assertIn("reminder IDs must be unique", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)

	def test_outcome_preview_is_read_only_and_exact(self) -> None:
		result = self.result(
			self.run_cli(
				"record-outcome",
				"--reminder-id",
				REMINDER_ID,
				"--outcome",
				"Review-ready PR opened; local checks passed.",
				"--finished-at",
				FINISHED_AT,
			)
		)
		self.assertEqual(result["status"], "preview")
		self.assertFalse(result["changed"])
		self.assertEqual(result["reminder_id"], REMINDER_ID)
		self.assertEqual(
			self.calls(),
			[
				[
					"show",
					"completed",
					"--list-id",
					LIST_ID,
					"--json",
					"--no-input",
				]
			],
		)
		inventory = json.loads(self.inventory_path.read_text())
		target = next(item for item in inventory if item["id"] == REMINDER_ID)
		self.assertNotIn("Outcome:", target["notes"])

	def test_outcome_rejects_non_object_delivery_receipt(self) -> None:
		receipt_path = next((self.state_dir / "receipts").glob("*.json"))
		receipt_path.write_text("[]", encoding="utf-8")
		completed = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Should fail.",
			"--finished-at",
			FINISHED_AT,
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("delivery receipt must be a JSON object", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(self.calls(), [])

	def test_outcome_rejects_non_object_outcome_receipt(self) -> None:
		outcomes_dir = self.state_dir / "outcomes"
		outcomes_dir.mkdir()
		(outcomes_dir / f"{self._event_id()}.json").write_text("[]", encoding="utf-8")
		completed = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Should fail.",
			"--finished-at",
			FINISHED_AT,
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("outcome receipt must be a JSON object", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(self.calls(), [])

	def test_outcome_rejects_non_object_outcome_claim(self) -> None:
		claim_dir = self.state_dir / "outcome-claims"
		claim_dir.mkdir()
		(claim_dir / f"{self._event_id()}.json").write_text("[]", encoding="utf-8")
		completed = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Should fail.",
			"--finished-at",
			FINISHED_AT,
			"--execute",
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("outcome claim must be a JSON object", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(self.calls(), [])

	def test_outcome_rejects_path_like_reminder_id_before_mapping_lookup(self) -> None:
		malicious_id = f"../requests/{THREAD_ID}"
		request_dir = self.state_dir / "requests"
		request_dir.mkdir()
		(request_dir / f"{THREAD_ID}.json").write_text(
			json.dumps({**self.mapping, "reminder_id": malicious_id}), encoding="utf-8"
		)
		completed = self.run_cli(
			"record-outcome",
			"--reminder-id",
			malicious_id,
			"--outcome",
			"Should not resolve outside gate custody.",
			"--finished-at",
			FINISHED_AT,
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("reminder ID must be one opaque path segment", completed.stderr)

	def test_outcome_execute_updates_only_exact_completed_gate_once(self) -> None:
		arguments = (
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Review-ready PR opened; local checks passed.",
			"--finished-at",
			FINISHED_AT,
			"--execute",
		)
		first = self.result(self.run_cli(*arguments))
		self.assertEqual(first["status"], "recorded")
		self.assertTrue(first["changed"])
		inventory = json.loads(self.inventory_path.read_text())
		target = next(item for item in inventory if item["id"] == REMINDER_ID)
		other = next(item for item in inventory if item["id"] == OTHER_REMINDER_ID)
		self.assertTrue(target["isCompleted"])
		self.assertEqual(target["completionDate"], "2026-08-10T05:40:00Z")
		self.assertIn(
			(
				"Outcome: Review-ready PR opened; local checks passed.\n"
				f"Finished: {FINISHED_AT}"
			),
			target["notes"],
		)
		self.assertTrue(
			target["notes"].endswith(
				f"remindctl URL (managed): agent-attention://threads/{THREAD_ID}"
			)
		)
		self.assertEqual(other, self.other)
		outcome_receipts = list((self.state_dir / "outcomes").glob("*.json"))
		self.assertEqual(len(outcome_receipts), 1)
		audit_lines = (self.state_dir / "outcome-audit.jsonl").read_text().splitlines()
		self.assertEqual(len(audit_lines), 1)
		self.assertEqual(json.loads(audit_lines[0]), json.loads(outcome_receipts[0].read_text()))
		self.assertEqual(
			self.calls(),
			[
				["show", "completed", "--list-id", LIST_ID, "--json", "--no-input"],
				["edit", REMINDER_ID, "--notes", target["notes"], "--json", "--no-input"],
				["show", "completed", "--list-id", LIST_ID, "--json", "--no-input"],
			],
		)

		second = self.result(self.run_cli(*arguments))
		self.assertEqual(second["status"], "already_recorded")
		self.assertFalse(second["changed"])
		self.assertEqual(len([call for call in self.calls() if call[0] == "edit"]), 1)
		self.assertEqual(
			len((self.state_dir / "outcome-audit.jsonl").read_text().splitlines()), 1
		)

	def test_outcome_bounds_completed_reads_and_edit(self) -> None:
		before = {**self.target}
		after = {**before}

		def fake_run_json(command: list[str], **_: Any) -> Any:
			if command[1:3] == ["show", "completed"]:
				return [{**after}]
			if command[1] == "edit":
				after["notes"] = command[command.index("--notes") + 1]
				after["lastModifiedDate"] = "2026-08-10T05:45:01Z"
				return {**after}
			raise AssertionError(f"unexpected command: {command}")

		run_json = mock.Mock(side_effect=fake_run_json)
		with mock.patch.object(AGENT_ATTENTION, "run_json", run_json):
			result = AGENT_ATTENTION.record_outcome(
				AGENT_ATTENTION.argparse.Namespace(
					state_dir=self.state_dir,
					reminder_id=REMINDER_ID,
					outcome="Bound every outcome command.",
					finished_at=FINISHED_AT,
					execute=True,
				)
			)
		self.assertEqual(result["status"], "recorded")
		self.assertEqual(len(run_json.call_args_list), 3)
		for invocation in run_json.call_args_list:
			self.assertEqual(
				invocation.kwargs,
				{"timeout_seconds": AGENT_ATTENTION.REMINDCTL_COMMAND_TIMEOUT_SECONDS},
			)

	def test_outcome_rejects_a_second_terminal_result(self) -> None:
		first = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"First terminal result.",
			"--finished-at",
			FINISHED_AT,
			"--execute",
		)
		self.assertEqual(first.returncode, 0, first.stderr)
		second = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Different terminal result.",
			"--finished-at",
			FINISHED_AT,
			"--execute",
		)
		self.assertEqual(second.returncode, 1)
		self.assertIn("different terminal outcome", second.stderr)
		self.assertEqual(len([call for call in self.calls() if call[0] == "edit"]), 1)

	def test_outcome_unknown_result_recovers_by_exact_reread_without_second_edit(self) -> None:
		arguments = (
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Recovered terminal result.",
			"--finished-at",
			FINISHED_AT,
			"--execute",
		)
		unknown = self.run_cli(
			*arguments, env_update={"FAKE_REMINDERS_FAIL_AFTER_EDIT": "1"}
		)
		self.assertEqual(unknown.returncode, 1)
		self.assertIn("inspect current state before retry", unknown.stdout)

		recovered = self.result(self.run_cli(*arguments))
		self.assertEqual(recovered["status"], "already_recorded")
		self.assertEqual(len([call for call in self.calls() if call[0] == "edit"]), 1)
		receipt = json.loads(next((self.state_dir / "outcomes").glob("*.json")).read_text())
		self.assertTrue(receipt["recovered"])

	def test_existing_outcome_claim_suppresses_a_concurrent_edit(self) -> None:
		outcome = "Concurrent terminal result."
		claim_dir = self.state_dir / "outcome-claims"
		claim_dir.mkdir()
		(claim_dir / f"{self._event_id()}.json").write_text(
			json.dumps(
				{
					"event_id": self._event_id(),
					"finished_at": FINISHED_AT,
					"outcome": outcome,
					"outcome_id": self._outcome_id(outcome),
					"reminder_id": REMINDER_ID,
				}
			),
			encoding="utf-8",
		)
		result = self.result(
			self.run_cli(
				"record-outcome",
				"--reminder-id",
				REMINDER_ID,
				"--outcome",
				outcome,
				"--finished-at",
				FINISHED_AT,
				"--execute",
			)
		)
		self.assertEqual(result["status"], "claimed")
		self.assertEqual(
			self.calls(),
			[["show", "completed", "--list-id", LIST_ID, "--json", "--no-input"]],
		)

	def test_outcome_rejects_incomplete_gate(self) -> None:
		self.target["isCompleted"] = False
		self.target.pop("completionDate")
		self._write_inventory()
		completed = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Should fail.",
			"--finished-at",
			FINISHED_AT,
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("Completed history", completed.stderr)

	def test_outcome_pre_edit_failure_releases_owned_claim_for_retry(self) -> None:
		arguments = (
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Retryable terminal result.",
			"--finished-at",
			FINISHED_AT,
			"--execute",
		)
		self.target["isCompleted"] = False
		self.target.pop("completionDate")
		self._write_inventory()
		failed = self.run_cli(*arguments)
		self.assertEqual(failed.returncode, 1)
		self.assertEqual(list((self.state_dir / "outcome-claims").glob("*.json")), [])

		self.target["isCompleted"] = True
		self.target["completionDate"] = "2026-08-10T05:40:00Z"
		self._write_inventory()
		retried = self.result(self.run_cli(*arguments))
		self.assertEqual(retried["status"], "recorded")
		self.assertEqual(len([call for call in self.calls() if call[0] == "edit"]), 1)

	def test_outcome_releases_owned_claim_when_edit_never_starts(self) -> None:
		arguments = (
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Retry after edit launch failure.",
			"--finished-at",
			FINISHED_AT,
			"--execute",
		)
		python_bin = self.root / "python-bin"
		python_bin.mkdir()
		(python_bin / "python3").symlink_to(sys.executable)
		failed = self.run_cli(
			*arguments,
			env_update={
				"FAKE_REMINDERS_REMOVE_AFTER_COMPLETED": "1",
				"PATH": f"{self.bin_dir}:{python_bin}:/usr/bin",
			},
		)
		self.assertEqual(failed.returncode, 1)
		self.assertIn("No such file or directory", failed.stderr)
		self.assertEqual(list((self.state_dir / "outcome-claims").glob("*.json")), [])

		self._write_fake_remindctl()
		retried = self.result(self.run_cli(*arguments))
		self.assertEqual(retried["status"], "recorded")
		self.assertEqual(len([call for call in self.calls() if call[0] == "edit"]), 1)

	def test_outcome_rejects_missing_delivery_receipt(self) -> None:
		for path in (self.state_dir / "receipts").glob("*.json"):
			path.unlink()
		completed = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Should fail.",
			"--finished-at",
			FINISHED_AT,
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("delivery receipt", completed.stderr)

	def test_outcome_rejects_delivery_receipt_for_a_different_task(self) -> None:
		receipt_path = next((self.state_dir / "receipts").glob("*.json"))
		receipt = json.loads(receipt_path.read_text())
		receipt["thread_id"] = "33333333-3333-4333-8333-333333333333"
		receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
		completed = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Should fail.",
			"--finished-at",
			FINISHED_AT,
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("does not match gate field: thread_id", completed.stderr)
		self.assertEqual(self.calls(), [])

	def test_outcome_rejects_multiline_history(self) -> None:
		completed = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"First line.\nSecond line.",
			"--finished-at",
			FINISHED_AT,
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("one concise line", completed.stderr)
		self.assertEqual(self.calls(), [])

	def test_submit_admits_one_gate_with_one_alert_and_suppresses_duplicate(self) -> None:
		preview = self.result(self.run_cli(*self.submit_arguments()))
		self.assertEqual(preview["status"], "admitted_preview")
		self.assertFalse(preview["changed"])
		self.assertEqual(self.calls(), [])
		self.assertEqual(preview["preview"]["priority"], "none")

		arguments = (*self.submit_arguments(), "--execute")
		first = self.result(self.run_cli(*arguments))
		self.assertEqual(first["status"], "gated")
		self.assertEqual(first["notification_count"], 1)
		add_calls = [call for call in self.calls() if call[0] == "add"]
		self.assertEqual(len(add_calls), 1)
		self.assertIn("--alarm", add_calls[0])
		self.assertNotIn("--due", add_calls[0])
		self.assertEqual(add_calls[0][add_calls[0].index("--priority") + 1], "none")
		inventory = json.loads(self.inventory_path.read_text())
		self.assertEqual(next(item for item in inventory if item["id"] == REMINDER_ID), self.target)
		self.assertEqual(next(item for item in inventory if item["id"] == OTHER_REMINDER_ID), self.other)
		self.assertEqual(len([item for item in inventory if item["id"] == NEW_REMINDER_ID]), 1)

		second = self.result(self.run_cli(*arguments))
		self.assertEqual(second["status"], "already_gated")
		self.assertFalse(second["changed"])
		self.assertEqual(len([call for call in self.calls() if call[0] == "add"]), 1)

	def test_completed_task_may_open_one_later_distinct_gate(self) -> None:
		first = self.result(
			self.run_cli(*self.submit_arguments(), "--execute")
		)
		request_path = self.state_dir / "requests" / f"{THREAD_ID}.json"
		request = json.loads(request_path.read_text())
		request["status"] = "completed"
		request_path.write_text(json.dumps(request), encoding="utf-8")

		second = self.result(
			self.run_cli(
				*self.submit_arguments(
					action="Approve later local router test",
					recommendation="Approve the later bounded local router test.",
					approval_meaning="Approve the later bounded local router test only.",
				),
				"--execute",
				env_update={
					"FAKE_REMINDERS_NEW_ID": "44444444-4444-4444-8444-444444444444"
				},
			)
		)

		self.assertEqual(first["status"], "gated")
		self.assertEqual(second["status"], "gated")
		self.assertEqual(len([call for call in self.calls() if call[0] == "add"]), 2)

	def test_submit_rejects_multi_choice_and_records_actionable_repair(self) -> None:
		result = self.result(
			self.run_cli(
				*self.submit_arguments(decision_type="multi_choice"),
				"--execute",
			)
		)
		self.assertEqual(result["status"], "rejected")
		self.assertIn("multi-choice", result["repair"])
		self.assertEqual(self.calls(), [])
		stop = self.result(self.run_cli("check-stop", "--thread-id", THREAD_ID))
		self.assertEqual(stop["status"], "repair")
		self.assertEqual(stop["hook_action"], "allow")

	def test_submit_rejects_information_updates_and_non_blockers(self) -> None:
		for overrides, expected in (
			({"decision_type": "information"}, "decision_type"),
			({"unblocks_paused_task": False}, "paused owning task"),
			({"discussion_link": "agent-attention://threads/wrong"}, "exact owning"),
		):
			with self.subTest(overrides=overrides):
				result = self.result(self.run_cli(*self.submit_arguments(**overrides)))
				self.assertEqual(result["status"], "rejected")
				self.assertIn(expected, result["repair"])
		self.assertEqual(self.calls(), [])

	def test_existing_submit_claim_suppresses_a_concurrent_gate_and_alert(self) -> None:
		claim_dir = self.state_dir / "request-locks"
		claim_dir.mkdir()
		lock_path = claim_dir / f"{THREAD_ID}.json"
		lock_path.write_text(
			json.dumps({"thread_id": THREAD_ID, "request_id": "winner"}),
			encoding="utf-8",
		)
		with lock_path.open("r+") as lock_handle:
			fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
			result = self.result(
				self.run_cli(*self.submit_arguments(), "--execute")
			)
		self.assertEqual(result["status"], "claimed")
		self.assertFalse(result["changed"])
		self.assertEqual(self.calls(), [])

	def test_submit_recovers_request_lock_abandoned_before_creation(self) -> None:
		claim_dir = self.state_dir / "request-locks"
		claim_dir.mkdir()
		lock_path = claim_dir / f"{THREAD_ID}.json"
		lock_path.write_text(
			json.dumps({"thread_id": THREAD_ID, "request_id": "abandoned"}),
			encoding="utf-8",
		)
		lock_inode = lock_path.stat().st_ino
		result = self.result(self.run_cli(*self.submit_arguments(), "--execute"))
		self.assertEqual(result["status"], "gated")
		self.assertTrue(lock_path.exists())
		self.assertEqual(lock_path.stat().st_ino, lock_inode)
		self.assertEqual(len([call for call in self.calls() if call[0] == "add"]), 1)

	def test_submit_bounds_remindctl_add_while_request_lock_is_held(self) -> None:
		created_gate: dict[str, Any] = {}

		def fake_run_json(command: list[str], **_: Any) -> Any:
			created_gate.update(
				{
					"id": NEW_REMINDER_ID,
					"listID": command[command.index("--list-id") + 1],
					"title": command[command.index("--title") + 1],
					"notes": command[command.index("--notes") + 1],
					"url": command[command.index("--url") + 1],
					"priority": command[command.index("--priority") + 1],
					"isCompleted": False,
				}
			)
			return {"id": NEW_REMINDER_ID}

		args = AGENT_ATTENTION.parser().parse_args(
			["--state-dir", str(self.state_dir), *self.submit_arguments(), "--execute"]
		)
		run_json = mock.Mock(side_effect=fake_run_json)
		read_inventory = mock.Mock(side_effect=lambda _config, **_: [{**created_gate}])
		with (
			mock.patch.object(AGENT_ATTENTION, "run_json", run_json),
			mock.patch.object(AGENT_ATTENTION, "read_inventory", read_inventory),
		):
			result = AGENT_ATTENTION.submit_approval(args)
		self.assertEqual(result["status"], "gated")
		self.assertEqual(run_json.call_count, 1)
		self.assertEqual(
			run_json.call_args.kwargs,
			{"timeout_seconds": AGENT_ATTENTION.REMINDCTL_COMMAND_TIMEOUT_SECONDS},
		)
		read_inventory.assert_called_once_with(
			{"version": 1, "list": self.mapping["list"]},
			timeout_seconds=AGENT_ATTENTION.REMINDCTL_COMMAND_TIMEOUT_SECONDS,
		)

	def test_submit_reclaims_claim_abandoned_before_request_declaration(self) -> None:
		arguments = self.submit_arguments()
		preview = self.result(self.run_cli(*arguments))
		claim_dir = self.state_dir / "request-claims"
		claim_dir.mkdir()
		(claim_dir / f"{preview['request_id']}.json").write_text(
			json.dumps(
				{
					"request_id": preview["request_id"],
					"thread_id": THREAD_ID,
				}
			),
			encoding="utf-8",
		)

		result = self.result(self.run_cli(*arguments, "--execute"))
		self.assertEqual(result["status"], "gated")
		self.assertEqual(len([call for call in self.calls() if call[0] == "add"]), 1)

	def test_submit_reclaims_truncated_pre_declaration_claim(self) -> None:
		arguments = self.submit_arguments()
		preview = self.result(self.run_cli(*arguments))
		claim_dir = self.state_dir / "request-claims"
		claim_dir.mkdir()
		(claim_dir / f"{preview['request_id']}.json").write_text("{", encoding="utf-8")

		result = self.result(self.run_cli(*arguments, "--execute"))
		self.assertEqual(result["status"], "gated")
		self.assertEqual(len([call for call in self.calls() if call[0] == "add"]), 1)

	def test_submit_reconciles_mapping_published_before_request_update(self) -> None:
		arguments = self.submit_arguments()
		first = self.result(self.run_cli(*arguments, "--execute"))
		request_path = self.state_dir / "requests" / f"{THREAD_ID}.json"
		request = json.loads(request_path.read_text())
		request["status"] = "declared"
		request.pop("reminder_id")
		request_path.write_text(json.dumps(request), encoding="utf-8")

		polled = self.result(self.run_cli("poll"))
		self.assertEqual(polled["status"], "waiting")
		reconciled = json.loads(request_path.read_text())
		self.assertEqual(reconciled["status"], "gated")
		self.assertEqual(reconciled["reminder_id"], first["reminder_id"])

		retried = self.result(self.run_cli(*arguments, "--execute"))
		self.assertEqual(retried["status"], "already_gated")
		self.assertEqual(retried["reminder_id"], first["reminder_id"])
		self.assertEqual(len([call for call in self.calls() if call[0] == "add"]), 1)

	def test_submit_blocks_distinct_intent_while_declared_attempt_is_unresolved(self) -> None:
		request_dir = self.state_dir / "requests"
		request_dir.mkdir()
		(request_dir / f"{THREAD_ID}.json").write_text(
			json.dumps(
				{
					"version": 1,
					"request_id": "0" * 64,
					"thread_id": THREAD_ID,
					"status": "declared",
				}
			),
			encoding="utf-8",
		)
		completed = self.run_cli(
			*self.submit_arguments(action="Approve a different action"),
			"--execute",
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("unresolved gate creation attempt", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(self.calls(), [])

	def test_failed_submit_releases_the_per_thread_request_lock(self) -> None:
		completed = self.run_cli(
			*self.submit_arguments(),
			"--execute",
			env_update={"FAKE_REMINDERS_NEW_ID": ""},
		)
		self.assertEqual(completed.returncode, 1)
		self.assertTrue(
			(self.state_dir / "request-locks" / f"{THREAD_ID}.json").exists()
		)

	def test_audit_file_is_private_before_the_first_write(self) -> None:
		path = self.state_dir / "audit-mode-test.jsonl"
		real_fdopen = os.fdopen
		modes_before_write: list[int] = []

		def checked_fdopen(descriptor: int, *args: Any, **kwargs: Any) -> Any:
			modes_before_write.append(stat.S_IMODE(os.fstat(descriptor).st_mode))
			return real_fdopen(descriptor, *args, **kwargs)

		previous_umask = os.umask(0)
		try:
			with mock.patch.object(AGENT_ATTENTION.os, "fdopen", side_effect=checked_fdopen):
				AGENT_ATTENTION.append_audit(path, {"event": "bounded-test"})
		finally:
			os.umask(previous_umask)
		self.assertEqual(modes_before_write, [0o600])
		self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

	def test_audit_rejects_symlinks_and_multiply_linked_files(self) -> None:
		target = self.state_dir / "audit-target.jsonl"
		target.parent.mkdir(parents=True, exist_ok=True)
		target.write_text("sentinel\n", encoding="utf-8")
		symlink = self.state_dir / "audit-symlink.jsonl"
		symlink.symlink_to(target)
		with self.assertRaises(OSError):
			AGENT_ATTENTION.append_audit(symlink, {"event": "must-not-write"})
		self.assertEqual(target.read_text(encoding="utf-8"), "sentinel\n")

		hardlink = self.state_dir / "audit-hardlink.jsonl"
		os.link(target, hardlink)
		with self.assertRaisesRegex(
			AGENT_ATTENTION.ContractError, "singly linked regular file"
		):
			AGENT_ATTENTION.append_audit(hardlink, {"event": "must-not-write"})
		self.assertEqual(target.read_text(encoding="utf-8"), "sentinel\n")

	def test_submit_releases_owned_claim_when_remindctl_never_starts(self) -> None:
		missing_bin = self.root / "missing-bin"
		missing_bin.mkdir()
		arguments = (*self.submit_arguments(), "--execute")
		failed = self.run_cli(*arguments, env_update={"PATH": str(missing_bin)})
		self.assertEqual(failed.returncode, 1)
		self.assertIn("No such file or directory", failed.stderr)
		self.assertEqual(list((self.state_dir / "request-claims").glob("*.json")), [])
		request = json.loads(
			(self.state_dir / "requests" / f"{THREAD_ID}.json").read_text()
		)
		self.assertEqual(request["status"], "repair")

		retried = self.result(self.run_cli(*arguments))
		self.assertEqual(retried["status"], "gated")
		self.assertEqual(len([call for call in self.calls() if call[0] == "add"]), 1)

	def test_submit_rejects_path_like_created_reminder_id_before_mapping_write(self) -> None:
		completed = self.run_cli(
			*self.submit_arguments(),
			"--execute",
			env_update={"FAKE_REMINDERS_NEW_ID": "../unexpected"},
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("reminder ID must be one opaque path segment", completed.stderr)
		self.assertFalse((self.state_dir / "unexpected.json").exists())
		self.assertEqual(
			[path.name for path in (self.state_dir / "gates").glob("*.json")],
			[f"{REMINDER_ID}.json"],
		)
		request = json.loads(
			(self.state_dir / "requests" / f"{THREAD_ID}.json").read_text()
		)
		self.assertEqual(request["status"], "repair")

	def test_submit_rejects_non_text_created_notes_without_traceback(self) -> None:
		completed = self.run_cli(
			*self.submit_arguments(),
			"--execute",
			env_update={"FAKE_REMINDERS_NEW_NOTES_JSON": '{"unexpected": true}'},
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("created reminder failed exact verification: notes", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		request = json.loads(
			(self.state_dir / "requests" / f"{THREAD_ID}.json").read_text()
		)
		self.assertEqual(request["status"], "repair")
		self.assertEqual(len([call for call in self.calls() if call[0] == "add"]), 1)

	def test_submit_persists_stable_id_when_post_add_inventory_is_malformed(self) -> None:
		completed = self.run_cli(
			*self.submit_arguments(),
			"--execute",
			env_update={"FAKE_REMINDERS_INVALID_SHOW_JSON": "1"},
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("command returned invalid JSON", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		request = json.loads(
			(self.state_dir / "requests" / f"{THREAD_ID}.json").read_text()
		)
		self.assertEqual(request["status"], "repair")
		self.assertEqual(request["reminder_id"], NEW_REMINDER_ID)
		self.assertIn("could not be verified", request["repair"])
		self.assertEqual(len([call for call in self.calls() if call[0] == "add"]), 1)

	def test_submit_requires_literal_false_created_completion_state(self) -> None:
		completed = self.run_cli(
			*self.submit_arguments(),
			"--execute",
			env_update={"FAKE_REMINDERS_NEW_COMPLETION_JSON": "0"},
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn(
			"created reminder failed exact verification: isCompleted",
			completed.stderr,
		)
		self.assertNotIn("Traceback", completed.stderr)

	def test_submit_rejects_non_object_request_state_without_traceback(self) -> None:
		request_dir = self.state_dir / "requests"
		request_dir.mkdir()
		(request_dir / f"{THREAD_ID}.json").write_text("[]", encoding="utf-8")
		completed = self.run_cli(*self.submit_arguments())
		self.assertEqual(completed.returncode, 1)
		self.assertIn("request state must be a JSON object", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(self.calls(), [])

	def test_stop_check_continues_declared_or_delivered_state_without_reading_prose(self) -> None:
		request_dir = self.state_dir / "requests"
		request_dir.mkdir()
		path = request_dir / f"{THREAD_ID}.json"
		path.write_text(
			json.dumps(
				{
					"version": 1,
					"thread_id": THREAD_ID,
					"status": "declared",
					"intent": {"continuation": "Run the exact continuation."},
				}
			),
			encoding="utf-8",
		)
		declared = self.result(self.run_cli("check-stop", "--thread-id", THREAD_ID))
		self.assertEqual(declared["hook_action"], "continue")
		self.assertNotIn("assistant", json.dumps(declared).casefold())

		state = json.loads(path.read_text())
		state["status"] = "delivered"
		path.write_text(json.dumps(state), encoding="utf-8")
		delivered = self.result(self.run_cli("check-stop", "--thread-id", THREAD_ID))
		self.assertEqual(delivered["hook_action"], "continue")
		self.assertIn("Run the exact continuation", delivered["reason"])

	def test_stop_check_rejects_non_object_request_state_without_traceback(self) -> None:
		request_dir = self.state_dir / "requests"
		request_dir.mkdir()
		(request_dir / f"{THREAD_ID}.json").write_text("[]", encoding="utf-8")
		completed = self.run_cli("check-stop", "--thread-id", THREAD_ID)
		result = self.result(completed)
		self.assertEqual(result["status"], "repair_needed")
		self.assertEqual(result["hook_action"], "continue")
		self.assertIn("owner state is malformed", result["reason"])
		self.assertNotIn("Traceback", completed.stderr)

	def test_stop_check_rejects_non_object_delivered_intent_without_traceback(self) -> None:
		request_dir = self.state_dir / "requests"
		request_dir.mkdir()
		(request_dir / f"{THREAD_ID}.json").write_text(
			json.dumps(
				{
					"version": 1,
					"thread_id": THREAD_ID,
					"status": "delivered",
					"intent": [],
				}
			),
			encoding="utf-8",
		)
		completed = self.run_cli("check-stop", "--thread-id", THREAD_ID)
		result = self.result(completed)
		self.assertEqual(result["status"], "repair_needed")
		self.assertEqual(result["hook_action"], "continue")
		self.assertIn("owner state is malformed", result["reason"])
		self.assertNotIn("Traceback", completed.stderr)

	def test_watch_detects_and_records_delivery_under_fifteen_seconds(self) -> None:
		self.target["isCompleted"] = False
		self.target.pop("completionDate")
		self._write_inventory()
		for path in (self.state_dir / "receipts").glob("*.json"):
			path.unlink()
		result = self.result(
			self.run_cli(
				"watch",
				"--interval-seconds",
				"0.05",
				"--timeout-seconds",
				"1",
				env_update={"FAKE_REMINDERS_COMPLETE_AFTER_POLLS": "2"},
			)
		)
		self.assertEqual(result["status"], "deliver")
		self.assertEqual(result["poll_count"], 2)
		self.assertLess(result["detection_latency_seconds"], 15)
		recorded = self.result(
			self.run_cli(
				"record-delivery",
				"--event-id",
				result["event_id"],
				"--tool-result",
				json.dumps({"threadId": THREAD_ID}),
			)
		)
		self.assertEqual(recorded["status"], "recorded")
		completion = datetime.fromisoformat(result["completion_date"])
		self.assertLess((datetime.now(timezone.utc) - completion).total_seconds(), 15)
		duplicate = self.result(self.run_cli("poll"))
		self.assertEqual(duplicate["status"], "waiting")
		self.assertEqual(
			len((self.state_dir / "audit.jsonl").read_text().splitlines()), 1
		)

	def test_watch_bounds_a_hung_remindctl_call(self) -> None:
		started = time.monotonic()
		completed = self.run_cli(
			"watch",
			"--interval-seconds",
			"0.05",
			"--timeout-seconds",
			"0.2",
			env_update={"FAKE_REMINDERS_HANG_SHOW_SECONDS": "2"},
		)
		self.assertEqual(completed.returncode, 1)
		self.assertLess(time.monotonic() - started, 1.9)
		self.assertIn("bounded execution window", completed.stderr)

	def test_watch_rejects_non_finite_durations_without_traceback(self) -> None:
		for flag, value, expected_error in (
			("--interval-seconds", "nan", "interval-seconds"),
			("--interval-seconds", "inf", "interval-seconds"),
			("--timeout-seconds", "nan", "timeout-seconds"),
			("--timeout-seconds", "inf", "timeout-seconds"),
		):
			with self.subTest(flag=flag, value=value):
				started = time.monotonic()
				completed = self.run_cli("watch", flag, value)
				self.assertEqual(completed.returncode, 1)
				self.assertLess(time.monotonic() - started, 1)
				self.assertIn(expected_error, completed.stderr)
				self.assertNotIn("Traceback", completed.stderr)
				self.assertEqual(json.loads(completed.stdout)["status"], "error")
				self.assertEqual(self.calls(), [])

	def test_poll_repairs_invalid_completion_timestamp_before_claiming(self) -> None:
		for path in (self.state_dir / "receipts").glob("*.json"):
			path.unlink()
		self.target["completionDate"] = "2026-08-10T05:40:00"
		self._write_inventory()
		completed = self.run_cli("poll")
		result = self.result(completed)
		self.assertEqual(result["status"], "waiting")
		self.assertEqual(list((self.state_dir / "claims").glob("*.json")), [])
		mapping = json.loads(
			(self.state_dir / "gates" / f"{REMINDER_ID}.json").read_text()
		)
		self.assertEqual(mapping["status"], "repair")
		self.assertIn("completionDate must include a timezone", mapping["repair"])
		self.assertNotIn("Traceback", completed.stderr)

	def test_poll_rejects_malformed_or_mismatched_existing_receipt(self) -> None:
		receipt_path = next((self.state_dir / "receipts").glob("*.json"))
		for receipt, expected_error in (
			("{", "Expecting property name"),
			(
				json.dumps(
					{
						"event_id": self._event_id(),
						"reminder_id": REMINDER_ID,
						"thread_id": OTHER_REMINDER_ID,
						"approval_meaning": APPROVAL_MEANING,
						"delivered_at": "2026-08-10T05:41:00Z",
					}
				),
				"does not match gate field: thread_id",
			),
			(
				json.dumps(
					{
						"event_id": self._event_id(),
						"reminder_id": REMINDER_ID,
						"thread_id": THREAD_ID,
						"approval_meaning": APPROVAL_MEANING,
						"delivered_at": "not-a-timestamp",
					}
				),
				"delivery receipt delivered_at must be an ISO 8601 timestamp",
			),
		):
			with self.subTest(expected_error=expected_error):
				receipt_path.write_text(receipt, encoding="utf-8")
				completed = self.run_cli("poll")
				self.assertEqual(completed.returncode, 1)
				self.assertIn(expected_error, completed.stderr)
				self.assertNotIn("Traceback", completed.stderr)
				self.assertEqual(list((self.state_dir / "claims").glob("*.json")), [])

	def test_poll_repairs_non_boolean_completion_without_claiming(self) -> None:
		for path in (self.state_dir / "receipts").glob("*.json"):
			path.unlink()
		for completion_state in ("false", 1, None):
			with self.subTest(completion_state=completion_state):
				self.target["isCompleted"] = completion_state
				self._write_inventory()
				completed = self.run_cli("poll")
				result = self.result(completed)
				self.assertEqual(result["status"], "waiting")
				self.assertEqual(list((self.state_dir / "claims").glob("*.json")), [])
				mapping = json.loads(
					(self.state_dir / "gates" / f"{REMINDER_ID}.json").read_text()
				)
				self.assertEqual(mapping["status"], "repair")
				self.assertIn("isCompleted must be a JSON boolean", mapping["repair"])
				self.assertNotIn("Traceback", completed.stderr)

	def test_poll_reconciles_request_state_from_existing_delivery_receipt(self) -> None:
		request_dir = self.state_dir / "requests"
		request_dir.mkdir()
		request_path = request_dir / f"{THREAD_ID}.json"
		request_path.write_text(
			json.dumps(
				{
					"version": 1,
					"request_id": "existing-request",
					"thread_id": THREAD_ID,
					"reminder_id": REMINDER_ID,
					"intent": {"continuation": "Resume exact work."},
					"status": "gated",
				}
			),
			encoding="utf-8",
		)
		result = self.result(self.run_cli("poll"))
		self.assertEqual(result["status"], "waiting")
		request = json.loads(request_path.read_text())
		self.assertEqual(request["status"], "delivered")
		self.assertEqual(request["event_id"], self._event_id())
		self.assertEqual(request["delivered_at"], "2026-08-10T05:41:00Z")

	def test_poll_never_demotes_completed_request_from_existing_delivery_receipt(self) -> None:
		request_dir = self.state_dir / "requests"
		request_dir.mkdir()
		request_path = request_dir / f"{THREAD_ID}.json"
		request_path.write_text(
			json.dumps(
				{
					"version": 1,
					"request_id": "0" * 64,
					"thread_id": THREAD_ID,
					"reminder_id": REMINDER_ID,
					"status": "completed",
					"outcome_id": "1" * 64,
				}
			),
			encoding="utf-8",
		)

		result = self.result(self.run_cli("poll"))
		self.assertEqual(result["status"], "waiting")
		request = json.loads(request_path.read_text())
		self.assertEqual(request["status"], "completed")
		self.assertEqual(request["outcome_id"], "1" * 64)

	def test_outcome_rejects_truthy_non_boolean_completion(self) -> None:
		self.target["isCompleted"] = "false"
		self._write_inventory()
		completed = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Must not record.",
			"--finished-at",
			FINISHED_AT,
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("already completed reminder", completed.stderr)
		self.assertEqual([call[0] for call in self.calls()], ["show"])

	def test_outcome_rejects_non_text_notes_and_releases_owned_claim(self) -> None:
		self.target["notes"] = {"unexpected": "shape"}
		self._write_inventory()
		completed = self.run_cli(
			"record-outcome",
			"--reminder-id",
			REMINDER_ID,
			"--outcome",
			"Must not record.",
			"--finished-at",
			FINISHED_AT,
			"--execute",
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("reminder notes must be text", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(list((self.state_dir / "outcome-claims").glob("*.json")), [])

	def test_poll_records_repair_for_one_broken_gate_and_delivers_the_next(self) -> None:
		for path in (self.state_dir / "receipts").glob("*.json"):
			path.unlink()
		later_meaning = "Approve the later bounded gate only."
		later_mapping = {
			**self.mapping,
			"reminder_id": OTHER_REMINDER_ID,
			"expected_title": "[APPROVE] Later bounded gate",
			"required_notes_line": f"Approval meaning: {later_meaning}",
			"approval_meaning": later_meaning,
		}
		(self.state_dir / "gates" / f"{OTHER_REMINDER_ID}.json").write_text(
			json.dumps(later_mapping), encoding="utf-8"
		)
		self.other.update(
			{
				"title": later_mapping["expected_title"],
				"notes": later_mapping["required_notes_line"],
				"isCompleted": True,
				"completionDate": "2026-08-10T05:50:00Z",
			}
		)
		self.inventory_path.write_text(json.dumps([self.other]), encoding="utf-8")

		result = self.result(self.run_cli("poll"))
		self.assertEqual(result["status"], "deliver")
		self.assertIn(later_meaning, result["prompt"])
		broken = json.loads(
			(self.state_dir / "gates" / f"{REMINDER_ID}.json").read_text()
		)
		self.assertEqual(broken["status"], "repair")
		self.assertIn(REMINDER_ID, broken["repair"])

	def test_poll_preserves_stale_claim_and_delivers_a_later_gate(self) -> None:
		for path in (self.state_dir / "receipts").glob("*.json"):
			path.unlink()
		claim_dir = self.state_dir / "claims"
		claim_dir.mkdir()
		(claim_dir / f"{self._event_id()}.json").write_text("{}", encoding="utf-8")
		later_meaning = "Approve the later bounded gate only."
		later_mapping = {
			**self.mapping,
			"reminder_id": OTHER_REMINDER_ID,
			"expected_title": "[APPROVE] Later bounded gate",
			"required_notes_line": f"Approval meaning: {later_meaning}",
			"approval_meaning": later_meaning,
		}
		(self.state_dir / "gates" / f"{OTHER_REMINDER_ID}.json").write_text(
			json.dumps(later_mapping), encoding="utf-8"
		)
		self.other.update(
			{
				"title": later_mapping["expected_title"],
				"notes": later_mapping["required_notes_line"],
				"isCompleted": True,
				"completionDate": "2026-08-10T05:50:00Z",
			}
		)
		self._write_inventory()

		result = self.result(self.run_cli("poll"))
		self.assertEqual(result["status"], "deliver")
		self.assertIn(later_meaning, result["prompt"])
		self.assertTrue((claim_dir / f"{self._event_id()}.json").exists())

	def test_doctor_bounds_remindctl_and_rejects_non_object_json(self) -> None:
		run_json = mock.Mock(return_value=[])
		with mock.patch.object(AGENT_ATTENTION, "run_json", run_json):
			with self.assertRaises(AGENT_ATTENTION.ContractError):
				AGENT_ATTENTION.doctor(
					AGENT_ATTENTION.argparse.Namespace(state_dir=self.state_dir)
				)
		run_json.assert_called_once_with(
			["remindctl", "doctor", "--for-agent", "--json"],
			timeout_seconds=30,
		)

	def test_doctor_rejects_malformed_link_handler_plist_without_traceback(self) -> None:
		home = self.root / "home"
		info_path = home / "Applications" / "Agent Attention Link.app" / "Contents" / "Info.plist"
		info_path.parent.mkdir(parents=True)
		info_path.write_text("truncated", encoding="utf-8")
		completed = self.run_cli("doctor", env_update={"HOME": str(home)})
		self.assertEqual(completed.returncode, 1)
		self.assertIn("Info.plist is malformed", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(json.loads(completed.stdout)["status"], "error")

	def test_doctor_rejects_malformed_link_handler_plist_shape(self) -> None:
		home = self.root / "home"
		info_path = home / "Applications" / "Agent Attention Link.app" / "Contents" / "Info.plist"
		info_path.parent.mkdir(parents=True)
		with info_path.open("wb") as handle:
			plistlib.dump({"CFBundleURLTypes": [[]]}, handle)
		completed = self.run_cli("doctor", env_update={"HOME": str(home)})
		self.assertEqual(completed.returncode, 1)
		self.assertIn("Info.plist URL types are malformed", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		self.assertEqual(json.loads(completed.stdout)["status"], "error")

	def test_doctor_requires_the_plist_selected_executable_for_readiness(self) -> None:
		home = self.root / "home"
		handler_path = home / "Applications" / "Agent Attention Link.app"
		info_path = handler_path / "Contents" / "Info.plist"
		info_path.parent.mkdir(parents=True)
		with info_path.open("wb") as handle:
			plistlib.dump(
				{
					"CFBundleExecutable": "AgentAttentionLink",
					"CFBundleURLTypes": [
						{"CFBundleURLSchemes": ["agent-attention"]}
					],
				},
				handle,
			)
		missing = self.result(self.run_cli("doctor", env_update={"HOME": str(home)}))
		self.assertEqual(missing["status"], "repair_needed")
		self.assertFalse(missing["link_handler"]["installed"])

		executable = handler_path / "Contents" / "MacOS" / "AgentAttentionLink"
		executable.parent.mkdir()
		executable.write_text("#!/bin/sh\n", encoding="utf-8")
		executable.chmod(0o644)
		non_executable = self.result(
			self.run_cli("doctor", env_update={"HOME": str(home)})
		)
		self.assertEqual(non_executable["status"], "repair_needed")
		self.assertFalse(non_executable["link_handler"]["installed"])

		executable.chmod(0o755)
		ready = self.result(self.run_cli("doctor", env_update={"HOME": str(home)}))
		self.assertEqual(ready["status"], "ready")
		self.assertTrue(ready["link_handler"]["installed"])

	def test_record_delivery_accepts_codex_exact_task_result(self) -> None:
		claim_dir = self.state_dir / "claims"
		claim_dir.mkdir()
		identifier = self._event_id()
		receipt_path = self.state_dir / "receipts" / f"{identifier}.json"
		receipt_path.unlink()
		(claim_dir / f"{identifier}.json").write_text(
			json.dumps(
				{
					"event_id": identifier,
					"reminder_id": REMINDER_ID,
					"thread_id": THREAD_ID,
					"approval_meaning": APPROVAL_MEANING,
				}
			),
			encoding="utf-8",
		)

		result = self.result(
			self.run_cli(
				"record-delivery",
				"--event-id",
				identifier,
				"--tool-result",
				json.dumps({"threadId": THREAD_ID}),
			)
		)

		self.assertEqual(result["status"], "recorded")
		self.assertEqual(
			json.loads(receipt_path.read_text())["tool_result"],
			{"threadId": THREAD_ID},
		)

	def test_record_delivery_rejects_invalid_event_ids_and_unbound_proof(self) -> None:
		for invalid_id in ("../requests/forged", "A" * 64, "0" * 63):
			with self.subTest(event_id=invalid_id):
				completed = self.run_cli(
					"record-delivery",
					"--event-id",
					invalid_id,
					"--tool-result",
					'{"delivered":true}',
				)
				self.assertEqual(completed.returncode, 1)
				self.assertIn("64 lowercase hexadecimal", completed.stderr)

		claim_dir = self.state_dir / "claims"
		claim_dir.mkdir()
		identifier = self._event_id()
		(self.state_dir / "receipts" / f"{identifier}.json").unlink()
		(claim_dir / f"{identifier}.json").write_text(
			json.dumps(
				{
					"event_id": identifier,
					"reminder_id": REMINDER_ID,
					"thread_id": THREAD_ID,
					"approval_meaning": APPROVAL_MEANING,
				}
			),
			encoding="utf-8",
		)
		for tool_result in (
			'{"delivered":true}',
			json.dumps({"threadId": OTHER_THREAD_ID}),
			json.dumps({"thread_id": THREAD_ID}),
			'[]',
		):
			with self.subTest(tool_result=tool_result):
				completed = self.run_cli(
					"record-delivery",
					"--event-id",
					identifier,
					"--tool-result",
					tool_result,
				)
				self.assertEqual(completed.returncode, 1)
				self.assertIn("does not confirm exact task delivery", completed.stderr)

	def test_record_delivery_rejects_incomplete_existing_receipt_before_reconciliation(self) -> None:
		request_dir = self.state_dir / "requests"
		request_dir.mkdir()
		request_path = request_dir / f"{THREAD_ID}.json"
		request_path.write_text(
			json.dumps(
				{
					"version": 1,
					"request_id": "existing-request",
					"thread_id": THREAD_ID,
					"reminder_id": REMINDER_ID,
					"intent": {"continuation": "Resume exact work."},
					"status": "gated",
				}
			),
			encoding="utf-8",
		)
		receipt_path = next((self.state_dir / "receipts").glob("*.json"))
		receipt = json.loads(receipt_path.read_text())
		receipt.pop("delivered_at")
		receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
		completed = self.run_cli(
			"record-delivery",
			"--event-id",
			self._event_id(),
			"--tool-result",
			'{"delivered":true}',
		)
		self.assertEqual(completed.returncode, 1)
		self.assertIn("delivery receipt delivered_at", completed.stderr)
		self.assertNotIn("Traceback", completed.stderr)
		request = json.loads(request_path.read_text())
		self.assertEqual(request["status"], "gated")
		self.assertNotIn("delivered_at", request)

	def test_delivered_historical_gate_may_be_human_deleted_without_blocking_poll(self) -> None:
		self.inventory_path.write_text(json.dumps([self.other]), encoding="utf-8")
		result = self.result(self.run_cli("poll"))
		self.assertEqual(result["status"], "waiting")
		self.assertFalse(result["changed"])
		self.assertEqual(
			self.calls(),
			[["show", "all", "--list-id", LIST_ID, "--json", "--no-input"]],
		)


if __name__ == "__main__":
	unittest.main()
