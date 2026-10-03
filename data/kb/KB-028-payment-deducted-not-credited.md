---
ref: KB-028
title: Payment deducted but recharge or bill not updated
product: billing
category: billing_dispute
tags: payment failed, money deducted, double debit, upi, refund, recharge failed
---

## Symptoms
- Money was debited from the bank/UPI but the recharge or bill payment is not reflected.
- Customer was charged twice for the same payment.

## Likely causes
- Payment gateway timeout; the bank debited but the confirmation did not reach us.
- Customer retried the payment, causing a double debit.

## Steps
1. Ask for the transaction reference (UPI ref / bank ref) and the date. Do not ask for card numbers or OTPs.
2. Search the transaction in the payments console.
3. If the payment is found as successful, post it to the account manually.
4. If the payment failed on our side, the bank auto-reverses it within **5-7 working days**. Share the reversal status.
5. For a double debit, mark the second payment for refund. Refunds go back to the original payment method in 5-7 working days.

## Escalate when
- The transaction is not found in the console after 48 hours.
- Refund is not received after 10 working days.
