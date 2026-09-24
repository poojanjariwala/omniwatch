import { useEffect, type ReactNode } from "react";

export function Chip({ tone = "neutral", children }: { tone?: string; children: ReactNode }) {
  return <span className={`chip ${tone}`}>{children}</span>;
}

export function Dot({ tone = "green" }: { tone?: string }) {
  return <span className={`dot ${tone}`} aria-hidden />;
}

export function Panel({
  title, right, children, className = "", bodyPad = true,
}: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string;
  bodyPad?: boolean;
}) {
  return (
    <div className={`panel ${className}`}>
      {(title || right) && (
        <div className="panel-head">
          <span className="panel-title">{title}</span>
          {right && <div>{right}</div>}
        </div>
      )}
      <div className={bodyPad ? "panel-body" : ""}>{children}</div>
    </div>
  );
}

export function Btn({
  children, onClick, kind, disabled, small, title, type = "button", ariaLabel,
}: {
  children: ReactNode; onClick?: (e?: React.MouseEvent<HTMLButtonElement>) => void;
  kind?: "primary" | "danger";
  disabled?: boolean; small?: boolean; title?: string; type?: "button" | "submit";
  ariaLabel?: string;
}) {
  return (
    <button
      type={type}
      className={`btn ${kind} ${small ? "small" : ""}`}
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={ariaLabel}
    >
      {children}
    </button>
  );
}

export function Field({
  label, children, hint,
}: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="flabel">
      {label}
      {children}
      {hint && <span className="caption" style={{ fontWeight: 400 }}> {hint}</span>}
    </label>
  );
}

export function Empty({ text = "No records" }: { text?: string }) {
  return <div className="empty">{text}</div>;
}

export function Err({ message }: { message?: string }) {
  if (!message) return null;
  return <div className="error-box" role="alert">{message}</div>;
}

export function Ok({ message }: { message?: string }) {
  if (!message) return null;
  return <div className="ok-box" aria-live="polite">{message}</div>;
}

export function TrustRow({ states }: { states: Array<{ label: string; ok: boolean | null }> }) {
  return (
    <div className="statusrow" role="list" aria-label="Verification status">
      {states.map((s) => (
        <Chip key={s.label} tone={s.ok === true ? "green" : s.ok === false ? "red" : "neutral"}>
          <Dot tone={s.ok === true ? "green" : s.ok === false ? "red" : "neutral"} />
          {s.label}
        </Chip>
      ))}
    </div>
  );
}

export function Modal({
  title, onClose, children, wide,
}: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  // Escape closes; focus is inside the dialog because the close flow starts
  // from a click within it (no focus trap needed for this MVP dialog).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 1200,
        display: "grid", placeItems: "center", padding: 24,
      }}
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="panel modal-panel"
        style={{ width: wide ? 900 : 520, maxHeight: "88vh", overflow: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="panel-head">
          <span className="panel-title">{title}</span>
          <Btn small onClick={onClose} ariaLabel="Close dialog">✕</Btn>
        </div>
        <div className="panel-body stack">{children}</div>
      </div>
    </div>
  );
}

export function FlowDiagram({ extra }: { extra?: ReactNode }) {
  return (
    <div className="flow" aria-label="Evidence flow">
      <span className="node">Data</span><span className="arrow">→</span>
      <span className="node ai">AI detect · prioritise · explain</span>
      <span className="arrow">→</span>
      <span className="node">Inspection</span><span className="arrow">→</span>
      <span className="node">Evidence</span><span className="arrow">→</span>
      <span className="node human">Authorised official verify · decide</span>
      <span className="arrow">→</span>
      <span className="node">Audit</span>
      {extra}
    </div>
  );
}

export function Kv({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <div className="kv">
      {rows.map(([k, v]) => (
        <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: 16, padding: "3px 0" }}>
          <span className="k">{k}</span>
          <span style={{ textAlign: "right" }}>{v}</span>
        </div>
      ))}
    </div>
  );
}
