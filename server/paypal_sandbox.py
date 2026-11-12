import base64
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import requests


class PayPalSandboxError(RuntimeError):
    """Raised when a PayPal Sandbox operation fails or is misconfigured."""


def parse_amount(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise PayPalSandboxError("Enter a valid payment amount.")
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise PayPalSandboxError("Enter a valid payment amount.") from None

    if not amount.is_finite() or amount <= 0 or amount > Decimal("10000.00"):
        raise PayPalSandboxError("Amount must be greater than zero and at most 10,000.")
    return amount


class PayPalSandbox:
    API_BASE = "https://api-m.sandbox.paypal.com"

    def __init__(self) -> None:
        self.client_id = os.environ.get("PAYPAL_CLIENT_ID", "").strip() ## for merchant specifically
        self.client_secret = os.environ.get("PAYPAL_CLIENT_SECRET", "").strip() ## for merchant specifically
        self.currency = os.environ.get("PAYPAL_CURRENCY", "USD").strip().upper()
        self._access_token: str | None = None

    def _credentials(self) -> str:
        if not self.client_id or not self.client_secret:
            raise PayPalSandboxError(
                "PayPal Sandbox is not configured. Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET."
            )
        return base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("ascii")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        request_id: str | None = None
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": request_id or str(uuid4())
        }
        try:
            response = requests.request(
                method,
                f"{self.API_BASE}{path}",
                headers=headers,
                json=payload,
                timeout=(5, 30)
            )
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as error:
            raise PayPalSandboxError("PayPal Sandbox request failed.") from error
        except ValueError as error:
            raise PayPalSandboxError("PayPal Sandbox returned invalid JSON.") from error

        if not isinstance(result, dict):
            raise PayPalSandboxError("PayPal Sandbox returned an unexpected response.")
        return result

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        authorization = self._credentials()
        try:
            response = requests.post(
                f"{self.API_BASE}/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {authorization}",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={"grant_type": "client_credentials"},
                timeout=(5, 30)
            )
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as error:
            raise PayPalSandboxError("PayPal Sandbox authentication failed.") from error
        except ValueError as error:
            raise PayPalSandboxError("PayPal Sandbox returned invalid authentication data.") from error

        token = result.get("access_token") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            raise PayPalSandboxError("PayPal Sandbox did not return an access token.")
        self._access_token = token
        return token

    def create_order(
        self,
        amount: Any,
        description: str,
        return_url: str,
        cancel_url: str
    ) -> tuple[str, str, Decimal]:
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise PayPalSandboxError("PAYPAL_CURRENCY must be a three-letter currency code.")

        parsed_amount = parse_amount(amount)
        order = self._request(
            "POST",
            "/v2/checkout/orders",
            payload={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": str(uuid4()),
                    "description": description[:127],
                    "amount": {
                        "currency_code": self.currency,
                        "value": format(parsed_amount, ".2f")
                    }
                }],
                "application_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                    "user_action": "PAY_NOW"
                }
            }
        )

        order_id = order.get("id")
        approval_url = next(
            (
                link.get("href")
                for link in order.get("links", [])
                if link.get("rel") == "approve"
            ),
            None
        )
        if not isinstance(order_id, str) or not isinstance(approval_url, str):
            raise PayPalSandboxError("PayPal Sandbox did not provide an approval link.")
        approval = urlparse(approval_url)
        if (
            approval.scheme != "https" or
            not approval.hostname or
            not (
                approval.hostname == "sandbox.paypal.com" or
                approval.hostname.endswith(".sandbox.paypal.com")
            )
        ):
            raise PayPalSandboxError("PayPal Sandbox returned an invalid approval URL.")
        return order_id, approval_url, parsed_amount

    def capture_order(self, order_id: str) -> dict[str, Any]:
        if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,80}", order_id):
            raise PayPalSandboxError("Invalid PayPal order ID.")
        return self._request(
            "POST",
            f"/v2/checkout/orders/{order_id}/capture",
            payload={},
            request_id=f"capture-{order_id}"
        )
