#!/usr/bin/env python3
"""Inspect a binary glTF avatar without loading Blender or third-party packages.

The command is intentionally read-only and emits either a concise text report or
machine-readable JSON.  It understands GLB 2.0 JSON chunks, morph target names,
skin joint lists, animation input accessors, material texture slots, and an
optional adjacent source-texture tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any


GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_glb_json(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise ValueError(f"Not a GLB file (short header): {path}")
        magic, version, declared_length = struct.unpack("<III", header)
        if magic != GLB_MAGIC:
            raise ValueError(f"Not a GLB file (bad magic): {path}")
        if version != 2:
            raise ValueError(f"Unsupported GLB version {version}: {path}")
        if declared_length != path.stat().st_size:
            raise ValueError(
                f"GLB length mismatch: header={declared_length}, file={path.stat().st_size}"
            )

        while handle.tell() < declared_length:
            chunk_header = handle.read(8)
            if len(chunk_header) != 8:
                raise ValueError(f"Malformed GLB chunk header: {path}")
            chunk_length, chunk_type = struct.unpack("<II", chunk_header)
            payload = handle.read(chunk_length)
            if len(payload) != chunk_length:
                raise ValueError(f"Malformed GLB chunk payload: {path}")
            if chunk_type == JSON_CHUNK:
                parsed = json.loads(payload.rstrip(b"\x00 \t\r\n").decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise ValueError(f"GLB JSON root is not an object: {path}")
                return parsed
    raise ValueError(f"GLB has no JSON chunk: {path}")


def _texture_slots(material: dict[str, Any]) -> dict[str, int]:
    slots: dict[str, int] = {}
    pbr = material.get("pbrMetallicRoughness") or {}
    for slot, value in (
        ("baseColor", pbr.get("baseColorTexture")),
        ("metallicRoughness", pbr.get("metallicRoughnessTexture")),
        ("normal", material.get("normalTexture")),
        ("occlusion", material.get("occlusionTexture")),
        ("emissive", material.get("emissiveTexture")),
    ):
        if isinstance(value, dict) and isinstance(value.get("index"), int):
            slots[slot] = value["index"]
    return slots


def _animation_duration(animation: dict[str, Any], accessors: list[dict[str, Any]]) -> float:
    duration = 0.0
    for sampler in animation.get("samplers") or []:
        accessor_index = sampler.get("input")
        if not isinstance(accessor_index, int) or accessor_index >= len(accessors):
            continue
        accessor = accessors[accessor_index]
        maximum = accessor.get("max")
        if isinstance(maximum, list) and maximum:
            # AnimationClip duration is the greatest keyframe time.  A one-key
            # export can start at 1/FPS, so subtracting min would incorrectly
            # report a zero-length clip.
            duration = max(duration, float(maximum[0]))
    return duration


def _source_texture_kind(path: Path) -> str:
    name = path.stem.lower().replace(" ", "_")
    rules = (
        ("wrinkle_flow", "wrinkle_flow"),
        ("wrinkle_roughness", "wrinkle_roughness"),
        ("wrinkle_normal", "wrinkle_normal"),
        ("wrinkle_diffuse", "wrinkle_diffuse"),
        ("micronmask", "micro_normal_mask"),
        ("micro_n", "micro_normal"),
        ("micron", "micro_normal"),
        ("sssmap", "sss"),
        ("transmap", "transmission"),
        ("specmask", "specular"),
        ("roughness", "roughness"),
        ("_ao", "ao"),
        ("normal", "normal"),
        ("_n", "normal"),
        ("diffuse", "base_color"),
        ("basecolor", "base_color"),
        ("base_color", "base_color"),
        ("flow_map", "hair_flow"),
        ("flowmap", "hair_flow"),
        ("root_map", "hair_root"),
        ("id_map", "hair_id"),
        ("weightmap", "hair_weight"),
        ("metallic", "metallic"),
        ("opacity", "opacity"),
        ("transparency", "opacity"),
    )
    for needle, kind in rules:
        if needle in name:
            return kind
    return "other"


def inspect_avatar(glb_path: Path, source_textures: Path | None = None) -> dict[str, Any]:
    document = load_glb_json(glb_path)
    nodes = document.get("nodes") or []
    meshes = document.get("meshes") or []
    materials = document.get("materials") or []
    textures = document.get("textures") or []
    images = document.get("images") or []
    skins = document.get("skins") or []
    accessors = document.get("accessors") or []

    morph_names: set[str] = set()
    morph_target_sets = 0
    mesh_summaries: list[dict[str, Any]] = []
    for index, mesh in enumerate(meshes):
        target_names = list((mesh.get("extras") or {}).get("targetNames") or [])
        morph_names.update(str(name) for name in target_names)
        primitive_target_count = sum(
            len(primitive.get("targets") or []) for primitive in mesh.get("primitives") or []
        )
        morph_target_sets += primitive_target_count
        mesh_summaries.append(
            {
                "index": index,
                "name": mesh.get("name") or f"mesh_{index}",
                "primitive_count": len(mesh.get("primitives") or []),
                "morph_target_name_count": len(target_names),
                "morph_target_set_count": primitive_target_count,
            }
        )

    joint_indices = sorted(
        {
            int(joint)
            for skin in skins
            for joint in skin.get("joints") or []
            if isinstance(joint, int)
        }
    )
    bone_names = [
        str(nodes[index].get("name") or f"node_{index}")
        for index in joint_indices
        if 0 <= index < len(nodes)
    ]

    animation_summaries = [
        {
            "name": animation.get("name") or f"animation_{index}",
            "duration_seconds": round(_animation_duration(animation, accessors), 6),
            "channel_count": len(animation.get("channels") or []),
        }
        for index, animation in enumerate(document.get("animations") or [])
    ]

    material_summaries = [
        {
            "index": index,
            "name": material.get("name") or f"material_{index}",
            "texture_slots": _texture_slots(material),
            "alpha_mode": material.get("alphaMode", "OPAQUE"),
            "double_sided": bool(material.get("doubleSided", False)),
            "extensions": sorted((material.get("extensions") or {}).keys()),
        }
        for index, material in enumerate(materials)
    ]

    image_names = [
        str(image.get("name") or image.get("uri") or f"image_{index}")
        for index, image in enumerate(images)
    ]
    embedded_image_stems = {Path(name).stem.lower() for name in image_names}

    source_files: list[Path] = []
    if source_textures and source_textures.exists():
        source_files = sorted(
            path
            for path in source_textures.rglob("*")
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tga", ".bmp"}
        )
    source_kind_counts = Counter(_source_texture_kind(path) for path in source_files)
    missing_source = [
        path.relative_to(source_textures).as_posix()
        for path in source_files
        if Path(path.name).stem.lower() not in embedded_image_stems
    ] if source_textures else []

    return {
        "schema_version": "avatar_asset_inspection_v1",
        "asset": {
            "path": glb_path.as_posix(),
            "size_bytes": glb_path.stat().st_size,
            "sha256": sha256_file(glb_path),
            "generator": (document.get("asset") or {}).get("generator"),
            "gltf_version": (document.get("asset") or {}).get("version"),
        },
        "counts": {
            "scenes": len(document.get("scenes") or []),
            "nodes": len(nodes),
            "meshes": len(meshes),
            "materials": len(materials),
            "textures": len(textures),
            "images": len(images),
            "skins": len(skins),
            "bones": len(joint_indices),
            "animations": len(animation_summaries),
            "unique_morph_targets": len(morph_names),
            "primitive_morph_target_sets": morph_target_sets,
        },
        "meshes": mesh_summaries,
        "materials": material_summaries,
        "images": image_names,
        "morph_targets": sorted(morph_names),
        "bones": bone_names,
        "animations": animation_summaries,
        "extensions_used": sorted(document.get("extensionsUsed") or []),
        "source_textures": {
            "root": source_textures.as_posix() if source_textures else None,
            "count": len(source_files),
            "bytes": sum(path.stat().st_size for path in source_files),
            "semantic_counts": dict(sorted(source_kind_counts.items())),
            "missing_from_glb_count": len(missing_source),
            "missing_from_glb": missing_source,
        },
    }


def _print_text(report: dict[str, Any]) -> None:
    asset = report["asset"]
    counts = report["counts"]
    source = report["source_textures"]
    print(f"Asset: {asset['path']}")
    print(f"Size: {asset['size_bytes']} bytes")
    print(f"SHA-256: {asset['sha256']}")
    print(f"Generator: {asset.get('generator') or 'unknown'}")
    print(
        "Counts: "
        + ", ".join(f"{key}={value}" for key, value in counts.items())
    )
    print("Animations:")
    for animation in report["animations"]:
        print(f"  {animation['name']}: {animation['duration_seconds']:.6f}s")
    if source["root"]:
        print(
            f"Source textures: {source['count']} files, {source['bytes']} bytes; "
            f"{source['missing_from_glb_count']} filenames not embedded"
        )
        print(
            "Source texture kinds: "
            + ", ".join(f"{key}={value}" for key, value in source["semantic_counts"].items())
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("glb", type=Path, help="Path to a GLB 2.0 file")
    parser.add_argument(
        "--source-textures",
        type=Path,
        help="Optional adjacent source texture directory to compare with embedded images",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--output", type=Path, help="Write report to this path")
    args = parser.parse_args(argv)

    try:
        report = inspect_avatar(args.glb, args.source_textures)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"inspect_avatar_asset: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(report, indent=2) + "\n" if args.json else None
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if rendered is None:
            rendered = json.dumps(report, indent=2) + "\n"
        args.output.write_text(rendered, encoding="utf-8")
    if args.json:
        sys.stdout.write(rendered or "")
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
