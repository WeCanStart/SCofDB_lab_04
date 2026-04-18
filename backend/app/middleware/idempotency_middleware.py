"""Idempotency middleware template for LAB 04."""

from datetime import datetime, timedelta
import hashlib
import json
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.application.payment_service import PaymentService
from app.infrastructure.db import SessionLocal
from app.api.payment_routes import router


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware для идемпотентности POST-запросов оплаты.

    Идея:
    - Клиент отправляет `Idempotency-Key` в header.
    - Если запрос с таким ключом уже выполнялся для того же endpoint и payload,
      middleware возвращает кэшированный ответ (без повторного списания).
    """

    def __init__(self, app, ttl_seconds: int = 24 * 60 * 60):
        super().__init__(app)
        self.ttl_seconds = ttl_seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        TODO: Реализовать алгоритм.

        Рекомендуемая логика:
        1) Пропускать только целевые запросы:
           - method == POST
           - path в whitelist для платежей
        2) Читать Idempotency-Key из headers.
           Если ключа нет -> обычный call_next(request)
        3) Считать request_hash (например sha256 от body).
        4) В транзакции:
           - проверить запись в idempotency_keys
           - если completed и hash совпадает -> вернуть кэш (status_code + body)
           - если key есть, но hash другой -> вернуть 409 Conflict
           - если ключа нет -> создать запись processing
        5) Выполнить downstream request через call_next.
        6) Сохранить response в idempotency_keys со статусом completed.
        7) Вернуть response клиенту.

        Дополнительно:
        - обработайте кейс конкурентных одинаковых ключей
          (уникальный индекс + retry/select existing).
        """

        # Текущая заглушка: middleware ничего не меняет.
        # TODO: заменить на полноценную реализацию с БД.
        if request.method != "POST" or not request.url.path.startswith("/api/payments"):
            return await call_next(request)
        
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)
        
        body = await request.body()
        request_hash = self.build_request_hash(body)

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        request._receive = receive
        request._body = body

        async with SessionLocal() as session:
            try:
                check = await session.execute(
                    text("""
                        SELECT * FROM idempotency_keys
                        WHERE idempotency_key = :key
                            AND request_method = :method
                            AND request_path = :path
                        LIMIT 1
                        """),
                    {"key": idempotency_key, "method": request.method, "path": request.url.path}
                )
                record = check.mappings().first()
                if record:
                    if record["request_hash"] != request_hash:
                        return JSONResponse(
                            {"detail": "Idempotency-Key conflict: same key with different payload"},
                            status_code=409
                        )

                    if record["status"] == "completed":
                        cached_body = self._serialize_body(record["response_body"])
                        response = Response(
                            content=cached_body,
                            status_code=record["status_code"],
                            media_type="application/json"
                        )
                        response.headers["X-Idempotency-Replayed"] = "true"
                        return response

                    if record["status"] == "processing":
                        return JSONResponse(
                            {"detail": "Request is already processing"},
                            status_code=409
                        )

                    return JSONResponse(
                        {"detail": "Previous request failed"},
                        status_code=409
                    )
                
                expires_at = datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
                try:
                    await session.execute(
                        text("""
                            INSERT INTO idempotency_keys (
                                idempotency_key,
                                request_method,
                                request_path,
                                request_hash,
                                status,
                                expires_at
                            )
                            VALUES (
                                :key,
                                :method,
                                :path,
                                :hash,
                                'processing',
                                :expires_at
                            )
                        """),
                        {
                            "key": idempotency_key,
                            "method": request.method,
                            "path": request.url.path,
                            "hash": request_hash,
                            "expires_at": expires_at,
                        },
                    )
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    check = await session.execute(
                        text("""
                            SELECT * FROM idempotency_keys
                            WHERE idempotency_key = :key
                                AND request_method = :method
                                AND request_path = :path
                            LIMIT 1
                        """),
                        {"key": idempotency_key, "method": request.method, "path": request.url.path}
                    )
                    record = check.mappings().first()
                    if record and record["status"] == "completed":
                        cached_body = self._serialize_body(record["response_body"])
                        response = Response(
                            content=cached_body,
                            status_code=record["status_code"],
                            media_type="application/json"
                        )
                        response.headers["X-Idempotency-Replayed"] = "true"
                        return response
                    return JSONResponse(
                        {"detail": "Request is already processing"},
                        status_code=409
                    )
            except Exception as db_error:
                await session.rollback()
                raise db_error
        
        response = await call_next(request)
        response_body_bytes = b""
        async for chunk in response.body_iterator:
            response_body_bytes += chunk

        response_body_text = response_body_bytes.decode("utf-8", errors="replace")

        async with SessionLocal() as session:
            try:
                await session.execute(
                    text("""
                        UPDATE idempotency_keys
                        SET status = 'completed',
                            status_code = :status_code,
                            response_body = :response_body,
                            updated_at = NOW()
                        WHERE idempotency_key = :key
                            AND request_method = :method
                            AND request_path = :path
                    """),
                    {
                        "status_code": response.status_code,
                        "response_body": response_body_text,
                        "key": idempotency_key,
                        "method": request.method,
                        "path": request.url.path,
                    },
                )
                await session.commit()
            except Exception:
                await session.rollback()

        response = Response(
            content=response_body_bytes,
            status_code=response.status_code,
            media_type=response.media_type or "application/json",
        )
        return response
    
    @staticmethod
    def build_request_hash(raw_body: bytes) -> str:
        """Стабильный хэш тела запроса для проверки reuse ключа с другим payload."""
        return hashlib.sha256(raw_body).hexdigest()

    @staticmethod
    def encode_response_payload(body_obj) -> str:
        """Сериализация response body для сохранения в idempotency_keys."""
        return json.dumps(body_obj, ensure_ascii=False)

    @staticmethod
    def _serialize_body(body) -> bytes:
        """Десериализация response body из idempotency_keys."""
        if body is None:
            return b""
        if isinstance(body, bytes):
            return body
        if isinstance(body, str):
            return body.encode("utf-8")
        if isinstance(body, dict):
            return json.dumps(body, ensure_ascii=False).encode("utf-8")
        return str(body).encode("utf-8")
