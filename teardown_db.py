#!/usr/bin/env python3
"""Danger: drops the four TT tables. Use only for cleanup once the tournament is over."""
import os
import boto3

AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")
TABLES = ["tt_users", "tt_matches", "tt_events", "tt_tournaments", "tt_settings", "tt_roster", "tt_registrations"]

if __name__ == "__main__":
    confirm = input(f"Delete ALL tables {TABLES} in {AWS_REGION}? Type 'yes' to proceed: ").strip()
    if confirm != "yes":
        print("Aborted.")
        raise SystemExit(1)
    ddb = boto3.client("dynamodb", region_name=AWS_REGION)
    for t in TABLES:
        try:
            ddb.delete_table(TableName=t)
            print(f"Deleted {t}")
        except ddb.exceptions.ResourceNotFoundException:
            print(f"{t} does not exist")
