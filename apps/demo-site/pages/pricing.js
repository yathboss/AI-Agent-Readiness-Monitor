import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

export default function Pricing() {
  // Large inline script/text to bloat initial HTML (helps trigger js_only heuristics)
  const bigNoise = useMemo(() => "x".repeat(180000), []);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setReady(true), 5000); // intentionally long delay
    return () => clearTimeout(t);
  }, []);

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, lineHeight: 1.4 }}>
      <h1>Pricing</h1>
      <p>
        <Link href="/">Home</Link> · <Link href="/contact">Contact</Link> · <Link href="/refund">Refund</Link>
      </p>

      {/* Big noise block */}
      <pre style={{ display: "none" }}>{bigNoise}</pre>

      {!ready ? (
        <div>
          <p>Loading plans...</p>
          <p>(Pricing is rendered via JavaScript after a delay.)</p>
        </div>
      ) : (
        <section>
          <h2>Plans</h2>
          <ul>
            <li>Starter — $9 / month</li>
            <li>Pro — $29 / month</li>
            <li>Enterprise — Contact us</li>
          </ul>
        </section>
      )}
    </main>
  );
}
