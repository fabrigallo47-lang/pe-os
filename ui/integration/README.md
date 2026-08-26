# Integration quick start

Run:

```bash
python3 integration/mock_server.py --open
```

The server has no third-party dependencies. It serves `app/` and implements the
same API the production adapters should expose.

Open `app/index.html` directly for demo/offline mode. Use the mock server for
connected-mode testing.
