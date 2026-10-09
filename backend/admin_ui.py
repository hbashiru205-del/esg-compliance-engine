"""Admin UI for manual activation, expiry and suspension."""
import hmac
from datetime import date, timedelta
import streamlit as st
from backend.accounts import list_accounts, set_subscription, suspend_account

def render_admin_panel():
    expected = str(st.secrets.get("ADMIN_PASSWORD", ""))
    if not expected:
        st.error("Admin panel disabled. Set ADMIN_PASSWORD in Streamlit secrets."); return
    if not st.session_state.get("clarix_admin_authenticated", False):
        password = st.text_input("Administrator password", type="password", key="clarix_admin_password")
        if st.button("Sign in to admin", key="clarix_admin_signin"):
            if hmac.compare_digest(password, expected):
                st.session_state["clarix_admin_authenticated"] = True
                st.rerun()
            else: st.error("Incorrect password.")
        return
    st.subheader("Account and subscription management")
    st.caption("Confirm payment before activating or extending access.")
    accounts = list_accounts()
    if not accounts: st.info("No accounts yet."); return
    labels = {f"{a['account_name']} · {a['token'][:8]} · {'active' if a['subscription_active'] else 'inactive'}":a for a in accounts}
    label = st.selectbox("Customer account", list(labels), key="clarix_admin_account")
    a = labels[label]
    st.write(f"**Name:** {a['account_name']}  \n**Questions used:** {a['questions_used']}  \n**Paid through:** {a.get('paid_through') or 'Not activated'}")
    try: default_date = date.fromisoformat(a["paid_through"]) if a.get("paid_through") else date.today()+timedelta(days=30)
    except ValueError: default_date = date.today()+timedelta(days=30)
    with st.form("clarix_subscription_form"):
        expiry = st.date_input("Paid-through date (inclusive)", value=default_date)
        paid = st.checkbox("I have confirmed the customer's payment")
        submit = st.form_submit_button("Activate / extend access")
        if submit:
            if not paid: st.error("Confirm payment first.")
            elif expiry < date.today(): st.error("Choose today or a future date.")
            else:
                try:
                    set_subscription(a["token"], expiry.isoformat())
                    st.success(f"Access active through {expiry.isoformat()}."); st.rerun()
                except ValueError as e: st.error(str(e))
    if a["suspended"]:
        if st.button("Unsuspend account", key="clarix_unsuspend"):
            suspend_account(a["token"], False); st.rerun()
    elif st.button("Suspend account now", key="clarix_suspend"):
        suspend_account(a["token"], True); st.rerun()
    st.markdown("#### Accounts")
    for item in accounts:
        status = "SUSPENDED" if item["suspended"] else "ACTIVE" if item["subscription_active"] else "TRIAL / EXPIRED"
        st.write(f"**{item['account_name']}** · {item['token'][:8]} · questions: {item['questions_used']} · paid through: {item.get('paid_through') or '—'} · {status}")
