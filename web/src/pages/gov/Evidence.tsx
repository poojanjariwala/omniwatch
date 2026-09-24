import { useEffect, useState } from "react";
import { Chip, Err, Empty, Kv, Panel, Btn } from "../../components/ui";
import { request, requestBlob } from "../../lib/api";
import { useGet } from "../../lib/hooks";
import { fmtTime, shortHash, titleCase } from "../../lib/format";

interface Evidence {
  id: number; kind: string; mime: string; sha256: string; chain_hash: string;
  chain_prev_hash: string; source: string; captured_at?: string; lat?: number | null;
  lng?: number | null; geofence_ok?: boolean | null; distance_m?: number | null;
  inspection_id?: number | null; case_id?: number | null; metadata?: any;
}

export default function GovEvidence() {
  const list = useGet<{ evidence: Evidence[] }>("/api/evidence?limit=120", [], { pollMs: 20000 });
  const [sel, setSel] = useState<Evidence | null>(null);
  const [blobUrl, setBlobUrl] = useState("");
  const [integrity, setIntegrity] = useState<any>(null);
  const [chain, setChain] = useState<Evidence[]>([]);

  useEffect(() => {
    let dead = false;
    setIntegrity(null);
    if (!sel) { setBlobUrl(""); return; }
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    requestBlob(`/api/evidence/${sel.id}/file`).then((b) => {
      if (!dead) setBlobUrl(URL.createObjectURL(b));
    }).catch(() => undefined);
    request<any>(`/api/evidence/${sel.id}`).then((d) => {
      if (!dead) setIntegrity(d.integrity);
    }).catch(() => undefined);
    if (sel.inspection_id) {
      request<{ evidence: Evidence[] }>(`/api/evidence?inspection_id=${sel.inspection_id}`)
        .then((d) => { if (!dead) setChain(d.evidence.slice().sort((a, b) => a.id - b.id)); })
        .catch(() => undefined);
    } else {
      setChain([]);
    }
    return () => { dead = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel?.id]);

  async function verifyNow() {
    if (!sel) return;
    setIntegrity(await request<any>(`/api/evidence/${sel.id}/verify`, { method: "POST" }));
  }

  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>Evidence console</h1>
      <div className="grid cols-2-1">
        <Panel title="Evidence list" bodyPad={false}>
          <table className="tbl">
            <thead><tr><th>ID</th><th>Kind / source</th><th>Captured</th><th>Geo</th><th>SHA-256</th></tr></thead>
            <tbody>
              {(list.data?.evidence ?? []).map((e) => (
                <tr key={e.id} className={sel?.id === e.id ? "" : "rowlink"}
                  onClick={() => setSel(e)}>
                  <td className="mono">{e.id}</td>
                  <td><Chip tone="neutral">{titleCase(e.kind)}</Chip> <span className="caption">{e.source}</span></td>
                  <td className="caption">{fmtTime(e.captured_at)}</td>
                  <td>{e.geofence_ok ? <Chip tone="green">ok</Chip> : e.geofence_ok === false ? <Chip tone="red">outside</Chip> : <span className="caption">n/a</span>}</td>
                  <td className="mono caption">{shortHash(e.sha256)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {list.error && <Err message={list.error} />}
          {!list.loading && !list.data?.evidence.length && <Empty text="No evidence captured yet" />}
        </Panel>

        <Panel title="Selected artifact" bodyPad={false}>
          {sel ? (
            <div className="stack" style={{ padding: 12 }}>
              <Kv rows={[
                ["Kind", `${sel.kind} (${sel.mime})`],
                ["Captured", fmtTime(sel.captured_at)],
                ["Source", sel.source],
                ["Geo", sel.lat != null ? `${sel.lat?.toFixed(5)}, ${sel.lng?.toFixed(5)}` : "—"],
                ["Geofence", sel.geofence_ok ? "inside (validated)" : sel.geofence_ok === false ? `outside by ${sel.distance_m?.toFixed(0)} m` : "not checked"],
                ["SHA-256", sel.sha256],
              ]} />
              <Btn small onClick={verifyNow}>Re-verify integrity</Btn>
              {integrity && (
                <div className={integrity.ok ? "ok-box" : "error-box"}>
                  integrity {integrity.ok ? "confirmed (hash + chain)" : "MISMATCH"}
                  {!integrity.ok && ` sha=${integrity.sha256_match}, chain=${integrity.chain_match}`}
                </div>
              )}
            </div>
          ) : <Empty text="Select an artifact" />}
        </Panel>
      </div>

      {sel && (
        <div className="grid cols-2">
          <Panel title="Media preview (authorized download)" bodyPad={false}>
            <div className="console-media">
              {blobUrl
                ? (sel.mime.startsWith("video")
                  ? <video src={blobUrl} controls />
                  : <img src={blobUrl} alt="evidence artifact" />)
                : <Empty text="Loading authorized preview…" />}
            </div>
          </Panel>
          <Panel title="Chain-of-custody for this evidence set" bodyPad>
            {chain.length === 0 && <Empty text="No chain context" />}
            <div className="chain-timeline">
              {chain.map((c) => (
                <div key={c.id} className="chain-item">
                  <div className="row">
                    <Chip tone={c.id === sel.id ? "blue" : "neutral"}>artifact {c.id}</Chip>
                    <span className="caption">{fmtTime(c.captured_at)}</span>
                    <Chip tone={c.geofence_ok ? "green" : c.geofence_ok === false ? "red" : "neutral"}>
                      {c.geofence_ok ? "geo ok" : c.geofence_ok === false ? "geo fail" : "n/a"}
                    </Chip>
                  </div>
                  <div className="mono caption">sha {shortHash(c.sha256, 18)}</div>
                  {c.id !== sel.id && <Btn small onClick={() => setSel(c)}>View</Btn>}
                </div>
              ))}
            </div>
            <p className="caption">Each artifact hashes content + metadata and links to its predecessor — tampering breaks the chain.</p>
          </Panel>
        </div>
      )}
    </div>
  );
}
