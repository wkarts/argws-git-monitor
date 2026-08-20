.PHONY: install up down restart logs status test validate validate-deploys backup update publish clean deploy-ghcr deploy-local deploy-dockge

install:
	./scripts/install.sh

up:
	docker compose up -d --remove-orphans

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f --tail=200

status:
	./scripts/status.sh

test:
	docker compose run --rm --no-deps api test

validate:
	python3 scripts/validate-package.py
	python3 scripts/validate-deploy-layout.py

validate-deploys:
	python3 scripts/validate-deploy-layout.py

deploy-ghcr:
	bash deploy/docker/deploy-ghcr.sh

deploy-local:
	bash deploy/docker/deploy-local.sh

deploy-dockge:
	bash deploy/dockge/deploy.sh

backup:
	./scripts/backup.sh

update:
	./scripts/update.sh

publish:
	./scripts/publish-github.sh

clean:
	docker compose down --remove-orphans
