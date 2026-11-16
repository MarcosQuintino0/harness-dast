"""Canal fechado de conhecimento entre duas rodadas de avaliação."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote, quote_plus

import yaml

from evals.runner.cases import EvalError, RoundDirs, load_round_case
from evals.runner.models import Case
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.strategy_basis import describe_strategy_basis, digest_strategy_document

MAX_BYTES = 100_000
PRODUCT = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class UniqueLoader(yaml.SafeLoader):
    """Le YAML sem aceitar chaves duplicadas ambiguas."""


def _mapping(loader: UniqueLoader, node: yaml.MappingNode) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise EvalError("Chave YAML duplicada ou inválida.")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _regular(root: Path, relative: str, max_bytes: int = MAX_BYTES) -> Path:
    """Recusa links em qualquer componente antes de ler arquivos lacrados ou coletados."""
    path = root
    if any(_link(parent) for parent in (root, *root.parents)):
        raise EvalError("Diretório de rodada não pode ser link.")
    if Path(relative).is_absolute():
        raise EvalError("Caminho inválido no canal de reuso.")
    for part in Path(relative).parts:
        if part in (".", ".."):
            raise EvalError("Caminho inválido no canal de reuso.")
        path = path / part
        if _link(path):
            raise EvalError("Links não são aceitos no canal de reuso.")
    if not path.is_file() or path.stat().st_size > max_bytes or path.stat().st_nlink != 1:
        raise EvalError("Arquivo do canal ausente ou grande demais.")
    return path


def _json(root: Path, relative: str) -> object:
    try:
        return json.loads(
            _regular(root, relative).read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs
        )
    except (OSError, UnicodeError, ValueError):
        raise EvalError("Arquivo do canal ausente ou malformado.") from None


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("chave duplicada")
        result[key] = value
    return result


def _identity(out: Path, expected_case: str | None) -> tuple[Case, dict[str, str]]:
    mode = _json(out, "sealed/mode.json")
    secrets = _json(out, "sealed/secrets.json")
    collect = _json(out, "trace/collect.json")
    if not isinstance(mode, dict) or not isinstance(mode.get("case"), str):
        raise EvalError("Identidade lacrada inválida.")
    if expected_case is not None and mode["case"] != expected_case:
        raise EvalError("O caso de origem difere do caso de destino.")
    _regular(out, "sealed/case.json")
    case = load_round_case(RoundDirs(out), mode["case"])
    product = case.product
    if not PRODUCT.fullmatch(product):
        raise EvalError("Produto inválido no caso lacrado.")
    if not isinstance(collect, dict) or not isinstance(collect.get("copied"), list):
        raise EvalError("Coleta ausente ou inválida.")
    if f"profile/final/{product}" not in collect["copied"]:
        raise EvalError("Conhecimento não veio de perfil coletado.")
    if not isinstance(secrets, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v for k, v in secrets.items()
    ):
        raise EvalError("Lacre de segredos ausente ou inválido.")
    if set(secrets) != set(case.secrets.generate) | set(case.secrets.fixed):
        raise EvalError("Lacre de segredos incompleto ou incompatível com o caso.")
    return case, secrets


def _check_basis(out: Path, product: str, expected: dict[str, object]) -> None:
    root = out / "trace" / "profile" / "final"
    _regular(root, f"{product}/target.yml")
    try:
        profile = FileProfileRepository(root).load(product)
        _regular(root / product, profile.openapi, 8 * 1024 * 1024)
        for name in ("data-rules.yml", "flows.yml"):
            if (root / product / name).exists() or _link(root / product / name):
                _regular(root / product, name, 8 * 1024 * 1024)
        contract, rules, flows = FileStrategyRepository(root).read_dependencies(product, profile)
        current = describe_strategy_basis(
            profile,
            openapi_sha256=digest_strategy_document(contract),
            data_rules_sha256=digest_strategy_document(rules),
            flows_sha256=digest_strategy_document(flows),
            engine_version=None,
        )
    except HarnessError:
        raise EvalError("Fontes do conhecimento inválidas; nada foi exportado.") from None
    if expected != current.model_dump(exclude={"engine"}):
        raise EvalError("Fontes do conhecimento mudaram; nada foi exportado.")


def _scan_text(text: str, secrets: dict[str, str], case: Case) -> None:
    forms = {
        form
        for value in secrets.values()
        for form in (value, quote(value, safe=""), quote_plus(value))
    }
    if any(form in text for form in forms):
        raise EvalError("Segredo detectado; nada foi exportado.")
    if re.search(
        r"(?i)\bbearer[ \t]+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
        r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.",
        text,
    ):
        raise EvalError("Possível credencial detectada; nada foi exportado.")
    for term in case.leak_terms:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE):
            raise EvalError("Termo do gabarito detectado; nada foi exportado.")


def _scan_originals(folder: Path, secrets: dict[str, str], case: Case) -> None:
    for name in ("knowledge.yml", "target.yml", "strategy.yml", "data-rules.yml", "flows.yml"):
        if (folder / name).exists() or _link(folder / name):
            try:
                _scan_text(_regular(folder, name).read_text(encoding="utf-8"), secrets, case)
            except (OSError, UnicodeError):
                raise EvalError("Receita ilegível; nada foi exportado.") from None


def _source(out: Path, expected_case: str | None = None) -> tuple[str, dict[str, str]]:
    """Revalida a coleta e retorna produto e conteúdo, sem expor os dados lacrados."""
    case, secrets = _identity(out, expected_case)
    product = case.product
    try:
        content = _regular(out, f"trace/profile/final/{product}/knowledge.yml").read_text(
            encoding="utf-8"
        )
        data = yaml.load(content, Loader=UniqueLoader)  # noqa: S506 - herda SafeLoader
    except (OSError, UnicodeError, yaml.YAMLError):
        raise EvalError("Conhecimento ausente ou malformado.") from None
    # O modelo fechado é a fronteira de formato, não uma prova de atualidade.
    from harness_dast.domain.knowledge import Knowledge

    try:
        knowledge = Knowledge.from_data(data)
    except HarnessError:
        raise EvalError("Conhecimento inválido; nada foi exportado.") from None
    _check_basis(out, product, knowledge.basis.model_dump(exclude={"engine"}))
    root = out / "trace" / "profile" / "final"
    _scan_originals(root / product, secrets, case)
    from evals.runner.reuse_recipes import recipes

    files = recipes(root, product, knowledge.basis.model_dump(), case)
    payload = knowledge.model_dump(mode="json")
    for name, key in (("data-rules.yml", "data_rules"), ("flows.yml", "flows")):
        if name in files:
            payload["basis"][key] = digest_strategy_document(files[name].encode("utf-8"))
    for entry in payload["entries"]:
        entry["state"] = "review_required"
    if "strategy.yml" in files:
        strategy = yaml.safe_load(files["strategy.yml"])
        for choice in strategy["choices"]:
            choice["basis"] = payload["basis"].copy()
        files["strategy.yml"] = yaml.safe_dump(strategy, sort_keys=True)
    files["knowledge.yml"] = yaml.safe_dump(payload, sort_keys=True)
    for text in files.values():
        _scan_text(text, secrets, case)
    return product, files


def export_reuse(out: Path, destination: Path) -> Path:
    """Exporta somente conhecimento validado; a validade contextual continua pendente."""
    product, files = _source(out)
    if destination.exists() or any(_link(parent) for parent in (destination, *destination.parents)):
        raise EvalError("Destino de exportação já existe.")
    destination.mkdir(parents=True)
    for name, content in files.items():
        (destination / name).write_text(content, encoding="utf-8", newline="")
    manifest = {
        "schema_version": 1,
        "product": product,
        "files": {
            name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in sorted(files.items())
        },
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def verify_reuse(out: Path, package: Path, expected_case: str) -> tuple[str, dict[str, str]]:
    """Confere novamente origem, segredos e conteúdo exato, sem confiar no manifesto isolado."""
    product, files = _source(out, expected_case)
    if _link(package) or not package.is_dir():
        raise EvalError("Pacote de reuso inválido.")
    if {item.name for item in package.iterdir()} != set(files) | {"manifest.json"}:
        raise EvalError("Pacote contém arquivos extras ou ausentes.")
    manifest = _json(package, "manifest.json")
    expected = {
        "schema_version": 1,
        "product": product,
        "files": {
            name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in sorted(files.items())
        },
    }
    try:
        equal = all(
            _regular(package, name).read_bytes() == content.encode("utf-8")
            for name, content in files.items()
        )
    except (OSError, UnicodeError):
        raise EvalError("Pacote inválido.") from None
    if manifest != expected or not equal:
        raise EvalError("Pacote foi alterado ou pertence a outro produto.")
    return product, files
