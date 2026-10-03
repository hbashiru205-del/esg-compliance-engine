"""Trial limit, and the paid-unlock flow once it's hit. Gated by a
persistent account (backend.accounts), not the in-session chat
history, so a page refresh does not reset the count.

No separate access gate exists before this any more: everyone gets a
free trial immediately on giving a name, and only hits an access-code
prompt once that trial is used up -- at which point the code is what
someone receives after paying for the pilot. Reuses the same
ACCESS_CODES secret the app already had configured.
"""
from backend.accounts import get_account, unlock_account
from backend.accounts import trial_exceeded as _account_trial_exceeded

TRIAL_LIMIT = 5
PILOT_PRICE = "£75"
PILOT_TERMS = "one document, 30 days"
CONTACT_EMAIL = "hello@clarixintel.com"


def trial_exceeded(token: str, limit: int = TRIAL_LIMIT) -> bool:
    return _account_trial_exceeded(token, limit)


def render_trial_status(st, token: str, limit: int = TRIAL_LIMIT):
    account = get_account(token)
    if account and account["unlocked"]:
        st.caption("\u2705 Unlocked — unlimited questions.")
        return
    used = account["questions_used"] if account else 0
    remaining = max(0, limit - used)
    if remaining > 0:
        st.caption(f"\U0001f50d Trial: {remaining} of {limit} free questions "
                    "remaining.")


def _valid_codes(st):
    return [c.strip() for c in st.secrets.get("ACCESS_CODES", "").split(",") if c.strip()]


def render_trial_blocked(st, token: str):
    st.warning(
        f"You've used all {TRIAL_LIMIT} free trial questions. Ready to run "
        f"this on your own compliance documents? The pilot is {PILOT_PRICE} "
        f"for {PILOT_TERMS} — email {CONTACT_EMAIL} to get started. Already "
        f"paid? Enter your access code below."
    )
    code = st.text_input("Access code", type="password", key="unlock_code_input")
    if st.button("Unlock", key="unlock_code_btn"):
        if code.strip() and code.strip() in _valid_codes(st):
            unlock_account(token)
            st.rerun()
        else:
            st.error(f"That code didn't work. Double-check it, or email "
                      f"{CONTACT_EMAIL} if you need one.")
