#!/bin/sh
set -eu

create_db_and_user() {
  db_name="$1"
  db_user="$2"
  db_password="$3"

  if [ "$(psql -tAc "SELECT 1 FROM pg_database WHERE datname='${db_name}'")" != "1" ]; then
    psql -c "CREATE DATABASE ${db_name}"
  fi

  if [ "$(psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${db_user}'")" != "1" ]; then
    echo "CREATE USER ${db_user} WITH PASSWORD :'pass'" | psql -v pass="${db_password}"
  fi

  psql -d "${db_name}" -c "GRANT ALL PRIVILEGES ON DATABASE ${db_name} TO ${db_user}"
}

create_db_and_user fleet_service fleet_service_user "${FLEET_SERVICE_DB_PASSWORD}"
create_db_and_user delivery_service delivery_service_user "${DELIVERY_SERVICE_DB_PASSWORD}"