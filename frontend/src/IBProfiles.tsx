import React, { useEffect, useState } from "react";
import { apiGet, apiPost, apiPatch, apiDelete } from "./api";

const BASE = "/settings/ib-profiles";

type Options = { levels: string[]; account_types: string[]; asset_classes: string[]; suffixes: string[] };
type Profile = {
  id: number; name: string; ib_level: string; account_types: string[];
  asset_class: string | null; match_symbols: string[]; match_suffixes: string[];
  points: number; min_hold_minutes: number; priority: number; active: boolean; published: boolean;
};

const blank = (level: string): Profile => ({
  id: 0, name: "", ib_level: level, account_types: [], asset_class: "forex",
  match_symbols: [], match_suffixes: [], points: 0, min_hold_minutes: 0,
  priority: 100, active: true, published: false,
});

export default function IBProfiles() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [opts, setOpts] = useState<Options | null>(null);
  const [lastPub, setLastPub] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [filter, setFilter] = useState<string>("all");
  const [edit, setEdit] = useState<Profile | null>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const d = await apiGet(BASE);
      setProfiles(d.profiles); setOpts(d.options);
      setLastPub(d.last_published_at); setDirty(d.has_unpublished);
      setErr("");
    } catch {
      setErr("Couldn't reach the server. Is the backend running on 127.0.0.1:8000?");
    }
  };
  useEffect(() => { load(); }, []);
  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 2500); };

  const save = async (p: Profile) => {
    try {
      if (p.id) await apiPatch(`${BASE}/${p.id}`, p);
      else await apiPost(BASE, p);
      setEdit(null); await load(); flash("Saved (draft — publish to go live)");
    } catch { flash("Save failed"); }
  };
  const duplicate = async (p: Profile) => {
    const lvl = prompt(`Duplicate "${p.name}" to which level?`, p.ib_level) || p.ib_level;
    try { await apiPost(`${BASE}/${p.id}/duplicate`, { ib_level: lvl }); await load(); flash("Duplicated"); }
    catch { flash("Duplicate failed"); }
  };
  const remove = async (p: Profile) => {
    if (!window.confirm(`Delete "${p.name}"?`)) return;
    try { await apiDelete(`${BASE}/${p.id}`); await load(); flash("Deleted"); }
    catch { flash("Delete failed"); }
  };
  const publish = async () => {
    if (!window.confirm("Publish all active profiles? They become live for commission calculations.")) return;
    try { await apiPost(`${BASE}/publish`, {}); await load(); flash("Published"); }
    catch { flash("Publish failed"); }
  };

  if (err) return <div style={S.page}><div style={S.errBox}>{err}</div></div>;
  if (!opts) return <div style={S.page}>Loading profiles…</div>;

  const shown = profiles.filter((p) => filter === "all" || p.ib_level === filter);
  const matchText = (p: Profile) =>
    p.match_symbols.length ? p.match_symbols.join(", ") : (p.asset_class || "any");

  return (
    <div style={S.page}>
      <div style={S.headRow}>
        <div>
          <h1 style={S.h1}>IB Commission Profiles</h1>
          <div style={S.sub}>
            Each profile = one rule (level + instruments + rate). Points are per 1.0 lot, in the symbol's quote currency.
            Last published: {lastPub ? new Date(lastPub).toLocaleString() : "never"}
            {dirty && <span style={S.badge}>Unpublished changes</span>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={S.btnGhost} onClick={() => setEdit(blank(opts.levels[0]))}>+ New profile</button>
          <button style={S.btnPrimary} onClick={publish}>Publish</button>
        </div>
      </div>

      <div style={S.tabs}>
        <button style={{ ...S.tab, ...(filter === "all" ? S.tabActive : {}) }} onClick={() => setFilter("all")}>All</button>
        {opts.levels.map((l) => (
          <button key={l} style={{ ...S.tab, ...(filter === l ? S.tabActive : {}) }} onClick={() => setFilter(l)}>{l}</button>
        ))}
      </div>

      <div style={S.card}>
        <table style={S.table}>
          <thead><tr>
            <th style={S.th}>Profile</th><th style={S.th}>Level</th><th style={S.th}>Matches</th>
            <th style={S.th}>Suffixes</th><th style={S.th}>Accounts</th>
            <th style={S.thNum}>Pts/lot</th><th style={S.thNum}>Min hold</th><th style={S.th}></th>
          </tr></thead>
          <tbody>
            {shown.map((p) => (
              <tr key={p.id} style={{ opacity: p.active ? 1 : 0.5 }}>
                <td style={S.tdLabel}>{p.name}{!p.published && <span style={S.dot} title="unpublished" />}</td>
                <td style={S.td}>{p.ib_level}</td>
                <td style={S.td}>{matchText(p)}</td>
                <td style={S.td}>{p.match_suffixes.length ? p.match_suffixes.map(s => s || "(none)").join(" ") : "any"}</td>
                <td style={S.td}>{p.account_types.length ? p.account_types.join(", ") : "any"}</td>
                <td style={S.tdNum}>{p.points}</td>
                <td style={S.tdNum}>{p.min_hold_minutes ? `${p.min_hold_minutes}m` : "—"}</td>
                <td style={S.tdNum}>
                  <button style={S.link} onClick={() => setEdit({ ...p })}>Edit</button>
                  <button style={S.link} onClick={() => duplicate(p)}>Duplicate</button>
                  <button style={{ ...S.link, color: "#b4232b" }} onClick={() => remove(p)}>Delete</button>
                </td>
              </tr>
            ))}
            {shown.length === 0 && <tr><td style={S.td} colSpan={8}>No profiles yet. Create one to get started.</td></tr>}
          </tbody>
        </table>
      </div>

      {edit && <Editor p={edit} opts={opts} onCancel={() => setEdit(null)} onSave={save} />}
      {msg && <div style={S.toast}>{msg}</div>}
    </div>
  );
}

function Editor({ p, opts, onCancel, onSave }:
  { p: Profile; opts: Options; onCancel: () => void; onSave: (p: Profile) => void }) {
  const [f, setF] = useState<Profile>(p);
  const set = (k: keyof Profile, v: any) => setF({ ...f, [k]: v });
  const toggle = (k: "account_types" | "match_suffixes", v: string) =>
    set(k, f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v]);

  return (
    <div style={S.overlay} onClick={onCancel}>
      <div style={S.modal} onClick={(e) => e.stopPropagation()}>
        <h2 style={S.h2}>{f.id ? "Edit profile" : "New profile"}</h2>

        <label style={S.lbl}>Name</label>
        <input style={S.in} value={f.name} placeholder="IB-5 / Gold"
          onChange={(e) => set("name", e.target.value)} />

        <div style={S.row}>
          <div style={{ flex: 1 }}>
            <label style={S.lbl}>IB level</label>
            <select style={S.in} value={f.ib_level} onChange={(e) => set("ib_level", e.target.value)}>
              {opts.levels.map((l) => <option key={l}>{l}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label style={S.lbl}>Points / lot</label>
            <input type="number" step="0.01" style={S.in} value={f.points}
              onChange={(e) => set("points", parseFloat(e.target.value) || 0)} />
          </div>
        </div>

        <label style={S.lbl}>Asset class (used when no explicit symbols below)</label>
        <select style={S.in} value={f.asset_class || ""} onChange={(e) => set("asset_class", e.target.value || null)}>
          <option value="">— none (use explicit symbols) —</option>
          {opts.asset_classes.map((a) => <option key={a}>{a}</option>)}
        </select>

        <label style={S.lbl}>Explicit base symbols (comma-separated, e.g. XAUUSD, BTCUSD) — overrides asset class</label>
        <input style={S.in} value={f.match_symbols.join(", ")}
          onChange={(e) => set("match_symbols", e.target.value.split(",").map(s => s.trim()).filter(Boolean))} />

        <label style={S.lbl}>Suffixes (which account variants; none selected = all)</label>
        <div style={S.chips}>
          {opts.suffixes.map((s) => (
            <button key={s} type="button"
              style={{ ...S.chip, ...(f.match_suffixes.includes(s) ? S.chipOn : {}) }}
              onClick={() => toggle("match_suffixes", s)}>{s || "(none)"}</button>
          ))}
        </div>

        <label style={S.lbl}>Account types (none selected = any)</label>
        <div style={S.chips}>
          {opts.account_types.map((a) => (
            <button key={a} type="button"
              style={{ ...S.chip, ...(f.account_types.includes(a) ? S.chipOn : {}) }}
              onClick={() => toggle("account_types", a)}>{a}</button>
          ))}
        </div>

        <div style={S.row}>
          <div style={{ flex: 1 }}>
            <label style={S.lbl}>Min hold (minutes; 0 = pay all)</label>
            <input type="number" style={S.in} value={f.min_hold_minutes}
              onChange={(e) => set("min_hold_minutes", parseInt(e.target.value) || 0)} />
          </div>
          <div style={{ flex: 1 }}>
            <label style={S.lbl}>Priority (lower wins on overlap)</label>
            <input type="number" style={S.in} value={f.priority}
              onChange={(e) => set("priority", parseInt(e.target.value) || 100)} />
          </div>
        </div>

        <label style={{ ...S.lbl, display: "flex", alignItems: "center", gap: 8, marginTop: 14 }}>
          <input type="checkbox" checked={f.active} onChange={(e) => set("active", e.target.checked)} /> Active
        </label>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <button style={S.btnGhost} onClick={onCancel}>Cancel</button>
          <button style={S.btnPrimary} onClick={() => onSave(f)} disabled={!f.name || !f.ib_level}>Save</button>
        </div>
      </div>
    </div>
  );
}

const S: Record<string, React.CSSProperties> = {
  page: { padding: 28, fontFamily: "Inter, Arial, sans-serif", color: "#1f2430", maxWidth: 1000 },
  errBox: { background: "#fde8e8", color: "#9b1c1c", border: "1px solid #f5c2c2", borderRadius: 10, padding: 16, fontSize: 14 },
  headRow: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 },
  h1: { fontSize: 22, fontWeight: 700, margin: 0 },
  h2: { fontSize: 17, fontWeight: 700, margin: "0 0 16px" },
  sub: { fontSize: 13, color: "#6b7280", marginTop: 6, maxWidth: 640 },
  badge: { marginLeft: 10, background: "#fdecc8", color: "#92610a", fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 10 },
  tabs: { display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 },
  tab: { padding: "6px 13px", border: "1px solid #d6dae1", background: "#fff", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 600, color: "#475063" },
  tabActive: { background: "#2f5496", color: "#fff", borderColor: "#2f5496" },
  card: { border: "1px solid #e6e9ef", borderRadius: 12, overflow: "hidden", background: "#fff" },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { textAlign: "left", fontSize: 11, color: "#6b7280", fontWeight: 600, padding: "11px 14px", textTransform: "uppercase", letterSpacing: 0.4, background: "#f8f9fb" },
  thNum: { textAlign: "right", fontSize: 11, color: "#6b7280", fontWeight: 600, padding: "11px 14px", textTransform: "uppercase", letterSpacing: 0.4, background: "#f8f9fb" },
  td: { padding: "10px 14px", fontSize: 13, borderTop: "1px solid #f0f2f5" },
  tdNum: { padding: "10px 14px", fontSize: 13, textAlign: "right", borderTop: "1px solid #f0f2f5", whiteSpace: "nowrap" },
  tdLabel: { padding: "10px 14px", fontSize: 13, fontWeight: 600, borderTop: "1px solid #f0f2f5" },
  dot: { display: "inline-block", width: 7, height: 7, borderRadius: 4, background: "#e0a800", marginLeft: 7 },
  link: { border: "none", background: "none", color: "#2f5496", cursor: "pointer", fontSize: 13, marginLeft: 10, padding: 0 },
  overlay: { position: "fixed", inset: 0, background: "rgba(20,25,35,0.45)", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "6vh 16px", zIndex: 50 },
  modal: { background: "#fff", borderRadius: 14, padding: 26, width: 520, maxHeight: "86vh", overflowY: "auto", boxShadow: "0 20px 60px rgba(0,0,0,0.25)" },
  lbl: { display: "block", fontSize: 12, color: "#475063", fontWeight: 600, margin: "12px 0 5px" },
  in: { width: "100%", padding: "9px 11px", border: "1px solid #d6dae1", borderRadius: 8, fontSize: 14, boxSizing: "border-box" },
  row: { display: "flex", gap: 12 },
  chips: { display: "flex", flexWrap: "wrap", gap: 6 },
  chip: { padding: "6px 11px", border: "1px solid #d6dae1", background: "#fff", borderRadius: 7, cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#475063" },
  chipOn: { background: "#2f5496", color: "#fff", borderColor: "#2f5496" },
  btnGhost: { padding: "9px 16px", border: "1px solid #d6dae1", background: "#fff", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 600, color: "#475063" },
  btnPrimary: { padding: "9px 18px", border: "none", background: "#2f5496", color: "#fff", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 600 },
  toast: { position: "fixed", bottom: 24, right: 24, background: "#1f2430", color: "#fff", padding: "10px 16px", borderRadius: 8, fontSize: 13 },
};
