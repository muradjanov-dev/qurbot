# Telegram product choices — 2026-09-18

AI product suggestions previously repeated a name truncated to 25 characters
across three quantity buttons per row. Similar variants therefore looked
identical and the quantity could be clipped by the Telegram client too.

New responses list the complete product names with stable 1–3 numbering and
show one full-width selection button per product. Selecting opens a separate
message with the full name, price and short quantity buttons. Selection alone
does not change the cart. Quantity selection retains ownership validation and
the existing cart revision conflict check. Unverified offers remain excluded.
An unavailable first product does not renumber subsequent choices.

Telegram may still truncate unusually long single-line button labels on narrow
screens; the matching number and full name in the message identify the variant.
Existing Telegram messages keep their previously sent keyboards. Existing
`chat:qty` callbacks continue to work; new AI responses use the selection step.

Regression checks: `tests/unit/test_ai_chat.py` and the Telegram outbox test in
`tests/integration/test_conversations.py` cover distinct full labels, stable
numbering, ownership, no cart change on selection, quantity changes and checkout.
Run `make check` before push. The regular master CI/build/SSH pipeline deploys
both web and worker. Previous runtime SHA for rollback:
`59459d36c3ae7c0fd1da8447eb56e077ea2ae0f7`.
