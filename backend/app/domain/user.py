"""Доменная сущность пользователя."""

import uuid
from datetime import datetime, UTC
from dataclasses import dataclass, field
import re

from .exceptions import InvalidEmailError


# TODO: Реализовать класс User
# - Использовать @dataclass
# - Поля: email, name, id, created_at
# - Реализовать валидацию email в __post_init__
# - Regex: r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

@dataclass
class User:
    email: str
    name: str = ""
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if isinstance(self.email, str):
            self.email = self.email.strip()
        if not isinstance(self.email, str) or not _EMAIL_RE.match(self.email):
            raise InvalidEmailError(f"Invalid email: {self.email}")
