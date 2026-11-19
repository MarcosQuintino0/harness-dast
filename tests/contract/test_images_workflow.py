from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contract
ROOT = Path(__file__).resolve().parents[2]


def test_publishes_images_lock_after_both_image_pushes() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/images.yml").read_text(encoding="utf-8"))
    publish = workflow["jobs"]["publish"]
    bundle = workflow["jobs"]["images-lock"]
    expected = {"zap", "scope-proxy"}

    assert {image["key"] for image in publish["strategy"]["matrix"]["include"]} == expected
    assert bundle["needs"] == "publish"
    assert "if" not in bundle

    steps = publish["steps"]
    build = next(index for index, step in enumerate(steps) if step.get("id") == "build")
    transfer = next(
        index for index, step in enumerate(steps) if "IMAGE_DIGEST" in step.get("env", {})
    )
    upload = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert steps[build]["with"]["push"] is True
    assert steps[transfer]["env"]["IMAGE_DIGEST"] == "${{ steps.build.outputs.digest }}"
    assert build < transfer < upload
    assert steps[upload]["with"]["name"] == "image-digest-${{ matrix.key }}"

    steps = bundle["steps"]
    download = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses", "").startswith("actions/download-artifact@")
    )
    write = next(
        index
        for index, step in enumerate(steps)
        if "scripts/write_images_lock.py" in step.get("run", "")
    )
    upload = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert steps[download]["with"]["pattern"] == "image-digest-*"
    assert all(f"/{image}.txt" in steps[write]["run"] for image in expected)
    assert download < write < upload
    assert steps[upload]["with"]["name"] == "images-lock"
    assert steps[upload]["with"]["path"] == "src/harness_dast/adapters/docker/images.lock.json"
    assert steps[upload]["with"]["if-no-files-found"] == "error"
