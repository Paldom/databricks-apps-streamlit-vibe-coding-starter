# RAG Test Set — Northwind Robotics Knowledge Base

A fictional corporate knowledge base of 3 interrelated PDFs, plus a graded
question set for evaluating retrieval and answer quality.

## Documents

| ID | File | Contents |
|----|------|----------|
| D1 | `01_Employee_Handbook.pdf` | Company overview, hours, PTO, parental leave, conduct, expenses |
| D2 | `02_Travel_Expense_Policy.pdf` | Booking, travel class, per-diem, mileage, submission rules |
| D3 | `03_Sustainability_Report_2024.pdf` | Emissions data, sustainable travel, product footprint, targets |

The documents deliberately overlap (e.g. the 30-day expense rule appears in
both D1 and D2; the travel policy is referenced by the sustainability report)
so you can test cross-document consistency and conflicting-source handling.

---

## A. Single-hop factual (answer in one chunk)

1. **How many PTO days does an employee with 4 years of tenure accrue per year?**
   → 24 days. *(D1, §3 table)*

2. **What is the receipt threshold for reimbursable expenses?**
   → Receipts are mandatory for any expense above 25 USD. *(D1 §6 / D2 §6)*

3. **What class of travel is permitted for a 6-hour flight?**
   → Premium Economy (Director approval needed to upgrade). *(D2, §3 table)*

4. **By how much did Scope 2 emissions change from 2023 to 2024?**
   → Down from 6,800 to 5,400 tCO2e. *(D3, §1 table)*

5. **Who chairs the Environmental Steering Committee?**
   → The Chief Operating Officer. *(D3, §5)*

6. **What are the core collaboration hours?**
   → 11:00 AM to 3:00 PM Pacific Time. *(D1, §2)*

## B. Multi-hop / cross-document (requires combining chunks)

7. **An employee in Berlin with 7 years of tenure has 30 unused PTO days on
   Dec 31. How many can they carry over, and why does this differ from the
   default rule?**
   → All 30 days, until March 31, because Berlin local law permits full
   carryover, overriding the standard 5-day cap. *(D1 §3 — two sentences)*

8. **The Sustainability Report credits the Travel Policy with avoiding ~600
   tCO2e. Which two specific travel rules drive that saving?**
   → The rail-first rule for short European journeys and tighter approval for
   trips above 5,000 USD. *(D3 §2 + corroborated by D2 §2 and §3)*

9. **If the Employee Handbook and the Travel & Expense Policy disagree on an
   expense matter, which one wins?**
   → The Travel & Expense Policy takes precedence. *(D2 §1 — tests precedence
   reasoning across D1/D2)*

10. **A staff member takes a 9-hour international flight to London and stays
    2 days. What travel class may they book and what is the per-diem total?**
    → Business class (over 8 hours, available to all staff) and 170 USD
    per-diem (London = Tier 1 = 85 USD × 2 days). *(D2 §3 + §4)*

## C. Edge cases (unanswerable / ambiguous / negative)

11. **What is Northwind's 401(k) employer match percentage?**
    → Not answerable. No retirement-plan details are in any document. A good
    RAG system should abstain rather than hallucinate.

12. **Does the per-diem rate include lodging?**
    → No — per-diem covers meals and incidentals only; lodging is reimbursed
    separately at actual cost. *(D2 §4 — tests a tempting false inference)*

13. **What were the use-phase emissions of sold products in 2024?**
    → Not reported. The methodology note explicitly states use-phase
    emissions are not yet included. *(D3 §6 — answerable as an explicit
    "not available")*

14. **Can a new hire (3 months tenure) take paid parental leave?**
    → No — eligibility requires at least 12 months of continuous service.
    *(D1 §4 — tests negative answer)*

15. **What is the company's mileage reimbursement rate?**
    → Ambiguous without location: 0.67 USD/mile in the US, 0.30 EUR/km in
    the EU. A strong answer surfaces both and notes the dependency. *(D2 §7)*

---

## Suggested metrics

- **Retrieval:** Hit@k / Recall@k against the cited section(s).
- **Faithfulness:** Does the answer stay within retrieved context (esp. Q11)?
- **Abstention:** Correctly says "not in the documents" for Q11.
- **Multi-hop:** Q7, Q8, Q10 require ≥2 chunks — track whether all are retrieved.
- **Conflict handling:** Q9 tests precedence between two sources.
