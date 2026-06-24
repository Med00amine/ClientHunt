#!/bin/sh
# Creates .env from .env.example with generated secrets (does not overwrite an existing .env).
set -e
cd "$(dirname "$0")/.."
[ -f .env ] && { echo ".env already exists; not touching it"; exit 0; }
cp .env.example .env
PW=$(python3 -c "import secrets;print(secrets.token_urlsafe(14))")
sed -i "s/^APP_PASSWORD=.*/APP_PASSWORD=$PW/" .env
sed -i "s/^SESSION_SECRET=.*/SESSION_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))')/" .env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(python3 -c 'import secrets;print(secrets.token_hex(16))')/" .env
chmod 600 .env
echo "Created .env. Your login password is: $PW"
