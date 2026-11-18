# 0012. Dependências `tzdata` e `pyyaml`

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** Achado A-11 da [revisão de QA](../reviews/2026-11-13-qa-m1-m2.md); [CONTRIBUTING.md](../../CONTRIBUTING.md) ("Como adicionar uma dependência")

## Contexto

Duas dependências entraram no `pyproject.toml` sem ADR, o que o projeto exige para qualquer dependência nova.

- **Janelas de execução** (`domain/window.py`) usam fusos IANA (`America/Sao_Paulo`) pelo módulo `zoneinfo` da biblioteca padrão. O `zoneinfo` lê o banco de fusos do sistema operacional. O Windows não tem esse banco, e o uso da V1 é local no Windows (P-11). Sem o banco, `ExecutionWindow` não consegue validar nem avaliar nenhuma janela.
- **Perfil de produto:** o `target.yml` é YAML. A biblioteca padrão do Python não lê YAML. O carregador do perfil (M2) precisa de um leitor, e um teste já valida o `products/_template/target.yml` com ele.

## Decisão

Vamos adicionar duas dependências de runtime, com versões travadas no `uv.lock`.

1. **`tzdata`** (>=2025.2): pacote oficial do projeto Python que distribui o banco de fusos IANA como dado. O `zoneinfo` o usa quando o sistema não tem o banco.
2. **`pyyaml`**: leitor de YAML. Deve ser usado **somente** com `yaml.safe_load` (nunca `yaml.load`, que pode instanciar objetos). Hoje só um teste o usa; o carregador de perfil (adaptador, M2) será o consumidor de produção. A leitura de arquivo fica em `config/` ou em adaptador, nunca em `domain` ([ADR 0004](0004-portas-e-adaptadores-em-tres-camadas.md)).

| Dependência | Licença (fonte) | Manutenção |
| --- | --- | --- |
| `tzdata` | Apache-2.0 (campo de licença da página do pacote no PyPI: <https://pypi.org/project/tzdata/>; código em <https://github.com/python/tzdata>) | Mantida sob a organização `python` no GitHub; nova versão a cada mudança do banco IANA. A versão 2026.6 foi enviada ao PyPI em 2026-10-28 |
| `pyyaml` | MIT (campo de licença e classificador "MIT License" na página do PyPI: <https://pypi.org/project/PyYAML/>; código em <https://github.com/yaml/pyyaml>) | Projeto estabelecido, mantido na organização `yaml`; a versão 6.0.3 é a mais recente no PyPI na data deste ADR |

A licença do projeto `harness-dast` segue indefinida (P-14). As duas licenças acima são permissivas e não impõem restrição à escolha.

## Alternativas consideradas

- **Só `zoneinfo`, sem `tzdata`.** Funciona em Linux e macOS, falha no Windows. Descartada.
- **Banco de fusos próprio ou `pytz`/`pendulum`.** Mais código ou mais dependência para o mesmo resultado. Descartada.
- **`ruamel.yaml`.** Preserva comentários e é mais fiel à especificação, mas é maior e a V1 não reescreve YAML. Descartada por ora.
- **Perfil em JSON ou TOML (TOML tem leitor na biblioteca padrão).** Elimina a dependência, mas o formato YAML já está no desenho aprovado e comentários no perfil ajudam o QA. Descartada.
- **Não adicionar `pyyaml` agora e validar o YAML só no adaptador futuro.** O teste do template ficaria de fora, e o template já tinha divergido do schema (achado A-02). Descartada.

## Consequências

- `zoneinfo` lê o banco do disco (ou do pacote `tzdata`), então o módulo `domain/window.py` não é "puro, sem I/O" no sentido literal. É uma exceção consciente e pequena: o resultado depende só do nome do fuso e do instante recebido. Fica registrada aqui.
- `profile_errors.py` importa `pydantic_core`, que vem junto do pydantic. É a mesma exceção de "só biblioteca padrão e pydantic".
- Toda atualização do banco IANA chega por `uv lock --upgrade-package tzdata`, em pull request próprio, e passa pelo `pip-audit` do CI.
- O uso de `pyyaml` só com `safe_load` precisa de um teste quando o carregador existir.
- Registrado no [CHANGELOG.md](../../CHANGELOG.md).
