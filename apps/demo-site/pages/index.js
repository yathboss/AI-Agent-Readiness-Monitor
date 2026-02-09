import Link from "next/link";

export default function Home() {
  return (
    <main style={{ fontFamily: "system-ui", padding: 24, lineHeight: 1.4 }}>
      <h1>AWOA Demo Site</h1>
      <p>
        This site contains intentionally &ldquo;agent-hostile&rdquo; patterns to test Phase-1 determinism.
      </p>
      <ul>
        <li><Link href="/pricing">Pricing</Link> (rendered via JS after delay + large HTML)</li>
        <li><Link href="/refund">Refund Policy</Link> (policy only via PDF link)</li>
        <li><Link href="/contact">Contact</Link> (email in plain text)</li>
      </ul>

      <p style={{ marginTop: 18 }}>
        Tip: Run the runner against <code>http://localhost:3000</code>.
      </p>
    </main>
  );
}
