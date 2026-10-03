---
ref: KB-020
title: Mobile number portability (port in / port out)
product: mobile
category: sim_activation_porting
tags: mnp, port, upc code, porting, number transfer
---

## Symptoms
- Customer wants to move their number to us from another operator, or away from us.
- Porting request was rejected or is taking too long.

## Likely causes
- Unique Porting Code (UPC) expired (valid for 4 days in most circles).
- Outstanding dues on the old connection.
- Name/document mismatch with the donor operator.

## Steps
1. For port-in: the customer sends `PORT <number>` to 1900 from the existing SIM, gets a UPC and visits a store or orders a SIM online with the UPC.
2. Porting completes within **3 working days** (5 for the North East and J&K). There is a short service gap on the night of porting.
3. If rejected, check the rejection reason in CRM and explain it (dues, UPC expired, mismatch).
4. For port-out requests, do not try to block the request. Share retention offers only if the customer is open to it.

## Escalate when
- Porting is pending beyond the regulatory timeline.
- The customer says the number was ported out without their request (fraud, KB-033).
