from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "register-image-provider-result.py"
PIPELINE_TEST = Path(__file__).with_name("test_image_job_pipeline.py")
PIPELINE_SPEC = importlib.util.spec_from_file_location(
    "test_image_job_pipeline_fixture", PIPELINE_TEST
)
assert PIPELINE_SPEC is not None and PIPELINE_SPEC.loader is not None
PIPELINE_MODULE = importlib.util.module_from_spec(PIPELINE_SPEC)
PIPELINE_SPEC.loader.exec_module(PIPELINE_MODULE)
PipelineFixture = PIPELINE_MODULE.PipelineFixture


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")


def canonical_sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class RegistrationFixture:
    def __init__(self, test: unittest.TestCase):
        self.test = test
        self.pipeline = PipelineFixture(test)
        self.pipeline.run("plan")
        self.workspace = self.pipeline.workspace
        self.request_path = (
            self.pipeline.canonical / "atomic_identity_test.json"
        )
        self.index_path = self.pipeline.canonical / "index.json"
        self.profile_path = self.pipeline.profile
        self.receipt_path = self.workspace / "provider-receipt.json"
        self.provider_png = self.workspace / "downloads" / "provider.png"
        self.write_png(self.provider_png, 1254, 1254, (24, 82, 121))
        self.write_receipt()

    def close(self) -> None:
        self.pipeline.close()

    @staticmethod
    def write_png(
        path: Path,
        width: int,
        height: int,
        color: tuple[int, int, int] = (24, 82, 121),
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (width, height), color).save(path, format="PNG")

    def documents(self) -> tuple[dict, dict, dict]:
        return tuple(
            json.loads(path.read_text(encoding="utf-8"))
            for path in (self.request_path, self.index_path, self.profile_path)
        )

    def receipt(self) -> dict:
        return json.loads(self.receipt_path.read_text(encoding="utf-8"))

    def write_receipt(self, **updates: object) -> None:
        request, index, profile = self.documents()
        receipt = {
            "schema": "provider-execution/v1",
            "provider_id": profile["provider_id"],
            "provider_profile_sha256": canonical_sha(profile),
            "model_id": "fake-image-model/v1",
            "attempt_id": "attempt-001",
            "submitted_at_utc": "2026-07-24T10:00:00Z",
            "completed_at_utc": "2026-07-24T10:00:12.500000Z",
            "provider_request_id": "provider-request-abc123",
            "status": "succeeded",
            "canonical_request_sha256": canonical_sha(request),
            "canonical_index_sha256": canonical_sha(index),
            "input_fingerprint_sha256": request["input_fingerprint_sha256"],
            "idempotency_key": request["idempotency_key"],
            "ordered_reference_sha256": [
                item["sha256"] for item in request["ordered_references"]
            ],
        }
        receipt.update(updates)
        self.receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def run(self, *, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--workspace",
                str(self.workspace),
                "--request",
                str(self.request_path),
                "--index",
                str(self.index_path),
                "--provider-profile",
                str(self.profile_path),
                "--execution-receipt",
                str(self.receipt_path),
                "--provider-png",
                str(self.provider_png),
            ],
            text=True,
            capture_output=True,
        )
        if expect_success:
            self.test.assertEqual(
                result.returncode,
                0,
                msg=f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
        else:
            self.test.assertNotEqual(
                result.returncode,
                0,
                msg=f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
        return result

    @property
    def attempt_dir(self) -> Path:
        return (
            self.pipeline.episode
            / "image-jobs"
            / "provider-execution"
            / "atomic_identity_test"
            / self.receipt()["attempt_id"]
        )


class RegisterImageProviderResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = RegistrationFixture(self)

    def tearDown(self) -> None:
        self.fx.close()

    def test_real_planned_request_registers_only_immutable_provider_original(self):
        result = self.fx.run()
        self.assertIn("REGISTERED", result.stdout)
        attempt = self.fx.attempt_dir
        self.assertEqual(
            {path.name for path in attempt.iterdir()},
            {"original.png", "result-provenance.json"},
        )
        self.assertEqual(
            (attempt / "original.png").read_bytes(), self.fx.provider_png.read_bytes()
        )
        provenance = json.loads(
            (attempt / "result-provenance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(provenance["schema"], "image-result-provenance/v1")
        self.assertEqual(provenance["review_state"], "unapproved_provider_original")
        self.assertFalse(provenance["direct_promotion_authorized"])
        self.assertFalse(provenance["direct_formal_write_authorized"])
        self.assertFalse(provenance["writes"]["candidate_written"])
        self.assertFalse(provenance["writes"]["formal_target_written"])
        self.assertEqual(provenance["network_calls_performed"], 0)
        self.assertFalse(self.fx.pipeline.formal.exists())
        self.assertFalse((self.fx.pipeline.episode / "candidates").exists())

    def test_exact_repeat_is_idempotent_but_conflicting_png_fails_closed(self):
        self.fx.run()
        original = (self.fx.attempt_dir / "original.png").read_bytes()
        repeated = self.fx.run()
        self.assertIn("IDEMPOTENT", repeated.stdout)
        self.fx.write_png(
            self.fx.provider_png, 1254, 1254, color=(180, 30, 20)
        )
        conflict = self.fx.run(expect_success=False)
        self.assertIn("conflicting immutable attempt", conflict.stderr)
        self.assertEqual((self.fx.attempt_dir / "original.png").read_bytes(), original)

    def test_conflicting_receipt_repeat_fails_closed(self):
        self.fx.run()
        original_provenance = (
            self.fx.attempt_dir / "result-provenance.json"
        ).read_bytes()
        self.fx.write_receipt(provider_request_id="a-different-request-id")
        conflict = self.fx.run(expect_success=False)
        self.assertIn("conflicting immutable attempt", conflict.stderr)
        self.assertEqual(
            (self.fx.attempt_dir / "result-provenance.json").read_bytes(),
            original_provenance,
        )

    def test_attempt_path_traversal_and_secret_fields_are_rejected(self):
        self.fx.write_receipt(attempt_id="../escape")
        traversal = self.fx.run(expect_success=False)
        self.assertIn("attempt_id", traversal.stderr)
        self.assertFalse(
            self.pipeline_provider_root().exists()
        )

        self.fx.write_receipt()
        receipt = self.fx.receipt()
        receipt["api_key"] = "must-never-be-written"
        self.fx.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        secret = self.fx.run(expect_success=False)
        self.assertIn("secret-bearing field", secret.stderr)
        self.assertFalse(self.pipeline_provider_root().exists())

    def pipeline_provider_root(self) -> Path:
        return self.fx.pipeline.episode / "image-jobs" / "provider-execution"

    def test_receipt_hash_and_order_bindings_are_all_verified(self):
        mutations = {
            "provider_profile_sha256": "0" * 64,
            "canonical_request_sha256": "1" * 64,
            "canonical_index_sha256": "2" * 64,
            "input_fingerprint_sha256": "3" * 64,
            "idempotency_key": "wrong",
            "ordered_reference_sha256": list(
                reversed(self.fx.receipt()["ordered_reference_sha256"])
            ),
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                self.fx.write_receipt(**{field: value})
                result = self.fx.run(expect_success=False)
                self.assertRegex(result.stderr, r"do(?:es)? not verify")
                self.assertFalse(self.pipeline_provider_root().exists())

    def test_current_reference_bytes_must_still_match_ordered_binding(self):
        self.fx.pipeline.style.write_bytes(
            self.fx.pipeline.style.read_bytes() + b"changed-after-plan"
        )
        result = self.fx.run(expect_success=False)
        self.assertIn("ordered reference hash no longer matches", result.stderr)
        self.assertFalse(self.pipeline_provider_root().exists())

    def test_png_must_be_real_decodable_square_and_within_edge_bounds(self):
        cases = (
            ("truncated", None, None),
            ("nonsquare", 1254, 1300),
            ("small", 1000, 1000),
            ("large", 2049, 2049),
        )
        for name, width, height in cases:
            with self.subTest(name=name):
                if name == "truncated":
                    self.fx.provider_png.write_bytes(
                        b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
                    )
                else:
                    assert width is not None and height is not None
                    self.fx.write_png(self.fx.provider_png, width, height)
                result = self.fx.run(expect_success=False)
                self.assertRegex(
                    result.stderr,
                    r"(decodable PNG|must be square|below required|exceeds provider)",
                )
                self.assertFalse(self.pipeline_provider_root().exists())

    def test_failed_timestamp_or_status_never_creates_attempt(self):
        for updates in (
            {"status": "failed"},
            {"submitted_at_utc": "2026-07-24 10:00:00"},
            {
                "submitted_at_utc": "2026-07-24T10:00:13Z",
                "completed_at_utc": "2026-07-24T10:00:12Z",
            },
        ):
            with self.subTest(updates=updates):
                self.fx.write_receipt(**updates)
                self.fx.run(expect_success=False)
                self.assertFalse(self.pipeline_provider_root().exists())


if __name__ == "__main__":
    unittest.main()
