.PHONY: install up down restart logs status test validate backup update publish clean

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

backup:
	./scripts/backup.sh

update:
	./scripts/update.sh

publish:
	./scripts/publish-github.sh

clean:
	docker compose down --remove-orphans
