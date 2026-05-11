import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="site-footer page-pad">
      <span>ChessBench by Arjun Sahlot</span>
      <Link href="https://github.com/ArjunSahlot/ChessBench" target="_blank" rel="noreferrer">
        Source
      </Link>
    </footer>
  );
}
