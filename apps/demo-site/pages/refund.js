import Link from "next/link";

export default function Refund() {
  return (
    <main style={{ fontFamily: "system-ui", padding: 24, lineHeight: 1.4 }}>
      <h1>Customer Policies</h1>
      <p>
        <Link href="/">Home</Link> · <Link href="/pricing">Pricing</Link> · <Link href="/contact">Contact</Link>
      </p>

      <p>
        Download the policy document:
      </p>

      {/* Intentionally avoid putting "refund" in the visible link text */}
      <a href="/files/refund-policy.pdf">Download PDF</a>
    </main>
  );
}
