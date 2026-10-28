# herdr support for Deep Agents Code (dcode)

A dcode plugin that makes dcode a first-class agent in [herdr](https://herdr.dev):
sidebar state (`idle` / `working` / `blocked`), finish and needs-input
notifications, `herdr agent wait`, and resuming the same thread after a herdr
server restart.

It follows herdr's [agent-reported integration](https://herdr.dev/docs/add-herdr-support/)
model: dcode [hooks](https://docs.langchain.com/oss/deepagents/code/hooks) call
`$HERDR_BIN_PATH pane report-agent` / `release-agent`. No herdr plugin or herdr
change is needed. Outside herdr the hook is a no-op.

## Install

```bash
dcode plugin marketplace add flemx/dcode-herdr-plugin
dcode plugin install herdr@herdr-local
```

Or from a running session: `/plugins` → **Marketplaces** → add `flemx/dcode-herdr-plugin`,
then install `herdr`.

Then start a new dcode session (or `/reload` in a running one) inside a herdr pane.

For local development, add a clone instead:
`dcode plugin marketplace add /path/to/dcode-herdr-plugin`.

Requires `python3` on `PATH` (stdlib only) and herdr >= 0.9.2 for resume.

## Event mapping

| dcode hook | herdr report |
| --- | --- |
| `SessionStart` (startup/resume/clear/compact) | `idle` + resume command `dcode -r <thread_id>` |
| `UserPromptSubmit` | `working` |
| `PermissionRequest`, `Notification` `permission_prompt` / `agent_needs_input` / `elicitation_dialog` | `blocked` |
| `PostToolUse`, `Notification` `elicitation_response` / `elicitation_complete` | `working` |
| `Notification` `agent_completed` | `idle` |
| `SessionEnd` `prompt_input_exit` / `other` | `release-agent` |
| `SessionEnd` `clear` / `resume` | nothing (the following `SessionStart` reports the new thread) |

Reports are fire-and-forget subprocesses with a nanosecond `--seq`, so they never
slow dcode down and late reports cannot overwrite newer state. Repeated identical
states (e.g. many `PostToolUse` calls) are deduplicated through a small file in the
plugin data directory.

## Verify

```bash
herdr pane get "$HERDR_PANE_ID"   # from inside the dcode pane, via ! or another shell
herdr agent list
```

Test restore in an isolated session: `herdr --session dcode-test`, run `dcode`,
send a prompt, `herdr session stop dcode-test`, then `herdr --session dcode-test`
again. The pane should reopen with `dcode -r <thread_id>`.

## Known limitations

- `agent_completed` is only sent when a turn ends cleanly. If you interrupt a turn
  with `Esc`, the pane may stay `working` until the next prompt or session event.
- The resume command is `dcode -r <thread_id>` only. It does not pin `-M` or `-a`
  flags, matching dcode's own printed resume hint.
