# Blender MCP for SynthPost

SynthPost development can use the community Blender MCP bridge to inspect and
edit the currently open Blender GUI scene from Codex. The installed integration
is `ahujasid/blender-mcp`, with MCP package `blender-mcp==1.6.5` and the Blender
add-on pinned to upstream commit `e3ece087adecce4242d4dc3e4db28c33010b51c4`.

## Installed paths and configuration

- Blender add-on:
  `~/Library/Application Support/Blender/5.1/scripts/addons/addon.py`
- Codex MCP configuration: `~/.codex/config.toml`
- Local bridge: `localhost:9876`
- Telemetry: disabled with `BLENDER_MCP_DISABLE_TELEMETRY=1`
- Optional external asset/generation integrations: disabled by default

Equivalent Codex registration command:

```bash
codex mcp add blender \
  --env BLENDER_HOST=localhost \
  --env BLENDER_PORT=9876 \
  --env BLENDER_MCP_DISABLE_TELEMETRY=1 \
  -- /opt/homebrew/bin/uvx --from blender-mcp==1.6.5 blender-mcp
```

Verify registration with:

```bash
codex mcp get blender
codex mcp list
```

## Usage

1. Open Blender normally and load the intended SynthPost `.blend` file.
2. The enabled add-on starts its localhost bridge automatically. The 3D View
   sidebar also contains a `BlenderMCP` panel for manual start/stop.
3. Restart Codex after first installation so the new MCP tools are loaded.
4. Ask Codex to inspect the current scene or viewport before authorizing edits.

The server exposes scene inspection, viewport screenshots, and arbitrary Blender
Python execution. Treat it as full control of the open scene: save a new copy
before experiments, never overwrite `blender/avatar_template.blend`, and review
the exact scene/file target before destructive operations.

The initial verification discovered 22 tools and successfully called
`get_scene_info` against Blender 5.1.2. No SynthPost scene was opened or modified
during installation; the verification read Blender's default scene.
