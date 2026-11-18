# 0004. Portas e adaptadores em três camadas

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** AD-04, AD-09

## Contexto

O projeto tem substituições reais previstas: motor de varredura (ZAP hoje, outros na V2), destino do relatório e fonte de segredos. O domínio (escopo, fingerprint, regras de dados) precisa ser testável sem Docker.

## Decisão

Vamos organizar o pacote `harness_dast` em três camadas e uma entrada.

- `domain`: regras puras, sem I/O. Importa só biblioteca padrão e pydantic.
- `application`: casos de uso e portas. Importa só `domain`.
- `adapters`: tecnologia concreta (ZAP, HTTP, OpenAPI, arquivos). Importa `domain`, as portas de `application` e bibliotecas de terceiros. Não importa adaptador irmão nem `cli`.
- `cli`: entrada. Monta as dependências em `cli/composition.py` e não contém regra de negócio.

A regra é verificada por import-linter (`uv run lint-imports`); o build quebra se `domain` importar um adaptador.

Composição e `typing.Protocol` no lugar de herança (AD-09):

- Interfaces são `Protocol`, declaradas em `application/ports.py` por quem as consome.
- Classes recebem colaboradores no construtor.
- Herança só na hierarquia de exceções e nos modelos pydantic.
- Porta só onde há segunda implementação real, dublê de teste necessário ou fronteira com sistema externo. Senão, classe concreta.

## Alternativas consideradas

- **Clean Architecture completa com quatro camadas, entidades e apresentadores.** Cerimônia sem ganho neste tamanho.
- **Módulos planos por funcionalidade.** Simples, mas o ZAP vaza para todo lado em poucas semanas.
- **Classes abstratas (`ABC`) com métodos-gabarito, como em Java.** Familiar, mas incentiva reaproveitar por herança. Descartada.
- **Funções soltas sem interface.** Simples, porém sem contrato verificável.

## Consequências

- Um nível de indireção a mais.
- Adicionar um motor de varredura novo é escrever uma classe que satisfaz o protocolo e registrá-la; ninguém herda de `ZapScanner`.
- Ficam fora do desenho: contêiner de injeção de dependência, Repository genérico, barramento de eventos, CQRS e fábricas abstratas. Entram só se um caso concreto pedir, com ADR.
- Porta nova exige ADR.
- Páginas por pacote em [../modules/](../desenvolver/modulos/domain.md).
