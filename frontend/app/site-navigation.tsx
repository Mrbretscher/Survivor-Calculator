"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const sections = [
  { href: "/", label: "Predictions" },
  { href: "/analytics", label: "Analytics" },
  { href: "/methodology", label: "Methodology" }
];

export default function SiteNavigation() {
  const pathname = usePathname();

  return (
    <header className="siteHeader">
      <div className="siteHeaderInner">
        <Link className="siteBrand" href="/">Survivor Calculator</Link>
        <nav className="siteNav" aria-label="Main navigation">
          {sections.map(({ href, label }) => {
            const active = href === "/"
              ? pathname === "/" || pathname.startsWith("/contestants/")
              : pathname === href || pathname.startsWith(`${href}/`);

            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? (pathname === href ? "page" : "location") : undefined}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
