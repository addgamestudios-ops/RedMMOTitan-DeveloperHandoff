# RedMMO Character Creator 5 local MCP bridge

This is a deliberately small bridge between an external Model Context Protocol
server and Reallusion Character Creator 5.11.  It replaces screenshot-only
automation for a narrow set of character-shaping operations without exposing a
generic Python console.

## Current verification state

| Layer | State |
|---|---|
| Installed CC host | Statically identified as Character Creator 5.11 at `D:\cc5\Character Creator 5` |
| Installed scripting API | CC5's CPython 3.8 `RLPy.py` and `_RLPy.pyd` signatures inspected |
| External MCP SDK | Source targets official stable `mcp==1.28.1`; dependencies were not installed by this work |
| Protocol and security tests | 33 focused offline/native-Windows tests pass |
| Plugin installation | A pre-final-review revision is installed and running through manual `Script > Load Python`; it must not be hot-reloaded with the current source |
| Local runtime | Private ACL and authenticated heartbeat verified; read-only inspect and paginated morph listing succeeded on a disposable Brute scene |
| MCP/Codex configuration | Not changed |
| Live CC5 morph or save operation | None; the live allowlist is empty and no save request was issued |

The in-CC5 queue path now has bounded read-only runtime evidence. This is not
full MCP, mutation, save, or autoload acceptance: the pinned external MCP SDK
environment is not installed or registered, the host still logs a separate
`main has no attribute rl_plugin` autoload warning, and the reviewed project
source contains reload-ownership, heartbeat-coalescing, and protocol 1.2
named linked-preset support that are not in the running installed copy. The
live protocol 1.0 config also lacks the required empty `linked_presets` field.
Close CC5 before migrating the config and synchronizing that exact reviewed
revision, then restart and repeat the read-only checks.

## Architecture

```text
Codex/MCP client
      |
      | MCP over local process stdin/stdout only
      v
Tools.CC5MCP.server  (external Python >= 3.10)
      |
      | authenticated, bounded JSON files on D:
      v
D:\RedMMOTitanWindowsData\CC5MCPBridge
      |
      | polled on CC5's main thread by RPyTimer
      v
cc5_plugin\main.py  (CC5 embedded Python 3.8 + RLPy)
```

The external server does not import `RLPy`.  The in-CC plugin does not import
the MCP SDK.  This split is required because the installed `_RLPy.pyd` is bound
to CC5's Python 3.8 host while the stable MCP SDK requires modern Python.

## Exposed tools

- `cc5_get_bridge_status`: reads a bounded heartbeat and reports whether it is
  fresh.
- `cc5_inspect_active_character`: inspects exactly one selected avatar.
- `cc5_list_active_character_morphs`: lists Character Creator shaping sliders
  using `RIAvatarShapingComponent`, with category filtering and pagination.
- `cc5_set_approved_morph`: requires the exact character and project-session
  bindings returned by inspection, then sets one alias explicitly mapped to
  one live CC5 morph ID within both configured and live slider limits.
- `cc5_apply_approved_linked_preset`: accepts only a named local preset; that
  preset fixes one exact body alias and one exact head alias to reviewed values,
  requires the inspected character signature plus current character/project
  bindings, authenticates the exact preset and referenced morph definitions
  across the external/plugin config boundary, and rolls both values back if
  either write cannot be verified.
- `cc5_save_project_as`: requires the inspected project-session binding and
  publishes a named `.ccProject` snapshot under the fixed D: output root. It
  rejects path input and cannot replace an existing target. Because CC5's
  `SaveProject` API has no atomic no-overwrite mode, this does not promise that
  the open CC5 session is rebound to the final snapshot name.

There is no tool for arbitrary Python, RLPy methods, shell commands, asset
loading, export, registry access, network access, arbitrary paths, or
overwrite.

## Security boundary

- MCP transport is hard-coded to `stdio`; the server provides no HTTP, SSE, or
  socket option.
- Every public MCP tool rejects unknown input fields. In particular, the linked
  preset tool accepts only character ID, project identity, and preset alias;
  caller-supplied values or expressions are refused before dispatch.
- IPC and saved snapshots are confined to the exact fixed NTFS root
  `D:\RedMMOTitanWindowsData\CC5MCPBridge`.
- The enabled bridge fails closed unless that root has inheritance disabled,
  is owned by the current user, and grants access only to that user, SYSTEM,
  and Builtin Administrators. The config must have one hard link, every
  runtime directory must already exist, and every existing path component
  must be free of junctions and other reparse points.
- Requests and responses use HMAC-SHA256 with a 64-hex local token (the token
  itself is never written into queue messages), plus strict schemas, UUIDv4
  IDs, short expiry, replay checks, atomic writes, size limits, and
  one-operation-per-timer-tick processing.
- Inspection returns a plugin-instance/project-epoch identity and the selected
  avatar's session-scoped `RIObject.GetID()`. Every mutation carries both
  values in its authenticated request and the plugin rechecks them immediately
  before writing, so a delayed request cannot silently target a newly selected
  character or reloaded project.
- Morph writes are denied unless an alias maps to an exact morph ID in the
  reviewed allowlist.  The plugin rechecks the live CC5 min/max and verifies
  the readback.
- Linked body/head presets contain no caller-supplied values or expressions.
  A preset must reference two distinct allowlisted aliases that resolve to two
  distinct morph IDs, bind to one SHA-256 character signature, and keep both
  fixed values inside configured and live ranges. Any partial failure attempts
  and verifies rollback of both prior values.
- Save-as accepts a simple version name and writes first to a private UUID
  staging file. It copies and flushes a complete publish temporary, then uses
  Windows `MoveFileExW` with write-through and without the replace flag. The
  final file's size, SHA-256, and rename identity are verified. If CC5 rebound
  its open session to the staging name, the result says so explicitly and the
  staging file is retained rather than breaking the session.
- Processed requests are moved to `completed`; malformed requests are moved to
  `quarantine`.  They are not silently deleted.
- The bridge never reads the Reallusion user registry.  That registry can
  contain launcher authentication material and is outside this tool's scope.

Treat the bridge token as a local secret.  Do not commit a populated
`config.json`.

The local trust boundary includes processes already running as the same
Windows user and elevated Administrators. The v1 checks are pathname-based and
revalidated before operations, but they do not pin directory handles against a
malicious race by either of those trusted principals. Do not run untrusted
same-user software while the bridge is enabled.

## Reviewed installation and launch procedure

The private runtime tree and an earlier plugin revision have now been created.
These steps remain the reproducible setup contract. Do not repeat or overwrite
working state blindly; compare hashes and close CC5 before replacing plugin
files.

1. Close CC5 before copying a plugin into its installation directory.

2. In a normal unelevated PowerShell owned by the same account that will run
   CC5 and the MCP server, create the exact private storage tree. These ACL
   commands are required;
   the inherited ACL on `D:\RedMMOTitanWindowsData` is intentionally rejected:

   ```powershell
   $bridgeRoot = 'D:\RedMMOTitanWindowsData\CC5MCPBridge'
   $currentSid = `
     ([System.Security.Principal.WindowsIdentity]::GetCurrent()).User.Value
   New-Item -ItemType Directory -Force $bridgeRoot | Out-Null
   icacls $bridgeRoot /inheritance:r
   icacls $bridgeRoot /grant:r `
     "*$($currentSid):(OI)(CI)F" `
     "*S-1-5-18:(OI)(CI)F" `
     "*S-1-5-32-544:(OI)(CI)F"
   @(
     'Queue\requests',
     'Queue\processing',
     'Queue\responses',
     'Queue\completed',
     'Queue\quarantine',
     'queue\status',
     'versions'
   ) | ForEach-Object {
     New-Item -ItemType Directory -Force (Join-Path $bridgeRoot $_) |
       Out-Null
   }
   ```

   Review `icacls $bridgeRoot` before continuing. Do not enable the bridge if
   it names Everyone, Authenticated Users, Builtin Users, or another account.

3. Create the local config and random token:

   ```powershell
   Copy-Item `
     'D:\RedMMOTitan\Tools\CC5MCP\config.example.json' `
     'D:\RedMMOTitanWindowsData\CC5MCPBridge\config.json'
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Replace the token placeholder with the printed 64-hex value.  Leave
   `enabled` as `false` for the first load and leave `morph_allowlist` empty.

4. Review the plugin source, close CC5, then copy only its folder:

   ```powershell
   $pluginSource = 'D:\RedMMOTitan\Tools\CC5MCP\cc5_plugin'
   $pluginTarget = `
     'D:\cc5\Character Creator 5\Bin64\OpenPlugin\RedMMO_CC5_MCP'
   New-Item -ItemType Directory -Force $pluginTarget | Out-Null
   @('__init__.py', 'main.py', 'bridge_core.py', 'windows_security.py') |
     ForEach-Object {
       Copy-Item (Join-Path $pluginSource $_) (Join-Path $pluginTarget $_)
     }
   ```

   CC5's documented convention loads
   `Bin64\OpenPlugin\<plugin>\main.py` through `initialize_plugin()`.  Manual
   `Script > Load Python` can load `main.py` and invoke `run_script()`.

5. Start CC5 once with `enabled: false`. A disabled or invalid configuration
   intentionally creates no queue directories and writes no fallback status
   file. Check CC5's Python console for configuration errors, then close CC5
   before changing installation files.

6. In a separate Python 3.10+ environment, install the reviewed dependency
   only when authorized:

   ```powershell
   python -m pip install -r 'D:\RedMMOTitan\Tools\CC5MCP\requirements.txt'
   ```

7. Before synchronizing protocol 1.2, add `"linked_presets": {}` to an existing
   local config while CC5 is closed. Change `enabled` to `true`, start CC5, load the plugin once with
   `Script > Load Python`, and launch the external server from the repository:

   ```powershell
   Set-Location 'D:\RedMMOTitan'
   python -m Tools.CC5MCP.server
   ```

   The process communicates over stdin/stdout. The currently authenticated
   read-only evidence used the queue client directly; it does not prove the
   pinned external FastMCP environment. Do not add the server to Codex MCP
   configuration until that standalone smoke test passes and configuration is
   explicitly authorized.

## Caricature Mixer allowlisting workflow

The installed HD Caricature Mixer includes Brute character content and named
slider files, but filenames are not guaranteed to equal live RLPy IDs.  Never
guess or category-allow these sliders.

1. Load a disposable Caricature Mixer test project.
2. Select exactly one avatar.
3. Run the inspection and paginated list tools only. Retain the returned
   `character.object_id`, `character.character_signature`, and
   `project.project_identity`; they are intentionally
   invalidated by a CC restart, plugin reload, project load, or relevant path
   change.
4. Review each desired result's `category`, `display_name`, `morph_id`, current
   value, and live min/max.
5. Add an explicit rule to `morph_allowlist`, for example:

   ```json
   {
     "brute_head_reviewed": {
       "morph_id": "EXACT_ID_RETURNED_BY_CC5",
       "minimum": -10.0,
       "maximum": 10.0,
       "label": "Reviewed Brute head shaping test"
     }
   }
   ```

6. Reload the plugin, inspect again for fresh bindings, and test a small
   reversible value on the disposable avatar.
7. Save an explicitly named version with the fresh project identity. Verify
   the reported SHA-256 and inspect the session-rebinding fields before
   continuing work in CC5.

For a reviewed Brute body/head pair, keep both individual rules above and add
one preset. The tool accepts only `preset_alias`; it never accepts the two
values from the caller. The external server computes a digest over the complete
preset and both referenced morph rules; the in-CC5 plugin refuses the request
if its startup-cached definition differs:

```json
{
  "linked_presets": {
    "brute_balanced_reviewed": {
      "required_character_signature": "EXACT_64_HEX_SIGNATURE_FROM_INSPECT",
      "label": "Reviewed Brute body and head pair",
      "body": {
        "morph_alias": "EXACT_REVIEWED_BRUTE_BODY_ALIAS",
        "value": 0.0
      },
      "head": {
        "morph_alias": "EXACT_REVIEWED_BRUTE_HEAD_ALIAS",
        "value": 0.0
      }
    }
  }
}
```

Do not populate that preset until the exact Brute body/head morph IDs and safe
values have been reviewed from live CC5 results. Keep the live preset map empty
until then.

## Compatibility sources

- Installed API authority:
  `D:\cc5\Character Creator 5\Bin64\RLPy.py`
- [Official MCP Python SDK v1 branch](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
- [Official MCP package](https://pypi.org/project/mcp/)
- [Reallusion Python plugin loading convention](https://wiki.reallusion.com/IC_Python_API%3AYour_First_iClone_Python_Plugin)
- [Reallusion CC5 Script menu](https://manual.reallusion.com/Character-Creator-5/Content/ENU/5.0/03-Main-Menu/Menu-Script.htm)
- [Reallusion RFileIO SaveProject API](https://wiki.reallusion.com/IC8_Python_API%3ARLPy_RFileIO)
- [Reallusion CC shaping slider example](https://discussions.reallusion.com/t/slider-morph-settings-in-python/15814)
