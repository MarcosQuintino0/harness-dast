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
