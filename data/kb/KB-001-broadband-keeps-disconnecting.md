---
ref: KB-001
title: Broadband keeps disconnecting - first checks
product: broadband
category: broadband_disconnection
tags: disconnection, router, power cycle, cables, los light
---

## Symptoms
- Internet drops several times a day and comes back on its own after a few minutes.
- Router lights blink or the internet/PON light goes off during the drop.
- Video calls freeze and downloads restart.

## Likely causes
- Loose or damaged LAN/fibre patch cord behind the router.
- Router running for weeks without a restart (memory leak, stale session).
- Power fluctuations at the customer premises.
- Line fault between the building and the exchange.

## Steps
1. Ask the customer to check the router lights during a drop. Note whether the **PON/DSL** light goes off (line problem) or only the **WiFi/Internet** light (router or session problem).
2. Check the line status from the CRM line test. If sync drops are logged, skip to step 6.
3. Have the customer power cycle the router: switch off, wait 30 seconds, switch on, wait 3 minutes.
4. Ask them to re-seat the fibre patch cord and LAN cables and make sure the fibre cable is not bent sharply.
5. If drops coincide with power cuts, recommend plugging the router into a UPS or surge protector.
6. If the line test shows repeated sync loss, raise a **line fault** ticket for a field visit (target: 24 hours).
7. Monitor the connection for 24 hours and call the customer back.

## Escalate when
- More than 3 drops a day continue after a router restart and cable check.
- Line test shows high attenuation or sync loss.
- The customer reports the same issue for the third time in 30 days.
