---
ref: KB-025
title: Channels not showing after recharge
product: dth
category: dth_channels_recharge
tags: recharge, channels missing, not subscribed, refresh, activation
---

## Symptoms
- Customer recharged but the TV still shows "channel not subscribed" or a recharge message.
- Some channels from the pack are missing.

## Likely causes
- The activation command has not reached the box yet.
- Recharge went to a different customer ID.
- Payment not confirmed.

## Steps
1. Confirm the recharge amount, date and customer ID in CRM.
2. Keep the box switched on on any channel and send a **refresh command** from CRM (or ask the customer to give a missed call to the refresh number). Channels return within 15 minutes.
3. If the recharge went to a wrong customer ID, raise a **recharge transfer** request (completed within 24 hours).
4. If the payment is pending, follow the payment failure process (KB-028).

## Escalate when
- Refresh does not restore channels within 2 hours.
