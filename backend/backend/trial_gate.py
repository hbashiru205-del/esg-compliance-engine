"""Session-scoped trial limit for the Ask Questions tab.

No accounts and no data persists between sessions (the app's own privacy
statement says each session starts fresh), so a trial limit here is
necessarily per-browser-session, not per-person: refreshing the page
resets it. That's a real, known gap given the current setup, not an
oversight -- closing it would mean adding accounts, which would be a
much bigger change and would also mean actually keeping data on people,
which cuts against the privacy stance. Fine for an early-stage product
with no way to be gamed at scale yet; worth revisiting once there's
real trial abuse to justify the added complexity.
"""

TRIAL_LIMIT = 5
PILOT_PRICE = "$75"
PILOT_TERMS = "one document, 30 days"
CONTACT_EMAIL = "hello@clarixintel.com"


def questions_used(chat) -> int:
    """Real questions asked so far this session (one chat turn per ask)."""
    return sum(1 for turn in chat if turn.get("role") == "user")


def trial_exceeded(chat, limit: int = TRIAL_LIMIT) -> bool:
    return questions_used(chat) >= limit


def render_trial_status(st, chat, limit: int = TRIAL_LIMIT):
    """Always-visible remaining-question count, shown above the input."""
    remaining = max(0, limit - questions_used(chat))
    if remaining > 0:
        st.caption(f"\U0001f50d Trial: {remaining} of {limit} free questions "
                    "remaining this session.")


def render_trial_blocked(st):
    """Shown instead of an answer once the trial limit is hit."""
    st.warning(
        f"You've used all {TRIAL_LIMIT} free trial questions. Ready to run "
        f"this on your own compliance documents? The pilot is {PILOT_PRICE} "
        f"for {PILOT_TERMS} — email {CONTACT_EMAIL} to get started."
  )
