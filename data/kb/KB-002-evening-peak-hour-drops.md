---
ref: KB-002
title: Internet drops or buffers in the evening (peak hours)
product: broadband
category: broadband_disconnection
tags: evening, peak hours, wifi congestion, channel, 5ghz, firmware
---

## Symptoms
- Connection is fine during the day but drops or buffers between 7 PM and 11 PM.
- Streaming quality falls and video calls lag in the evening.
- Several devices are online at the same time when the problem happens.

## Likely causes
- WiFi channel congestion from neighbouring routers in apartments.
- Too many devices on the 2.4 GHz band.
- Old router firmware with known stability bugs.
- Congestion on the local access node (OLT/port) during peak hours.

## Steps
1. Confirm the timing pattern with the customer (which days, which hours).
2. Ask the customer to run a **wired** speed test (laptop on LAN cable) during the problem window. If wired is fine, it is a WiFi issue.
3. For WiFi issues: log in to the router remotely (ACS) and switch the 2.4 GHz channel to 1, 6 or 11, whichever is least crowded. Enable the 5 GHz band and ask the customer to use it for laptops and TVs.
4. Push the latest firmware to the router from ACS and reboot it.
5. If the wired test is also slow or drops, check the node utilisation report. If the node is above 80% in peak hours, raise a **capacity** ticket with the network team.
6. Call the customer back the next evening to confirm.

## Escalate when
- Wired connection also drops during peak hours.
- Node utilisation is above 80% for 3 days in a row.
- Firmware update fails or the router model is end-of-life (offer a router replacement).
