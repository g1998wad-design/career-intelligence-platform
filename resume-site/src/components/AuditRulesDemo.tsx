"use client";

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import StatusChip from "./StatusChip";
import { syntheticDataLabel } from "@/content/site";
import {
  SEED_DOCUMENTS,
  SEED_PAYMENTS,
  evaluatePaymentRow,
  type PaymentRow,
} from "@/lib/auditRules";

const PAYMENT_METHOD_OPTIONS = ["EFT", "CHECK", "WIRE"];

function cloneSeed(): PaymentRow[] {
  return SEED_PAYMENTS.map((row) => ({ ...row }));
}

export default function AuditRulesDemo() {
  const [rows, setRows] = useState<PaymentRow[]>(cloneSeed);

  function updateRow(index: number, field: keyof PaymentRow, value: string) {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  }

  function reset() {
    setRows(cloneSeed());
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text">
            Edit a payment record and watch the control engine re-evaluate it
          </p>
          <p className="mt-1 text-sm text-muted">
            This is a simplified client-side reimplementation of the deterministic control logic
            described above, running entirely in your browser for demonstration — ({syntheticDataLabel}).
            The production version also includes AI-assisted document extraction feeding these
            same rules; no AI runs here, and nothing is sent anywhere.
          </p>
        </div>
        <button
          type="button"
          onClick={reset}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:border-accent-blue/60 hover:text-text"
        >
          <RotateCcw aria-hidden="true" size={14} />
          Reset
        </button>
      </div>

      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <caption className="sr-only">
            Editable synthetic payment population evaluated against two synthetic support packets
          </caption>
          <thead>
            <tr className="bg-surface-light">
              <th scope="col" className="whitespace-nowrap px-3 py-2 font-mono text-xs font-medium uppercase tracking-wide text-muted">
                voucher_id
              </th>
              <th scope="col" className="whitespace-nowrap px-3 py-2 font-mono text-xs font-medium uppercase tracking-wide text-muted">
                invoice_id
              </th>
              <th scope="col" className="whitespace-nowrap px-3 py-2 font-mono text-xs font-medium uppercase tracking-wide text-muted">
                payment_method
              </th>
              <th scope="col" className="whitespace-nowrap px-3 py-2 font-mono text-xs font-medium uppercase tracking-wide text-muted">
                gross_amount
              </th>
              <th scope="col" className="whitespace-nowrap px-3 py-2 font-mono text-xs font-medium uppercase tracking-wide text-muted">
                Rule result
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const evaluation = evaluatePaymentRow(row, SEED_DOCUMENTS);
              return (
                <tr key={i} className="border-t border-border align-top">
                  <td className="px-3 py-2">
                    <label className="sr-only" htmlFor={`voucher-${i}`}>
                      Voucher ID for row {i + 1}
                    </label>
                    <input
                      id={`voucher-${i}`}
                      value={row.voucherId}
                      onChange={(e) => updateRow(i, "voucherId", e.target.value)}
                      className="w-32 rounded-md border border-border bg-bg px-2 py-1 font-mono text-xs text-text focus-visible:border-accent-blue"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <label className="sr-only" htmlFor={`invoice-${i}`}>
                      Invoice ID for row {i + 1}
                    </label>
                    <input
                      id={`invoice-${i}`}
                      value={row.invoiceId}
                      onChange={(e) => updateRow(i, "invoiceId", e.target.value)}
                      className="w-28 rounded-md border border-border bg-bg px-2 py-1 font-mono text-xs text-text focus-visible:border-accent-blue"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <label className="sr-only" htmlFor={`method-${i}`}>
                      Payment method for row {i + 1}
                    </label>
                    <select
                      id={`method-${i}`}
                      value={row.paymentMethod}
                      onChange={(e) => updateRow(i, "paymentMethod", e.target.value)}
                      className="rounded-md border border-border bg-bg px-2 py-1 font-mono text-xs text-text focus-visible:border-accent-blue"
                    >
                      {PAYMENT_METHOD_OPTIONS.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <label className="sr-only" htmlFor={`amount-${i}`}>
                      Gross amount for row {i + 1}
                    </label>
                    <input
                      id={`amount-${i}`}
                      value={row.grossAmount}
                      onChange={(e) => updateRow(i, "grossAmount", e.target.value)}
                      inputMode="decimal"
                      className="w-24 rounded-md border border-border bg-bg px-2 py-1 font-mono text-xs text-text focus-visible:border-accent-blue"
                    />
                  </td>
                  <td className="min-w-[260px] px-3 py-2">
                    <div className="flex flex-col gap-1.5">
                      <StatusChip status={evaluation.status} />
                      <p className="text-xs leading-relaxed text-muted">{evaluation.message}</p>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs text-muted">
        Only two synthetic support packets exist (for voucher_id 00018427 and 00018428) — try
        changing a gross_amount, an invoice_id, or the payment_method to see PASS, FAIL, REVIEW,
        and EXCLUDED all appear, or restore the original values with Reset.
      </p>
    </div>
  );
}
