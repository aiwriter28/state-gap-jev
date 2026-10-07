# Synthetic example: add service hours

An existing customer has a valid service agreement and wants five additional hours. They should reach an add-hours checkout without signing a second contract.

The original design models the payment confirmation but leaves `payment.ready.add_hours` undecided. The corrected design connects that event to a pending payment. A successful payment updates entitlement and the operations ledger. A failed payment returns the payment to ready for another attempt.

Refunds after hours have been granted require service operations to review consumed time and reconcile entitlement and the ledger manually. Duplicate purchase notifications and repeated provider events must be deduplicated using original IDs. These are design decisions, not proof of working integrations.

The example deliberately has a small domain profile with payment, entitlement and operations. Its six events cross eight states to make 48 cells. It does not model every possible commerce concern. The explicit ignored decisions are assumptions of this fictional workflow only.

The local browser demo is narrower: it checks whether the customer can find the correct checkout entry. It cannot prove billing, extra hours, ledger updates, refunds or deduplication. Those properties require independent backend observations and sandbox adapters.

Model boundary: one additional-hours purchase by a customer who already has a valid agreement. Entry is that customer selecting add hours; successful fulfillment credits exactly five hours. A later legitimate purchase begins another instance of this workflow. Repeated clicks or callbacks for this purchase must not create another entitlement. Acquisition, signing a first agreement and account eligibility are outside this bounded example.
