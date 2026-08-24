# History regression test

The local history checks were run on 2026-08-15 with the project test runtime:

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/formulaocr-stage-h-venv/bin/python tools/test_history.py
history store: PASS
```

The test covers local record creation, copied image cleanup, draft updates,
merged API metadata, active-source persistence, deletion, and pruning to the
20-record lower bound. GUI smoke coverage also loaded a saved record and
persisted an edited draft without starting a second OCR request.
