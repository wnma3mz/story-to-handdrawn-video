#!/usr/bin/env python3
"""Apply scene-specific image references to an isolated Codex image manifest.

The story planner can attach one global character sheet, but dense episodic work
often needs different character, object, and institution references per scene.
This utility replaces that global list with an explicit map and rewrites the
indexed input paragraph in both the manifest prompt and its prompt file.

Schema version 1 preserves the original episode-wide ``identity_mode`` behavior.
Schema version 2 compiles a scene-local cast/reference contract and lints the
result so anonymous prompts contain no recurring identity blocks or paths, while
named prompts contain only explicitly allowed identities.

For a chapter with intentionally anonymous one-scene figures, set
``identity_mode`` to ``anonymous`` and ``discard_reference_jobs`` to true. This
removes the planner's automatic actor sheet and its fixed-protagonist wording
instead of silently turning anonymous figures into a recurring cast.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COMPOSITION_PROMPTS = {
    "single_tableau": (
        "Composition mode: single_tableau. Show one continuous tableau; never use panels, "
        "a collage, a reference sheet, separated catalogue blocks, or an infographic layout."
    ),
    "relational_wide": (
        "Composition mode: relational_wide. Show one connected wide world view containing "
        "the required locations; never use a map, chart, panels, donor-sheet blocks, or a "
        "repeated reference layout."
    ),
}

LOCKED_PROTAGONIST_SENTENCE = (
    "Create one concrete, immediately readable tableau for that sentence. "
    "Use the locked recurring protagonists whenever the current sentence requires them."
)
SCENE_CONTRACT_SENTENCE = (
    "Create one concrete, immediately readable tableau for that sentence. "
    "Follow the scene-local cast contract exactly and do not add identities or bystanders."
)
FIXED_CHARACTER_SHEET_SENTENCE = (
    "Continuity: preserve the locked character design. Use the fixed character sheet only for "
    "the protagonist's identity, never copy its pose or composition. Include only people required "
    "by the current narrative sentence."
)
SCENE_LOCAL_CONTINUITY_SENTENCE = (
    "Continuity: follow the scene-local cast, world, safety and clothing contract. Include exactly "
    "the named identities and generic roles declared for this scene, and no other people."
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def input_paragraph(reference_keys: list[str], definitions: dict) -> str:
    lines = [
        "Input images, exact indexed mapping:",
        "- Image 1: approved black-and-white series style reference; use only uneven line behavior and simplified anatomy, never its people, text, or scene.",
        "- Image 2: approved selective-color series style reference; use only muted crayon palette, white field, and material rendering, never its people, text, or scene.",
    ]
    for index, key in enumerate(reference_keys, start=3):
        lines.append(f"- Image {index}: {definitions[key]['instruction']}")
    lines.append("Ignore all text in every reference. References define only the identities or objects stated above; they are never an automatic cast or prop list.")
    return "\n".join(lines)


def replace_input_paragraph(prompt: str, replacement: str) -> str:
    pattern = r"^Input images(?:, exact indexed mapping)?:.*?(?=^Narrative sentence to illustrate:)"
    updated, count = re.subn(pattern, replacement + "\n", prompt, count=1, flags=re.MULTILINE | re.DOTALL)
    if count != 1:
        raise ValueError("prompt does not contain one replaceable Input images paragraph")
    return updated


def apply_identity_mode(prompt: str, mode: str) -> str:
    if mode == "locked":
        return prompt
    if mode != "anonymous":
        raise ValueError(f"unsupported identity_mode: {mode}")

    replacements = {
        (
            "Create one concrete, immediately readable tableau for that sentence. "
            "Use the locked recurring protagonists whenever the current sentence requires them."
        ): (
            "Create one concrete, immediately readable tableau for that sentence. "
            "Use only the anonymous or one-scene figures required by the immediate action; "
            "do not invent a recurring protagonist identity."
        ),
        (
            "Continuity: preserve the locked character design. Use the fixed character sheet only for "
            "the protagonist's identity, never copy its pose or composition. Include only people required "
            "by the current narrative sentence."
        ): (
            "Continuity: follow the episode's world, safety, clothing and cast-boundary lock, but do not "
            "impose a recurring face or fixed actor identity. Include only people required by the current "
            "narrative sentence."
        ),
    }
    updated = prompt
    for original, replacement in replacements.items():
        if original in updated:
            updated = updated.replace(original, replacement, 1)
        elif replacement not in updated:
            raise ValueError(f"anonymous identity mode could not find required prompt text: {original}")
    return updated


def require_string(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def require_string_list(value, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    result = [item.strip() for item in value]
    if not allow_empty and not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_v2_identities(mapping: dict, definitions: dict) -> dict[str, dict]:
    raw_identities = mapping.get("identities", {})
    if not isinstance(raw_identities, dict):
        raise ValueError("schema v2 identities must be an object")

    identities: dict[str, dict] = {}
    for key, raw in raw_identities.items():
        identity_key = require_string(key, "identity key")
        if not isinstance(raw, dict):
            raise ValueError(f"identity {identity_key} must be an object")
        name = require_string(raw.get("name", identity_key), f"identity {identity_key}.name")
        positive_prompt = require_string(
            raw.get("positive_prompt", raw.get("prompt")),
            f"identity {identity_key}.positive_prompt",
        )
        fingerprints = require_string_list(
            raw.get("fingerprints", []),
            f"identity {identity_key}.fingerprints",
            allow_empty=False,
        )
        reference_keys = require_string_list(
            raw.get("reference_keys", []),
            f"identity {identity_key}.reference_keys",
        )
        unknown_references = [ref for ref in reference_keys if ref not in definitions]
        if unknown_references:
            raise ValueError(
                f"identity {identity_key} has unknown reference_keys: {unknown_references}"
            )
        identities[identity_key] = {
            "name": name,
            "positive_prompt": positive_prompt,
            "fingerprints": fingerprints,
            "reference_keys": reference_keys,
        }
    return identities


def reference_identity_owners(
    reference_key: str,
    definition: dict,
    identities: dict[str, dict],
) -> set[str]:
    owners: set[str] = set()
    declared = definition.get("identities")
    if declared is None and definition.get("identity") is not None:
        declared = [definition["identity"]]
    if declared is not None:
        owners.update(
            require_string_list(
                declared,
                f"reference {reference_key}.identities",
                allow_empty=False,
            )
        )
    for identity_key, identity in identities.items():
        if reference_key in identity["reference_keys"]:
            owners.add(identity_key)
    unknown = sorted(owners - set(identities))
    if unknown:
        raise ValueError(f"reference {reference_key} names unknown identities: {unknown}")
    if definition.get("kind") == "identity" and not owners:
        raise ValueError(f"identity reference {reference_key} must declare an identity owner")
    return owners


def validate_v2_scene(
    scene_id: str,
    raw_scene,
    identities: dict[str, dict],
    definitions: dict,
) -> dict:
    if not isinstance(raw_scene, dict):
        raise ValueError(f"schema v2 scene {scene_id} must be an object")

    raw_cast = raw_scene.get("cast")
    if not isinstance(raw_cast, dict):
        raise ValueError(f"scene {scene_id}.cast must be an object")
    mode = raw_cast.get("mode")
    if mode not in {"anonymous", "named"}:
        raise ValueError(f"scene {scene_id}.cast.mode must be anonymous or named")
    allowed = require_string_list(
        raw_cast.get("allowed_identities", []),
        f"scene {scene_id}.cast.allowed_identities",
    )
    unknown_identities = sorted(set(allowed) - set(identities))
    if unknown_identities:
        raise ValueError(f"scene {scene_id} allows unknown identities: {unknown_identities}")
    if mode == "anonymous" and allowed:
        raise ValueError(f"anonymous scene {scene_id} must not allow recurring identities")
    if mode == "named" and not allowed:
        raise ValueError(f"named scene {scene_id} must allow at least one recurring identity")

    raw_roles = raw_cast.get("generic_roles", [])
    if not isinstance(raw_roles, list):
        raise ValueError(f"scene {scene_id}.cast.generic_roles must be a list")
    roles: list[dict] = []
    role_names: set[str] = set()
    for index, raw_role in enumerate(raw_roles):
        if not isinstance(raw_role, dict):
            raise ValueError(f"scene {scene_id} generic role {index} must be an object")
        role = require_string(raw_role.get("role"), f"scene {scene_id} generic role {index}.role")
        if role in role_names:
            raise ValueError(f"scene {scene_id} duplicates generic role {role!r}")
        role_names.add(role)
        count = raw_role.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError(
                f"scene {scene_id} generic role {role!r} count must be a positive integer"
            )
        description = raw_role.get("description", "")
        if description:
            description = require_string(
                description,
                f"scene {scene_id} generic role {role!r}.description",
            )
        roles.append({"role": role, "count": count, "description": description})

    composition_mode = raw_scene.get("composition_mode")
    if composition_mode not in COMPOSITION_PROMPTS:
        raise ValueError(
            f"scene {scene_id}.composition_mode must be one of "
            f"{sorted(COMPOSITION_PROMPTS)}"
        )

    bindings = raw_scene.get("references", [])
    if not isinstance(bindings, list):
        raise ValueError(f"scene {scene_id}.references must be a list")
    normalized_bindings: list[dict] = []
    seen_reference_keys: set[str] = set()
    for index, raw_binding in enumerate(bindings):
        if not isinstance(raw_binding, dict):
            raise ValueError(f"scene {scene_id} reference binding {index} must be an object")
        key = require_string(
            raw_binding.get("key"),
            f"scene {scene_id} reference binding {index}.key",
        )
        if key not in definitions:
            raise ValueError(f"scene {scene_id} has unknown reference: {key}")
        if key in seen_reference_keys:
            raise ValueError(f"scene {scene_id} binds reference {key!r} more than once")
        seen_reference_keys.add(key)
        definition = definitions[key]
        if not isinstance(definition, dict):
            raise ValueError(f"reference {key} must be an object")

        capabilities = require_string_list(
            raw_binding.get("capabilities", []),
            f"scene {scene_id} reference {key}.capabilities",
        )
        raw_capability_definitions = definition.get("capabilities", {})
        if not isinstance(raw_capability_definitions, dict):
            raise ValueError(f"reference {key}.capabilities must be an object")
        unknown_capabilities = [cap for cap in capabilities if cap not in raw_capability_definitions]
        if unknown_capabilities:
            raise ValueError(
                f"scene {scene_id} reference {key} selects unknown capabilities: "
                f"{unknown_capabilities}"
            )

        instruction = raw_binding.get("instruction")
        if instruction is not None:
            instruction = require_string(
                instruction,
                f"scene {scene_id} reference {key}.instruction",
            )
        raw_overrides = raw_binding.get("capability_overrides", {})
        if not isinstance(raw_overrides, dict):
            raise ValueError(
                f"scene {scene_id} reference {key}.capability_overrides must be an object"
            )
        capability_overrides: dict[str, str] = {}
        for capability, override in raw_overrides.items():
            capability = require_string(
                capability,
                f"scene {scene_id} reference {key} capability override key",
            )
            if capability not in capabilities:
                raise ValueError(
                    f"scene {scene_id} reference {key} overrides unselected capability "
                    f"{capability!r}"
                )
            capability_overrides[capability] = require_string(
                override,
                f"scene {scene_id} reference {key} capability override {capability}",
            )
        if instruction is not None and capability_overrides:
            raise ValueError(
                f"scene {scene_id} reference {key} cannot combine instruction with "
                "capability_overrides"
            )
        if instruction is None and not capabilities:
            raise ValueError(
                f"scene {scene_id} reference {key} needs capabilities or a scene-local instruction"
            )

        owners = reference_identity_owners(key, definition, identities)
        if mode == "anonymous" and owners:
            raise ValueError(
                f"anonymous scene {scene_id} must not bind identity reference {key}: "
                f"{sorted(owners)}"
            )
        forbidden_owners = sorted(owners - set(allowed))
        if forbidden_owners:
            raise ValueError(
                f"scene {scene_id} reference {key} exposes forbidden identities: "
                f"{forbidden_owners}"
            )
        if mode == "anonymous" and definition.get("contains_people") is True:
            raise ValueError(
                f"anonymous scene {scene_id} object reference {key} contains people"
            )
        contains_people = definition.get("contains_people", False)
        if not isinstance(contains_people, bool):
            raise ValueError(f"reference {key}.contains_people must be a boolean")
        contains_text = definition.get("contains_text", False)
        if not isinstance(contains_text, bool):
            raise ValueError(f"reference {key}.contains_text must be a boolean")
        if contains_text:
            raise ValueError(
                f"scene {scene_id} reference {key} contains text; use an atomic text-free reference"
            )
        panel_count = definition.get("panel_count", 1)
        if isinstance(panel_count, bool) or not isinstance(panel_count, int) or panel_count < 1:
            raise ValueError(f"reference {key}.panel_count must be a positive integer")
        if panel_count > 1:
            raise ValueError(
                f"scene {scene_id} reference {key} is composite (panel_count={panel_count}); "
                "use an atomic reference"
            )

        normalized_bindings.append(
            {
                "key": key,
                "capabilities": capabilities,
                "instruction": instruction,
                "capability_overrides": capability_overrides,
                "identity_owners": owners,
            }
        )

    bound_keys = {binding["key"] for binding in normalized_bindings}
    for identity_key in allowed:
        missing = sorted(set(identities[identity_key]["reference_keys"]) - bound_keys)
        if missing:
            raise ValueError(
                f"scene {scene_id} is missing required references for identity "
                f"{identity_key}: {missing}"
            )

    constraints = require_string_list(
        raw_scene.get("constraints", []),
        f"scene {scene_id}.constraints",
    )
    return {
        "cast": {
            "mode": mode,
            "allowed_identities": allowed,
            "generic_roles": roles,
        },
        "references": normalized_bindings,
        "composition_mode": composition_mode,
        "constraints": constraints,
    }


def capability_instruction(definition: dict, reference_key: str, capability: str) -> str:
    raw = definition["capabilities"][capability]
    if isinstance(raw, str):
        return require_string(raw, f"reference {reference_key} capability {capability}")
    if isinstance(raw, dict):
        return require_string(
            raw.get("instruction"),
            f"reference {reference_key} capability {capability}.instruction",
        )
    raise ValueError(
        f"reference {reference_key} capability {capability} must be a string or object"
    )


def v2_reference_instruction(binding: dict, definitions: dict) -> str:
    if binding["instruction"] is not None:
        return binding["instruction"]
    definition = definitions[binding["key"]]
    instructions = []
    for capability in binding["capabilities"]:
        instructions.append(
            binding["capability_overrides"].get(
                capability,
                capability_instruction(definition, binding["key"], capability),
            )
        )
    return " ".join(instructions)


def input_paragraph_v2(bindings: list[dict], definitions: dict) -> str:
    lines = [
        "Input images, exact indexed mapping:",
        "- Image 1: approved black-and-white series style reference; use only uneven line behavior and simplified anatomy, never its people, text, or scene.",
        "- Image 2: approved selective-color series style reference; use only muted crayon palette, white field, and material rendering, never its people, text, or scene.",
    ]
    for index, binding in enumerate(bindings, start=3):
        capabilities = binding["capabilities"]
        capability_label = ", ".join(capabilities) if capabilities else "scene-local instruction"
        lines.append(
            f"- Image {index}: scene-local binding `{binding['key']}`; allowed capabilities: "
            f"{capability_label}. {v2_reference_instruction(binding, definitions)}"
        )
    lines.append(
        "Ignore all text in every reference. Use each reference only for its scene-local "
        "allowed capabilities; never import its people, identities, layout, or unlisted objects."
    )
    return "\n".join(lines)


def replace_character_lock(prompt: str, replacement: str) -> str:
    pattern = r"^Character lock:.*?(?=^Style:)"
    updated, count = re.subn(
        pattern,
        "Character lock: scene-local isolation contract.\n" + replacement + "\n",
        prompt,
        count=1,
        flags=re.MULTILINE | re.DOTALL,
    )
    if count != 1:
        raise ValueError("prompt does not contain one replaceable Character lock section")
    return updated


def apply_scene_local_template_language(prompt: str) -> str:
    updated = prompt.replace(
        LOCKED_PROTAGONIST_SENTENCE,
        SCENE_CONTRACT_SENTENCE,
        1,
    )
    updated = updated.replace(
        FIXED_CHARACTER_SHEET_SENTENCE,
        SCENE_LOCAL_CONTINUITY_SENTENCE,
        1,
    )
    return updated


def scene_contract_paragraph(
    scene_id: str,
    scene: dict,
    identities: dict[str, dict],
    global_prompt: str,
) -> str:
    cast = scene["cast"]
    lines = [
        f"Scene ID: {scene_id}.",
        f"Cast mode: {cast['mode']}.",
    ]
    if cast["mode"] == "anonymous":
        lines.append(
            "Recurring cast count: exactly 0. Use only the generic roles declared below."
        )
    else:
        lines.append(
            f"Allowed recurring identity count: exactly {len(cast['allowed_identities'])}."
        )
        for identity_key in cast["allowed_identities"]:
            identity = identities[identity_key]
            lines.append(
                f'Allowed recurring identity "{identity["name"]}": '
                f'{identity["positive_prompt"]}'
            )
        lines.append("No other recurring identity is allowed.")

    total_generic = sum(role["count"] for role in cast["generic_roles"])
    lines.append(f"Total generic figure count: exactly {total_generic}.")
    for role in cast["generic_roles"]:
        line = f'Generic role "{role["role"]}": exactly {role["count"]}.'
        if role["description"]:
            line += f" {role['description']}"
        lines.append(line)

    lines.append(COMPOSITION_PROMPTS[scene["composition_mode"]])
    if global_prompt:
        lines.append(f"Global world/style continuity: {global_prompt}")
    for constraint in scene["constraints"]:
        lines.append(f"Scene constraint: {constraint}")
    return "\n".join(lines)


def identity_lint_tokens(identity_key: str, identity: dict) -> list[str]:
    # Identity keys are schema handles, not necessarily story fingerprints.
    # A key such as "other" or "mother" may be ordinary prose in an unrelated
    # scene, so only declared display names and explicit fingerprints are safe
    # semantic leak detectors. Reference-key/path leakage is checked separately.
    tokens = [identity["name"]]
    tokens.extend(token for token in identity["fingerprints"] if len(token) >= 3)
    return sorted(set(tokens))


def lint_v2_prompt(
    scene_id: str,
    prompt: str,
    scene: dict,
    identities: dict[str, dict],
    reference_definitions: dict,
    expected_references: list[str],
    style_paths: list[str],
) -> None:
    cast = scene["cast"]
    allowed = set(cast["allowed_identities"])

    for identity_key, identity in identities.items():
        tokens = identity_lint_tokens(identity_key, identity)
        if identity_key in allowed:
            if prompt.count(identity["positive_prompt"]) != 1:
                raise ValueError(
                    f"scene {scene_id} must contain exactly one positive block for "
                    f"identity {identity_key}"
                )
            continue
        leaked = [token for token in tokens if token in prompt]
        if leaked:
            raise ValueError(
                f"scene {scene_id} prompt leaks forbidden identity {identity_key}: {leaked}"
            )

    if cast["mode"] == "anonymous":
        if "Allowed recurring identity \"" in prompt:
            raise ValueError(f"anonymous scene {scene_id} contains a named identity block")
        if "Recurring cast count: exactly 0." not in prompt:
            raise ValueError(f"anonymous scene {scene_id} is missing zero-recurring-cast lock")
    else:
        if prompt.count("Allowed recurring identity \"") != len(allowed):
            raise ValueError(
                f"named scene {scene_id} identity block count does not match allowlist"
            )

    identity_paths: dict[str, set[str]] = {}
    identity_path_tokens: dict[str, set[str]] = {}
    for reference_key, definition in reference_definitions.items():
        owners = reference_identity_owners(reference_key, definition, identities)
        if owners:
            raw_path = require_string(
                definition.get("path"),
                f"reference {reference_key}.path",
            )
            resolved_path = str(resolve_path(raw_path).resolve())
            identity_paths[resolved_path] = owners
            identity_path_tokens[resolved_path] = owners
            identity_path_tokens[raw_path] = owners
    for path in expected_references:
        owners = identity_paths.get(path, set())
        if cast["mode"] == "anonymous" and owners:
            raise ValueError(
                f"anonymous scene {scene_id} references identity path {path}: {sorted(owners)}"
            )
        forbidden = sorted(owners - allowed)
        if forbidden:
            raise ValueError(
                f"scene {scene_id} references forbidden identity path {path}: {forbidden}"
            )
    for path_token, owners in identity_path_tokens.items():
        if path_token not in prompt:
            continue
        forbidden = sorted(owners if cast["mode"] == "anonymous" else owners - allowed)
        if forbidden:
            raise ValueError(
                f"scene {scene_id} prompt contains forbidden identity path "
                f"{path_token}: {forbidden}"
            )
    if any(path in identity_paths for path in style_paths):
        raise ValueError("style references must not also be declared as identity references")

    expected_total = sum(role["count"] for role in cast["generic_roles"])
    total_line = f"Total generic figure count: exactly {expected_total}."
    if prompt.count(total_line) != 1:
        raise ValueError(f"scene {scene_id} is missing exact generic figure total")
    for role in cast["generic_roles"]:
        role_line = f'Generic role "{role["role"]}": exactly {role["count"]}.'
        if prompt.count(role_line) != 1:
            raise ValueError(
                f"scene {scene_id} is missing exact count for generic role {role['role']!r}"
            )

    composition_line = COMPOSITION_PROMPTS[scene["composition_mode"]]
    if prompt.count(composition_line) != 1:
        raise ValueError(
            f"scene {scene_id} is missing composition mode {scene['composition_mode']}"
        )
    other_modes = [
        text
        for mode, text in COMPOSITION_PROMPTS.items()
        if mode != scene["composition_mode"] and text in prompt
    ]
    if other_modes:
        raise ValueError(f"scene {scene_id} contains conflicting composition modes")
    if LOCKED_PROTAGONIST_SENTENCE in prompt or FIXED_CHARACTER_SHEET_SENTENCE in prompt:
        raise ValueError(f"scene {scene_id} retains episode-wide identity template text")
    if prompt.count("Character lock: scene-local isolation contract.") != 1:
        raise ValueError(f"scene {scene_id} is missing one scene-local character lock")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("episode_dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    episode_dir = args.episode_dir.resolve()
    manifest_path = episode_dir / "codex-image-jobs.json"
    map_path = episode_dir / "reference-map.json"
    manifest = load_json(manifest_path)
    mapping = load_json(map_path)

    schema_version = mapping.get("schema_version")
    if schema_version not in {1, 2}:
        raise ValueError("reference-map.json schema_version must be 1 or 2")

    definitions = mapping["references"]
    if not isinstance(definitions, dict):
        raise ValueError("reference-map.json references must be an object")
    identity_mode = mapping.get("identity_mode", "locked") if schema_version == 1 else "scene-local"
    discard_reference_jobs = bool(mapping.get("discard_reference_jobs", False))
    manifest_jobs = manifest.get("jobs", [])
    reference_jobs = [job for job in manifest_jobs if job.get("role") == "reference"]
    reference_jobs_by_id = {job.get("id"): job for job in reference_jobs}
    resolved = {}
    for key, definition in definitions.items():
        path = resolve_path(definition["path"]).resolve()
        if not path.is_file():
            generated_by_job = definition.get("generated_by_job")
            producer = reference_jobs_by_id.get(generated_by_job)
            if not producer:
                upstream_owner = definition.get("execution_owner")
                local_owner = f"episode{episode_dir.name}"
                is_declared_upstream_dependency = (
                    schema_version == 2
                    and definition.get("status")
                    == "contract_ready_atomic_image_pending_provider"
                    and isinstance(generated_by_job, str)
                    and bool(generated_by_job)
                    and isinstance(upstream_owner, str)
                    and upstream_owner.startswith("episode")
                    and upstream_owner != local_owner
                    and definition.get("sha256") is None
                )
                if not is_declared_upstream_dependency:
                    raise FileNotFoundError(f"reference {key} is missing: {path}")
                resolved[key] = str(path)
                continue
            producer_output = Path(producer.get("output_master", "")).resolve()
            if producer_output != path:
                raise ValueError(
                    f"reference {key} expects {path}, but producer job "
                    f"{generated_by_job!r} writes {producer_output}"
                )
        resolved[key] = str(path)
        if schema_version == 2 and definition.get("sha256") is not None:
            expected_sha256 = require_string(
                definition["sha256"],
                f"reference {key}.sha256",
            )
            actual_sha256 = sha256_file(path)
            if actual_sha256 != expected_sha256:
                raise ValueError(
                    f"reference {key} sha256 mismatch: expected {expected_sha256}, "
                    f"got {actual_sha256}"
                )

    jobs = [job for job in manifest_jobs if job.get("role") == "scene"]
    job_ids = [job["id"] for job in jobs]
    scene_map = mapping["scenes"]
    if set(job_ids) != set(scene_map):
        missing = sorted(set(job_ids) - set(scene_map))
        extra = sorted(set(scene_map) - set(job_ids))
        raise ValueError(f"reference map scene mismatch; missing={missing}, extra={extra}")

    style_paths = [str(resolve_path(path).resolve()) for path in mapping["style_references"]]
    if len(style_paths) != 2 or not all(Path(path).is_file() for path in style_paths):
        raise ValueError("style_references must contain exactly two existing files")

    identities = (
        validate_v2_identities(mapping, definitions)
        if schema_version == 2
        else {}
    )
    global_prompt = ""
    if schema_version == 2 and mapping.get("global_prompt"):
        global_prompt = require_string(mapping["global_prompt"], "global_prompt")

    changed = False
    for job in jobs:
        if schema_version == 1:
            keys = scene_map[job["id"]]
            unknown = [key for key in keys if key not in definitions]
            if unknown:
                raise ValueError(f"scene {job['id']} has unknown references: {unknown}")
            expected_references = style_paths + [resolved[key] for key in keys]
            expected_prompt = replace_input_paragraph(
                job["prompt"],
                input_paragraph(keys, definitions),
            )
            expected_prompt = apply_identity_mode(expected_prompt, identity_mode)
        else:
            scene = validate_v2_scene(
                job["id"],
                scene_map[job["id"]],
                identities,
                definitions,
            )
            expected_references = style_paths + [
                resolved[binding["key"]] for binding in scene["references"]
            ]
            expected_prompt = replace_input_paragraph(
                job["prompt"],
                input_paragraph_v2(scene["references"], definitions),
            )
            expected_prompt = replace_character_lock(
                expected_prompt,
                scene_contract_paragraph(
                    job["id"],
                    scene,
                    identities,
                    global_prompt,
                ),
            )
            expected_prompt = apply_scene_local_template_language(expected_prompt)
            lint_v2_prompt(
                job["id"],
                expected_prompt,
                scene,
                identities,
                definitions,
                expected_references,
                style_paths,
            )
        prompt_path = Path(job["prompt_file"])

        if job.get("references") != expected_references or job["prompt"] != expected_prompt:
            changed = True
        job["references"] = expected_references
        job["prompt"] = expected_prompt

        if args.check:
            if not prompt_path.is_file() or prompt_path.read_text(encoding="utf-8") != expected_prompt:
                raise ValueError(f"prompt file is stale: {prompt_path}")
        else:
            prompt_path.write_text(expected_prompt, encoding="utf-8")

    if discard_reference_jobs and reference_jobs:
        changed = True
        if not args.check:
            manifest["jobs"] = [job for job in manifest_jobs if job.get("role") != "reference"]

    if (
        (schema_version == 1 and "identity_mode" in mapping)
        or schema_version == 2
    ) and manifest.get("identity_mode") != identity_mode:
        changed = True
    if (
        schema_version == 2
        and manifest.get("prompt_isolation_lint") != "passed"
    ):
        changed = True

    manifest["reference_map"] = str(map_path)
    manifest["reference_map_schema_version"] = schema_version
    manifest["identity_mode"] = identity_mode
    if schema_version == 2:
        manifest["prompt_isolation_lint"] = "passed"

    if args.check:
        if changed:
            raise ValueError("manifest references or indexed prompt mappings are stale")
        suffix = " and prompt isolation lint passed" if schema_version == 2 else ""
        print(
            f"PASS {episode_dir.name}: {len(jobs)} scene jobs match "
            f"reference-map.json{suffix}"
        )
        return 0

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    suffix = " with prompt isolation lint" if schema_version == 2 else ""
    print(
        f"Applied scene reference map to {len(jobs)} jobs{suffix}: "
        f"{manifest_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
