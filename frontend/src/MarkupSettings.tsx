import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';
import { CT } from './crmTable';

const fmtUSD = (n: number) => (n < 0 ? '-$' : '$') + Math.abs(Math.round(n || 0)).toLocaleString('en-GB');
const CAT_LABEL: Record<string, string> = { XAUUSD: 'Gold (XAUUSD)', FX: 'Forex', METAL: 'Metals', CRYPTO: 'Crypto', OTHER: 'Other' };

const inp: React.CSSProperties = { width: 64, padding: '5px 7px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 12, outline: 'none', textAlign: 'right' };

function MarkupTable({ atype, rows, onSaved }: { atype: string; rows: any[]; onSaved: () => void }) {
  const [edits, setEdits] = useState<Record<string, { bid: string; ask: string }>>({});
  const setVal = (ns: string, f: 'bid' | 'ask', v: string, cur: any) =>
    setEdits(e => ({ ...e, [ns]: { bid: f === 'bid' ? v : (e[ns]?.bid ?? String(cur.bid)), ask: f === 'ask' ? v : (e[ns]?.ask ?? String(cur.ask)) } }));
  const save = async (r: any) => {
    const e = edits[r.symbol_norm]; if (!e) return;
    const bid = parseFloat(e.bid) || 0, ask = parseFloat(e.ask) || 0;
    if (bid === r.bid && ask === r.ask) return;
    await apiPost('/markups/update', { account_type: atype, symbol_norm: r.symbol_norm, bid, ask });
    onSaved();
  };
  if (!rows.length) return <div style={{ padding: 30, color: '#667', textAlign: 'center' }}>No markups configured for {atype}. (Not in the OZ Markups sheet — add them or they default to none.)</div>;

  // group by category
  const cats: Record<string, any[]> = {};
  rows.forEach(r => { (cats[r.category] = cats[r.category] || []).push(r); });
  const order = ['XAUUSD', 'FX', 'METAL', 'CRYPTO', 'OTHER'].filter(c => cats[c]);

  return (
    <table style={CT.table}>
      <thead><tr style={CT.theadTr}>{['Symbol', 'Contract size', 'Digits', 'Quote ccy', 'Bid markup', 'Ask markup', 'Total (pts)', ''].map(h => <th key={h} style={CT.th()}>{h}</th>)}</tr></thead>
      <tbody>
        {order.map(cat => (
          <React.Fragment key={cat}>
            <tr><td colSpan={8} style={{ padding: '8px 12px', background: '#1b2027', color: '#ffaa00', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: .5 }}>{CAT_LABEL[cat] || cat} · {cats[cat].length}</td></tr>
            {cats[cat].map(r => {
              const e = edits[r.symbol_norm];
              const bid = e ? parseFloat(e.bid) || 0 : r.bid;
              const ask = e ? parseFloat(e.ask) || 0 : r.ask;
              const dirty = e && (bid !== r.bid || ask !== r.ask);
              return (
                <tr key={r.symbol_norm} style={CT.row()}>
                  <td style={{ ...CT.td, fontWeight: 600, color: '#cfd6e0' }}>{r.symbol}</td>
                  <td style={{ ...CT.td, color: '#9aa3b2' }}>{r.contract_size != null ? Number(r.contract_size).toLocaleString('en-GB') : '—'}</td>
                  <td style={{ ...CT.td, color: '#9aa3b2' }}>{r.digits != null ? r.digits : '—'}</td>
                  <td style={{ ...CT.td, color: '#00aaff', fontWeight: 600 }}>{r.quote_currency || '—'}</td>
                  <td style={CT.td}><input style={inp} value={e ? e.bid : String(r.bid)} onChange={ev => setVal(r.symbol_norm, 'bid', ev.target.value, r)} onBlur={() => save(r)} /></td>
                  <td style={CT.td}><input style={inp} value={e ? e.ask : String(r.ask)} onChange={ev => setVal(r.symbol_norm, 'ask', ev.target.value, r)} onBlur={() => save(r)} /></td>
                  <td style={{ ...CT.td, color: '#00e5a0', fontWeight: 700 }}>{Math.abs(bid) + Math.abs(ask)}</td>
                  <td style={CT.td}>{dirty && <span style={{ fontSize: 10, color: '#ffaa00' }}>● unsaved (tab out to save)</span>}</td>
                </tr>
              );
            })}
          </React.Fragment>
        ))}
      </tbody>
    </table>
  );
}

function OthersTab() {
  const [rows, setRows] = useState<any[]>([]);
  const [draft, setDraft] = useState<Record<string, { at: string; bid: string; ask: string }>>({});
  const load = useCallback(() => { apiGet('/markups/others').then((d: any) => setRows(d.others || [])); }, []);
  useEffect(() => { load(); }, [load]);
  const set = (ns: string, f: 'at' | 'bid' | 'ask', v: string) =>
    setDraft(d => ({ ...d, [ns]: { at: f === 'at' ? v : (d[ns]?.at || 'STD'), bid: f === 'bid' ? v : (d[ns]?.bid || ''), ask: f === 'ask' ? v : (d[ns]?.ask || '') } }));
  const add = async (r: any) => {
    const e = draft[r.symbol_norm] || { at: 'STD', bid: '', ask: '' };
    await apiPost('/markups/update', { account_type: e.at, symbol_norm: r.symbol_norm, bid: parseFloat(e.bid) || 0, ask: parseFloat(e.ask) || 0 });
    load();
  };
  return (
    <div style={{ padding: 12 }}>
      <div style={{ fontSize: 12, color: '#9aa3b2', marginBottom: 10 }}>
        {rows.length} traded symbol(s) are <b>not</b> in any markup sheet. Add a markup (pick the account type, enter Bid/Ask points) — it then moves into that tab.
      </div>
      <div style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 10, overflow: 'hidden' }}>
        <div style={CT.scroll}>
        <table style={CT.table}>
          <thead><tr style={CT.theadTr}>{['Symbol', 'Lots', 'Markup earned', 'Add to', 'Bid', 'Ask', ''].map(h => <th key={h} style={CT.th()}>{h}</th>)}</tr></thead>
          <tbody>
            {rows.length === 0 ? <tr><td colSpan={7} style={{ padding: 24, textAlign: 'center', color: '#556' }}>All traded symbols are covered 🎉</td></tr>
              : rows.map((r: any) => {
                const e = draft[r.symbol_norm] || { at: 'STD', bid: '', ask: '' };
                return (
                  <tr key={r.symbol_norm} style={CT.row()}>
                    <td style={{ ...CT.td, fontWeight: 600, color: '#cfd6e0' }}>{r.sample} <span style={{ color: '#667', fontSize: 10 }}>({r.symbol_norm})</span></td>
                    <td style={{ ...CT.td, color: '#9aa3b2' }}>{Math.round(r.lots).toLocaleString('en-GB')}</td>
                    <td style={{ ...CT.td, color: '#00e5a0' }}>{fmtUSD(r.markup_usd)}</td>
                    <td style={CT.td}>
                      <select value={e.at} onChange={ev => set(r.symbol_norm, 'at', ev.target.value)} style={{ ...inp, width: 80, textAlign: 'left' }}>
                        {['STD', 'VIP', 'FIX', 'ZERO', 'CENT'].map(t => <option key={t}>{t}</option>)}
                      </select>
                    </td>
                    <td style={CT.td}><input style={inp} value={e.bid} onChange={ev => set(r.symbol_norm, 'bid', ev.target.value)} placeholder="0" /></td>
                    <td style={CT.td}><input style={inp} value={e.ask} onChange={ev => set(r.symbol_norm, 'ask', ev.target.value)} placeholder="0" /></td>
                    <td style={CT.td}><button onClick={() => add(r)} style={{ padding: '5px 12px', background: '#00e5a0', border: 'none', borderRadius: 6, color: '#0a0c10', fontWeight: 700, fontSize: 11, cursor: 'pointer' }}>Add</button></td>
                  </tr>
                );
              })}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}

function CrossCheck() {
  const [d, setD] = useState<any>(null);
  const [onlyLosing, setOnlyLosing] = useState(false);
  useEffect(() => { apiGet('/markups/crosscheck').then(setD); }, []);
  if (!d) return <div style={{ padding: 30, color: '#667' }}>Loading…</div>;
  const rows = onlyLosing ? d.rows.filter((r: any) => r.losing) : d.rows;
  const s = d.summary;
  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8, marginBottom: 14 }}>
        {[['Symbols', s.symbols, '#e6e9ef'], ['Losing symbols', s.losing_symbols, s.losing_symbols ? '#ff5d6c' : '#00e5a0'],
          ['Total markup', fmtUSD(s.total_markup), '#00e5a0'], ['Total IB paid', fmtUSD(s.total_ib), '#ff8c00'],
          ['Net', fmtUSD(s.total_net), s.total_net >= 0 ? '#00aaff' : '#ff5d6c']].map(([l, v, c]: any) => (
          <div key={l} style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 9, padding: '9px 12px' }}>
            <div style={{ fontSize: 9, color: '#667', textTransform: 'uppercase', letterSpacing: .4 }}>{l}</div>
            <div style={{ fontSize: 17, fontWeight: 700, color: c }}>{v}</div>
          </div>
        ))}
      </div>
      {s.losing_symbols > 0 && (
        <div style={{ background: 'rgba(255,93,108,0.1)', border: '1px solid rgba(255,93,108,0.4)', borderRadius: 8, padding: '10px 14px', marginBottom: 12, color: '#ff8a93', fontSize: 12 }}>
          ⚠ {s.losing_symbols} symbol(s) where we paid IBs MORE than the markup we earned — net loss {fmtUSD(s.loss_on_losing)} on those.
        </div>
      )}
      <label style={{ fontSize: 12, color: '#9aa3b2', cursor: 'pointer', display: 'inline-flex', gap: 6, marginBottom: 8 }}>
        <input type="checkbox" checked={onlyLosing} onChange={e => setOnlyLosing(e.target.checked)} /> Show only losing symbols
      </label>
      <div style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 10, overflow: 'hidden' }}>
        <div style={CT.scroll}>
        <table style={CT.table}>
          <thead><tr style={CT.theadTr}>{['Symbol', 'Lots', 'Markup earned', 'IB paid', 'Net', ''].map(h => <th key={h} style={CT.th()}>{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((r: any, i: number) => (
              <tr key={i} style={{ ...CT.row(), background: r.losing ? 'rgba(255,93,108,0.07)' : 'transparent' }}>
                <td style={{ ...CT.td, fontWeight: 600, color: '#cfd6e0' }}>{r.symbol}</td>
                <td style={{ ...CT.td, color: '#9aa3b2' }}>{Math.round(r.lots).toLocaleString('en-GB')}</td>
                <td style={{ ...CT.td, color: '#00e5a0' }}>{fmtUSD(r.markup_usd)}</td>
                <td style={{ ...CT.td, color: '#ff8c00' }}>{fmtUSD(r.ib_usd)}</td>
                <td style={{ ...CT.td, color: r.net_usd >= 0 ? '#00aaff' : '#ff5d6c', fontWeight: 600 }}>{fmtUSD(r.net_usd)}</td>
                <td style={CT.td}>{r.losing && <span style={{ fontSize: 10, color: '#ff5d6c', fontWeight: 700 }}>LOSING</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}

export default function MarkupSettings() {
  const [data, setData] = useState<any>(null);
  const [atype, setAtype] = useState('STD');
  const [view, setView] = useState<'markups' | 'check'>('markups');
  const load = useCallback(() => { apiGet('/markups').then(setData); }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#20252f' }}>
      <div style={{ padding: '12px 16px 0', borderBottom: '1px solid #373f4d', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#e6e9ef' }}>💹 Markups</div>
          <div style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>
            {(['markups', 'check'] as const).map(v => (
              <button key={v} onClick={() => setView(v)}
                style={{ padding: '6px 14px', borderRadius: 8, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
                  border: `1px solid ${view === v ? '#00e5a0' : '#2a2f3a'}`, background: view === v ? 'rgba(0,229,160,0.1)' : 'transparent', color: view === v ? '#00e5a0' : '#889' }}>
                {v === 'markups' ? 'Markup table' : '⚠ IB vs Markup check'}
              </button>
            ))}
          </div>
        </div>
        {view === 'markups' && (
          <div style={{ display: 'flex', gap: 4 }}>
            {[...(data?.types || ['STD', 'VIP', 'FIX', 'ZERO', 'CENT']), 'OTHERS'].map((t: string) => (
              <button key={t} onClick={() => setAtype(t)}
                style={{ padding: '8px 18px', borderRadius: '8px 8px 0 0', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                  border: 'none', background: atype === t ? '#262c36' : 'transparent', color: atype === t ? '#00e5a0' : '#889',
                  borderBottom: atype === t ? '2px solid #00e5a0' : '2px solid transparent' }}>
                {t === 'OTHERS' ? '⚠ Others' : t} <span style={{ fontSize: 10, color: '#667' }}>{data && t !== 'OTHERS' ? (data.markups[t] || []).length : ''}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {!data ? <div style={{ padding: 30, color: '#667' }}>Loading…</div>
          : view === 'check' ? <CrossCheck />
          : atype === 'OTHERS' ? <OthersTab />
          : <MarkupTable atype={atype} rows={data.markups[atype] || []} onSaved={load} />}
      </div>
      <div style={{ padding: '6px 16px', borderTop: '1px solid #373f4d', fontSize: 10, color: '#556', flexShrink: 0 }}>
        Markup is in price points (Bid + Ask). Edit a value and tab out to save. The "IB vs Markup check" compares realized markup earned vs IB commission paid per symbol.
      </div>
    </div>
  );
}
