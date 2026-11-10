"""schemas.py — request bodies, validated by Pydantic before any route code runs."""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BR_STATES = {"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB",
             "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"}


def _email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address.")
    return value


class SignupIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    email: str
    password: str = Field(min_length=8, max_length=128)
    city: Optional[str] = Field(default=None, max_length=60)
    state: Optional[str] = Field(default=None, max_length=2)

    _email = field_validator("email")(_email)

    @field_validator("state")
    @classmethod
    def _state(cls, value):
        if value in (None, ""):
            return None
        value = value.upper()
        if value not in BR_STATES:
            raise ValueError("Use a 2-letter Brazilian state code, e.g. SP.")
        return value


class LoginIn(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    _email = field_validator("email")(_email)


class CartItemIn(BaseModel):
    product_id: str = Field(min_length=6, max_length=64)
    quantity: int = Field(default=1, ge=1, le=20)


class CartQuantityIn(BaseModel):
    quantity: int = Field(ge=0, le=20)


class AddressIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    street: str = Field(min_length=3, max_length=120)
    city: str = Field(min_length=2, max_length=60)
    state: str = Field(min_length=2, max_length=2)
    zip: str = Field(min_length=5, max_length=9)

    @field_validator("state")
    @classmethod
    def _state(cls, value):
        value = value.upper()
        if value not in BR_STATES:
            raise ValueError("Use a 2-letter Brazilian state code, e.g. SP.")
        return value


class PaymentIn(BaseModel):
    method: Literal["credit_card", "debit_card", "boleto", "voucher"]
    installments: int = Field(default=1, ge=1, le=10)
    card_number: Optional[str] = Field(default=None, max_length=23)
    card_name: Optional[str] = Field(default=None, max_length=80)
    expiry: Optional[str] = Field(default=None, max_length=5)   # MM/YY
    cvv: Optional[str] = Field(default=None, max_length=4)


class CheckoutIn(BaseModel):
    shipping: AddressIn
    payment: PaymentIn
    coupon_code: Optional[str] = Field(default=None, max_length=20)


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: Optional[str] = Field(default=None, max_length=80)
    message: Optional[str] = Field(default=None, max_length=1000)


class EventIn(BaseModel):
    event_type: Literal["cart_abandon", "view_category"]
    category: Optional[str] = Field(default=None, max_length=60)


class SimulatorIn(BaseModel):
    action: Literal["start", "stop"]
    sessions_per_min: int = Field(default=30, ge=1, le=240)
