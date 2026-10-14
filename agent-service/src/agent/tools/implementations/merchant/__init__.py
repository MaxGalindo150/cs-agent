"""Tools for aliados: read Cashea's merchant API as the aliado.

Every call is sent with the aliado's own token (``ToolContext.host_credential``)
so Cashea's backend scopes it to their merchant and applies their role's
permissions — the agent never widens what the portal itself would show them.
All read-only. Each tool returns a trimmed, allowlisted view of the response:
only what the aliado needs, and never a buyer's contact details.
"""
