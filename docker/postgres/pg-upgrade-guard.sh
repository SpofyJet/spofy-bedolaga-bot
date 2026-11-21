#!/bin/sh
# Точка входа контейнера postgres: не даёт новому PostgreSQL молча создать пустую
# базу поверх установки, где данные ещё лежат в томе прошлой версии.
#
# Без этой проверки после обновления compose контейнер увидел бы пустой новый
# том, выполнил initdb, и бот стартовал бы на пустой базе — со стороны это
# выглядит как потеря всех данных, хотя они целы в старом томе.
#
# Старые тома смонтированы сюда только на чтение (см. docker-compose.yml):
# /mnt/pg-legacy/<версия>. До PostgreSQL 18 кластер лежит в корне тома,
# начиная с 18 — в <версия>/docker.
set -eu

LEGACY_ROOT="${PG_LEGACY_ROOT:-/mnt/pg-legacy}"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
	for version_file in "$LEGACY_ROOT"/*/*/docker/PG_VERSION "$LEGACY_ROOT"/*/PG_VERSION; do
		[ -s "$version_file" ] || continue
		legacy_version="$(cat "$version_file")"
		cat >&2 <<EOF

==========================================================================
  PostgreSQL не запущен: база ещё на PostgreSQL ${legacy_version}.

  Бот перешёл на PostgreSQL ${PG_MAJOR:-новой версии}, а ваши данные лежат в старом томе.
  Чтобы перенести их без потерь, выполните в папке бота:

      make pg-upgrade

  (или: bash scripts/pg-upgrade.sh)

  Скрипт сделает резервную копию, перенесёт данные в новую версию,
  сверит их и запустит бота. Старый том при этом не удаляется.
  Подробно: docs/postgresql-18-upgrade.md
==========================================================================

EOF
		exit 1
	done
fi

exec docker-entrypoint.sh "$@"
