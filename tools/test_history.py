"""HistoryStore regression checks (run with the packaged Python dependencies)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from gui.history import HistoryStore


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="formulaocr-history-test-"))
    store = HistoryStore(root, limit=20)
    record = store.create_local(
        b"png-bytes",
        local_raw_latex=r"x_{}",
        local_draft_latex=r"x_{}",
        local_render_error=None,
    )
    assert Path(record.image_path).is_file()
    store.update_draft(record.id, "local", r"x_{1}^{2}")
    store.update_api(
        record.id,
        api_raw_latex=r"x^2",
        api_draft_latex=r"x^{2}",
        api_profile_name="test",
        api_model="model",
        api_render_error=None,
    )
    loaded = store.get(record.id)
    assert loaded is not None and loaded.has_api
    assert loaded.local_draft_latex == r"x_{1}^{2}"
    store.set_active_source(record.id, "api")
    assert store.get(record.id).active_source == "api"  # type: ignore[union-attr]
    assert store.delete(record.id)
    assert not store.list_records()
    for index in range(21):
        store.create_local(
            f"png-{index}".encode(),
            local_raw_latex=str(index),
            local_draft_latex=str(index),
            local_render_error=None,
        )
    assert len(store.list_records()) == 20
    store.close()
    print("history store: PASS")


if __name__ == "__main__":
    main()
