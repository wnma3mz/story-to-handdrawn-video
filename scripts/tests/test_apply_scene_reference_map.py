from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "apply-scene-reference-map.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "base-scene-prompt.txt"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CompilerFixture:
    def __init__(self, test: unittest.TestCase):
        self.test = test
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.episode = self.root / "episode"
        self.episode.mkdir()
        self.styles = []
        for name in ("style-bw.png", "style-color.png"):
            path = self.root / name
            path.write_bytes(f"fixture-{name}".encode())
            self.styles.append(str(path))
        self.references: dict[str, dict] = {}
        self.jobs: list[dict] = []
        self.scenes: dict[str, dict | list[str]] = {}
        self.identities: dict[str, dict] = {}
        self.base_prompt = FIXTURE.read_text(encoding="utf-8").rstrip("\n")

    def close(self):
        self.temp.cleanup()

    def add_reference(
        self,
        key: str,
        *,
        capabilities: dict[str, str] | None = None,
        instruction: str | None = None,
        kind: str = "object",
        identities: list[str] | None = None,
        contains_people: bool = False,
        panel_count: int = 1,
    ) -> Path:
        path = self.root / f"{key}.png"
        path.write_bytes(f"fixture-reference-{key}".encode())
        definition: dict = {
            "path": str(path),
            "sha256": digest(path),
            "kind": kind,
            "contains_people": contains_people,
            "contains_text": False,
            "panel_count": panel_count,
        }
        if capabilities is not None:
            definition["capabilities"] = capabilities
        if instruction is not None:
            definition["instruction"] = instruction
        if identities is not None:
            definition["identities"] = identities
        self.references[key] = definition
        return path

    def add_job(self, scene_id: str, *, prompt: str | None = None):
        prompt_path = self.episode / f"{scene_id}.txt"
        source_prompt = self.base_prompt if prompt is None else prompt
        prompt_path.write_text(source_prompt, encoding="utf-8")
        self.jobs.append(
            {
                "id": scene_id,
                "role": "scene",
                "prompt_file": str(prompt_path),
                "prompt": source_prompt,
                "output_master": str(self.root / f"{scene_id}_master.png"),
                "references": [],
            }
        )

    def write(self, *, schema_version: int = 2, global_prompt: str = ""):
        manifest = {"schema_version": 1, "jobs": self.jobs}
        (self.episode / "codex-image-jobs.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        mapping: dict = {
            "schema_version": schema_version,
            "style_references": self.styles,
            "references": self.references,
            "scenes": self.scenes,
        }
        if schema_version == 1:
            mapping["identity_mode"] = "locked"
        else:
            mapping["identities"] = self.identities
            if global_prompt:
                mapping["global_prompt"] = global_prompt
        (self.episode / "reference-map.json").write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def run(self, *, check: bool = False, expect_success: bool = True):
        command = [sys.executable, str(SCRIPT), str(self.episode)]
        if check:
            command.append("--check")
        result = subprocess.run(command, text=True, capture_output=True)
        if expect_success:
            self.test.assertEqual(
                result.returncode,
                0,
                msg=f"command failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
        else:
            self.test.assertNotEqual(
                result.returncode,
                0,
                msg=f"command unexpectedly passed:\n{result.stdout}",
            )
        return result

    def compiled_manifest(self) -> dict:
        return json.loads((self.episode / "codex-image-jobs.json").read_text())

    def compiled_job(self, scene_id: str) -> dict:
        return next(job for job in self.compiled_manifest()["jobs"] if job["id"] == scene_id)

    def compile_and_check(self):
        first = self.run()
        self.test.assertIn("with prompt isolation lint", first.stdout)
        checked = self.run(check=True)
        self.test.assertIn("prompt isolation lint passed", checked.stdout)


class ApplySceneReferenceMapTests(unittest.TestCase):
    def setUp(self):
        self.fx = CompilerFixture(self)
        self.fx.identities = {
            "hero": {
                "name": "Hero Alpha",
                "positive_prompt": "Hero Alpha has a square face and a red sash.",
                "fingerprints": ["Hero Alpha", "square face and a red sash"],
                "reference_keys": ["hero_identity"],
            },
            "other": {
                "name": "Other Beta",
                "positive_prompt": "Other Beta has tight curls and a blue cloak.",
                "fingerprints": ["Other Beta", "tight curls and a blue cloak"],
                "reference_keys": ["other_identity"],
            },
        }
        self.hero_path = self.fx.add_reference(
            "hero_identity",
            capabilities={"identity": "Use only Hero Alpha's approved identity."},
            kind="identity",
            identities=["hero"],
            contains_people=True,
        )
        self.other_path = self.fx.add_reference(
            "other_identity",
            capabilities={"identity": "Use only Other Beta's approved identity."},
            kind="identity",
            identities=["other"],
            contains_people=True,
        )
        self.institution_path = self.fx.add_reference(
            "institution",
            capabilities={
                "public_counter": "Use only one low-technology public counter.",
                "senate_shelter": "Use only one sparse timber Senate shelter.",
                "watchtower": "Use only one watchtower.",
            },
        )
        self.trade_path = self.fx.add_reference(
            "trade",
            capabilities={
                "boat_form": "Use only the low-technology cargo-boat form.",
                "fish_crates": "Use only fish-imprint cargo crates.",
            },
        )

    def tearDown(self):
        self.fx.close()

    def test_anonymous_scene_strips_all_identity_blocks_and_counts_roles(self):
        self.fx.add_job("01")
        self.fx.scenes["01"] = {
            "cast": {
                "mode": "anonymous",
                "allowed_identities": [],
                "generic_roles": [
                    {
                        "role": "technician",
                        "count": 1,
                        "description": "Plain work clothes and a non-signature appearance.",
                    }
                ],
            },
            "references": [
                {"key": "institution", "capabilities": ["public_counter"]}
            ],
            "composition_mode": "single_tableau",
        }
        self.fx.write(global_prompt="Keep the island low-technology and unlettered.")
        self.fx.compile_and_check()

        job = self.fx.compiled_job("01")
        prompt = job["prompt"]
        self.assertNotIn("Hero Alpha", prompt)
        self.assertNotIn("Other Beta", prompt)
        self.assertNotIn("square face and a red sash", prompt)
        self.assertNotIn("tight curls and a blue cloak", prompt)
        self.assertIn("Recurring cast count: exactly 0.", prompt)
        self.assertIn('Generic role "technician": exactly 1.', prompt)
        self.assertIn("Total generic figure count: exactly 1.", prompt)
        self.assertIn("Use only one low-technology public counter.", prompt)
        self.assertNotIn("Senate shelter", prompt)
        self.assertNotIn("watchtower", prompt)
        self.assertEqual(job["references"], self.fx.styles + [str(self.institution_path)])
        manifest = self.fx.compiled_manifest()
        self.assertEqual(manifest["identity_mode"], "scene-local")
        self.assertEqual(manifest["prompt_isolation_lint"], "passed")

    def test_named_scene_keeps_only_allowed_identity_plus_exact_bystanders(self):
        self.fx.add_job("02")
        self.fx.scenes["02"] = {
            "cast": {
                "mode": "named",
                "allowed_identities": ["hero"],
                "generic_roles": [
                    {
                        "role": "senator",
                        "count": 3,
                        "description": "Generic clean-shaven adults in plain muted garments.",
                    }
                ],
            },
            "references": [
                {"key": "hero_identity", "capabilities": ["identity"]},
                {"key": "institution", "capabilities": ["senate_shelter"]},
            ],
            "composition_mode": "single_tableau",
        }
        self.fx.write()
        self.fx.compile_and_check()

        job = self.fx.compiled_job("02")
        prompt = job["prompt"]
        self.assertEqual(
            prompt.count("Hero Alpha has a square face and a red sash."),
            1,
        )
        self.assertNotIn("Other Beta", prompt)
        self.assertNotIn("tight curls and a blue cloak", prompt)
        self.assertIn("Allowed recurring identity count: exactly 1.", prompt)
        self.assertIn('Generic role "senator": exactly 3.', prompt)
        self.assertIn("Total generic figure count: exactly 3.", prompt)
        self.assertEqual(
            job["references"],
            self.fx.styles + [str(self.hero_path), str(self.institution_path)],
        )

    def test_institution_capability_override_excludes_unrelated_blocks(self):
        self.fx.add_job("03")
        self.fx.scenes["03"] = {
            "cast": {
                "mode": "anonymous",
                "allowed_identities": [],
                "generic_roles": [{"role": "clerk", "count": 1}],
            },
            "references": [
                {
                    "key": "institution",
                    "capabilities": ["public_counter"],
                    "capability_overrides": {
                        "public_counter": (
                            "Use one anonymous public-payment counter and nothing else."
                        )
                    },
                }
            ],
            "composition_mode": "single_tableau",
        }
        self.fx.write()
        self.fx.compile_and_check()

        prompt = self.fx.compiled_job("03")["prompt"]
        self.assertIn(
            "Use one anonymous public-payment counter and nothing else.",
            prompt,
        )
        self.assertNotIn("Use only one low-technology public counter.", prompt)
        self.assertNotIn("Senate shelter", prompt)
        self.assertNotIn("watchtower", prompt)

    def test_relational_wide_supports_whole_binding_instruction_override(self):
        self.fx.add_job("04")
        self.fx.scenes["04"] = {
            "cast": {
                "mode": "anonymous",
                "allowed_identities": [],
                "generic_roles": [{"role": "island_trader", "count": 4}],
            },
            "references": [
                {
                    "key": "trade",
                    "capabilities": ["boat_form"],
                    "instruction": (
                        "Use only one neutral sail-less boat form; cargo and people are "
                        "defined by this scene."
                    ),
                }
            ],
            "composition_mode": "relational_wide",
        }
        self.fx.write()
        self.fx.compile_and_check()

        prompt = self.fx.compiled_job("04")["prompt"]
        self.assertIn("Composition mode: relational_wide.", prompt)
        self.assertNotIn("Composition mode: single_tableau.", prompt)
        self.assertIn("Use only one neutral sail-less boat form", prompt)
        self.assertNotIn("Use only the low-technology cargo-boat form.", prompt)
        self.assertNotIn("fish-imprint cargo crates", prompt)

    def test_e13_regression_fingerprints_are_scene_local(self):
        del self.fx.references["hero_identity"]
        del self.fx.references["other_identity"]
        self.fx.identities = {
            "chuck": {
                "name": "查克·小鼓",
                "positive_prompt": "查克·小鼓：浓密短卷黑发、短下巴胡须、暖黄色短叶衣与砖红单肩披巾。",
                "fingerprints": ["查克·小鼓", "浓密短卷黑发", "砖红单肩披巾"],
                "reference_keys": [],
            },
            "cobble": {
                "name": "靠布柱·迪克森",
                "positive_prompt": "靠布柱·迪克森：后梳灰黑短发、细灰胡须与深灰蓝长叶衣。",
                "fingerprints": ["靠布柱·迪克森", "后梳灰黑短发", "深灰蓝长叶衣"],
                "reference_keys": [],
            },
            "bernanke": {
                "name": "本·伯南柯",
                "positive_prompt": "本·伯南柯：后退灰黑短发、短灰胡须、灰蓝短叶衣与鼠尾草绿长背心。",
                "fingerprints": ["本·伯南柯", "后退灰黑短发", "鼠尾草绿长背心"],
                "reference_keys": ["bernanke_identity"],
            },
            "rophy": {
                "name": "罗非·里实",
                "positive_prompt": "罗非·里实：短直黑发夹灰、鼠尾草绿长叶衣与砖红细腰带。",
                "fingerprints": ["罗非·里实", "短直黑发夹灰", "砖红细腰带"],
                "reference_keys": [],
            },
        }
        bernanke_path = self.fx.add_reference(
            "bernanke_identity",
            capabilities={"identity": "Use only the approved Bernanke identity."},
            kind="identity",
            identities=["bernanke"],
            contains_people=True,
        )
        old_lock = (
            "Character lock: 查克·小鼓有浓密短卷黑发与砖红单肩披巾。\n"
            "靠布柱·迪克森有后梳灰黑短发与深灰蓝长叶衣。\n"
            "本·伯南柯有后退灰黑短发与鼠尾草绿长背心。\n"
            "罗非·里实有短直黑发夹灰与砖红细腰带。"
        )
        prompt = self.fx.base_prompt.replace(
            "Character lock: Hero Alpha has a square face and a red sash.\n"
            "Other Beta has tight curls and a blue cloak.",
            old_lock,
        )
        self.fx.add_job("05", prompt=prompt)
        self.fx.add_job("08", prompt=prompt)
        self.fx.scenes["05"] = {
            "cast": {
                "mode": "anonymous",
                "allowed_identities": [],
                "generic_roles": [{"role": "technician", "count": 1}],
            },
            "references": [
                {"key": "institution", "capabilities": ["public_counter"]}
            ],
            "composition_mode": "single_tableau",
        }
        self.fx.scenes["08"] = {
            "cast": {
                "mode": "named",
                "allowed_identities": ["bernanke"],
                "generic_roles": [{"role": "senator", "count": 3}],
            },
            "references": [
                {"key": "bernanke_identity", "capabilities": ["identity"]},
                {"key": "institution", "capabilities": ["senate_shelter"]},
            ],
            "composition_mode": "single_tableau",
        }
        self.fx.write()
        self.fx.compile_and_check()

        anonymous_prompt = self.fx.compiled_job("05")["prompt"]
        for text in (
            "查克·小鼓",
            "靠布柱·迪克森",
            "本·伯南柯",
            "罗非·里实",
            "浓密短卷黑发",
            "后梳灰黑短发",
            "后退灰黑短发",
            "短直黑发夹灰",
        ):
            self.assertNotIn(text, anonymous_prompt)
        self.assertNotIn(str(bernanke_path), self.fx.compiled_job("05")["references"])

        named_prompt = self.fx.compiled_job("08")["prompt"]
        self.assertEqual(named_prompt.count("本·伯南柯："), 1)
        self.assertIn('Generic role "senator": exactly 3.', named_prompt)
        for text in ("查克·小鼓", "靠布柱·迪克森", "罗非·里实"):
            self.assertNotIn(text, named_prompt)
        self.assertIn(str(bernanke_path), self.fx.compiled_job("08")["references"])

    def test_lint_rejects_identity_fingerprint_in_anonymous_constraint(self):
        self.fx.add_job("06")
        self.fx.scenes["06"] = {
            "cast": {
                "mode": "anonymous",
                "allowed_identities": [],
                "generic_roles": [{"role": "worker", "count": 1}],
            },
            "references": [
                {"key": "institution", "capabilities": ["public_counter"]}
            ],
            "composition_mode": "single_tableau",
            "constraints": ["Give the worker a square face and a red sash."],
        }
        self.fx.write()
        result = self.fx.run(expect_success=False)
        self.assertIn("leaks forbidden identity hero", result.stderr)

    def test_anonymous_scene_rejects_identity_reference_path(self):
        self.fx.add_job("07")
        self.fx.scenes["07"] = {
            "cast": {
                "mode": "anonymous",
                "allowed_identities": [],
                "generic_roles": [{"role": "worker", "count": 1}],
            },
            "references": [
                {"key": "hero_identity", "capabilities": ["identity"]}
            ],
            "composition_mode": "single_tableau",
        }
        self.fx.write()
        result = self.fx.run(expect_success=False)
        self.assertIn("must not bind identity reference hero_identity", result.stderr)

    def test_schema_v2_rejects_composite_reference_before_generation(self):
        self.fx.add_reference(
            "composite_counter",
            capabilities={"counter": "Use only the public counter."},
            panel_count=3,
        )
        self.fx.add_job("09")
        self.fx.scenes["09"] = {
            "cast": {
                "mode": "anonymous",
                "allowed_identities": [],
                "generic_roles": [{"role": "clerk", "count": 1}],
            },
            "references": [
                {"key": "composite_counter", "capabilities": ["counter"]}
            ],
            "composition_mode": "single_tableau",
        }
        self.fx.write()
        result = self.fx.run(expect_success=False)
        self.assertIn("is composite (panel_count=3)", result.stderr)

    def test_schema_v2_allows_declared_missing_upstream_atomic_dependency(self):
        upstream_path = self.fx.root / "episode16" / "atomic-references" / "dock.png"
        self.fx.references["upstream_dock"] = {
            "path": str(upstream_path),
            "status": "contract_ready_atomic_image_pending_provider",
            "generated_by_job": "atomic_institution_dock",
            "execution_owner": "episode16",
            "kind": "institution",
            "contains_people": False,
            "contains_text": False,
            "panel_count": 1,
            "capabilities": {"dock": "Use only the future approved upstream dock."},
        }
        self.fx.add_job("10")
        self.fx.scenes["10"] = {
            "cast": {
                "mode": "anonymous",
                "allowed_identities": [],
                "generic_roles": [],
            },
            "references": [
                {"key": "upstream_dock", "capabilities": ["dock"]}
            ],
            "composition_mode": "single_tableau",
        }
        self.fx.write()
        self.fx.compile_and_check()
        self.assertEqual(
            self.fx.compiled_job("10")["references"],
            self.fx.styles + [str(upstream_path.resolve())],
        )

    def test_schema_v2_rejects_unowned_missing_reference(self):
        missing_path = self.fx.root / "missing.png"
        self.fx.references["missing"] = {
            "path": str(missing_path),
            "status": "contract_ready_atomic_image_pending_provider",
            "generated_by_job": "atomic_object_missing",
            "kind": "object",
            "contains_people": False,
            "contains_text": False,
            "panel_count": 1,
            "capabilities": {"object": "Use only the future object."},
        }
        self.fx.add_job("11")
        self.fx.scenes["11"] = {
            "cast": {
                "mode": "anonymous",
                "allowed_identities": [],
                "generic_roles": [],
            },
            "references": [{"key": "missing", "capabilities": ["object"]}],
            "composition_mode": "single_tableau",
        }
        self.fx.write()
        result = self.fx.run(expect_success=False)
        self.assertIn("reference missing is missing", result.stderr)

    def test_schema_v1_locked_behavior_is_preserved(self):
        self.fx.identities = {}
        self.fx.add_job("01")
        self.fx.scenes["01"] = ["institution"]
        self.fx.references["institution"].pop("capabilities")
        self.fx.references["institution"]["instruction"] = (
            "Use the complete legacy institution instruction."
        )
        self.fx.write(schema_version=1)
        self.fx.run()
        self.fx.run(check=True)

        job = self.fx.compiled_job("01")
        self.assertIn("Hero Alpha has a square face and a red sash.", job["prompt"])
        self.assertIn("Other Beta has tight curls and a blue cloak.", job["prompt"])
        self.assertIn("Use the complete legacy institution instruction.", job["prompt"])
        self.assertIn(LOCKED_SENTENCE_FRAGMENT, job["prompt"])
        manifest = self.fx.compiled_manifest()
        self.assertEqual(manifest["identity_mode"], "locked")
        self.assertEqual(manifest["reference_map_schema_version"], 1)
        self.assertNotIn("prompt_isolation_lint", manifest)


LOCKED_SENTENCE_FRAGMENT = "Use the locked recurring protagonists"


if __name__ == "__main__":
    unittest.main()
