from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "image-job-pipeline.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_png_header(path: Path, width: int = 720, height: int = 960) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
    )


class PipelineFixture:
    def __init__(self, test: unittest.TestCase):
        self.test = test
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name).resolve()
        self.episode = self.workspace / "series" / "episodes" / "99"
        self.episode.mkdir(parents=True)
        self.style = self.workspace / "references" / "style.png"
        self.donor = self.workspace / "references" / "donor.png"
        write_png_header(self.style)
        write_png_header(self.donor, 1024, 1024)
        self.prompt = self.episode / "atomic-prompts" / "atomic_identity_test.txt"
        self.prompt.parent.mkdir()
        self.prompt_text = (
            "Create exactly one fictional adult on pure white. No text or scenery."
        )
        self.prompt.write_text(self.prompt_text + "\n", encoding="utf-8")
        self.formal = self.episode / "atomic-references" / "identity-test-v01.png"
        self.profile = self.workspace / "provider.json"
        self.write_profile()
        self.write_contracts()

    def close(self) -> None:
        self.temp.cleanup()

    def relative(self, path: Path) -> str:
        return path.relative_to(self.workspace).as_posix()

    def write_profile(self, **updates: object) -> None:
        profile = {
            "schema": "image-provider-capability/v1",
            "provider_id": "fake-test-provider",
            "max_reference_images": 4,
            "reference_order_preserved": True,
            "labeled_references": True,
            "accepted_input_formats": ["image/png"],
            "minimum_input_edge_px": 1,
            "supported_output_formats": ["image/png"],
            "maximum_output_edge_px": 2048,
            "square_output": True,
        }
        profile.update(updates)
        self.profile.write_text(
            json.dumps(profile, sort_keys=True) + "\n", encoding="utf-8"
        )

    def write_contracts(self) -> None:
        atomic_id = "atomic_identity_test"
        source_reference = self.relative(self.donor)
        plan = {
            "schema_version": 1,
            "episode": "99",
            "execution_authorized": False,
            "scene_generation_authorized": False,
            "phase_authorization": {
                "schema": "image-generation-phase-authorization/v1",
                "authorized_phase": "atomic_reference",
                "authorized_role": "reference",
                "authorized_job_ids": [atomic_id],
                "scene_generation_authorized": False,
                "execution_command_available": False,
            },
            "jobs": [
                {
                    "id": atomic_id,
                    "key": "identity_test",
                    "output": self.formal.name,
                    "kind": "identity",
                    "source_references": [source_reference],
                    "prompt": self.prompt_text,
                    "prompt_file": self.relative(self.prompt),
                    "source_reference_sha256": {
                        source_reference: sha256(self.donor)
                    },
                }
            ],
        }
        reference_map = {
            "schema_version": 2,
            "style_references": [self.relative(self.style)],
            "references": {
                "identity_test": {
                    "path": self.relative(self.formal),
                    "status": "contract_ready_atomic_image_pending_provider",
                    "generated_by_job": atomic_id,
                    "kind": "identity",
                    "contains_people": True,
                    "contains_text": False,
                    "panel_count": 1,
                }
            },
        }
        manifest = {
            "version": 1,
            "execution_authorized": False,
            "scene_generation_authorized": False,
            "phase_authorization": plan["phase_authorization"],
            "jobs": [
                {
                    "id": atomic_id,
                    "role": "reference",
                    "reference_key": "identity_test",
                    "prompt_file": str(self.prompt),
                    "prompt": self.prompt_text,
                    "output_master": str(self.formal),
                    "references": [str(self.style), str(self.donor)],
                },
                {
                    "id": "01",
                    "role": "scene",
                    "prompt_file": str(self.episode / "01.txt"),
                    "prompt": "A scene that must remain unauthorized.",
                    "output_master": str(self.episode / "01_master.png"),
                    "references": [str(self.style)],
                },
            ],
        }
        for name, value in (
            ("ATOMIC_REFERENCE_PLAN.json", plan),
            ("reference-map.json", reference_map),
            ("codex-image-jobs.json", manifest),
        ):
            (self.episode / name).write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    @property
    def canonical(self) -> Path:
        return self.episode / "image-jobs" / "canonical"

    def run(
        self,
        command: str,
        *,
        job_id: str | None = None,
        expect_success: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            sys.executable,
            str(SCRIPT),
            command,
            "--workspace",
            str(self.workspace),
            "--episode",
            str(self.episode),
            "--provider-profile",
            str(self.profile),
        ]
        if job_id is not None:
            args.extend(["--job-id", job_id])
        result = subprocess.run(args, text=True, capture_output=True)
        if expect_success:
            self.test.assertEqual(
                result.returncode,
                0,
                msg=f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
        else:
            self.test.assertNotEqual(result.returncode, 0, msg=result.stdout)
        return result


class ImageJobPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = PipelineFixture(self)

    def tearDown(self) -> None:
        self.fx.close()

    def request(self) -> dict:
        return json.loads(
            (
                self.fx.canonical / "atomic_identity_test.json"
            ).read_text(encoding="utf-8")
        )

    def test_plan_is_deterministic_provider_neutral_and_never_promotes(self):
        first = self.fx.run("plan")
        self.assertIn("network calls=0", first.stdout)
        first_hashes = {
            path.name: sha256(path) for path in self.fx.canonical.iterdir()
        }
        self.fx.run("plan")
        second_hashes = {
            path.name: sha256(path) for path in self.fx.canonical.iterdir()
        }
        self.assertEqual(first_hashes, second_hashes)
        self.assertEqual(
            set(first_hashes), {"atomic_identity_test.json", "index.json"}
        )
        self.assertFalse(self.fx.formal.exists())
        self.assertFalse((self.fx.episode / "candidates").exists())
        self.assertFalse(
            (self.fx.episode / "image-jobs" / "provider-execution").exists()
        )
        request = self.request()
        self.assertEqual(request["schema"], "image-job-request/v1")
        self.assertEqual(request["phase"], "atomic_reference")
        self.assertEqual(request["role"], "reference")
        self.assertFalse(
            request["output_contract"]["direct_formal_write_authorized"]
        )
        self.assertEqual(
            request["output_contract"]["canvas"]["minimum_edge_px"], 1254
        )
        self.assertEqual(
            request["provider_requirements"]["minimum_output_edge_px"], 1254
        )
        serialized = json.dumps(request).lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("access_token", serialized)
        self.assertNotIn("client_secret", serialized)
        self.fx.run("validate")

    def test_scene_job_is_rejected_by_phase_authorization(self):
        result = self.fx.run("plan", job_id="01", expect_success=False)
        self.assertIn("not authorized", result.stderr)
        self.assertFalse(self.fx.canonical.exists())
        self.assertFalse(self.fx.formal.exists())

    def test_reordered_or_missing_references_are_rejected(self):
        for mutation in ("reverse", "drop"):
            with self.subTest(mutation=mutation):
                self.fx.run("plan")
                path = self.fx.canonical / "atomic_identity_test.json"
                request = json.loads(path.read_text(encoding="utf-8"))
                if mutation == "reverse":
                    request["ordered_references"].reverse()
                else:
                    request["ordered_references"].pop()
                path.write_text(json.dumps(request) + "\n", encoding="utf-8")
                result = self.fx.run("validate", expect_success=False)
                self.assertIn("differs from source contracts", result.stderr)
                self.fx.run("plan")

    def test_reference_hash_change_invalidates_idempotency(self):
        self.fx.run("plan")
        first = self.request()
        self.fx.style.write_bytes(self.fx.style.read_bytes() + b"changed")
        self.fx.run("plan")
        second = self.request()
        self.assertNotEqual(
            first["ordered_references"][0]["sha256"],
            second["ordered_references"][0]["sha256"],
        )
        self.assertNotEqual(
            first["input_fingerprint_sha256"],
            second["input_fingerprint_sha256"],
        )
        self.assertNotEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertFalse(self.fx.formal.exists())

    def test_insufficient_provider_capabilities_fail_without_fallback(self):
        cases = (
            {"max_reference_images": 1},
            {"reference_order_preserved": False},
            {"labeled_references": False},
            {"accepted_input_formats": ["image/jpeg"]},
            {"minimum_input_edge_px": 2048},
            {"supported_output_formats": ["image/jpeg"]},
            {"maximum_output_edge_px": 1253},
            {"square_output": False},
        )
        for updates in cases:
            with self.subTest(updates=updates):
                self.fx.write_profile(**updates)
                result = self.fx.run("plan", expect_success=False)
                self.assertIn("UNSUPPORTED", result.stderr)
                self.assertFalse(self.fx.canonical.exists())
                self.assertFalse(self.fx.formal.exists())


if __name__ == "__main__":
    unittest.main()
