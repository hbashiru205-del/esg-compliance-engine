"""Five-question trial and paid-access status UI."""
from backend.accounts import get_account
TRIAL_LIMIT = 5
PILOT_PRICE = "£75"
PILOT_TERMS = "one document, 30 days"
CONTACT_EMAIL = "hello@clarixintel.com"

def trial_exceeded(token, limit=TRIAL_LIMIT):
    a = get_account(token)
    if not a or a.get("subscription_active"):
        return False
    if a.get("unlocked"):
        return True
    return a["questions_used"] >= limit

def render_trial_status(st, token, limit=TRIAL_LIMIT):
    a = get_account(token)
    if not a: return
    if a.get("subscription_active"):
        st.caption(f"✅ Paid access active through {a['paid_through']}."); return
    remaining = max(0, limit-a["questions_used"])
    if remaining:
        st.caption(f"🔎 Trial: {remaining} of {limit} free questions remaining.")
    elif a.get("expired"):
        st.warning(f"Paid access expired on {a.get('paid_through')}. Contact {CONTACT_EMAIL} to renew.")
    elif a.get("suspended"):
        st.warning(f"Your account is suspended. Contact {CONTACT_EMAIL}.")
    else:
        st.caption("Your free trial has ended.")

def render_trial_blocked(st, token):
    a = get_account(token) or {}
    if a.get("expired"): message = f"Your paid access expired on {a.get('paid_through')}."
    elif a.get("suspended"): message = "Your account has been suspended."
    else: message = f"You've used all {TRIAL_LIMIT} free trial questions."
    st.warning(f"{message} The ClariX pilot is {PILOT_PRICE} for {PILOT_TERMS}. "
               f"Email {CONTACT_EMAIL} to arrange payment and activation. "
               "Access is restored after the administrator confirms payment.")
