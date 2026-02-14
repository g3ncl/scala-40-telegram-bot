"""DynamoDB repository implementations for production."""

from __future__ import annotations

import os

import boto3
from botocore.exceptions import ClientError

from src.game.models import GameState


# Initialize DynamoDB resource at module level for Lambda warm starts
_dynamodb = None
_prefix = os.environ.get("DYNAMODB_TABLE_PREFIX", "Scala40")


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


class DynamoDBGameRepository:
    def __init__(self, table_name: str | None = None) -> None:
        self._table_name = table_name or f"{_prefix}_Games"
        self._table = _get_dynamodb().Table(self._table_name)

    def get_game(self, game_id: str) -> GameState | None:
        response = self._table.get_item(
            Key={"gameId": game_id},
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not item:
            return None
        return GameState.from_dict(item)

    def save_game(self, game: GameState) -> None:
        item = game.to_dict()
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression=(
                    "attribute_not_exists(gameId) OR version = :v"
                ),
                ExpressionAttributeValues={":v": game.version},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError("Version conflict") from e
            raise

    def delete_game(self, game_id: str) -> None:
        self._table.delete_item(Key={"gameId": game_id})


class DynamoDBLobbyRepository:
    def __init__(self, table_name: str | None = None) -> None:
        self._table_name = table_name or f"{_prefix}_Lobbies"
        self._table = _get_dynamodb().Table(self._table_name)

    def get_lobby(self, lobby_id: str) -> dict | None:
        response = self._table.get_item(Key={"lobbyId": lobby_id})
        return response.get("Item")

    def save_lobby(self, lobby: dict) -> None:
        self._table.put_item(Item=lobby)

    def delete_lobby(self, lobby_id: str) -> None:
        self._table.delete_item(Key={"lobbyId": lobby_id})

    def get_lobby_by_code(self, code: str) -> dict | None:
        # Scan is acceptable for small datasets in free tier
        response = self._table.scan(
            FilterExpression="code = :c AND #s = :w",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":c": code, ":w": "waiting"},
        )
        items = response.get("Items", [])
        return items[0] if items else None


class DynamoDBUserRepository:
    def __init__(self, table_name: str | None = None) -> None:
        self._table_name = table_name or f"{_prefix}_Users"
        self._table = _get_dynamodb().Table(self._table_name)

    def get_user(self, user_id: str) -> dict | None:
        response = self._table.get_item(Key={"userId": user_id})
        return response.get("Item")

    def save_user(self, user: dict) -> None:
        self._table.put_item(Item=user)

    def update_user_stats(self, user_id: str, stats_update: dict) -> None:
        update_expr_parts = []
        expr_values = {}
        for key, value in stats_update.items():
            safe_key = key.replace(".", "_")
            update_expr_parts.append(f"stats.{key} = :{safe_key}")
            expr_values[f":{safe_key}"] = value

        if update_expr_parts:
            self._table.update_item(
                Key={"userId": user_id},
                UpdateExpression="SET " + ", ".join(update_expr_parts),
                ExpressionAttributeValues=expr_values,
            )
