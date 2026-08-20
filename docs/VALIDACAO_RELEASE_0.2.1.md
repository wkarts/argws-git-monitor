# Validação operacional — ARGWS Git Monitor v0.2.1

## Objetivo

A versão 0.2.1 corrige o processo de entrega posterior ao merge da aplicação. O objetivo desta versão é garantir que código aprovado na branch `main` produza, de forma rastreável, uma GitHub Release e imagens Docker consumíveis tanto pelo GHCR quanto por build local.

## Fluxo automatizado

O workflow `Release e GHCR` executa, nesta ordem:

1. valida a igualdade das versões em `VERSION`, `backend/pyproject.toml` e `frontend/package.json`;
2. executa Ruff, compilação Python, testes e cobertura mínima do backend;
3. executa validação estrutural, typecheck e build do frontend;
4. valida o pacote, `compose.yaml` e `compose.dockge.yaml`;
5. constrói as imagens `api` e `web` para `linux/amd64` e `linux/arm64`;
6. publica as imagens no GitHub Container Registry;
7. inspeciona os manifests publicados no GHCR;
8. cria a Git tag `v0.2.1` somente depois que as imagens forem publicadas e verificadas;
9. publica a GitHub Release com ZIP, TAR.GZ e `SHA256SUMS.txt`.

## Imagens previstas

```text
ghcr.io/wkarts/argws-git-monitor-api:0.2.1
ghcr.io/wkarts/argws-git-monitor-web:0.2.1
ghcr.io/wkarts/argws-git-monitor-api:latest
ghcr.io/wkarts/argws-git-monitor-web:latest
```

Também são produzidas as tags `0.2` e `sha-<commit>`.

## Build local

O build local permanece suportado e é validado pela CI:

```bash
./scripts/generate-env.sh
docker compose -f compose.yaml up -d --build --remove-orphans
```

Os instaladores Windows e Linux tentam primeiro as imagens do GHCR. Quando o pull não está disponível, executam automaticamente o build local como contingência.

## Dockge e Portainer

A versão inclui `compose.dockge.yaml`, sem blocos `build`, para permitir implantação direta pelas imagens publicadas:

```bash
docker compose -f compose.dockge.yaml pull
docker compose -f compose.dockge.yaml up -d --no-build --remove-orphans
```

## Dependabot

Os Pull Requests automáticos de atualização de versão foram desativados. A manutenção de dependências passa a ser planejada, agrupada manualmente e validada pelo CI, evitando a abertura massiva de PRs sem revisão.

## Critério de conclusão

A entrega 0.2.1 é considerada concluída quando:

- a tag `v0.2.1` apontar para o mesmo commit publicado em `main`;
- as imagens API e Web estiverem disponíveis com a tag `0.2.1`;
- os manifests `amd64` e `arm64` forem inspecionados com sucesso pelo workflow;
- a GitHub Release contiver os pacotes e checksums;
- não houver Pull Requests automáticos abertos pelo Dependabot.
