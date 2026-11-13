import pytest

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.host import parse_host


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("[::ffff:127.0.0.1]", id="ipv4_mapped"),
        pytest.param("[::ffff:7f00:1]", id="ipv4_mapped_hex"),
        pytest.param("[2002:7f00:1::]", id="six_to_four"),
        pytest.param("[fe80::1]", id="link_local_v6"),
        pytest.param("[fe80::1%25eth0]", id="zone_id"),
        pytest.param("[::]", id="unspecified_v6"),
        pytest.param("[ff02::1]", id="multicast_v6"),
        pytest.param("[::1", id="unclosed_bracket"),
        pytest.param("[zzzz]", id="invalid_v6"),
        pytest.param("0.0.0.0", id="unspecified_v4"),  # noqa: S104 - caso de teste
        pytest.param("169.254.1.1", id="link_local_v4"),
        pytest.param("224.0.0.1", id="multicast_v4"),
        pytest.param("240.0.0.1", id="reserved_v4"),
        pytest.param("169.254.169.254", id="aws_metadata"),
        pytest.param("[fd00:ec2::254]", id="aws_metadata_v6"),
        pytest.param("metadata.google.internal", id="gcp_metadata_name"),
        pytest.param("2130706433", id="decimal_ipv4"),
        pytest.param("0x7f000001", id="hex_ipv4"),
        pytest.param("0x7f.0.0.1", id="hex_octet"),
        pytest.param("0177.0.0.1", id="octal_ipv4"),
        pytest.param("127.1", id="short_ipv4"),
    ],
)
def test_parse_host_rejects_when_host_is_ambiguous_or_forbidden(host: str) -> None:
    with pytest.raises(ScopeViolation) as caught:
        parse_host(host)

    assert caught.value.hint


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("", id="empty"),
        pytest.param(".", id="only_dot"),
        pytest.param("a..com", id="empty_label"),
        pytest.param("a.com..", id="two_trailing_dots"),
        pytest.param("*.a.com", id="wildcard"),
        pytest.param("a_b.com", id="underscore"),
        pytest.param("-a.com", id="leading_hyphen"),
        pytest.param("a-.com", id="trailing_hyphen"),
        pytest.param("a" * 64 + ".com", id="label_too_long"),
        pytest.param(("a" * 60 + ".") * 5 + "com", id="name_too_long"),
        pytest.param("a b.com", id="space"),
        pytest.param("a%41.com", id="percent_in_host"),
        pytest.param("xn--zz.example", id="invalid_punycode"),
        pytest.param("xn--.example", id="empty_punycode"),
        pytest.param("a\uff20b.com", id="fullwidth_at_sign"),
        pytest.param("\uff41pi.permitido.com", id="fullwidth_letter"),
        pytest.param("api.permitido.com\u3002", id="ideographic_full_stop"),
        pytest.param("ß.de", id="sharp_s_maps_to_ss"),
    ],
)
def test_parse_host_rejects_when_name_is_malformed_or_not_canonical(host: str) -> None:
    with pytest.raises(ScopeViolation):
        parse_host(host)


def test_parse_host_compares_in_punycode_when_host_is_unicode() -> None:
    assert parse_host("MÜNCHEN.example").text == parse_host("xn--mnchen-3ya.example").text


def test_parse_host_keeps_lookalike_distinct_when_letters_come_from_another_alphabet() -> None:
    lookalike = parse_host("\u0430pi.permitido.com")  # 'a' cirílico

    assert lookalike.text != "api.permitido.com"
    assert lookalike.text.startswith("xn--")


def test_parse_host_canonicalizes_ipv6_when_written_in_long_form() -> None:
    assert parse_host("[0:0:0:0:0:0:0:1]").text == "[::1]"
    assert parse_host("[2001:DB8::1]").text == "[2001:db8::1]"


def test_parse_host_flags_local_names_when_they_only_make_sense_in_the_lab() -> None:
    assert parse_host("localhost").is_local
    assert parse_host("vampi").is_local
    assert parse_host("api.localhost").is_local
    assert parse_host("host.docker.internal").is_local
    assert parse_host("printer.local").is_local
    assert parse_host("10.0.0.5").is_local


def test_parse_host_flags_public_names_as_not_local_when_they_have_a_real_domain() -> None:
    assert not parse_host("api.permitido.com").is_local


def test_parse_host_marks_only_loopback_and_private_ips_as_lab_addresses() -> None:
    assert parse_host("127.0.0.1").is_lab_address
    assert parse_host("10.1.2.3").is_lab_address
    assert parse_host("[::1]").is_lab_address
    assert not parse_host("93.184.216.34").is_lab_address
    assert not parse_host("100.64.0.1").is_lab_address
    assert not parse_host("example.com").is_lab_address
