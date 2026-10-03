---
ref: KB-009
title: Phone or laptop cannot connect to WiFi
product: broadband
category: router_wifi_setup
tags: authentication error, cannot connect, wifi, device, ip address
---

## Symptoms
- Device shows "authentication problem", "incorrect password" or "no internet, secured".
- Other devices work fine on the same WiFi.

## Likely causes
- Saved password on the device is old.
- Device does not support WPA3 or the 5 GHz band.
- Router has reached its maximum client limit or MAC filtering is on.

## Steps
1. Ask the customer to "forget" the network on the device and reconnect with the current password.
2. Restart the device and the router.
3. If the device is old, switch the router security mode to **WPA2/WPA3 mixed** from the app or router page.
4. Check the connected device list in the app. If it shows more than 30 devices, remove unknown ones and change the password (KB-007).
5. Check that MAC filtering is off unless the customer set it intentionally.

## Escalate when
- No device can connect to the WiFi even after a router restart (treat as router fault, see KB-008).
