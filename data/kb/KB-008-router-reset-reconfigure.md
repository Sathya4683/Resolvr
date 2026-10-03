---
ref: KB-008
title: Router factory reset and reconfiguration
product: broadband
category: router_wifi_setup
tags: factory reset, pppoe, router configuration, credentials, replacement
---

## Symptoms
- Router settings were changed by mistake and the internet stopped working.
- Router was reset (reset button pressed) and now shows no internet.
- Customer bought a new router of their own.

## Likely causes
- PPPoE username/password or VLAN settings were erased by a reset.

## Steps
1. Check if the router is company-provided. Company routers can be re-provisioned remotely from ACS: trigger **re-provision** and ask the customer to reboot after 5 minutes.
2. For customer-owned routers, share the PPPoE username from CRM. Reset the PPPoE password and share it over SMS to the registered number only.
3. Guide the customer to set **WAN type: PPPoE**, VLAN ID as per their circle (shown in CRM), and save.
4. Set up the WiFi name and password again (KB-007).
5. Confirm the internet light turns green and run a speed test.

## Escalate when
- Re-provisioning fails twice.
- The company router does not power on or the reset button is stuck (raise router replacement; free within warranty).
