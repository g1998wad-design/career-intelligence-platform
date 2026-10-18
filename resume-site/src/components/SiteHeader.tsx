import Link from "next/link";
import { nav, siteName } from "@/content/site";
import Container from "./Container";

export default function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-bg/90 backdrop-blur-sm">
      <Container className="flex h-16 items-center justify-between">
        <Link
          href="/"
          className="font-semibold tracking-tight text-text transition-colors hover:text-accent-cyan"
        >
          {siteName}
        </Link>
        <nav aria-label="Primary">
          <ul className="flex items-center gap-6 text-sm text-muted">
            {nav.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className="transition-colors hover:text-text"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </Container>
    </header>
  );
}
