import { PhoneModal, EmailModal } from './ContactModals';
import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';
import DepositCaseModal from './DepositCaseModal';

type TxType = 'deposit' | 'withdrawal' | 'internal_transfer' | 'bonus' | 'mt_adjustment';

const METHODS_AUTO = ['USDT','Ovadraft','Visa/Master'];
const nc = (n: number) => n >= 7 ? '#ff4d4d' : n >= 4 ? '#ffaa00' : '#00e5a0';
const fmtUSD = (n: number) => '$' + Math.round(n).toLocaleString();

// Ticket #43: the bare platform value "MT5" is NOT a payment method — it marks an
// internal MT5 balance adjustment. Show a clearer label. Prefer the backend's
// method_label; fall back here so old rows / other views still read well.
const methodLabel = (tx: any): string => {
  if (tx && tx.method_label) return tx.method_label;
  const m = (tx?.method || '').trim();
  if (m.toUpperCase() === 'MT5') return 'Internal / MT5 adjustment';
  return m || '—';
};

// Match the Clients / Leads list table (header = bg-input row, light-grey labels, hairline borders).
const thS: React.CSSProperties = {
  padding: '9px 8px', textAlign: 'left', color: '#cfd6e0', fontWeight: 600,
  fontSize: 11, borderBottom: '1px solid #4f596b', whiteSpace: 'nowrap', cursor: 'pointer',
};
const tdS: React.CSSProperties = {
  padding: '9px 8px', borderBottom: '1px solid #373f4d', verticalAlign: 'middle', fontSize: 12,
};

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    pending:    ['#3a2a0e', '#ffaa00'],
    processing: ['#0a1a3a', '#00aaff'],
    approved:   ['#0e3a2a', '#00e5a0'],
    rejected:   ['#3a0e0e', '#ff4d4d'],
  };
  const [bg, col] = map[status] || ['#373f4d', '#555'];
  return <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: bg, color: col, fontWeight: 500 }}>{status}</span>;
}

function MethodBadge({ method, mtype, onClick }: { method: string; mtype: string; onClick: () => void }) {
  const auto = mtype === 'auto';
  return (
    <span onClick={onClick} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: auto ? '#0e3a2a' : '#3a2a0e', color: auto ? '#00e5a0' : '#ffaa00', fontWeight: 500, cursor: 'pointer' }} title="Click to filter">
      {method}
    </span>
  );
}



function TxCountTooltip({ tx, x, y, onClose }: any) {
  const [txs, setTxs] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const API = '/api';
  React.useEffect(() => {
    const token = localStorage.getItem('token') || '';
    fetch(`${API}/transactions?login=${tx.login}&page_size=20&tx_type_multi=deposit,withdrawal`, {
      headers: { Authorization: `Bearer ${token}` }
    }).then(r=>r.json()).then(d=>{
      const list = d.transactions || d.items || [];
      list.sort((a:any,b:any)=>new Date(b.tx_date).getTime()-new Date(a.tx_date).getTime());
      setTxs(list.slice(0,15)); setLoading(false);
    }).catch(()=>setLoading(false));
  }, [tx.login]);
  const left = Math.min(x+10, window.innerWidth-320);
  const top  = Math.min(y-10, window.innerHeight-420);
  const typeColor: any = { deposit:'#00e5a0', withdrawal:'#ff4d4d', bonus_deposit:'#ffaa00', credit_in:'#00aaff', credit_out:'#ff8800' };
  return (
    <div onMouseLeave={onClose} style={{ position:'fixed', left, top, zIndex:99999, background:'#2c333e', border:'1px solid #626d80', borderRadius:10, padding:14, width:340, boxShadow:'0 8px 32px rgba(0,0,0,0.6)', pointerEvents:'none' }}>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:10 }}>
        <div style={{ fontSize:12, fontWeight:600 }}>All transactions</div>
        <div style={{ fontSize:11, color:'#555' }}>{tx.client_name} · #{tx.login}</div>
      </div>
      {loading ? <div style={{ color:'#555', fontSize:12 }}>Loading...</div> : txs.length === 0 ? <div style={{ color:'#555', fontSize:12 }}>No transactions</div> : (
        <>
          <div style={{ display:'grid', gridTemplateColumns:'72px 70px 65px 60px', gap:4, marginBottom:4 }}>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase' }}>Date</div>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase' }}>Type</div>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase' }}>Method</div>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', textAlign:'right' }}>Amount</div>
          </div>
          {txs.map((t:any,i:number)=>(
            <div key={i} style={{ display:'grid', gridTemplateColumns:'72px 70px 65px 60px', gap:4, padding:'4px 0', borderBottom:'1px solid #373f4d', fontSize:10 }}>
              <div style={{ color:'#888' }}>{t.tx_date ? new Date(t.tx_date).toLocaleDateString('en-GB') : '—'}</div>
              <div style={{ color: typeColor[t.tx_type] || '#888' }}>{t.tx_type==='deposit'?'Dep':t.tx_type==='withdrawal'?'With':t.tx_type}</div>
              <div style={{ color:'#666', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{methodLabel(t)}</div>
              <div style={{ color:'#e0e0e0', textAlign:'right', fontWeight:500 }}>${(t.amount||0).toLocaleString()}</div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function NetworkHoverPopup({ tx, rect, onClose, onCancelClose }: any) {
  const [nodes, setNodes] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const API = '/api';
  React.useEffect(() => {
    const token = localStorage.getItem('token') || '';
    fetch(`${API}/network/traverse/${tx.login}?layers=2`, {
      headers: { Authorization: `Bearer ${token}` }
    }).then(r=>r.json()).then(d=>{
      const ns = (d.nodes||[]).filter((n:any)=>n.layer>0);
      // CID (same physical device) is the strongest signal — always on top, then IP, then rest
      const rank = (t:string)=> t==='cid'?0 : t==='ip'?1 : 2;
      ns.sort((a:any,b:any)=> rank(a.type)-rank(b.type));
      setNodes(ns); setLoading(false);
    }).catch(()=>setLoading(false));
  }, [tx.login]);

  // anchor to the badge element (no cursor gap), flip above if it would overflow the bottom
  const W = 300, H = 420;
  let left = Math.min(Math.max(8, rect.left - 20), window.innerWidth - W - 8);
  let top  = rect.bottom + 1;                       // touch the badge -> no dead zone
  if (top + H > window.innerHeight) top = Math.max(8, rect.top - H - 1);
  const score = tx.network_score || 0;
  const scoreColor = score>=7?'#ff4d4d':score>=4?'#ffaa00':'#00e5a0';
  const cidCount = nodes.filter((n:any)=>n.type==='cid').length;
  const ipCount  = nodes.filter((n:any)=>n.type==='ip').length;

  const goToNetwork = (login:number)=>{
    window.dispatchEvent(new CustomEvent('navigate', { detail:{ page:'network', login } }));
    onClose && onClose();
  };

  return (
    <div onMouseEnter={onCancelClose} onMouseLeave={onClose}
      style={{ position:'fixed', left, top, zIndex:99999, background:'#2c333e', border:'1px solid #626d80', borderRadius:10, padding:14, width:300, boxShadow:'0 8px 32px rgba(0,0,0,0.6)' }}>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
        <div style={{ fontSize:12, fontWeight:600 }}>Network score — #{tx.login}</div>
        <div style={{ fontSize:14, fontWeight:700, color:scoreColor }}>{score}/10</div>
      </div>
      <div style={{ fontSize:10, color:'#777', marginBottom:8 }}>
        {cidCount>0 && <span style={{color:'#ff4d4d'}}>📱 {cidCount} same-device (CID)</span>}
        {cidCount>0 && ipCount>0 && <span> · </span>}
        {ipCount>0 && <span style={{color:'#ffaa00'}}>🌐 {ipCount} same-IP</span>}
        {cidCount===0 && ipCount===0 && <span>No shared device/IP links</span>}
      </div>
      {loading ? <div style={{ color:'#555', fontSize:11 }}>Loading connections...</div>
      : nodes.length===0 ? <div style={{ color:'#555', fontSize:11 }}>No linked accounts found.</div>
      : <>
        <div style={{ fontSize:10, color:'#555', marginBottom:4 }}>Linked to (click to open full network):</div>
        {nodes.slice(0,8).map((n:any,i:number)=>(
          <div key={i} onClick={()=>goToNetwork(n.login)} title={`Open #${n.login} in Network page`}
            style={{ display:'flex', alignItems:'center', gap:8, padding:'5px 4px', borderBottom:'1px solid #373f4d', cursor:'pointer', borderRadius:4 }}
            onMouseEnter={e=>(e.currentTarget.style.background='#373f4d')}
            onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
            <div style={{ width:22, height:22, borderRadius:6, background:n.type==='cid'?'#3a0e0e':'#3a2a0e', display:'flex', alignItems:'center', justifyContent:'center', fontSize:11, flexShrink:0 }}>{n.type==='cid'?'📱':'🌐'}</div>
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ fontSize:11, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', color:'#4d9fff' }}>{n.name}</div>
              <div style={{ fontSize:9, color:'#666' }}>#{n.login} · {n.type==='cid'?'same device':n.type==='ip'?'same IP':n.type}{n.connect_via?(' · '+String(n.connect_via).substring(0,14)):''}</div>
            </div>
            <div style={{ fontSize:9, padding:'1px 5px', borderRadius:3, background:n.type==='cid'?'rgba(255,77,77,0.2)':'rgba(255,170,0,0.2)', color:n.type==='cid'?'#ff4d4d':'#ffaa00', flexShrink:0, fontWeight:700 }}>{(n.type||'').toUpperCase()}</div>
          </div>
        ))}
        {nodes.length>8 && <div style={{ fontSize:9, color:'#555', marginTop:5 }}>+{nodes.length-8} more — click any to see the full graph</div>}
      </>}
    </div>
  );
}

function AbuseDetailModal({ tx, onClose }: any) {
  const [cases, setCases] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const API = '/api';

  React.useEffect(() => {
    const token = localStorage.getItem('token') || '';
    fetch(`${API}/abuse/cases?login=${tx.login}&page_size=10`, {
      headers: { Authorization: `Bearer ${token}` }
    }).then(r=>r.json())
    .then(d=>{ setCases(d.cases || []); setLoading(false); })
    .catch(()=>setLoading(false));
  }, [tx.login]);

  const severityColor: any = { critical:'#ff4d4d', high:'#ff8800', medium:'#ffaa00', low:'#888' };
  const typeLabel: any = {
    margin_partner:'🔥 Margin-Out Partner', bonus_ring:'🎁 Bonus Ring',
    bonus_cashout:'🎁 Bonus Cash-Out', chip_dump:'🔀 Chip Dumping',
    swap_carry:'💱 Swap Carry', toxic_arb:'☢️ Toxic / Latency',
  };

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.8)', zIndex:99999, display:'flex', alignItems:'center', justifyContent:'center' }} onClick={onClose}>
      <div style={{ background:'#2c333e', border:'1px solid #626d80', borderRadius:14, padding:24, width:520, maxHeight:560, display:'flex', flexDirection:'column' }} onClick={e=>e.stopPropagation()}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:16 }}>
          <div>
            <div style={{ fontSize:14, fontWeight:600, color:'#ff4d4d' }}>⚠️ Abuse Detection</div>
            <div style={{ fontSize:11, color:'#555', marginTop:2 }}>{tx.client_name} · #{tx.login} · Withdrawal ${(tx.amount||0).toLocaleString()}</div>
          </div>
          <div onClick={onClose} style={{ cursor:'pointer', color:'#555', fontSize:20, lineHeight:1 }}>✕</div>
        </div>
        <div style={{ overflowY:'auto', flex:1 }}>
          {loading ? (
            <div style={{ textAlign:'center', color:'#555', padding:30 }}>Loading abuse cases...</div>
          ) : cases.length === 0 ? (
            <div style={{ padding:16, background:'#373f4d', borderRadius:8, textAlign:'center' }}>
              <div style={{ color:'#555', fontSize:13 }}>No abuse cases detected for #{tx.login}</div>
              <div style={{ color:'#626d80', fontSize:11, marginTop:6 }}>This withdrawal was flagged for: {tx.abuse_flag}</div>
            </div>
          ) : cases.map((c:any,i:number)=>(
            <div key={i} style={{ padding:14, background:'#1a0a0a', border:`1px solid ${severityColor[c.severity]||'#626d80'}44`, borderRadius:8, marginBottom:10 }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                <div style={{ fontSize:13, fontWeight:600, color: severityColor[c.severity]||'#888' }}>
                  {typeLabel[c.abuse_type]||c.abuse_type}
                </div>
                <div style={{ display:'flex', gap:6 }}>
                  <span style={{ fontSize:10, padding:'2px 7px', borderRadius:99, background: `${severityColor[c.severity]||'#888'}22`, color: severityColor[c.severity]||'#888' }}>{c.severity}</span>
                  <span style={{ fontSize:10, padding:'2px 7px', borderRadius:99, background:'rgba(255,170,0,0.1)', color:'#ffaa00' }}>Risk {c.risk_score}/100</span>
                </div>
              </div>
              <div style={{ fontSize:11, color:'#aaa', lineHeight:1.6, marginBottom:8 }}>{c.evidence}</div>
              <div style={{ display:'flex', gap:16, fontSize:10, color:'#555' }}>
                <span>Accounts: {(c.all_logins||[]).join(', ')}</span>
                <span>Exposure: ${(c.exposure||0).toLocaleString()}</span>
                <span>{c.created_at ? new Date(c.created_at).toLocaleDateString() : ''}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}


// ─── Modals ─────────────────────────────────────────────────────────────────
function AccountModal({ tx, onClose }: { tx: any; onClose: () => void }) {
  if (!tx) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }} onClick={onClose}>
      <div style={{ background: '#2c333e', border: '1px solid #626d80', borderRadius: 14, padding: 20, width: 380, maxWidth: '95vw' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>Trading account #{tx.login}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>
        {[
          ['Login',    `#${tx.login}`],
          ['Group',    tx.group || '—'],
          ['Balance',  fmtUSD(tx.balance || 0)],
          ['Equity',   fmtUSD(tx.equity || 0)],
          ['Leverage', tx.leverage || '—'],
          ['Client',   tx.client_name || '—'],
        ].map(([l, v]) => (
          <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid #373f4d', fontSize: 12 }}>
            <span style={{ color: '#555' }}>{l}</span>
            <span style={{ color: l === 'Balance' ? '#00e5a0' : '#e0e0e0', fontWeight: l === 'Balance' ? 600 : 400 }}>{v}</span>
          </div>
        ))}
        <button style={{ width: '100%', marginTop: 12, padding: 8, background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}>
          Open full account →
        </button>
      </div>
    </div>
  );
}

function ClientModal({ tx, onClose, onNavigate }: { tx: any; onClose: () => void; onNavigate?: (login:number)=>void }) {
  if (!tx) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }} onClick={onClose}>
      <div style={{ background: '#2c333e', border: '1px solid #626d80', borderRadius: 14, padding: 20, width: 440, maxWidth: '95vw' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>Client profile</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <div style={{ width: 44, height: 44, borderRadius: '50%', background: '#0e3a2a', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, fontWeight: 600, color: '#00e5a0' }}>
            {(tx.client_name || '?').substring(0, 2).toUpperCase()}
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{tx.client_name}</div>
            <div style={{ color: '#555', fontSize: 11 }}>Login #{tx.login}</div>
          </div>
        </div>
        {[
          ['Sales agent',       tx.agent || '—'],
          ['IB',                tx.ib || '—'],
          ['Balance',           fmtUSD(tx.balance || 0)],
          ['Total deposits',    fmtUSD(tx.total_deposits || 0)],
          ['Total withdrawals', fmtUSD(tx.total_withdrawals || 0)],
          ['Network risk',      `${tx.network_score || 0}/10`],
          ['# Transactions',    String(tx.tx_count || 0)],
        ].map(([l, v]) => (
          <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #373f4d', fontSize: 12 }}>
            <span style={{ color: '#555' }}>{l}</span>
            <span style={{ color: l === 'Balance' ? '#00e5a0' : l === 'IB' ? '#00aaff' : l === 'Network risk' ? nc(parseInt(v)) : '#e0e0e0', fontWeight: l === 'Balance' ? 600 : 400 }}>{v}</span>
          </div>
        ))}
        <button onClick={()=>{ onClose(); if(onNavigate) onNavigate(tx.login); }} style={{ width: '100%', marginTop: 12, padding: 8, background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}>
          Open full client profile →
        </button>
      </div>
    </div>
  );
}

function ReviewModal({ tx, onClose, onAction }: { tx: any; onClose: () => void; onAction: (action: string, note: string) => void }) {
  const [note, setNote] = useState('');
  if (!tx) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }} onClick={onClose}>
      <div style={{ background: '#2c333e', border: '1px solid #626d80', borderRadius: 14, padding: 20, width: 420, maxWidth: '95vw' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>Review {tx.tx_type}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>
        <div style={{ background: '#373f4d', borderRadius: 8, padding: 12, marginBottom: 14, fontSize: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              ['Client',     tx.client_name],
              ['Amount',     fmtUSD(tx.amount)],
              ['Method',     methodLabel(tx)],
              ['Wallet ID',  tx.wallet_id],
              ['Network',    `${tx.network_score || 0}/10`],
              ['# Txns',     String(tx.tx_count || 0)],
            ].map(([l, v]) => (
              <div key={l}>
                <div style={{ color: '#555', fontSize: 10 }}>{l}</div>
                <div style={{ marginTop: 2, color: l === 'Network' ? nc(parseInt(v)) : l === 'Amount' ? (tx.tx_type === 'withdrawal' ? '#ff4d4d' : '#00e5a0') : '#e0e0e0', fontWeight: l === 'Amount' ? 600 : 400, fontSize: 12 }}>{v || '—'}</div>
              </div>
            ))}
            {tx.abuse_flag && (
              <div style={{ gridColumn: 'span 2' }}>
                <div style={{ color: '#555', fontSize: 10 }}>Abuse flag</div>
                <div style={{ marginTop: 2, color: '#ff4d4d' }}>⚠️ {tx.abuse_flag}</div>
              </div>
            )}
          </div>
        </div>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, color: '#555', marginBottom: 6 }}>Note (optional)</div>
          <textarea value={note} onChange={e => setNote(e.target.value)} rows={3}
            style={{ width: '100%', padding: 8, background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#e0e0e0', fontSize: 12, fontFamily: 'inherit', resize: 'none', outline: 'none' }}
            placeholder="Add a review note..." />
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button onClick={() => onAction('approve', note)} style={{ flex: 1, padding: '7px 0', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontWeight: 600, cursor: 'pointer', fontSize: 12 }}>✅ Approve → MT5</button>
          <button onClick={() => onAction('risk', note)}    style={{ flex: 1, padding: '7px 0', background: '#3a2a0e', border: '1px solid #ffaa00', borderRadius: 8, color: '#ffaa00', fontWeight: 500, cursor: 'pointer', fontSize: 12 }}>⚠️ Send to risk</button>
          <button onClick={() => onAction('reject', note)}  style={{ flex: 1, padding: '7px 0', background: '#3a0e0e', border: '1px solid #ff4d4d', borderRadius: 8, color: '#ff4d4d', fontWeight: 500, cursor: 'pointer', fontSize: 12 }}>❌ Reject</button>
          <button onClick={onClose} style={{ width: '100%', marginTop: 4, padding: '6px 0', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#888', cursor: 'pointer', fontSize: 12 }}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

// ─── Read-only full Details modal (ticket #91) — view every field of a deposit/withdrawal ───
function DetailsModal({ tx, onClose }: { tx: any; onClose: () => void }) {
  if (!tx) return null;
  // #2 — manual deposits (Qi card / Zain cash / Fastpay / bank wire …) carry sender wallet-id +
  // receiver card + from/to; AUTO (gateway) deposits don't, so hide those empty fields for them.
  const manualRe = /qi\s*card|zain|zc|fast\s*?pay|bank\s*wire|local\s*bank|wallet\s*cash|hawala|sham|cash|usdt|crypto|tether/i;
  const isManual = manualRe.test(String(tx.method || tx.wallet_type || ''));
  const showWallet = isManual || tx.tx_type !== 'deposit';   // keep for manual deposits + withdrawals/transfers
  const rows: [string, any][] = [
    ['Type',            (tx.tx_type || '').replace('_', ' ')],
    ['Client',          tx.client_name],
    ['Login',           tx.login],
    ['Amount',          fmtUSD(tx.amount)],
    ['Currency',        tx.currency || 'USD'],
    ['Card / Method',   methodLabel(tx)],
    ...(showWallet ? ([['Wallet type', tx.wallet_type], ['Wallet ID', tx.wallet_id]] as [string, any][]) : []),
    ['Payment reference', tx.psp_reference],
    ['Status',          tx.status],
    ['Date',            tx.tx_date],
    ['Approved at',     tx.approved_at],
    ['Reference / Deal #', tx.ref_id || tx.deal_id],
    ...(showWallet ? ([['From account', tx.from_account], ['To account', tx.to_account]] as [string, any][]) : []),
    ['Sales agent',     tx.agent_name],
    ['IB',              tx.ib_name],
    ['Network score',   `${tx.network_score || 0}/10`],
    ['# Transactions',  tx.tx_count],
    ['Notes',           tx.notes],
  ];
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }} onClick={onClose}>
      <div style={{ background: '#2c333e', border: '1px solid #626d80', borderRadius: 14, padding: 20, width: 520, maxWidth: '95vw', maxHeight: '88vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <span style={{ fontSize: 14, fontWeight: 700 }}>Transaction details</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {rows.map(([l, v]) => (
            <div key={l} style={{ background: '#373f4d', borderRadius: 8, padding: '8px 10px' }}>
              <div style={{ color: '#8a93a3', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.03em' }}>{l}</div>
              <div style={{ marginTop: 3, color: l === 'Amount' ? (tx.tx_type === 'withdrawal' ? '#ff6b6b' : '#00e5a0') : '#e8edf2', fontWeight: l === 'Amount' ? 700 : 400, fontSize: 12.5, wordBreak: 'break-word' }}>
                {(v === null || v === undefined || v === '') ? '—' : String(v)}
              </div>
            </div>
          ))}
        </div>
        {tx.abuse_flag && (
          <div style={{ marginTop: 10, background: 'rgba(255,77,77,0.1)', border: '1px solid #ff4d4d55', borderRadius: 8, padding: '8px 10px', fontSize: 12, color: '#ff8888' }}>⚠️ Abuse flag: {tx.abuse_flag}</div>
        )}
        <div style={{ marginTop: 12, fontSize: 11, color: '#667' }}>Note: card-number / wallet-ID and gateway payment info populate for payment-gateway transactions; these journal-sourced rows carry the payment method only.</div>
      </div>
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function Transactions({ readOnly = false }: { readOnly?: boolean }) {
  const [txType, setTxType]       = useState<TxType>('deposit');
  const [txDetail, setTxDetail]   = useState<any>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [txPopup, setTxPopup] = useState<{tx:any,x:number,y:number}|null>(null);
  const [abuseTx, setAbuseTx] = useState<any>(null);
  const [netHover, setNetHover] = useState<any>(null);
  const [abuseHover, setAbuseHover] = useState<any>(null);
  const netCloseTimer = React.useRef<any>(null);
  const [phoneContact, setPhoneContact] = useState<any>(null);
  const [emailContact, setEmailContact] = useState<any>(null);
  const [txs, setTxs]             = useState<any[]>([]);
  const [kpis, setKpis]           = useState<any>({});
  const [total, setTotal]         = useState(0);
  const [page, setPage]           = useState(1);
  const [pageSize, setPageSize]   = useState(20);
  const [sort, setSort]           = useState('date');
  const [sortDir, setSortDir]     = useState<'asc'|'desc'>('desc');
  const [search, setSearch]       = useState('');
  const [filterMethod, setFilterMethod] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterAgent, setFilterAgent]   = useState('');
  const [filterIB, setFilterIB]         = useState('');
  const [filterClient, setFilterClient] = useState('');
  const [dateFrom, setDateFrom]   = useState('');
  const [dateTo, setDateTo]       = useState('');
  const [loading, setLoading]     = useState(true);
  const [period, setPeriod]       = useState('all_time');
  // Pending withdrawals + per-method stats (ticket #16)
  const [pwOpen, setPwOpen]   = useState(false);
  const [pwData, setPwData]   = useState<any>(null);
  useEffect(() => { if (pwOpen && !pwData) apiGet('/transactions/pending-withdrawals').then(setPwData).catch(() => {}); }, [pwOpen, pwData]);
  // Portal deposit/withdrawal REQUESTS awaiting admin — shown INLINE as pending rows in the main
  // table (no separate bar); back-office actions them straight from the Action column.
  const [reqData, setReqData] = useState<any>(null);
  const loadReqs = () => apiGet('/transactions/requests').then(setReqData).catch(() => {});
  useEffect(() => { loadReqs(); }, []);   // eslint-disable-line
  const actReq = async (id: number, action: string, reason?: string) => {
    if (action === 'reject' && !reason && !window.confirm('Reject this request?')) return;
    try { await apiPost(`/transactions/requests/${id}/action`, { action, reason: reason || '' }); setDepositCase(null); loadReqs(); load(); } catch {}
  };
  // case-file popup for a pending deposit proof (opened from the yellow request rows)
  const [depositCase, setDepositCase] = useState<any>(null);   // holds the _req row
  // Sales-agent filter dropdown (same as Leads/Clients)
  const [agentList, setAgentList] = useState<any[]>([]);
  useEffect(() => { apiGet('/agents').then((d:any) => setAgentList(d.agents || [])).catch(() => {}); }, []);
  const [dashKpis, setDashKpis]   = useState<any>(null);
  const [accountModal, setAccountModal] = useState<any>(null);
  const [clientModal, setClientModal]   = useState<any>(null);
  const [reviewModal, setReviewModal]   = useState<any>(null);
  const [detailsModal, setDetailsModal] = useState<any>(null);   // read-only details (ticket #91)

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({
        page: String(page), page_size: String(pageSize),
        tx_type: txType, sort, sort_dir: sortDir,
        search, method: filterMethod, status: filterStatus,
        agent: filterAgent, ib: filterIB, client: filterClient,
        date_from: dateFrom, date_to: dateTo, period,
      });
      const data = await apiGet(`/transactions?${p}`);
      const txList = data.transactions || [];
      setTxs(txList);
      if (txList.length > 0 && txList[0].tx_date) {
        setLastUpdated(new Date(txList[0].tx_date).toLocaleDateString('en-GB'));
      }
      setTotal(data.total || 0);
      setKpis(data.kpis || {});
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [page, pageSize, txType, sort, sortDir, search, filterMethod, filterStatus, filterAgent, filterIB, filterClient, dateFrom, dateTo, period]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh the live list to keep transactions up to date. Only poll the
  // default top-of-list view (page 1, no active search) so we don't repeatedly
  // re-run heavy filtered/paginated/searched queries while the user is reading.
  useEffect(() => {
    if (page !== 1 || search) return;
    const interval = setInterval(() => { load(); }, 60000);
    return () => clearInterval(interval);
  }, [load, page, search]);

  useEffect(() => {
    const kp = new URLSearchParams({ period, agent: filterAgent, date_from: dateFrom, date_to: dateTo });
    apiGet(`/dashboard/kpis?${kp}`)
      .then((d:any) => setDashKpis(d)).catch(() => {});
  }, [period, filterAgent, dateFrom, dateTo]);

  const handleSort = (col: string) => {
    if (sort === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSort(col); setSortDir('desc'); }
  };

  const handleAction = async (action: string, note: string) => {
    if (!reviewModal) return;
    try {
      await apiPost('/transactions/action', { deal_id: reviewModal.deal_id, action, note });
      setReviewModal(null);
      load();
    } catch (e) { alert('Action failed'); }
  };

  const filterBy = (field: string, val: string) => {
    if (!val || val === '—') return;
    if (field === 'method') setFilterMethod(val);
    if (field === 'agent')  setFilterAgent(val);
    if (field === 'ib')     setFilterIB(val);
    setPage(1);
  };

  const clearFilters = () => {
    setFilterMethod(''); setFilterStatus(''); setFilterAgent(''); setFilterIB(''); setFilterClient('');
    setDateFrom(''); setDateTo(''); setSearch(''); setPage(1);
  };

  const hasFilters = filterMethod || filterStatus || filterAgent || filterIB || filterClient || dateFrom || dateTo || search;

  // Only Jwan / Narmeen (and the super admin) may export the transactions list.
  const _uName = (localStorage.getItem('userName') || '').trim().toLowerCase();
  const _uRole = (localStorage.getItem('userRole') || '').trim().toLowerCase();
  const canExport = _uRole === 'admin' || _uRole === 'super_admin' || _uName === 'jwan' || _uName === 'narmeen';
  const [exporting, setExporting] = useState(false);
  const doExport = async () => {
    setExporting(true);
    try {
      const p = new URLSearchParams({
        tx_type: txType, sort, sort_dir: sortDir, search, method: filterMethod, status: filterStatus,
        agent: filterAgent, ib: filterIB, client: filterClient,
        date_from: dateFrom, date_to: dateTo, period, export: 'csv',
      });
      const token = localStorage.getItem('token') || '';
      const res = await fetch(`/api/transactions?${p}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) { alert(res.status === 403 ? 'You are not allowed to export.' : 'Export failed.'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `transactions_${txType}.csv`; document.body.appendChild(a); a.click();
      a.remove(); URL.revokeObjectURL(url);
    } catch { alert('Export failed.'); }
    finally { setExporting(false); }
  };

  const thSort = (col: string, label: string) => (
    <th style={thS} onClick={() => handleSort(col)}>
      {label}{sort === col ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
    </th>
  );

  const TABS: { key: TxType; label: string; count: number }[] = [
    { key: 'deposit',           label: 'Deposits',           count: dashKpis?.deposit_count || 0 },
    { key: 'withdrawal',        label: 'Withdrawals',         count: dashKpis?.withdrawal_count || 0 },
    { key: 'internal_transfer', label: 'Internal transfers',  count: dashKpis?.transfer_count || 0 },
    { key: 'bonus',             label: 'Bonus',               count: dashKpis?.bonus_count || 0 },
    { key: 'mt_adjustment',     label: 'MT5/MT4 fixes',       count: dashKpis?.mt_adjustment_count || 0 },
  ];

  // Pending portal deposit/withdrawal requests are shown INLINE as pending rows at the top of the
  // matching tab; back-office approves ("make the deposit") straight from the Action column.
  const reqRows = (page === 1 && !hasFilters && (txType === 'deposit' || txType === 'withdrawal')
    ? (reqData?.requests || []).filter((r:any) => r.kind === txType)
    : []
  ).map((r:any) => ({
    _req: r, tx_date: r.date, client_name: r.name, login: r.login, amount: r.amount,
    method: r.method, wallet_type: r.card_name || '', wallet_id: r.wallet_id || '',
    tx_count: r.tx_count || 0, agent_name: r.agent_name || '',
    ib_name: r.ib_name || '', network_score: r.network_score || 0,
    status: (r.status || '').toLowerCase() === 'rejected' ? 'rejected' : 'pending', tx_type: r.kind,
  }));
  const rows = [...reqRows, ...txs];

  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', overflow:'hidden', minHeight:0 }}>
      {/* Pending withdrawals + payment-method stats (ticket #16) */}
      <div style={{ margin:'6px 0 2px' }}>
        <button onClick={() => setPwOpen(o => !o)} style={{ display:'flex', alignItems:'center', gap:8, padding:'7px 13px', borderRadius:8, background: pwOpen?'rgba(255,170,0,0.10)':((pwData?.pending?.total_count||0)>0?'rgba(255,170,0,0.14)':'#2c333e'), border:`1px solid ${pwOpen?'#ffaa00':((pwData?.pending?.total_count||0)>0?'#ffaa00':'#4f596b')}`, color: pwOpen?'#ffaa00':((pwData?.pending?.total_count||0)>0?'#ffc04d':'#cdd4de'), fontSize:12.5, fontWeight:600, cursor:'pointer', fontFamily:'inherit' }}>
          💸 Pending withdrawals & payment-method stats
          {pwData && ((pwData.pending?.total_count||0)>0
            ? <span style={{ fontSize:11, fontWeight:700, color:'#20252f', background:'#ffaa00', padding:'2px 9px', borderRadius:99 }}>⚠ {pwData.pending.total_count} pending (${(pwData.pending?.total_value||0).toLocaleString()})</span>
            : <span style={{ fontSize:11, color:'#888' }}>· none pending</span>)}
          <span style={{ color:'#888' }}>{pwOpen?'▲':'▼'}</span>
        </button>
        {pwOpen && (
          <div style={{ background:'#2c333e', border:'1px solid #4f596b', borderRadius:10, padding:14, marginTop:8 }}>
            {!pwData ? <div style={{ color:'#888', fontSize:12 }}>Loading…</div> : (
              <>
              {/* Breakdown by transaction type — deposit / withdrawal / internal transfer (ticket #16) */}
              {pwData.by_type && (
                <div style={{ marginBottom:14 }}>
                  <div style={{ fontSize:11, color:'#888', fontWeight:600, marginBottom:6 }}>By transaction type</div>
                  <div style={{ display:'grid', gridTemplateColumns:`repeat(${Math.min(pwData.by_type.length,4)||1},1fr)`, gap:8 }}>
                    {pwData.by_type.map((t:any,i:number) => {
                      const col = t.type==='deposit'?'#00e5a0':t.type==='withdrawal'?'#ff8888':t.type==='internal_transfer'?'#00aaff':'#ffaa00';
                      return (
                        <div key={i} style={{ background:'#20252f', border:'1px solid #3a4250', borderRadius:8, padding:'9px 12px' }}>
                          <div style={{ fontSize:10.5, color:'#888' }}>{t.label}</div>
                          <div style={{ fontSize:18, fontWeight:600, color:col }}>${t.value.toLocaleString()}</div>
                          <div style={{ fontSize:10.5, color:'#667' }}>{t.count.toLocaleString()} transactions</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
                {/* Pending queue */}
                <div>
                  <div style={{ display:'flex', gap:10, marginBottom:10 }}>
                    <div style={{ flex:1, background:'#20252f', border:'1px solid #3a4250', borderRadius:8, padding:'9px 12px' }}>
                      <div style={{ fontSize:10.5, color:'#888' }}>Pending — not yet performed</div>
                      <div style={{ fontSize:20, fontWeight:600, color:'#ffaa00' }}>{pwData.pending.total_count}</div>
                    </div>
                    <div style={{ flex:1, background:'#20252f', border:'1px solid #3a4250', borderRadius:8, padding:'9px 12px' }}>
                      <div style={{ fontSize:10.5, color:'#888' }}>Pending value</div>
                      <div style={{ fontSize:20, fontWeight:600, color:'#ffaa00' }}>${pwData.pending.total_value.toLocaleString()}</div>
                    </div>
                  </div>
                  <div style={{ fontSize:11, color:'#888', fontWeight:600, marginBottom:6 }}>Pending by method</div>
                  {pwData.pending.by_method.length === 0
                    ? <div style={{ fontSize:12, color:'#667' }}>✓ No pending withdrawals right now — the queue is clear.</div>
                    : pwData.pending.by_method.map((m:any,i:number) => (
                      <div key={i} style={{ display:'flex', justifyContent:'space-between', padding:'4px 0', borderBottom:'1px solid #373f4d', fontSize:12 }}>
                        <span style={{ color:'#cdd4de' }}>{m.method}</span>
                        <span style={{ color:'#888' }}>{m.count} · <b style={{ color:'#e8edf2' }}>${m.value.toLocaleString()}</b></span>
                      </div>
                    ))}
                </div>
                {/* All withdrawals by method (the per-method statistics) */}
                <div>
                  <div style={{ fontSize:11, color:'#888', fontWeight:600, marginBottom:6 }}>Withdrawals by payment method — all time <span style={{ color:'#667' }}>({pwData.all_total.count} · ${pwData.all_total.value.toLocaleString()})</span></div>
                  <div style={{ maxHeight:200, overflowY:'auto' }}>
                    {pwData.all_by_method.map((m:any,i:number) => {
                      const pct = pwData.all_total.value ? Math.round(m.value/pwData.all_total.value*100) : 0;
                      return (
                        <div key={i} style={{ padding:'4px 0', borderBottom:'1px solid #373f4d' }}>
                          <div style={{ display:'flex', justifyContent:'space-between', fontSize:12 }}>
                            <span style={{ color:'#cdd4de' }}>{m.method}</span>
                            <span style={{ color:'#888' }}>{m.count} · <b style={{ color:'#e8edf2' }}>${m.value.toLocaleString()}</b> · {pct}%</span>
                          </div>
                          <div style={{ height:4, borderRadius:3, background:'#00aaff', width:`${pct}%`, minWidth:2, marginTop:3 }} />
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Period selector */}
      <div style={{ display:'flex', gap:4, padding:'8px 0 4px', overflowX:'auto' }}>
        {[['all_time','All time'],['today','Today'],['this_week','This week'],['last_week','Last week'],['this_month','This month'],['last_month','Last month'],['this_year','This year'],['last_year','Last year']].map(([k,l]) => (
          <button key={k} onClick={() => setPeriod(k)}
            style={{ padding:'4px 12px', borderRadius:6, border:`1px solid ${period===k?'#00e5a0':'#626d80'}`, background:period===k?'rgba(0,229,160,0.1)':'transparent', color:period===k?'#00e5a0':'#555', cursor:'pointer', fontSize:11, whiteSpace:'nowrap', fontFamily:'inherit' }}>
            {l}
          </button>
        ))}
      </div>

      {/* Search + filters bar (matches Leads / Clients) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', marginBottom: 14, background: '#2c333e', borderBottom: '1px solid #373f4d', flexShrink: 0, flexWrap: 'wrap' }}>
        <div style={{ fontWeight: 600, fontSize: 13 }}>Transactions</div>
        <div style={{ fontSize: 11, color: '#555' }}>{total.toLocaleString()} records</div>
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="Search name, login, wallet ID..."
          style={{ flex: 1, minWidth: 200, padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 12, outline: 'none' }} />
        <input type="date" value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11, width: 130 }} />
        <span style={{ color: '#555' }}>—</span>
        <input type="date" value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11, width: 130 }} />
        <select value={filterMethod} onChange={e => { setFilterMethod(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11 }}>
          <option value="">All methods</option>
          {['Qi card','ZainCash','AsiaPay','USDT','Ovadraft','Visa/Master','Bank wire'].map(m => <option key={m}>{m}</option>)}
        </select>
        <input value={filterClient} onChange={e => { setFilterClient(e.target.value); setPage(1); }}
          placeholder="Filter by client" title="Filter by client name or login"
          style={{ padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11, width: 150, outline: 'none' }} />
        <input list="tx-agent-list" value={filterAgent} onChange={e => { setFilterAgent(e.target.value); setPage(1); }}
          placeholder="All sales agents" title="Filter by sales agent — type to search"
          style={{ padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11, width: 150, outline: 'none' }} />
        <datalist id="tx-agent-list">
          {agentList.map((a:any) => <option key={a.id} value={a.name} />)}
        </datalist>
        <select value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11 }}>
          <option value="">All statuses</option>
          {['pending','processing','approved','rejected'].map(s => <option key={s}>{s}</option>)}
        </select>
        {canExport && (
          <button onClick={doExport} disabled={exporting}
            title="Export the filtered transactions to CSV"
            style={{ padding: '6px 14px', background: exporting ? '#2c333e' : '#00e5a0', border: '1px solid ' + (exporting ? '#626d80' : '#00e5a0'), borderRadius: 8, color: exporting ? '#888' : '#0a1a14', fontWeight: 700, fontSize: 12, cursor: exporting ? 'default' : 'pointer' }}>
            {exporting ? 'Exporting…' : '⬇ Export'}
          </button>
        )}
      </div>

      {/* Active filters */}
      {hasFilters && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: '#555' }}>Filtered by:</span>
          {filterMethod && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterMethod('')}>Method: {filterMethod} ✕</span>}
          {filterStatus && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterStatus('')}>Status: {filterStatus} ✕</span>}
          {filterClient && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterClient('')}>Client: {filterClient} ✕</span>}
          {filterAgent  && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterAgent('')}>Agent: {filterAgent} ✕</span>}
          {filterIB     && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterIB('')}>IB: {filterIB} ✕</span>}
          <span style={{ fontSize: 11, color: '#ff4d4d', cursor: 'pointer' }} onClick={clearFilters}>Clear all</span>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, background: '#373f4d', borderRadius: 10, padding: 4, marginBottom: 14 }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => { setTxType(t.key); setPage(1); }}
            style={{ padding: '6px 16px', borderRadius: 7, fontSize: 12, cursor: 'pointer', border: txType === t.key ? '1px solid #626d80' : 'none', background: txType === t.key ? '#2c333e' : 'transparent', color: '#fff', fontWeight: txType === t.key ? 600 : 400, fontFamily: 'inherit' }}>
            {t.label} <span style={{ color: '#aab2c0', fontSize: 10 }}>{t.count.toLocaleString()}</span>
          </button>
        ))}
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8, marginBottom: 14 }}>
        {txType === 'deposit' && <>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00e5a0' }}>{fmtUSD(dashKpis?.deposits || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Total deposited</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#ffaa00' }}>{dashKpis?.pending_w || 0}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Pending review</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00aaff' }}>{(dashKpis?.deposit_count || 0).toLocaleString()}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Total deposits</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00e5a0' }}>{fmtUSD(dashKpis?.deposit_3d || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Last 3 days</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00e5a0' }}>{fmtUSD(dashKpis?.today_amount || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Today</div></div>
        </>}
        {txType === 'withdrawal' && <>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#ff4d4d' }}>{fmtUSD(dashKpis?.withdrawals || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Total withdrawn</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#ffaa00' }}>{dashKpis?.pending_w || 0}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Pending review</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00aaff' }}>{(dashKpis?.withdrawal_count || 0).toLocaleString()}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Total withdrawals</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#ff4d4d' }}>{fmtUSD(dashKpis?.withdrawal_3d || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Last 3 days</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#ff4d4d' }}>{dashKpis?.flagged_count || 0} flagged</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Network risk ≥6/10</div></div>
        </>}
        {(txType === 'internal_transfer' || txType === 'bonus') && <>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00aaff' }}>{fmtUSD(kpis.total_amount || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Total amount</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00aaff' }}>{(dashKpis?.bonus_count || 0).toLocaleString()}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Total records</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#9966ff' }}>{fmtUSD(dashKpis?.bonus_3d || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Last 3 days</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00e5a0' }}>{fmtUSD(dashKpis?.today_amount || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Today</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#555' }}>0</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>Pending</div></div>
        </>}
      </div>

      {/* Table */}
      <div style={{ flex: 1, overflowX: 'auto', overflowY: 'auto', minHeight: 0 }}>
      <div style={{ background: 'transparent', overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1200, fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#373f4d', position: 'sticky', top: 0, zIndex: 10 }}>
                {thSort('date',   'Date & time')}
                <th style={thS}>Client</th>
                <th style={thS}>Login</th>
                {thSort('amount', 'Amount')}
                {txType === 'internal_transfer' ? (<>
                  <th style={thS}>From</th>
                  <th style={thS}>To</th>
                </>) : (<>
                  <th style={thS}>Card / Method</th>
                  <th style={thS}>Card name / Wallet</th>
                  <th style={thS}>Wallet ID</th>
                </>)}
                <th style={thS}># Txns</th>
                <th style={thS}>Sales agent</th>
                <th style={thS}>IB</th>
                <th style={thS}>Network</th>
                {txType === 'withdrawal' && <th style={thS}>Abuse flag</th>}
                {txType === 'bonus' && <th style={thS}>Type</th>}
                <th style={thS}>Status</th>
                <th style={thS}>Action</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={14} style={{ textAlign: 'center', color: '#555', padding: 40 }}>Loading...</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={14} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No records found</td></tr>
              ) : rows.map((tx, i) => {
                const isManual = !METHODS_AUTO.includes(tx.method);
                const isPending = tx.status === 'pending' || tx.status === 'processing';
                const isReq = !!tx._req;
                return (
                  <tr key={i} style={{ cursor: 'default', background: isReq ? 'rgba(255,170,0,0.07)' : 'transparent' }}
                    onMouseEnter={e => (e.currentTarget.style.background = isReq ? 'rgba(255,170,0,0.12)' : '#2c333e')}
                    onMouseLeave={e => (e.currentTarget.style.background = isReq ? 'rgba(255,170,0,0.07)' : 'transparent')}>
                    <td style={tdS}>
                      <div>{tx.tx_date ? new Date(tx.tx_date).toLocaleDateString() : '—'}</div>
                      <div style={{ fontSize: 10, color: '#555' }}>{tx.tx_date ? new Date(tx.tx_date).toLocaleTimeString() : ''}</div>
                    </td>
                    <td style={tdS}>
                      <span onClick={() => { const nm = tx.client_name || String(tx.login); if (filterClient === nm) { setClientModal(tx); } else { setFilterClient(nm); setPage(1); } }}
                        title={filterClient === (tx.client_name || String(tx.login)) ? 'Open client profile' : 'Filter by this client (click again to open profile)'}
                        style={{ color: '#e0e0e0', cursor: 'pointer', fontWeight: 500 }} className="hover-underline">
                        {tx.client_name || `#${tx.login}`}
                      </span>
                    </td>
                    <td style={tdS}>
                      <span onClick={() => setAccountModal(tx)} style={{ color: '#00aaff', cursor: 'pointer', fontFamily: 'monospace' }}>
                        {tx.login}
                      </span>
                    </td>
                    <td style={{ ...tdS, color: txType === 'withdrawal' ? '#ff4d4d' : txType === 'bonus' ? '#ffaa00' : '#00e5a0', fontWeight: 600 }}>
                      {fmtUSD(tx.amount || 0)}
                    </td>
                    {txType === 'internal_transfer' ? (<>
                      <td style={tdS}>
                        {tx.from_account
                          ? <span onClick={() => { setSearch(String(tx.from_account)); setPage(1); }}
                              title={String(tx.from_account) === String(tx.login) ? 'This account' : 'Show this account'}
                              style={{ color: String(tx.from_account) === String(tx.login) ? '#e0e0e0' : '#00aaff', cursor: 'pointer', fontFamily: 'monospace', fontWeight: String(tx.from_account) === String(tx.login) ? 600 : 400 }}>
                              {tx.from_account}</span>
                          : <span style={{ color: '#555' }}>—</span>}
                      </td>
                      <td style={tdS}>
                        {tx.to_account
                          ? <span onClick={() => { setSearch(String(tx.to_account)); setPage(1); }}
                              title={String(tx.to_account) === String(tx.login) ? 'This account' : 'Show this account'}
                              style={{ color: String(tx.to_account) === String(tx.login) ? '#e0e0e0' : '#00aaff', cursor: 'pointer', fontFamily: 'monospace', fontWeight: String(tx.to_account) === String(tx.login) ? 600 : 400 }}>
                              {tx.to_account}</span>
                          : <span style={{ color: '#555' }}>—</span>}
                      </td>
                    </>) : (<>
                      <td style={tdS}>
                        <MethodBadge method={methodLabel(tx)} mtype={isManual ? 'manual' : 'auto'} onClick={() => filterBy('method', tx.method)} />
                      </td>
                      <td style={{ ...tdS, color: '#666' }}>{tx.wallet_type || '—'}</td>
                      <td style={{ ...tdS, color: '#555', fontSize: 11, maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                          title={tx.sender_acct ? `Sender: ${tx.sender_acct}` : (tx.wallet_id || (tx.sender_block ? `Qi sender block ${tx.sender_block} (4 digits — full account not read)` : ''))}>
                        {tx.sender_acct
                          ? (<span>
                              <span style={{ fontFamily: 'monospace', color: '#0E6E6B', fontWeight: 600 }}>{tx.sender_acct}</span>
                              {tx.wallet_confidence === 'ambiguous' && <span title="Multiple candidate transactions — verify" style={{ color: '#d97706', marginLeft: 4 }}>~</span>}
                            </span>)
                          : tx.wallet_id
                            ? <span style={{ fontFamily: 'monospace' }}>{tx.wallet_id}</span>
                            : tx.sender_block
                              ? <span style={{ fontFamily: 'monospace', color: '#999' }}>{tx.sender_block}<span style={{ fontSize: 10 }}> ·block</span></span>
                              : '—'}
                      </td>
                    </>)}
                    <td style={{ ...tdS, textAlign: 'center' }} onClick={e=>e.stopPropagation()}>
                      <span
                        onMouseEnter={e=>setTxPopup({tx, x:e.clientX, y:e.clientY})}
                        onMouseLeave={()=>setTxPopup(null)}
                        style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', fontWeight: 500, cursor:'default' }}>
                        {tx.tx_count || 0}
                      </span>
                    </td>
                    <td style={tdS}>
                      <span onClick={() => filterBy('agent', tx.agent_name)} style={{ color: '#888', cursor: tx.agent_name ? 'pointer' : 'default' }}>
                        {tx.agent_name || '—'}
                      </span>
                    </td>
                    <td style={tdS}>
                      <span onClick={() => { if(!tx.ib_name) return; if(filterIB===tx.ib_name){ window.dispatchEvent(new CustomEvent('navigate',{detail:{page:'ib_admin',ib:tx.ib_name}})); } else { filterBy('ib', tx.ib_name); } }}
                        title={tx.ib_name ? (filterIB===tx.ib_name ? 'Open IB page' : 'Filter by this IB (click again to open IB page)') : ''}
                        style={{ color: '#00aaff', cursor: tx.ib_name ? 'pointer' : 'default' }}>
                        {tx.ib_name || '—'}
                      </span>
                    </td>
                    <td style={tdS} onClick={e=>e.stopPropagation()}>
                      <span
                        onMouseEnter={e=>{ if(netCloseTimer.current) clearTimeout(netCloseTimer.current); const r=e.currentTarget.getBoundingClientRect(); setNetHover({tx, rect:{left:r.left,right:r.right,top:r.top,bottom:r.bottom}}); }}
                        onMouseLeave={()=>{ netCloseTimer.current = setTimeout(()=>setNetHover(null), 400); }}
                        style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${nc(tx.network_score || 0)}22`, color: nc(tx.network_score || 0), fontWeight: 500, cursor:'pointer' }}>
                        {tx.network_score || 0}/10
                      </span>
                    </td>
                    {txType === 'withdrawal' && (
                      <td style={tdS}>
                        {tx.abuse_flag
                          ? (() => {
                              const sc: any = { critical:'#ff4d4d', high:'#ff8800', medium:'#ffaa00' };
                              const col = sc[tx.abuse_severity] || '#ff4d4d';
                              return <span onClick={()=>setAbuseTx(tx)}
                                onMouseEnter={e=>setAbuseHover({tx, x:e.clientX, y:e.clientY})}
                                onMouseLeave={()=>setAbuseHover(null)}
                                title="This account is in an open abuse case — hold the withdrawal and review"
                                style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${col}22`, color: col, fontWeight: 700, cursor:'pointer', border:`1px solid ${col}66`, whiteSpace:'nowrap' }}>
                                {tx.abuse_hot ? '🔥 ' : ''}⛔ HOLD · {tx.abuse_flag}</span>;
                            })()
                          : <span style={{ color: '#626d80' }}>—</span>}
                      </td>
                    )}
                    {txType === 'bonus' && (
                      <td style={tdS}>
                        <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: tx.tx_type === 'bonus_deposit' ? '#3a2a0e' : '#3a0e0e', color: tx.tx_type === 'bonus_deposit' ? '#ffaa00' : '#ff4d4d', fontWeight: 500 }}>
                          {tx.tx_type === 'bonus_deposit' ? 'Bonus in' : 'Bonus out'}
                        </span>
                      </td>
                    )}
                    <td style={tdS}><StatusBadge status={tx.status || 'approved'} /></td>
                    <td style={tdS}>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        {isReq ? (
                          // one "Details" button for every pending/rejected request — approve/reject happens
                          // inside the popup. Yellow while pending, red once rejected.
                          (() => {
                            const isRej = (tx._req.status || '').toLowerCase() === 'rejected';
                            return <button onClick={() => setDepositCase(tx._req)}
                              title={isRej ? 'View this rejected request' : 'Review & approve/reject this request'}
                              style={{ padding: '4px 12px', background: isRej ? 'rgba(240,85,106,0.12)' : '#3a2a0e', border: `1px solid ${isRej ? '#f0556a' : '#ffaa00'}`, borderRadius: 6, color: isRej ? '#f0556a' : '#ffc04d', cursor: 'pointer', fontSize: 11, fontWeight: 700, fontFamily: 'inherit' }}>👁 Details</button>;
                          })()
                        ) : (<>
                          <button onClick={() => setDetailsModal(tx)} title="View full transaction details"
                            style={{ padding: '4px 10px', background: '#0a1a3a', border: '1px solid #00aaff', borderRadius: 6, color: '#00aaff', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>👁 Details</button>
                          {isPending && !readOnly &&
                            <button onClick={() => setReviewModal(tx)} style={{ padding: '4px 10px', background: '#3a2a0e', border: '1px solid #ffaa00', borderRadius: 6, color: '#ffaa00', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>Review</button>}
                        </>)}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderTop: '1px solid #373f4d' }}>
          <span style={{ color: '#555', fontSize: 11 }}>Page {page} · {total.toLocaleString()} records</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
              style={{ padding: '3px 6px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 5, color: '#888', fontSize: 11 }}>
              {[20, 50, 100, 200].map(s => <option key={s} value={s}>{s}/page</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: page === 1 ? '#626d80' : '#888', cursor: page === 1 ? 'default' : 'pointer', fontSize: 12 }}>← Prev</button>
            <button onClick={() => setPage(p => p + 1)} disabled={txs.length < pageSize}
              style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: txs.length < pageSize ? '#626d80' : '#00e5a0', cursor: txs.length < pageSize ? 'default' : 'pointer', fontSize: 12, borderColor: txs.length < pageSize ? '#626d80' : '#00e5a0' }}>Next →</button>
          </div>
        </div>
      </div>

      </div>
      {/* Modals */}
      {accountModal && <AccountModal tx={accountModal} onClose={() => setAccountModal(null)} />}
      {clientModal  && <ClientModal  tx={clientModal}  onClose={() => setClientModal(null)} onNavigate={(login)=>{ setClientModal(null); window.dispatchEvent(new CustomEvent('navigate', {detail:{page:'clients',search:String(login),openProfile:login}})); }} />}
      {reviewModal  && <ReviewModal  tx={reviewModal}  onClose={() => setReviewModal(null)} onAction={handleAction} />}
      {detailsModal && <DetailsModal tx={detailsModal} onClose={() => setDetailsModal(null)} />}
      {depositCase && <DepositCaseModal rid={depositCase.id} reasons={reqData?.reject_reasons || []} canAct={!readOnly}
        onClose={() => setDepositCase(null)}
        onApprove={() => actReq(depositCase.id, 'approve')}
        onReject={(reason: string) => actReq(depositCase.id, 'reject', reason)} />}
      {phoneContact && <PhoneModal contact={phoneContact} onClose={()=>setPhoneContact(null)} />}
      {emailContact && <EmailModal contact={emailContact} type="client" onClose={()=>setEmailContact(null)} />}
      {txPopup && <TxCountTooltip tx={txPopup.tx} x={txPopup.x} y={txPopup.y} onClose={()=>setTxPopup(null)} />}
      {abuseTx && <AbuseDetailModal tx={abuseTx} onClose={()=>setAbuseTx(null)} />}
      {netHover && <NetworkHoverPopup tx={netHover.tx} rect={netHover.rect}
        onCancelClose={()=>{ if(netCloseTimer.current) clearTimeout(netCloseTimer.current); }}
        onClose={()=>setNetHover(null)} />}
      {abuseHover && (() => {
        const t = abuseHover.tx;
        const left = Math.min(abuseHover.x+10, window.innerWidth-300);
        const top  = Math.min(abuseHover.y+14, window.innerHeight-180);
        return (
          <div style={{ position:'fixed', left, top, zIndex:99999, background:'#2c333e', border:'1px solid #ff4d4d44', borderRadius:10, padding:13, width:280, boxShadow:'0 8px 32px rgba(0,0,0,0.6)', pointerEvents:'none' }}>
            <div style={{ fontSize:12, fontWeight:600, color:'#ff4d4d', marginBottom:6 }}>⚠️ {t.abuse_flag}</div>
            <div style={{ fontSize:10, color:'#999', lineHeight:1.6 }}>
              <div><b style={{color:'#ccc'}}>Why:</b> flagged by the trading-behaviour detectors (bonus hedging, swap arbitrage, latency abuse, …) — based on how this account <i>traded</i>, not its network links.</div>
              <div style={{marginTop:5}}><b style={{color:'#ccc'}}>What:</b> #{t.login} · {t.client_name} · withdrawing ${(t.amount||0).toLocaleString()}.</div>
              <div style={{marginTop:6, color:'#666'}}>Click for the full abuse-case detail.</div>
            </div>
          </div>
        );
      })()}
      {txDetail && (
        <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.7)', zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center' }} onClick={()=>setTxDetail(null)}>
          <div style={{ background:'#2c333e', border:'1px solid #626d80', borderRadius:12, padding:22, width:420 }} onClick={e=>e.stopPropagation()}>
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:16 }}>
              <div style={{ fontSize:14, fontWeight:600 }}>Transaction detail</div>
              <div onClick={()=>setTxDetail(null)} style={{ cursor:'pointer', color:'#555' }}>✕</div>
            </div>
            {[['Client', txDetail.client_name],['Login', '#'+txDetail.login],['Type', txDetail.tx_type],['Amount', '$'+(txDetail.amount||0).toLocaleString()],['Method', methodLabel(txDetail)],['Date', txDetail.tx_date ? new Date(txDetail.tx_date).toLocaleDateString() : '—'],['Status', txDetail.status||'—'],['Agent', txDetail.agent_name||'—'],['IB', txDetail.ib_name||'—'],['Notes', txDetail.notes||'—']].map(([k,v])=>(
              <div key={k as string} style={{ display:'flex', justifyContent:'space-between', padding:'7px 0', borderBottom:'1px solid #373f4d', fontSize:12 }}>
                <span style={{ color:'#555' }}>{k}</span>
                <span style={{ color:'#e0e0e0', maxWidth:250, textAlign:'right' as any }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
