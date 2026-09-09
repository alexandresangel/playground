"""Names that current Diapason clients, historic blobs or Grafana queries still require.

Remove an alias only with the corresponding external migration. New application
logic uses Capture, operation and receipt terminology.
"""

CAPTURE_HTTP_PATH = "/api/skills/intelligence-contract"


def capture_health_fields(enabled: bool) -> dict:
    return {"intelligence_contract_enabled": enabled}


def strip_private_receipts(turn: dict) -> dict:
    output = dict(turn)
    output.pop("skill_run", None)  # Read old Blob records without exposing their artifacts.
    output.pop("capture_receipt", None)
    return output


def completion_prefix(identity, session_id, usage, cost, tool_names, workflow) -> dict:
    # Keep order: original observability/generate_dashboards.py uses an adjacent-field regex.
    return {
        "customer": identity.customer_id,
        "user": identity.user_id,
        "session": session_id,
        "tokens_in": usage.get("input", 0),
        "tokens_out": usage.get("output", 0),
        "cost_usd": cost,
        "tools": tool_names,
        "skills": workflow,
    }
