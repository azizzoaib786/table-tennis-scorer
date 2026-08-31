#!/usr/bin/env python3
"""Setup script — creates DynamoDB tables and default admin for Table Tennis Scorer."""
import os
import time
import uuid

import boto3

AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")

ddb = boto3.client("dynamodb", region_name=AWS_REGION)


def _create(table_name: str, key_schema: list, attr_defs: list) -> None:
    try:
        ddb.create_table(
            TableName=table_name,
            KeySchema=key_schema,
            AttributeDefinitions=attr_defs,
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"Created {table_name}")
        ddb.get_waiter("table_exists").wait(TableName=table_name)
        print(f"{table_name} is ready")
    except ddb.exceptions.ResourceInUseException:
        print(f"{table_name} already exists")


def create_users_table():
    _create(
        "tt_users",
        [{"AttributeName": "user_id", "KeyType": "HASH"}],
        [{"AttributeName": "user_id", "AttributeType": "S"}],
    )


def create_matches_table():
    _create(
        "tt_matches",
        [{"AttributeName": "match_id", "KeyType": "HASH"}],
        [{"AttributeName": "match_id", "AttributeType": "S"}],
    )


def create_events_table():
    _create(
        "tt_events",
        [
            {"AttributeName": "match_id", "KeyType": "HASH"},
            {"AttributeName": "ts", "KeyType": "RANGE"},
        ],
        [
            {"AttributeName": "match_id", "AttributeType": "S"},
            {"AttributeName": "ts", "AttributeType": "S"},
        ],
    )


def create_tournaments_table():
    _create(
        "tt_tournaments",
        [{"AttributeName": "tournament_id", "KeyType": "HASH"}],
        [{"AttributeName": "tournament_id", "AttributeType": "S"}],
    )


def create_settings_table():
    _create(
        "tt_settings",
        [{"AttributeName": "config_id", "KeyType": "HASH"}],
        [{"AttributeName": "config_id", "AttributeType": "S"}],
    )


def create_roster_table():
    _create(
        "tt_roster",
        [{"AttributeName": "player_id", "KeyType": "HASH"}],
        [{"AttributeName": "player_id", "AttributeType": "S"}],
    )


def seed_default_settings():
    settings_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table("tt_settings")
    resp = settings_table.get_item(Key={"config_id": "global"})
    if resp.get("Item"):
        print("Global settings already exist — leaving as-is")
        return
    settings_table.put_item(Item={
        "config_id": "global",
        "default_best_of": 5,
        "default_points_to_win": 11,
        "service_interval": 2,
        "deuce_interval": 1,
        "deciding_side_change_at": 5,
        "hard_cap_enabled": False,
        "hard_cap_at": 15,
    })
    print("Seeded default global settings")


def create_admin_user():
    from app.auth import hash_password
    import secrets
    import string
    time.sleep(1)
    users_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table("tt_users")
    resp = users_table.scan(
        FilterExpression="username = :u",
        ExpressionAttributeValues={":u": "admin"},
    )
    if resp.get("Items"):
        print("Admin user already exists — leaving as-is")
        return

    # Prefer explicit env var (never printed); otherwise generate a random one and print ONCE.
    password = os.getenv("TT_ADMIN_PASSWORD", "").strip()
    generated = False
    if not password:
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(16))
        generated = True

    users_table.put_item(Item={
        "user_id": uuid.uuid4().hex,
        "username": "admin",
        "password_hash": hash_password(password),
        "is_admin": True,
        "is_active": True,
        "email": "",
        "role": "scorer",
        "stat_matches_played": 0,
        "stat_matches_won": 0,
        "stat_games_played": 0,
        "stat_games_won": 0,
        "stat_points_scored": 0,
    })
    print("Created admin user (username: admin)")
    if generated:
        print("")
        print("╔══════════════════════════════════════════════════════════════╗")
        print(f"║ Generated admin password: {password}                 ║")
        print("║ ⚠️  Save this now — it is NOT stored anywhere else and will   ║")
        print("║    not be printed again. Change it after first login.        ║")
        print("╚══════════════════════════════════════════════════════════════╝")
    else:
        print("Used TT_ADMIN_PASSWORD env var (value not printed).")


if __name__ == "__main__":
    print("Setting up Table Tennis Scorer database...")
    print()
    create_users_table()
    create_matches_table()
    create_events_table()
    create_tournaments_table()
    create_settings_table()
    create_roster_table()
    seed_default_settings()
    create_admin_user()
    print()
    print("Setup complete!")
    print()
    print("Next steps:")
    print("  1. pip install -r requirements.txt")
    print("  2. uvicorn app.main:app --reload --host 0.0.0.0 --port 8002")
    print("  3. Login as admin (username: admin, password: admin)")
