import type { Metadata } from "next";
import { ExternalLink, Mail, FileText } from "lucide-react";
import Container from "@/components/Container";
import { contact } from "@/content/contact";

export const metadata: Metadata = {
  title: "Contact",
  description: "Get in touch with Gurkirat Singh about analytics, automation, and applied AI work.",
};

const links = [
  { label: contact.email, href: `mailto:${contact.email}`, icon: Mail },
  { label: contact.linkedin, href: `https://${contact.linkedin}`, icon: ExternalLink },
  { label: contact.github, href: `https://${contact.github}`, icon: ExternalLink },
  { label: "Resume available on request", href: contact.resumeHref, icon: FileText },
];

export default function ContactPage() {
  return (
    <Container className="py-16">
      <h1 className="text-3xl font-bold tracking-tight text-text sm:text-4xl">Contact</h1>
      <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted">{contact.intro}</p>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {links.map(({ label, href, icon: Icon }) => (
          <a
            key={label}
            href={href}
            className="flex items-center gap-3 rounded-lg border border-border bg-surface px-5 py-4 text-sm font-medium text-text transition-colors hover:border-accent-blue/60"
          >
            <Icon aria-hidden="true" size={18} className="shrink-0 text-accent-cyan" />
            {label}
          </a>
        ))}
      </div>
    </Container>
  );
}
