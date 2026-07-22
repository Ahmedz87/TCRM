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
  // overflow/ellipsis make a cell CLIP under table-layout:fixed (no effect on auto-layout tables,
  // where the column just grows to fit) — so pages that opt into fixed widths never scroll sideways.
  td: { padding: '9px 8px', borderBottom: '1px solid #373f4d', fontSize: 12, color: 'var(--text,#e6e9ef)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } as React.CSSProperties,
  // Cap a free-text cell (names, notes) so a long value can't stretch the auto-layout table and
  // push later columns (e.g. action buttons) off-screen. Wrap the cell's content in a <span
  // style={CT.ellip(180)} title={value}> — it clips with "…" and shows the full text on hover.
  ellip(maxWidth = 180): React.CSSProperties {
    return { display: 'block', maxWidth, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } as React.CSSProperties;
  },
  row(selected = false): React.CSSProperties {
    return { borderBottom: '1px solid #373f4d', background: selected ? 'rgba(0,229,160,0.06)' : 'transparent' } as React.CSSProperties;
  },
  pagerBar: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderTop: '1px solid #4f596b', background: 'var(--bg-card,#2c333e)', flexShrink: 0 } as React.CSSProperties,
};

// Type-to-jump page box: the user types a page number and presses Enter (or tabs away) to jump
// straight there — easier than clicking the arrows one page at a time when there are many pages.
// Shows "/ N" so the total page count is always visible. Input is clamped to 1..totalPages.
function PageJump({ page, totalPages, setPage, style }: {
  page: number; totalPages: number; setPage: (n: number) => void; style: React.CSSProperties;
}) {
  const [draft, setDraft] = React.useState(String(page));
  React.useEffect(() => { setDraft(String(page)); }, [page]);
  const commit = () => {
    const n = Math.max(1, Math.min(totalPages, parseInt(draft, 10) || 1));
    setDraft(String(n));
    if (n !== page) setPage(n);
  };
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#888' }}>
      <input
        value={draft}
        inputMode="numeric"
        onChange={e => setDraft(e.target.value.replace(/\D/g, ''))}
        onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
        onBlur={commit}
        title={`Type a page number (1–${totalPages}) and press Enter`}
        style={{ ...style, width: 46, textAlign: 'center' }}
      />
      <span style={{ color: '#667', whiteSpace: 'nowrap' }}>/ {totalPages.toLocaleString('en-GB')}</span>
    </span>
  );
}

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
  const selStyle: React.CSSProperties = { padding: '3px 8px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 5, color: 'var(--text2,#888)', fontSize: 11 };
  // Total page count is known only when the caller passes `total`. When it is, show a
  // type-to-jump page box (see PageJump) so the user can enter a page number directly instead
  // of clicking the arrows one page at a time. Falls back to the plain page number otherwise.
  const totalPages = total != null && total > 0 ? Math.max(1, Math.ceil(total / pageSize)) : null;
  const curPage = totalPages != null ? Math.min(page, totalPages) : page;
  return (
    <div style={CT.pagerBar}>
      <div style={{ fontSize: 12, color: '#555' }}>{total != null ? `${total.toLocaleString('en-GB')} ${label}` : label}</div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }} title="Rows per page" style={selStyle}>
          {sizes.map(s => <option key={s} value={s}>{s}/page</option>)}
        </select>
        <button onClick={() => setPage((p: number) => Math.max(1, p - 1))} disabled={page === 1} style={btn(page === 1)}>←</button>
        {totalPages != null ? (
          <PageJump page={curPage} totalPages={totalPages} setPage={n => setPage(n)} style={selStyle} />
        ) : (
          <span style={{ fontSize: 12, color: '#888', padding: '0 8px' }}>{page}</span>
        )}
        <button onClick={() => setPage((p: number) => p + 1)} disabled={count < pageSize} style={btn(count < pageSize)}>→</button>
      </div>
    </div>
  );
}
