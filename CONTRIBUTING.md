# Contributing

Bug fixes, NAS installation improvements, documentation, and focused feature changes are welcome.

1. Search existing issues before opening a new one.
2. Create a branch from `master`.
3. Keep changes scoped and update documentation when behavior or environment variables change.
4. Run the verification commands below.
5. Open a pull request with the problem, approach, and test evidence.

```shell
python3 -m py_compile youtube-dl-server.py upd_schedule.py
node --check static/logical_js/logic.js
pytest -q
docker compose --env-file .env.example config
git diff --check
```

Do not include credentials, cookies, downloaded media, or private URLs in commits, logs, screenshots, or issues.
