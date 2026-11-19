import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from harness_dast.domain.images_lock import ImagesLock


def lock_data() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "version": "1.12.2",
        "images": {
            "zap": {
                "repository": "registry.example:5000/qa/hdast-zap",
                "tag": "1.12.2",
                "digest": "sha256:" + "a" * 64,
            },
            "scope_proxy": {
                "repository": "registry.example/qa/hdast-scope-proxy",
                "tag": "1.12.2",
                "digest": "sha256:" + "b" * 64,
            },
        },
    }


def test_validates_images_when_both_references_are_pinned() -> None:
    lock = ImagesLock.model_validate_json(json.dumps(lock_data()))

    assert lock.images.zap.reference() == "registry.example:5000/qa/hdast-zap:1.12.2@sha256:" + (
        "a" * 64
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["images"]["zap"].update(digest="sha256:" + "a" * 63),
        lambda data: data["images"]["zap"].update(digest="a" * 64),
        lambda data: data["images"]["zap"].update(digest="sha256:" + "z" * 64),
        lambda data: data["images"]["zap"].update(repository="registry.example/zap:latest"),
        lambda data: data["images"]["zap"].update(tag="1.12.3"),
        lambda data: data["images"]["zap"].pop("digest"),
        lambda data: data["images"].pop("scope_proxy"),
        lambda data: data.update(version=""),
        lambda data: data.update(schema_version=3),
        lambda data: data.update(schema_version=True),
        lambda data: data.update(extra=True),
        lambda data: data["images"]["scope_proxy"].update(extra=True),
    ],
)
def test_rejects_images_when_lock_fields_are_invalid(
    mutate: Callable[[dict[str, Any]], object],
) -> None:
    data = lock_data()
    mutate(data)

    with pytest.raises(ValidationError):
        ImagesLock.model_validate(data)


def test_rejects_changes_when_lock_has_been_validated() -> None:
    lock = ImagesLock.model_validate(lock_data())

    with pytest.raises(ValidationError, match="frozen_instance"):
        setattr(lock.images.zap, "tag", "1.12.3")  # noqa: B010 - testa o congelamento em runtime


def lock_data_v2() -> dict[str, Any]:
    data = lock_data()
    data["schema_version"] = 2
    data["images"]["nuclei"] = {
        "repository": "registry.example/qa/hdast-nuclei",
        "tag": "1.12.2",
        "digest": "sha256:" + "c" * 64,
    }
    return data


def test_schema_1_has_no_nuclei_and_reports_it_unavailable() -> None:
    lock = ImagesLock.model_validate(lock_data())

    assert lock.images.nuclei is None
    assert lock.supports_nuclei is False
    assert [image.repository.rsplit("/", 1)[1] for image in lock.images_present()] == [
        "hdast-zap",
        "hdast-scope-proxy",
    ]


def test_schema_2_pins_the_nuclei_image_with_the_same_tag() -> None:
    lock = ImagesLock.model_validate(lock_data_v2())

    assert lock.supports_nuclei is True
    assert lock.images.nuclei is not None
    assert lock.images.nuclei.reference() == "registry.example/qa/hdast-nuclei:1.12.2@sha256:" + (
        "c" * 64
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["images"].pop("nuclei"),
        lambda data: data["images"]["nuclei"].update(tag="1.12.3"),
        lambda data: data["images"]["nuclei"].update(digest="sha256:" + "c" * 63),
        lambda data: data["images"]["nuclei"].update(repository="registry.example/n:latest"),
        lambda data: data["images"].update(nuclei=None),
        lambda data: data["images"]["nuclei"].update(extra=True),
    ],
)
def test_rejects_schema_2_when_the_nuclei_image_is_missing_or_invalid(
    mutate: Callable[[dict[str, Any]], object],
) -> None:
    data = lock_data_v2()
    mutate(data)

    with pytest.raises(ValidationError):
        ImagesLock.model_validate(data)


def test_rejects_schema_1_that_carries_a_nuclei_image() -> None:
    data = lock_data_v2()
    data["schema_version"] = 1

    with pytest.raises(ValidationError, match="Nuclei"):
        ImagesLock.model_validate(data)
