#!/usr/bin/env python3
"""Compute the same frame-locked scene timeline used by the Remotion renderer."""

from __future__ import annotations


def _scene_frames(scene: dict, fps: int) -> int:
    frames = round(float(scene["duration_sec"]) * fps)
    if frames < 1:
        raise ValueError(f"{scene.get('id', '(unnamed scene)')}: duration rounds below one frame")
    return frames


def transition_frames(storyboard: dict) -> int:
    """Mirror src/storyboard.ts transitionFramesFor()."""
    project = storyboard["project"]
    scenes = storyboard["scenes"]
    if project.get("transition") != "page-flip" or len(scenes) < 2:
        return 0
    fps = int(project["fps"])
    requested = max(1, round(float(project.get("transition_sec", 0.7)) * fps))
    shortest = min(_scene_frames(scene, fps) for scene in scenes)
    return min(requested, max(1, int(shortest * 0.45)))


def compute_scene_timeline(storyboard: dict) -> tuple[dict[str, dict], float]:
    """Return scene frame/second bounds and the rendered composition duration.

    Remotion rounds every scene to whole frames. Accumulating the editorial
    decimal seconds instead can drift enough to misalign narration cues or
    reject an otherwise valid rendered picture.
    """
    project = storyboard["project"]
    scenes = storyboard["scenes"]
    fps = int(project["fps"])
    if fps < 1:
        raise ValueError("project.fps must be positive")
    if not scenes:
        raise ValueError("storyboard must contain at least one scene")

    overlap_frames = transition_frames(storyboard)
    cursor_frames = 0
    timeline: dict[str, dict] = {}
    for index, scene in enumerate(scenes):
        duration_frames = _scene_frames(scene, fps)
        end_frame = cursor_frames + duration_frames
        timeline[str(scene["id"])] = {
            "start_frame": cursor_frames,
            "end_frame": end_frame,
            "duration_frames": duration_frames,
            "start_sec": cursor_frames / fps,
            "end_sec": end_frame / fps,
        }
        cursor_frames = end_frame
        if index < len(scenes) - 1:
            cursor_frames -= overlap_frames

    return timeline, max(1, cursor_frames) / fps
