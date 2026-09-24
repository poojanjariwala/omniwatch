import { useState } from "react";
import { apiErrorText, reauthenticate } from "../lib/api";
import { Btn, Modal, Err } from "./ui";

/** Runs a sensitive backend call only after password re-authentication mints a
 *  short-lived action token (server enforces it too). */
export default function ReauthBtn({
  label, kind = "primary", onDone, children,
}: {
  label?: string; kind?: "primary" | "danger"; onDone: (token: string) => Promise<void>;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const token = await reauthenticate(pw);
      await onDone(token);
      setOpen(false); setPw("");
    } catch (ex) {
      setErr(apiErrorText(ex));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Btn kind={kind} onClick={() => setOpen(true)}>{label ?? children}</Btn>
      {open && (
        <Modal title="Re-authenticate (sensitive action)" onClose={() => setOpen(false)}>
          <p className="muted" style={{ marginTop: 0 }}>
            This action is highly sensitive. Re-enter your password to authorise it.
          </p>
          <form className="stack" onSubmit={submit}>
            <input className="field" type="password" value={pw} autoFocus
              onChange={(e) => setPw(e.target.value)} placeholder="Password"
              autoComplete="current-password" />
            {err && <Err message={err} />}
            <div className="row">
              <Btn kind="primary" type="submit" disabled={busy || !pw}>{busy ? "Authorising…" : "Authorise"}</Btn>
              <Btn onClick={() => setOpen(false)}>Cancel</Btn>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
