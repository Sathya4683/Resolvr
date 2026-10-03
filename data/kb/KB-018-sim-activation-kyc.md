---
ref: KB-018
title: New SIM activation and KYC verification
product: mobile
category: sim_activation_porting
tags: sim activation, kyc, new sim, replacement sim, verification
---

## Symptoms
- New or replacement SIM is not active after several hours.
- Customer got an SMS saying KYC verification failed.

## Likely causes
- e-KYC still under verification.
- Tele-verification call (for outstation customers) not completed.
- Document mismatch.

## Steps
1. Check the activation status in CRM. Normal activation time is **up to 4 hours** after successful e-KYC.
2. If tele-verification is pending, ask the customer to call the verification number from the new SIM and confirm their details.
3. If KYC failed, explain the reason and ask the customer to visit a store with the original ID proof. Do not accept documents over chat or email.
4. For replacement SIMs, the old SIM stops working once the new one is active.

## Escalate when
- Activation is pending for more than 24 hours with KYC approved.
- The customer did not request the replacement SIM (treat as possible SIM swap fraud, KB-033).
