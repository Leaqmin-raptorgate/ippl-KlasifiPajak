# Definition of done

A story is done when all of these are true:

- Behavior is covered by a test you can run with `pytest` or `docker compose run --rm test`.
- You can explain every number the story produces.
- Tax amounts come from `src/klasifipajak/engine/`. No model call sits on that path.
- Public functions have a docstring. Indentation is 4 spaces.
- Secrets are not in the repo. `.env` stays local.
- The backlog status is updated in the same change.
