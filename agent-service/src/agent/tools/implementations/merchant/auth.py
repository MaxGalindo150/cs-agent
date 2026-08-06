"""Merchant auth/2FA tools — check employee 2FA status and register phone.

2FA is the most common support topic: the aliado can't access reports because
their phone isn't registered for 2FA, or they want to register/change the
phone number.
"""

from __future__ import annotations

import json

import httpx

from agent.tools.context import ToolContext
from agent.tools.registry import Tool


def make_get_employee_2fa_tool(client: httpx.AsyncClient) -> Tool:
    async def get_employee_2fa(ctx: ToolContext, employee_id: str = "") -> str:
        assert ctx.principal is not None
        eid = employee_id or ctx.principal.employee_id or ""
        if not eid:
            return "get_employee_2fa needs an employee_id."
        try:
            resp = await client.get(f"/api/v1/employees/{eid}")
        except httpx.RequestError:
            return "The merchant service is unavailable right now — try again shortly."
        if resp.status_code == 404:
            return f"No employee found with id '{eid}'."
        if resp.status_code != 200:
            return f"Could not look up employee '{eid}' (status {resp.status_code})."
        employee = resp.json()
        if not isinstance(employee, dict) or str(employee.get("merchantId")) != (
            ctx.principal.merchant_id or ""
        ):
            return f"No employee found with id '{eid}'."
        visible_fields = (
            "id",
            "phoneRegistered",
            "mustChangePassword",
            "securityCodeSet",
            "lastLoginAt",
            "role",
            "onboardingStatus",
        )
        return json.dumps(
            {key: employee.get(key) for key in visible_fields}, separators=(",", ":")
        )

    return Tool(
        name="get_employee_2fa",
        progress_label="Checking 2FA status for employee {employee_id}",
        description=(
            "Look up an employee's profile and 2FA status: phoneRegistered "
            "(whether a phone is registered for 2FA), mustChangePassword, "
            "securityCodeSet, lastLoginAt, role (ADMIN/MANAGER/CASHIER), and "
            "onboardingStatus. Use this for 'no puedo entrar a reportes' or "
            "'no he recibido el código de verificación'. If phoneRegistered "
            "is false, the employee needs to register their phone first via "
            "register_2fa_phone."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {
                    "type": "string",
                    "description": "The employee id. If omitted, uses the "
                    "employee identified in the conversation.",
                }
            },
        },
        fn=get_employee_2fa,
        requires_identity=True,
    )


def make_register_2fa_phone_tool(client: httpx.AsyncClient) -> Tool:
    async def register_2fa_phone(ctx: ToolContext, phone: str = "") -> str:
        assert ctx.principal is not None
        eid = ctx.principal.employee_id or ""
        if not eid:
            return (
                "Registering a 2FA phone requires an employee identified by the portal."
            )
        if not phone:
            return (
                "register_2fa_phone needs a 'phone' number. Ask the merchant "
                "for the phone number they want to register."
            )
        try:
            employee_response = await client.get(f"/api/v1/employees/{eid}")
            employee = (
                employee_response.json()
                if employee_response.status_code == 200
                else None
            )
            if not isinstance(employee, dict) or str(employee.get("merchantId")) != (
                ctx.principal.merchant_id or ""
            ):
                return f"No employee found with id '{eid}'."
            resp = await client.post(
                f"/api/v1/employees/{eid}/2fa/register-phone",
                json={"phone": phone},
            )
        except httpx.RequestError:
            return "The merchant service is unavailable right now — try again shortly."
        if resp.status_code == 409:
            body = resp.json() if resp.text else {}
            err = body.get("error", "Conflict")
            return f"Could not register phone: {err}"
        if resp.status_code != 200:
            return f"Could not register phone (status {resp.status_code})."
        return resp.text

    return Tool(
        name="register_2fa_phone",
        progress_label="Registering employee 2FA phone",
        description=(
            "Register a phone number for an employee's 2FA (two-factor "
            "authentication). After registering, the employee will receive a "
            "verification code via SMS. Use this when phoneRegistered is false "
            "and the merchant wants to enable 2FA. If the phone is already "
            "registered, the server returns a 409 — tell the merchant their "
            "phone is already registered."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "The phone number to register, e.g. "
                    "'+58 412 123 4567'.",
                },
            },
            "required": ["phone"],
        },
        fn=register_2fa_phone,
        requires_identity=True,
    )
