import Link from "next/link";

export default function Contact() {
  return (
    <main style={{ fontFamily: "system-ui", padding: 24, lineHeight: 1.4 }}>
      <h1>Contact</h1>
      <p>
        <Link href="/">Home</Link> · <Link href="/pricing">Pricing</Link> · <Link href="/refund">Refund</Link>
      </p>

      <p>
        You can reach us at: <strong>support@awoa-demo.local</strong>
      </p>

      <p>
        Or use our contact page (you are already here).
      </p>
    </main>
  );
}
