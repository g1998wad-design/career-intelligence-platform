import Link from "next/link";
import { footerDisclosure, nav, siteName } from "@/content/site";
import Container from "./Container";

export default function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="mt-24 border-t border-border/60">
      <Container className="flex flex-col gap-6 py-10">
        <p className="max-w-3xl text-sm leading-relaxed text-muted">
          {footerDisclosure}
        </p>
        <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
          <p className="text-sm text-muted">
            &copy; {year} {siteName}
          </p>
          <nav aria-label="Footer">
            <ul className="flex items-center gap-6 text-sm text-muted">
              {nav.map((item) => (
                <li key={item.href}>
                  <Link href={item.href} className="transition-colors hover:text-text">
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </Container>
    </footer>
  );
}
