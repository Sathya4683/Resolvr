---
ref: KB-016
title: Mobile data not working
product: mobile
category: mobile_data_issue
tags: mobile data, apn, internet not working, 4g, 5g, data balance
---

## Symptoms
- Calls work but the internet does not open on mobile data.
- Data icon (4G/5G) is shown but apps say "no internet".

## Likely causes
- Daily data quota exhausted.
- Wrong or missing APN settings.
- Mobile data or data roaming switched off.

## Steps
1. Check the data balance in CRM. If the daily quota is used up, explain the reset time and offer a data booster.
2. Ask the customer to switch mobile data off and on, and to toggle airplane mode.
3. Reset the APN: Settings > Mobile network > Access Point Names > **Reset to default**. The correct APN is `mynet` with no username or password.
4. Restart the phone.
5. Check that the plan includes data (some voice-only plans do not).
6. If still not working, push a fresh data profile from CRM.

## Escalate when
- Data balance is available, the APN is correct and the profile push did not help.
