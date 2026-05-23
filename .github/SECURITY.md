# Security Policy

Storyteller is a small hobby project, but if you find something that looks
like a security issue, please report it **privately** instead of opening a
public issue.

## How to report

- **Preferred:** open a [private security advisory](https://github.com/marceld23/StoryTeller/security/advisories/new)
  on GitHub. The maintainer is notified and the discussion stays private
  until a fix is ready.
- Or: email the maintainer (address in the latest commits' author field).

Please include enough detail to reproduce the issue — affected component
(Pi voice loop / web admin / web player / CLI / core), version/commit, and
steps to trigger it.

## Scope

Things worth reporting:

- Unauthenticated access to the admin or player web UIs / WebSockets.
- Token leakage via logs or transcripts.
- Path traversal, command injection, or SSRF in any backend route.
- Prompt-injection paths that bypass the moderation gate in a way that
  could cause real harm beyond "the narrator says weird things".

Things that are **not** in scope:

- The narrator producing inappropriate fiction despite moderation — that's
  a tuning issue; please open a regular issue with the prompt that did it.
- Anything that requires already-root / already-on-the-Pi access.

## Response

This is a one-person hobby project, so expect best-effort, not SLAs. I'll
acknowledge within a few days and try to ship a fix in a reasonable timeframe
depending on severity.
