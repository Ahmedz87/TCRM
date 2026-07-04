import React from 'react';

/* Unified CRM list-table design — extracted verbatim from the Clients page (the reference look)
   so every list page (Trading Accounts, Leads, IB Admin, Sales Agents, …) shares the SAME
   header bar, fonts, colours, sizes, row dividers, scroll behaviour and pagination.

   Usage on a page:
     <div style={CT.scroll}>
       <table style={CT.table}>
         <thead><tr style={CT.theadTr}>
           <th style={CT.th()}>Name</th>
           <th style={CT.th(sortActive, 'right')}>Balance</th>
         </tr></thead>
         <tbody>
           {rows.map(r => <tr style={CT.row()}> <td style={CT.td}>…</td> </tr>)}
         </tbody>
       </table>
     </div>
     <Pager page={page} setPage={setPage} pageSize={pageSize} setPageSize={setPageSize}
            count={rows.length} total={total} label="accounts" />
*/

type Align = 'left' | 'center' | 'right';

export const CT = {
  // scroll container (horizontal + vertical, thin bar). Put it on the element that wraps <table>.
  scroll: { overflowX: 'auto', overflowY: 'auto', flex: 1, minHeight: 0, scrollbarWidth: 'thin' } as React.CSSProperties,
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 12 } as React.CSSProperties,
  theadTr: { background: 'var(--bg-input,#373f4d)', position: 'sticky', top: 0, zIndex: 10 } as React.CSSProperties,
  th(active = false, align: Align = 'left'): React.CSSProperties {
    return {
      padding: '9px 8px', textAlign: align, color: active ? 'var(--accent,#00e5a0)' : '#cfd6e0',
      fontWeight: 600, borderBottom: '1px solid var(--border,#4f596b)', whiteSpace: 'nowrap',
      fontSize: 11, userSelect: 'none', textTransform: 'none', letterSpacing: 0,
    } as React.CSSProperties;
  },
  td: { padding: '9px 8px', borderBottom: '1px solid #373f4d', fontSize: 12, color: 'var(--text,#e6e9ef)', whiteSpace: 'nowrap' } as React.CSSProperties,
  row(selected = false): React.CSSProperties {
    return { borderBottom: '1px solid #373f4d', background: selected ? 'rgba(0,229,160,0.06)' : 'transparent' } as React.CSSProperties;
  },
  pagerBar: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderTop: '1px solid #4f596b', background: 'var(--bg-card,#2c333e)', flexShrink: 0 } as React.CSSProperties,
};

export function Pager({ page, setPage, pageSize, setPageSize, count, total, label = 'rows', sizes = [20, 50, 100, 200] }: {
  page: number;
  setPage: (f: any) => void;
  pageSize: number;
  setPageSize: (n: number) => void;
  count: number;          // rows on the current page (to disable "next" at the end)
  total?: number;         // total rows (for the "N rows" label) — optional
  label?: string;
  sizes?: number[];
}) {
  const btn = (dis: boolean): React.CSSProperties => ({
    padding: '5px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6,
    color: dis ? '#626d80' : '#888', cursor: dis ? 'default' : 'pointer', fontSize: 12,
  });
  return (
    <div style={CT.pagerBar}>
      <div style={{ fontSize: 12, color: '#555' }}>{total != null ? `${total.toLocaleString()} ${label}` : label}</div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
          style={{ padding: '3px 8px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 5, color: 'var(--text2,#888)', fontSize: 11 }}>
          {sizes.map(s => <option key={s} value={s}>{s}/page</option>)}
        </select>
        <button onClick={() => setPage((p: number) => Math.max(1, p - 1))} disabled={page === 1} style={btn(page === 1)}>←</button>
        <span style={{ fontSize: 12, color: '#888', padding: '0 8px' }}>{page}</span>
        <button onClick={() => setPage((p: number) => p + 1)} disabled={count < pageSize} style={btn(count < pageSize)}>→</button>
      </div>
    </div>
  );
}
