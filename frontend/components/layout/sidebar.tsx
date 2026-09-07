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
  { href: "/simulator", label: "Simulator" },
  { href: "/checkout", label: "Checkout Demo" },
  { href: "/about", label: "About" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    // Below `lg`, this collapses from a left column into a horizontal top bar
    // (a scrollable nav row, wordmark and StatusPill stacked above it) rather
    // than a hamburger/drawer -- every nav item stays one tap away with no
    // extra state, and it's a pure Tailwind-breakpoint change with no new
    // interactivity to get wrong. At `lg` and above this is byte-for-byte the
    // original fixed-width left sidebar.
    <aside className="flex w-full shrink-0 flex-col gap-4 border-b border-border bg-surface px-4 py-4 lg:h-full lg:w-60 lg:justify-between lg:border-b-0 lg:border-r lg:px-5 lg:py-6">
      <div>
        <div className="mb-4 lg:mb-10">
          <p className="font-display text-lg text-text">Fraud Detection</p>
          <p className="mt-1 font-mono text-[11px] uppercase tracking-wider text-text-muted">
            paysim &middot; xgboost &middot; shap
          </p>
        </div>

        <nav className="flex gap-1 overflow-x-auto lg:flex-col">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`shrink-0 whitespace-nowrap rounded-md border-l-2 px-3 py-2 text-sm transition-colors ${
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
