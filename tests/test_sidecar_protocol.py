"""Headless checks for the Tauri JSON-lines sidecar foundation."""

import base64
import json
import os
import subprocess
import sys
import io
from pathlib import Path


def test_sidecar_health_and_shutdown(tmp_path: Path):
    env = os.environ.copy()
    env["FORMULAOCR_DATA_ROOT"] = str(tmp_path / "data")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.Popen(
        [sys.executable, "-m", "sidecar"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(json.dumps({"id": "health", "method": "system.health", "params": {}}) + "\n")
    process.stdin.write(json.dumps({"id": "stop", "method": "system.shutdown", "params": {}}) + "\n")
    process.stdin.flush()
    responses = {item["id"]: item for item in [json.loads(process.stdout.readline()), json.loads(process.stdout.readline())]}
    process.wait(timeout=5)
    assert responses["health"]["ok"] is True
    assert responses["health"]["result"]["protocol"] == 1
    assert responses["stop"]["ok"] is True


def test_sidecar_image_lifecycle(tmp_path: Path):
    from sidecar.server import Sidecar

    old = os.environ.get("FORMULAOCR_DATA_ROOT")
    os.environ["FORMULAOCR_DATA_ROOT"] = str(tmp_path / "data")
    try:
        service = Sidecar()
        image_id = "test-image"
        from PIL import Image
        stream = io.BytesIO()
        Image.new("RGB", (4, 3), "white").save(stream, format="PNG")
        png = stream.getvalue()
        opened = service.dispatch("image.open", {"image_id": image_id, "png_base64": base64.b64encode(png).decode()})
        assert opened["image_id"] == image_id
        image = service._image({"image_id": image_id})
        assert image.size == (4, 3)
        service.dispatch("image.release", {"image_id": image_id})
        try:
            service._image({"image_id": image_id})
        except ValueError:
            pass
        else:
            raise AssertionError("released image remained available")
        service.close()
    finally:
        if old is None:
            os.environ.pop("FORMULAOCR_DATA_ROOT", None)
        else:
            os.environ["FORMULAOCR_DATA_ROOT"] = old


def test_sidecar_staged_path_is_scoped_and_deleted(tmp_path: Path):
    from sidecar.server import Sidecar

    data_root = tmp_path / "data"
    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    old_data = os.environ.get("FORMULAOCR_DATA_ROOT")
    old_stage = os.environ.get("FORMULAOCR_STAGE_ROOT")
    os.environ["FORMULAOCR_DATA_ROOT"] = str(data_root)
    os.environ["FORMULAOCR_STAGE_ROOT"] = str(stage_root)
    try:
        from PIL import Image
        staged = stage_root / "capture.png"
        Image.new("RGB", (5, 2), "white").save(staged)
        service = Sidecar()
        opened = service.dispatch("image.openPath", {"path": str(staged)})
        assert not staged.exists()
        assert service._image({"image_id": opened["image_id"]}).size == (5, 2)
        outside = tmp_path / "outside.png"
        Image.new("RGB", (1, 1), "white").save(outside)
        try:
            service.dispatch("image.openPath", {"path": str(outside)})
        except ValueError as error:
            assert "outside" in str(error)
        else:
            raise AssertionError("out-of-scope staged image was accepted")
        service.close()
    finally:
        if old_data is None: os.environ.pop("FORMULAOCR_DATA_ROOT", None)
        else: os.environ["FORMULAOCR_DATA_ROOT"] = old_data
        if old_stage is None: os.environ.pop("FORMULAOCR_STAGE_ROOT", None)
        else: os.environ["FORMULAOCR_STAGE_ROOT"] = old_stage
