"""Smoke-test the packaged protocol in disposable storage (never user history)."""
import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    resources = args.app / "Contents/Resources"
    with tempfile.TemporaryDirectory(prefix="formulaocr-packaged-check-") as directory:
        env = {**os.environ, "FORMULAOCR_DATA_ROOT": directory, "FORMULAOCR_STAGE_ROOT": directory,
               "FORMULAOCR_MODEL_PATH": str(resources / "pp_formulanet_plus_l.onnx"), "FORMULAOCR_KEYCHAIN_SERVICE":"FormulaOCR Test"}
        process = subprocess.Popen([str(resources / "formulaocr-sidecar/formulaocr-sidecar")], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        replies = {}
        def send(id, method, params=None):
            process.stdin.write(json.dumps({"id":id,"method":method,"params":params or {}}) + "\n")
            process.stdin.flush()
        def receive(id):
            while id not in replies:
                line = process.stdout.readline()
                if not line:
                    raise RuntimeError("Sidecar exited: " + process.stderr.read()[-1000:])
                value = json.loads(line)
                replies[value["id"]] = value
            value = replies[id]
            assert value["ok"], value
            return value["result"]
        try:
            started = time.perf_counter()
            send("load", "ocr.preload")
            send("health", "system.health")
            receive("health")
            health_ms = (time.perf_counter() - started) * 1000
            staged = Path(directory) / "sample.png"
            staged.write_bytes(args.image.read_bytes())
            send("image", "image.openPath", {"path":str(staged)})
            image = receive("image")
            assert not staged.exists()
            receive("load")
            started = time.perf_counter()
            send("ocr", "ocr.recognize", {"image_id":image["image_id"], "mode":"chemistry"})
            send("settings", "settings.get")
            receive("settings")
            control_ms = (time.perf_counter() - started) * 1000
            result = receive("ocr")
            send("conversion", "conversion.toMathML", {"latex":result["formatted_latex"]})
            assert receive("conversion")["mathml"].startswith("<math")
            send("release", "image.release", {"image_id":image["image_id"]})
            receive("release")
            send("quit", "system.shutdown")
            receive("quit")
            process.wait(timeout=10)
            assert process.returncode == 0
            print(json.dumps({"health_ms":round(health_ms,1), "control_during_ocr_ms":round(control_ms,1), "ocr_ms":round(result["elapsed_ms"],1), "preview":True, "exit":process.returncode}))
        finally:
            if process.poll() is None:
                process.kill(); process.wait()

if __name__ == "__main__":
    main()
