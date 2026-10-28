# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

A Deep Agents Code (dcode) plugin that reports dcode's lifecycle state to
[herdr](https://herdr.dev) so herdr shows dcode as `idle` / `working` / `blocked`,
notifies on completion or blocks, and resumes the thread after a herdr server restart.

It uses herdr's agent-reported integration model, not a herdr plugin: dcode hooks
shell out to `$HERDR_BIN_PATH pane report-agent` / `pane release-agent`.

Reference docs:

- herdr: https://herdr.dev/docs/add-herdr-support/, https://herdr.dev/docs/agents/
- dcode hooks: https://docs.langchain.com/oss/deepagents/code/hooks
- dcode plugins: https://docs.langchain.com/oss/deepagents/code/plugins

## Layout

```
.claude-plugin/marketplace.json        local dcode marketplace ("herdr-local")
plugins/herdr/.claude-plugin/plugin.json
plugins/herdr/hooks/hooks.json         hook registrations (argv form, no shell)
plugins/herdr/hooks/herdr_report.py    event -> herdr report mapping
```

All behavior lives in `herdr_report.py`. `hooks.json` only routes events to it.

## Invariants (do not break)

- **Never write to stdout.** For `SessionStart` and `UserPromptSubmit`, non-JSON
  stdout is injected into the model's context.
- **Always exit 0 and swallow exceptions.** A non-zero exit surfaces as a hook
  error, and exit 2 blocks prompts or tools.
- **No-op outside herdr.** Do nothing unless `HERDR_ENV=1` and `HERDR_PANE_ID` /
  `HERDR_BIN_PATH` are set.
- **Never block dcode.** Reports are detached `subprocess.Popen` calls. Do not
  wait on herdr.
- **No shell.** Build argv lists only. Validate any payload value (e.g.
  `session_id`) against `_SAFE_ID` before it goes into argv or a file path.
- **`--seq` must increase across processes and restarts.** It uses `time.time_ns()`.
- **Resume argv rules (herdr):** first word is a bare command on `PATH` (`dcode`),
  no apostrophes or control characters, at most 64 args and 8 KiB total.
- **`--source` stays `dcode`.** It must never start with `herdr:`.
- **Stdlib only.** The hook runs under whatever `python3` is on `PATH`, not dcode's venv.
- Hook handler env has names containing `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, or
  `APIKEY` stripped by dcode, so do not rely on such variables.

## Testing

Exercise the script with a fake herdr binary that logs its argv:

```bash
T=$(mktemp -d)
printf '#!/bin/sh\necho "$@" >> "%s/calls.log"\n' "$T" > "$T/fakeherdr"; chmod +x "$T/fakeherdr"
echo '{"hook_event_name":"SessionStart","source":"startup","session_id":"thr_1"}' \
  | HERDR_ENV=1 HERDR_PANE_ID=w1:p1 HERDR_BIN_PATH="$T/fakeherdr" \
    python3 -I plugins/herdr/hooks/herdr_report.py "$T/data"
sleep 1; cat "$T/calls.log"
```

Check that stdout is empty and the exit code is 0 for every case, including invalid JSON.

Validate `hooks.json` with dcode's own loader (path to dcode's venv may differ):

```bash
~/.local/share/uv/tools/deepagents-code/bin/python3 -I -c "
from pathlib import Path
from deepagents_code.hooks.loading import _read_hooks_document
print(_read_hooks_document(Path('plugins/herdr/hooks/hooks.json'))[1])"
```

An empty tuple means no diagnostics.

End to end: install the plugin (see README), run `dcode` in a herdr pane, and
check `herdr agent list` and `herdr pane get "$HERDR_PANE_ID"`.

## Conventions

- When adding an event, update the hook registration in `hooks.json`, the mapping
  in `_state_for`, and the event table in `README.md` together.
- Bump `version` in `plugins/herdr/.claude-plugin/plugin.json` for user-visible changes.
