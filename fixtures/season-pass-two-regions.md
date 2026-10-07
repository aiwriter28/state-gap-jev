# Two-region fixture evidence map

Every element below comes from the committed Run A spec in
`evidence/state-gap-mapper-2026-08-31/runA-spec.txt`.

| Fixture element | Run A sentence |
|---|---|
| `payment`, `full_series_checkout_completed`, `visitor -> paid` | A Visitor or Subscribed parent completes Stripe checkout and moves to Paid. |
| `fulfillment`, `paid`, `paid_parent_fulfilled`, `paid -> paid` | Fulfillment sends Calendar invitations, grants Drive access, and sends a welcome email. |
| `calendar`, `file sharing` | Fulfillment sends Calendar invitations and grants Drive access. |
| `marketing groups`, `campaign sends`, `sales_campaign_sent` | MailerLite sends a sales campaign to the family and friends group. |
| `reminder sequences` | MailerLite sends two-day and one-day reminders. |
| `workflow engine` | The Stripe webhook creates an order. |
| `CRM` marked none | No sentence names a CRM. |
| Fulfillment states `visitor`, `paid`, `closed` | The parent starts as Visitor, checkout moves the parent to Paid, and cohort close moves Paid to Closed. |
| Marketing states `eligible`, `subscribed`, `unsubscribed` | Marketing is separate; consent adds the parent to the group, and unsubscribe stops campaigns. |
| `unsubscribe_clicked`, `subscribed -> unsubscribed` | Clicking unsubscribe moves Subscribed to Unsubscribed. |
| `cohort_closed`, `paid -> closed` | Cohort close moves every Paid parent to Closed. |
| Fulfillment ignores `sales_campaign_sent` | Marketing state is separate from fulfillment. |
| Fulfillment records `unsubscribe_clicked` absent | The spec defines unsubscribe only for the marketing audience and names no fulfillment handling. |
