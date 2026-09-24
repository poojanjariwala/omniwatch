import { useState } from "react";
import { Chip, Err, Panel } from "../components/ui";
import { apiErrorText, request } from "../lib/api";

export default function VerifyPage() {
  const [code, setCode] = useState("");
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");

  async function check(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setResult(null);
    try {
      setResult(await request("/api/qr/verify", { method: "POST", json: { code } }));
    } catch (ex) { setErr(apiErrorText(ex)); }
  }

  return (
    <div className="stack" style={{ maxWidth: 520 }}>
      <h1 style={{ margin: 0 }}>Verify a handout</h1>
      <Panel title="QR handout status">
        <form className="stack" onSubmit={check}>
          <input className="field mono" placeholder="Enter the item QR code (or scan code text)" value={code}
            onChange={(e) => setCode(e.target.value)} />
          <button className="btn primary" type="submit">Check status</button>
        </form>
        {err && <Err message={err} />}
        {result && (
          <div className="row">
            <Chip tone={result.status === "consumed" ? "green" : "amber"}>{result.status}</Chip>
            <span>{result.message}</span>
            {result.serial && <span className="caption">item #{result.serial}</span>}
          </div>
        )}
      </Panel>
      <p className="caption">This read-only check never exposes personal, alert or risk information.</p>
    </div>
  );
}
