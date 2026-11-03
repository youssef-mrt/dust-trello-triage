"""Sample data for "BillingCompany", a fictional invoicing software company. All names are invented."""

ENGINEERING_ISSUES = [
    {
        "key": "exports",
        "list": "in_progress",
        "name": "Scheduled CSV exports time out for workspaces with more than 10k invoices",
        "desc": (
            "## Summary\nScheduled exports run as a single job with a 300s limit. Workspaces with more than "
            "~10,000 invoices hit the limit, the job is marked `Failed - timeout` in Export history and no "
            "email is sent.\n\n## Customer impact\nFinance teams stop receiving weekly/monthly exports. "
            "Workaround: manual export filtered by date range.\n\n## Status\nChunked export job in progress.\n\n"
            "## Linked support reports\n- River Logistics (see attachment)"
        ),
    },
    {
        "key": "sso",
        "list": "fix_merged",
        "name": "SSO sign-in loops back to the login page in Safari 17+ (Okta SAML)",
        "desc": (
            "## Summary\nSafari's tracking prevention drops the `ldg_sso_state` cookie during the SAML POST "
            "from Okta, so the callback cannot match the session and redirects to /login again. No error is "
            "shown. Chrome and Firefox are unaffected.\n\n## Fix\nState moved to a first-party, SameSite=None "
            "cookie. PR merged; ships with the next release (planned v4.13.0).\n\n## Workaround\nUse Chrome or "
            "Firefox, or sign in from the Okta dashboard tile."
        ),
    },
    {
        "key": "dashboard",
        "list": "released",
        "name": "Revenue chart shifts by one day for workspaces in UTC-negative timezones",
        "desc": "## Summary\nDaily buckets were computed in UTC.\n\nRelease: v4.11.2",
    },
    {
        "key": "stripe",
        "list": "triage",
        "name": "Duplicate payment.succeeded webhooks when Stripe retries delivery",
        "desc": "## Summary\nOutgoing webhooks are not de-duplicated on Stripe retry; some customers see two events.",
    },
    {
        "key": "reminders",
        "list": "in_progress",
        "name": "Invoice reminder emails sent twice on daylight-saving change",
        "desc": "## Summary\nThe reminder scheduler runs twice during the repeated hour in autumn DST changes.",
    },
]

# Already escalated before the demo starts, so the exports issue visibly has one linked report.
PRE_ESCALATED_REPORT = {
    "issue_key": "exports",
    "name": "Scheduled export missing - River Logistics",
    "desc": (
        "Customer: River Logistics (workspace river, ~22k invoices)\n"
        "Monthly scheduled CSV export to finance@river.example did not arrive. "
        "Export history shows 'Failed - timeout'."
    ),
}

CASES = {
    # Case 1: a clear new bug with no matching engineering issue -> create a new one.
    "case1": {
        "name": "PDF invoices show $ instead of CHF - Alpine Hotels",
        "desc": (
            "Customer: Alpine Hotels (workspace alpine, plan Business)\n"
            "Reported by: Martina Keller, Head of Finance\n\n"
            "Since Monday, every PDF invoice we generate for clients billed in Swiss francs shows the '$' "
            "symbol instead of 'CHF'. The amounts themselves are correct, and the invoice looks right in the "
            "BillingCompany web view - only the PDF (download and email attachment) is wrong.\n\n"
            "Examples: INV-2026-0871, INV-2026-0874, INV-2026-0880 (all CHF clients). EUR invoices look fine.\n"
            "Steps: open any CHF invoice > Download PDF.\n\n"
            "This is urgent for us: month-end invoicing runs this Friday and our accountant will not accept "
            "invoices with the wrong currency."
        ),
    },
    # Case 2: same root cause as an existing issue -> link, no duplicate card.
    "case2": {
        "name": "Weekly scheduled export never arrives - Nordic Freight",
        "desc": (
            "Customer: Nordic Freight (workspace nordic, ~14,500 invoices)\n"
            "Reported by: Erik Lindqvist, Controller\n\n"
            "Our weekly scheduled CSV export to finance@nordic.example has not arrived for the last two "
            "weeks. In Settings > Exports > History both runs say 'Failed - timeout'. A manual export of "
            "last month works fine.\n\nWe use the export to reconcile with our ERP every Monday."
        ),
    },
    # Case 3: too vague to act on -> needs information, then reinvestigated with the answers.
    "case3": {
        "name": "Can't log in - Bluebird Labs",
        "desc": (
            "Customer: Bluebird Labs\n\n"
            "Several people on our team can't log in since this morning. It just keeps going back to the "
            "login page. Please fix asap!"
        ),
    },
}
