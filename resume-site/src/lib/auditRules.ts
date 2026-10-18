import type { RuleStatus } from "@/types/project";

export type PaymentRow = {
  voucherId: string;
  supplierName: string;
  invoiceId: string;
  paymentMethod: string;
  grossAmount: string;
};

export type DocumentRecord = {
  voucherId: string;
  invoiceId: string;
  invoiceAmount: number;
  approvalFound: boolean;
};

export type RuleEvaluation = {
  status: RuleStatus;
  message: string;
};

const IN_SCOPE_PAYMENT_METHODS = ["EFT", "CHECK"];
const AMOUNT_TOLERANCE = 0.01;

export function normalizeIdentifier(value: string): string {
  if (!value) return "";
  return value.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function normalizeAmount(value: string): number | null {
  if (!value || !value.trim()) return null;
  const cleaned = value.replace(/[^0-9.-]/g, "");
  if (!cleaned) return null;
  const parsed = Number(cleaned);
  if (Number.isNaN(parsed)) return null;
  return Math.round(parsed * 100) / 100;
}

/** Deterministic reimplementation of the case study's control logic, for demonstration only. */
export function evaluatePaymentRow(row: PaymentRow, documents: DocumentRecord[]): RuleEvaluation {
  const voucherKey = normalizeIdentifier(row.voucherId);
  if (!voucherKey) {
    return {
      status: "REVIEW",
      message: "Voucher ID could not be read from the input — insufficient evidence to evaluate.",
    };
  }

  const methodKey = normalizeIdentifier(row.paymentMethod);
  if (!IN_SCOPE_PAYMENT_METHODS.includes(methodKey)) {
    return {
      status: "EXCLUDED",
      message: `Payment method "${row.paymentMethod}" is outside the configured audit scope.`,
    };
  }

  const doc = documents.find((d) => normalizeIdentifier(d.voucherId) === voucherKey);
  if (!doc) {
    return {
      status: "FAIL",
      message: "No matching support packet was found for this in-scope record.",
    };
  }

  const invoiceKey = normalizeIdentifier(row.invoiceId);
  const docInvoiceKey = normalizeIdentifier(doc.invoiceId);
  if (invoiceKey !== docInvoiceKey) {
    return {
      status: "FAIL",
      message: `Invoice identifier "${row.invoiceId}" does not match the support packet after normalization.`,
    };
  }

  const amount = normalizeAmount(row.grossAmount);
  if (amount === null) {
    return {
      status: "REVIEW",
      message: "Payment amount could not be parsed — insufficient evidence to evaluate.",
    };
  }
  if (Math.abs(amount - doc.invoiceAmount) > AMOUNT_TOLERANCE) {
    return {
      status: "FAIL",
      message: `Payment amount (${amount.toFixed(2)}) does not match the support packet (${doc.invoiceAmount.toFixed(2)}) within tolerance.`,
    };
  }

  if (!doc.approvalFound) {
    return {
      status: "REVIEW",
      message: "Approval evidence could not be confirmed from the supplied packet.",
    };
  }

  return {
    status: "PASS",
    message: "Evidence supports every configured rule for this record.",
  };
}

export const SEED_PAYMENTS: PaymentRow[] = [
  {
    voucherId: "00018427",
    supplierName: "Supplier Alpha",
    invoiceId: "INV-1048",
    paymentMethod: "EFT",
    grossAmount: "2840.50",
  },
  {
    voucherId: "00018428",
    supplierName: "Supplier Bravo",
    invoiceId: "SB-7781",
    paymentMethod: "CHECK",
    grossAmount: "6725.00",
  },
  {
    voucherId: "00018429",
    supplierName: "Supplier Charlie",
    invoiceId: "2026-0312",
    paymentMethod: "EFT",
    grossAmount: "1198.20",
  },
];

export const SEED_DOCUMENTS: DocumentRecord[] = [
  { voucherId: "00018427", invoiceId: "INV-1048", invoiceAmount: 2840.5, approvalFound: true },
  { voucherId: "00018428", invoiceId: "SB-7781", invoiceAmount: 6725.0, approvalFound: false },
];
