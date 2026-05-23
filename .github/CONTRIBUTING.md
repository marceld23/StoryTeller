# Contributing

Thanks for your interest in Storyteller! This is a small hobby-style project,
so the process is light — please just be considerate and pragmatic.

## Reporting issues

- **Bug?** [Open an issue](https://github.com/marceld23/StoryTeller/issues/new?template=bug_report.md)
  and include what you did, what you expected, what you got, the platform
  (Pi / PC / browser), and ideally a snippet from `data/storyteller.log` or
  `journalctl -u storyteller`.
- **Idea / feature?** [Open a feature request](https://github.com/marceld23/StoryTeller/issues/new?template=feature_request.md).
- **Security issue?** See [SECURITY.md](SECURITY.md) — please don't file a
  public issue for vulnerabilities.

## Pull requests

1. Fork, branch, push.
2. Run the same checks CI runs locally before pushing:
   ```bash
   uv run ruff check .          # lint
   uv run pytest                # tests
   ```
3. Keep changes focused. A small PR that does one thing well lands faster.
4. Open a PR against `main`. The PR template prompts for a short *what /
   why / how it was tested*.

## Local development

`docs/SETUP_PI.md` covers the Pi appliance; `docs/SETUP_PC.md` the PC/dev
setup; `AGENTS.md` documents the conventions the codebase follows (uv
workspaces, layering, no implicit globals, …).

## Scope

Storyteller is intentionally small. Big architectural changes — adding new
backends, new frontends, new providers — are welcome, but please open an
issue first so we can talk about fit before you write a lot of code.
