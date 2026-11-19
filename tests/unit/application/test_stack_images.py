import pytest

from harness_dast.application.stack_images import OWN_SERVICES
from harness_dast.domain.errors import ConfigError
from tests.fakes.host import FakeHost, published_images


def test_resolves_compose_references_when_lock_is_absent() -> None:
    host = FakeHost()

    images = host.stack_images().references(OWN_SERVICES, local=False)

    assert images == {service: host.images[service] for service in OWN_SERVICES}


def test_pulls_digest_references_when_lock_matches_cli() -> None:
    host = FakeHost()
    host.images_lock = published_images()
    expected = (
        "registry.example/zap:" + host.images_lock.version + "@sha256:" + "a" * 64,
        "registry.example/proxy:" + host.images_lock.version + "@sha256:" + "b" * 64,
    )
    host.remote.update(expected)
    host.present.clear()

    assert host.stack_images().pull() == expected
    assert host.present == set(expected)


def test_rejects_images_before_docker_when_lock_version_differs() -> None:
    host = FakeHost()
    host.images_lock = published_images("0.0.0")

    with pytest.raises(ConfigError, match=r"da versão 0\.0\.0") as error:
        host.stack_images().pull()

    assert error.value.hint
    assert host.docker_calls == 0


def test_pulls_the_nuclei_image_too_when_lock_is_schema_2() -> None:
    host = FakeHost()
    host.images_lock = published_images(nuclei=True)
    version = host.images_lock.version
    nuclei = "registry.example/nuclei:" + version + "@sha256:" + "c" * 64
    host.remote.update(image.reference() for image in host.images_lock.images_present())

    pulled = host.stack_images().pull()

    assert pulled[-1] == nuclei
    assert len(pulled) == 3
    assert nuclei in host.present


def test_schema_1_lock_makes_nuclei_unavailable_with_a_clear_error() -> None:
    host = FakeHost()
    host.images_lock = published_images()
    host.remote.update(image.reference() for image in host.images_lock.images_present())
    images = host.stack_images()

    assert images.nuclei_available() is False
    with pytest.raises(ConfigError, match=r"sem a imagem do Nuclei") as error:
        images.require_nuclei()
    assert "extra_checks.nuclei" in (error.value.hint or "")
    assert len(images.pull()) == 2


def test_schema_1_lock_drops_nuclei_from_the_resolved_references() -> None:
    host = FakeHost()
    host.images_lock = published_images()

    refs = host.stack_images().references((*OWN_SERVICES, "nuclei"), local=False)

    assert "nuclei" not in refs
    assert "nuclei" not in host.requested_services


def test_schema_2_lock_and_clone_make_nuclei_available() -> None:
    clone = FakeHost()
    packaged = FakeHost()
    packaged.images_lock = published_images(nuclei=True)

    assert clone.stack_images().nuclei_available() is True
    assert packaged.stack_images().nuclei_available() is True
    packaged.stack_images().require_nuclei()


def test_compose_env_pins_the_nuclei_image_only_when_it_is_selected() -> None:
    host = FakeHost()
    host.images_lock = published_images(nuclei=True)
    images = host.stack_images()

    with_nuclei = images.compose_env(images.references((*OWN_SERVICES, "nuclei"), local=False))
    without = images.compose_env(images.references(OWN_SERVICES, local=False))

    assert with_nuclei["HDAST_NUCLEI_IMAGE"].endswith("@sha256:" + "c" * 64)
    assert "HDAST_NUCLEI_IMAGE" not in without


def test_local_build_selects_the_local_nuclei_tag() -> None:
    host = FakeHost()
    images = host.stack_images()

    refs = images.references((*OWN_SERVICES, "nuclei"), local=True)

    assert refs["nuclei"] == "hdast/nuclei:local"
