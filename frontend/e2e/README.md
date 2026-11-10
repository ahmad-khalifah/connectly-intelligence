# End-to-end tests

These run in a real browser against a running stack with the boundary data loaded
(`connectly bootstrap`). CI runs them against the Docker Compose stack (see
`.github/workflows/ci.yml`, job `stack`).

They need a fresh admin account created with `connectly users create`, and its temporary
password:

```bash
E2E_EMAIL=admin@example.org E2E_TEMP_PASSWORD='<printed password>' \
E2E_NEW_PASSWORD='a-long-test-passphrase' npx playwright test
```

The tests create one organisation and solution named "E2E test ..." in the directory and
retire them at the end. Run them against a disposable database, not production.
