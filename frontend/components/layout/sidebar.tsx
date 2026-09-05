"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { StatusPill } from "./status-pill";

/** Reflects what actually exists in this project -- no Rules/Models/
 * Integrations/Customers pages, because this app doesn't have those. */
const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/transactions", label: "Transactions" },
  { href: "/test-transaction", label: "Test a Transaction" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col justify-between border-r border-border bg-surface px-5 py-6">
      <div>
        <div className="mb-10">
          <p className="font-display text-lg text-text">Fraud Detection</p>
          <p className="mt-1 font-mono text-[11px] uppercase tracking-wider text-text-muted">
            paysim &middot; xgboost &middot; shap
          </p>
        </div>

        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md border-l-2 px-3 py-2 text-sm transition-colors ${
                  active
                    ? "border-accent bg-surface-2 font-medium text-text"
                    : "border-transparent text-text-muted hover:bg-surface-2 hover:text-text"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <StatusPill />
    </aside>
  );
}
