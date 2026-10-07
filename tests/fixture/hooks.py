"""Fixture hooks: the four behaviors a site may add, in their smallest form, for the runner's tests."""


def harmless(event):
    """The fixture site answers 401 on /api/intake/?action=orders for an anonymous visitor by design."""
    return event.get("status") == 401 and "/api/intake/?action=orders" in event.get("url", "")


def verification_link(email, origin, site):
    return f"{origin}/intake/return/#verify=fixture-{email.split('@')[0]}"


def created(addresses, site):
    return []


def preflight(origin, site):
    return {"auth": {"kind": "supabase", "ref": "abcdefgh"}, "database": {"production": True},
            "payment": {"provider": "stripe", "account": "acct_test", "livemode": False}, "webhook": origin}
