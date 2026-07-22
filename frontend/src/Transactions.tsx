import { PhoneModal, EmailModal } from './ContactModals';
import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, openIbProfile } from './api';
import NetworkBadge from './NetworkBadge';
import DepositCaseModal from './DepositCaseModal';
import { CT } from './crmTable';
import { useT } from './adminI18n';

type TxType = 'deposit' | 'withdrawal' | 'internal_transfer' | 'bonus' | 'mt_adjustment';

const METHODS_AUTO = ['USDT','Ovadraft','Visa/Master'];
const nc = (n: number) => n >= 7 ? '#ff4d4d' : n >= 4 ? '#ffaa00' : '#00e5a0';
// #247 — NEVER round money for display (98.5 must show 98.50, not 99): whole amounts show
// clean, fractional amounts keep exactly 2 decimals so totals reconcile with the source.
const fmtUSD = (n: number) => {
  const v = Number(n) || 0;
  return '$' + (Number.isInteger(v)
    ? v.toLocaleString('en-GB')
    : v.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
};

// FACE-VALUE display (desk rule): show tx_date exactly as its source system (MT/TradeSoft)
// stamps it — the desk reconciles against those displays. Do NOT convert timezones here.
const asStamp = (s?: string) => {
  if (!s) return null;
  const d = new Date(s.includes('T') ? s : s.replace(' ', 'T'));
  return isNaN(d.getTime()) ? null : d;
};
const fmtIqDate = (s?: string) => { const d = asStamp(s); return d ? d.toLocaleDateString('en-GB') : '—'; };
const fmtIqTime = (s?: string) => { const d = asStamp(s); return d ? d.toLocaleTimeString('en-GB') : ''; };
const fmtIqDT   = (s?: string) => { const d = asStamp(s); return d ? d.toLocaleString('en-GB') : '—'; };

// Ticket #43: the bare platform value "MT5" is NOT a payment method — it marks an
// internal MT5 balance adjustment. Show a clearer label. Prefer the backend's
// method_label; fall back here so old rows / other views still read well.
const methodLabel = (tx: any): string => {
  if (tx && tx.method_label) return tx.method_label;
  const m = (tx?.method || '').trim();
  if (m.toUpperCase() === 'MT5') return 'Internal / MT5 adjustment';
  return m || '—';
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
  const t = useT();
  const auto = mtype === 'auto';
  return (
    <span onClick={onClick} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: auto ? '#0e3a2a' : '#3a2a0e', color: auto ? '#00e5a0' : '#ffaa00', fontWeight: 500, cursor: 'pointer' }} title={t('Click to filter')}>
      {method}
    </span>
  );
}



function TxCountTooltip({ tx, x, y, onClose }: any) {
  const t = useT();
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
        <div style={{ fontSize:12, fontWeight:600 }}>{t('All transactions')}</div>
        <div style={{ fontSize:11, color:'#555' }}>{tx.client_name} · #{tx.login}</div>
      </div>
      {loading ? <div style={{ color:'#555', fontSize:12 }}>{t('Loading...')}</div> : txs.length === 0 ? <div style={{ color:'#555', fontSize:12 }}>{t('No transactions')}</div> : (
        <>
          <div style={{ display:'grid', gridTemplateColumns:'72px 70px 65px 60px', gap:4, marginBottom:4 }}>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase' }}>{t('Date')}</div>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase' }}>{t('Type')}</div>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase' }}>{t('Method')}</div>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', textAlign:'right' }}>{t('Amount')}</div>
          </div>
          {txs.map((tt:any,i:number)=>(
            <div key={i} style={{ display:'grid', gridTemplateColumns:'72px 70px 65px 60px', gap:4, padding:'4px 0', borderBottom:'1px solid #373f4d', fontSize:10 }}>
              <div style={{ color:'#888' }}>{fmtIqDate(tt.tx_date)}</div>
              <div style={{ color: typeColor[tt.tx_type] || '#888' }}>{tt.tx_type==='deposit'?t('Dep'):tt.tx_type==='withdrawal'?t('With'):tt.tx_type}</div>
              <div style={{ color:'#666', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{methodLabel(tt)}</div>
              <div style={{ color:'#e0e0e0', textAlign:'right', fontWeight:500 }}>${(tt.amount||0).toLocaleString('en-GB')}</div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function NetworkHoverPopup({ tx, rect, onClose, onCancelClose }: any) {
  const t = useT();
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
        <div style={{ fontSize:12, fontWeight:600 }}>{t('Network score')} — #{tx.login}</div>
        <div style={{ fontSize:14, fontWeight:700, color:scoreColor }}>{score}/10</div>
      </div>
      <div style={{ fontSize:10, color:'#777', marginBottom:8 }}>
        {cidCount>0 && <span style={{color:'#ff4d4d'}}>📱 {cidCount} {t('same-device (CID)')}</span>}
        {cidCount>0 && ipCount>0 && <span> · </span>}
        {ipCount>0 && <span style={{color:'#ffaa00'}}>🌐 {ipCount} {t('same-IP')}</span>}
        {cidCount===0 && ipCount===0 && <span>{t('No shared device/IP links')}</span>}
      </div>
      {loading ? <div style={{ color:'#555', fontSize:11 }}>{t('Loading connections...')}</div>
      : nodes.length===0 ? <div style={{ color:'#555', fontSize:11 }}>{t('No linked accounts found.')}</div>
      : <>
        <div style={{ fontSize:10, color:'#555', marginBottom:4 }}>{t('Linked to (click to open full network):')}</div>
        {nodes.slice(0,8).map((n:any,i:number)=>(
          <div key={i} onClick={()=>goToNetwork(n.login)} title={`${t('Open')} #${n.login} ${t('in Network page')}`}
            style={{ display:'flex', alignItems:'center', gap:8, padding:'5px 4px', borderBottom:'1px solid #373f4d', cursor:'pointer', borderRadius:4 }}
            onMouseEnter={e=>(e.currentTarget.style.background='#373f4d')}
            onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
            <div style={{ width:22, height:22, borderRadius:6, background:n.type==='cid'?'#3a0e0e':'#3a2a0e', display:'flex', alignItems:'center', justifyContent:'center', fontSize:11, flexShrink:0 }}>{n.type==='cid'?'📱':'🌐'}</div>
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ fontSize:11, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', color:'#4d9fff' }}>{n.name}</div>
              <div style={{ fontSize:9, color:'#666' }}>#{n.login} · {n.type==='cid'?t('same device'):n.type==='ip'?t('same IP'):n.type}{n.connect_via?(' · '+String(n.connect_via).substring(0,14)):''}</div>
            </div>
            <div style={{ fontSize:9, padding:'1px 5px', borderRadius:3, background:n.type==='cid'?'rgba(255,77,77,0.2)':'rgba(255,170,0,0.2)', color:n.type==='cid'?'#ff4d4d':'#ffaa00', flexShrink:0, fontWeight:700 }}>{(n.type||'').toUpperCase()}</div>
          </div>
        ))}
        {nodes.length>8 && <div style={{ fontSize:9, color:'#555', marginTop:5 }}>+{nodes.length-8} {t('more — click any to see the full graph')}</div>}
      </>}
    </div>
  );
}

function AbuseDetailModal({ tx, onClose }: any) {
  const t = useT();
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
    margin_partner:'🔥 '+t('Margin-Out Partner'), bonus_ring:'🎁 '+t('Bonus Ring'),
    bonus_cashout:'🎁 '+t('Bonus Cash-Out'), chip_dump:'🔀 '+t('Chip Dumping'),
    swap_carry:'💱 '+t('Swap Carry'), toxic_arb:'☢️ '+t('Toxic / Latency'),
  };

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.8)', zIndex:99999, display:'flex', alignItems:'center', justifyContent:'center' }} onClick={onClose}>
      <div style={{ background:'#2c333e', border:'1px solid #626d80', borderRadius:14, padding:24, width:520, maxHeight:560, display:'flex', flexDirection:'column' }} onClick={e=>e.stopPropagation()}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:16 }}>
          <div>
            <div style={{ fontSize:14, fontWeight:600, color:'#ff4d4d' }}>⚠️ {t('Abuse Detection')}</div>
            <div style={{ fontSize:11, color:'#555', marginTop:2 }}>{tx.client_name} · #{tx.login} · {t('Withdrawal')} ${(tx.amount||0).toLocaleString('en-GB')}</div>
          </div>
          <div onClick={onClose} style={{ cursor:'pointer', color:'#555', fontSize:20, lineHeight:1 }}>✕</div>
        </div>
        <div style={{ overflowY:'auto', flex:1 }}>
          {loading ? (
            <div style={{ textAlign:'center', color:'#555', padding:30 }}>{t('Loading abuse cases...')}</div>
          ) : cases.length === 0 ? (
            <div style={{ padding:16, background:'#373f4d', borderRadius:8, textAlign:'center' }}>
              <div style={{ color:'#555', fontSize:13 }}>{t('No abuse cases detected for')} #{tx.login}</div>
              <div style={{ color:'#626d80', fontSize:11, marginTop:6 }}>{t('This withdrawal was flagged for:')} {tx.abuse_flag}</div>
            </div>
          ) : cases.map((c:any,i:number)=>(
            <div key={i} style={{ padding:14, background:'#1a0a0a', border:`1px solid ${severityColor[c.severity]||'#626d80'}44`, borderRadius:8, marginBottom:10 }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                <div style={{ fontSize:13, fontWeight:600, color: severityColor[c.severity]||'#888' }}>
                  {typeLabel[c.abuse_type]||c.abuse_type}
                </div>
                <div style={{ display:'flex', gap:6 }}>
                  <span style={{ fontSize:10, padding:'2px 7px', borderRadius:99, background: `${severityColor[c.severity]||'#888'}22`, color: severityColor[c.severity]||'#888' }}>{c.severity}</span>
                  <span style={{ fontSize:10, padding:'2px 7px', borderRadius:99, background:'rgba(255,170,0,0.1)', color:'#ffaa00' }}>{t('Risk')} {c.risk_score}/100</span>
                </div>
              </div>
              <div style={{ fontSize:11, color:'#aaa', lineHeight:1.6, marginBottom:8 }}>{c.evidence}</div>
              <div style={{ display:'flex', gap:16, fontSize:10, color:'#555' }}>
                <span>{t('Accounts:')} {(c.all_logins||[]).join(', ')}</span>
                <span>{t('Exposure:')} ${(c.exposure||0).toLocaleString('en-GB')}</span>
                <span>{c.created_at ? fmtIqDate(c.created_at) : ''}</span>
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
  const t = useT();
  if (!tx) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }} onClick={onClose}>
      <div style={{ background: '#2c333e', border: '1px solid #626d80', borderRadius: 14, padding: 20, width: 380, maxWidth: '95vw' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{t('Trading account')} #{tx.login}</span>
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
            <span style={{ color: '#555' }}>{t(l as string)}</span>
            <span style={{ color: l === 'Balance' ? '#00e5a0' : '#e0e0e0', fontWeight: l === 'Balance' ? 600 : 400 }}>{v}</span>
          </div>
        ))}
        <button onClick={() => { window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'accounts', login: tx.login } })); onClose(); }}
          style={{ width: '100%', marginTop: 12, padding: 8, background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}>
          {t('Open full account')} →
        </button>
      </div>
    </div>
  );
}

function ClientModal({ tx, onClose, onNavigate }: { tx: any; onClose: () => void; onNavigate?: (login:number)=>void }) {
  const t = useT();
  if (!tx) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }} onClick={onClose}>
      <div style={{ background: '#2c333e', border: '1px solid #626d80', borderRadius: 14, padding: 20, width: 440, maxWidth: '95vw' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{t('Client profile')}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <div style={{ width: 44, height: 44, borderRadius: '50%', background: '#0e3a2a', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, fontWeight: 600, color: '#00e5a0' }}>
            {(tx.client_name || '?').substring(0, 2).toUpperCase()}
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{tx.client_name}</div>
            <div style={{ color: '#555', fontSize: 11 }}>{t('Login')} #{tx.login}</div>
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
            <span style={{ color: '#555' }}>{t(l as string)}</span>
            <span style={{ color: l === 'Balance' ? '#00e5a0' : l === 'IB' ? '#00aaff' : l === 'Network risk' ? nc(parseInt(v)) : '#e0e0e0', fontWeight: l === 'Balance' ? 600 : 400 }}>{v}</span>
          </div>
        ))}
        <button onClick={()=>{ onClose(); if(onNavigate) onNavigate(tx.login); }} style={{ width: '100%', marginTop: 12, padding: 8, background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}>
          {t('Open full client profile')} →
        </button>
      </div>
    </div>
  );
}

function ReviewModal({ tx, onClose, onAction }: { tx: any; onClose: () => void; onAction: (action: string, note: string) => void }) {
  const t = useT();
  const [note, setNote] = useState('');
  if (!tx) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }} onClick={onClose}>
      <div style={{ background: '#2c333e', border: '1px solid #626d80', borderRadius: 14, padding: 20, width: 420, maxWidth: '95vw' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{t('Review')} {tx.tx_type}</span>
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
                <div style={{ color: '#555', fontSize: 10 }}>{t(l as string)}</div>
                <div style={{ marginTop: 2, color: l === 'Network' ? nc(parseInt(v)) : l === 'Amount' ? (tx.tx_type === 'withdrawal' ? '#ff4d4d' : '#00e5a0') : '#e0e0e0', fontWeight: l === 'Amount' ? 600 : 400, fontSize: 12 }}>{v || '—'}</div>
              </div>
            ))}
            {tx.abuse_flag && (
              <div style={{ gridColumn: 'span 2' }}>
                <div style={{ color: '#555', fontSize: 10 }}>{t('Abuse flag')}</div>
                <div style={{ marginTop: 2, color: '#ff4d4d' }}>⚠️ {tx.abuse_flag}</div>
              </div>
            )}
          </div>
        </div>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, color: '#555', marginBottom: 6 }}>{t('Note (optional)')}</div>
          <textarea value={note} onChange={e => setNote(e.target.value)} rows={3}
            style={{ width: '100%', padding: 8, background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#e0e0e0', fontSize: 12, fontFamily: 'inherit', resize: 'none', outline: 'none' }}
            placeholder={t('Add a review note...')} />
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button onClick={() => onAction('approve', note)} style={{ flex: 1, padding: '7px 0', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontWeight: 600, cursor: 'pointer', fontSize: 12 }}>✅ {t('Approve')} → MT5</button>
          <button onClick={() => onAction('risk', note)}    style={{ flex: 1, padding: '7px 0', background: '#3a2a0e', border: '1px solid #ffaa00', borderRadius: 8, color: '#ffaa00', fontWeight: 500, cursor: 'pointer', fontSize: 12 }}>⚠️ {t('Send to risk')}</button>
          <button onClick={() => onAction('reject', note)}  style={{ flex: 1, padding: '7px 0', background: '#3a0e0e', border: '1px solid #ff4d4d', borderRadius: 8, color: '#ff4d4d', fontWeight: 500, cursor: 'pointer', fontSize: 12 }}>❌ {t('Reject')}</button>
          <button onClick={onClose} style={{ width: '100%', marginTop: 4, padding: '6px 0', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#888', cursor: 'pointer', fontSize: 12 }}>{t('Cancel')}</button>
        </div>
      </div>
    </div>
  );
}

// ─── Read-only full Details modal (ticket #91) — view every field of a deposit/withdrawal ───
// The actual payment-proof image (Qi/ZC/Sham receipt) served by /transactions/{id}/receipt.
// <img> can't carry the JWT, so fetch as a blob with the Authorization header.
function ReceiptImage({ txId }: { txId: number }) {
  const t = useT();
  const [url, setUrl] = useState<string>('');
  const [err, setErr] = useState<string>('');
  useEffect(() => {
    let obj = '';
    fetch(`/api/transactions/${txId}/receipt`, {
      headers: { Authorization: 'Bearer ' + (localStorage.getItem('token') || '') },
    })
      .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.blob(); })
      .then(b => { obj = URL.createObjectURL(b); setUrl(obj); })
      .catch(() => setErr(t('Receipt not available')));
    return () => { if (obj) URL.revokeObjectURL(obj); };
  }, [txId]);
  if (err) return <div style={{ color: '#8a93a3', fontSize: 11, padding: 8 }}>{err}</div>;
  if (!url) return <div style={{ color: '#8a93a3', fontSize: 11, padding: 8 }}>{t('Loading receipt…')}</div>;
  return (
    <a href={url} target="_blank" rel="noreferrer" title={t('Open full size')}>
      <img src={url} alt={t('Payment receipt')} style={{ maxWidth: '100%', maxHeight: 380, borderRadius: 8, display: 'block', margin: '0 auto', cursor: 'zoom-in' }} />
    </a>
  );
}

function DetailsModal({ tx, onClose }: { tx: any; onClose: () => void }) {
  const t = useT();
  if (!tx) return null;
  // #2 — manual deposits (Qi card / Zain cash / Fastpay / bank wire …) carry sender wallet-id +
  // receiver card + from/to; AUTO (gateway) deposits don't, so hide those empty fields for them.
  const manualRe = /qi\s*card|zain|zc|fast\s*?pay|bank\s*wire|local\s*bank|wallet\s*cash|hawala|sham|cash|usdt|crypto|tether/i;
  const isManual = manualRe.test(String(tx.method || tx.wallet_type || ''));
  const showWallet = isManual || tx.tx_type !== 'deposit';   // keep for manual deposits + withdrawals/transfers
  const zcFp = /zc|zain|fast\s*pay|fastpay/i.test(String(tx.method || ''));
  const receiverField: [string, any] = zcFp
    ? ['Card receiver number', tx.receiver_acct || tx.card_name || tx.wallet_type]
    : ['Card receiver name', tx.card_name || tx.receiver_acct || tx.wallet_type];
  const senderField: [string, any] = ['Sender details', tx.sender_acct || tx.wallet_id || tx.sender_block];
  // card_holder = back-office team member holding the receiving card (from the Card settings) — resolved
  // by the backend from payment_cards by the receiver account / card name.
  const rows: [string, any][] = [
    ['Type',            (tx.tx_type || '').replace('_', ' ')],
    ['Client',          tx.client_name],
    ['Login',           tx.login],
    ['Amount',          fmtUSD(tx.amount)],
    ['Card / Method',   methodLabel(tx)],
    ...(showWallet ? ([receiverField, senderField] as [string, any][]) : []),
    ['TXID',            tx.psp_reference],
    ...(tx.card_holder ? ([['Card holder name', tx.card_holder]] as [string, any][]) : []),
    ['Status',          tx.status],
    ['Date',            fmtIqDT(tx.tx_date)],
    ['Approved at',     tx.approved_at ? fmtIqDT(tx.approved_at) : '—'],
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
          <span style={{ fontSize: 14, fontWeight: 700 }}>{t('Transaction details')}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {rows.map(([l, v]) => (
            <div key={l} style={{ background: '#373f4d', borderRadius: 8, padding: '8px 10px' }}>
              <div style={{ color: '#8a93a3', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.03em' }}>{t(l as string)}</div>
              <div style={{ marginTop: 3, color: l === 'Amount' ? (tx.tx_type === 'withdrawal' ? '#ff6b6b' : '#00e5a0') : '#e8edf2', fontWeight: l === 'Amount' ? 700 : 400, fontSize: 12.5, wordBreak: 'break-word' }}>
                {(v === null || v === undefined || v === '') ? '—' : String(v)}
              </div>
            </div>
          ))}
        </div>
        {tx.abuse_flag && (
          <div style={{ marginTop: 10, background: 'rgba(255,77,77,0.1)', border: '1px solid #ff4d4d55', borderRadius: 8, padding: '8px 10px', fontSize: 12, color: '#ff8888' }}>⚠️ {t('Abuse flag:')} {tx.abuse_flag}</div>
        )}
        {tx.has_receipt && (
          <div style={{ marginTop: 12 }}>
            <div style={{ color: '#8a93a3', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.03em', marginBottom: 6 }}>{t('Payment receipt')}</div>
            <div style={{ background: '#373f4d', borderRadius: 8, padding: 8 }}>
              <ReceiptImage txId={tx.id} />
            </div>
          </div>
        )}
        {!tx.has_receipt && (
          <div style={{ marginTop: 12, fontSize: 11, color: '#667' }}>{t('Note: card-number / wallet-ID and gateway payment info populate for payment-gateway transactions; these journal-sourced rows carry the payment method only.')}</div>
        )}
      </div>
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function Transactions({ readOnly = false, lang }: { readOnly?: boolean; lang?: string }) {
  const t = useT();
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
  // debounced search: the raw input commits to `search` after 400ms so each keystroke
  // doesn't fire two 2.1M-row aggregate scans on the server
  const [searchInput, setSearchInput] = useState('');
  useEffect(() => { const t = setTimeout(() => { setSearch(searchInput); setPage(1); }, 400); return () => clearTimeout(t); }, [searchInput]);
  const [filterMethod, setFilterMethod] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterAgent, setFilterAgent]   = useState('');
  const [filterIB, setFilterIB]         = useState('');
  const [filterCountry, setFilterCountry] = useState('');
  // No longer has a filter box of its own — still set by clicking a client name in the table
  // (click again on the filtered client opens their profile) and cleared via the filter chip.
  const [filterClient, setFilterClient] = useState('');
  const [dateFrom, setDateFrom]   = useState('');
  const [dateTo, setDateTo]       = useState('');
  const [loading, setLoading]     = useState(true);
  const [period, setPeriod]       = useState('all_time');
  // Portal deposit/withdrawal REQUESTS awaiting admin — shown INLINE as pending rows in the main
  // table (no separate bar); back-office actions them straight from the Action column.
  const [reqData, setReqData] = useState<any>(null);
  const loadReqs = () => apiGet('/transactions/requests').then(setReqData).catch(() => {});
  useEffect(() => { loadReqs(); }, []);   // eslint-disable-line
  const actReq = async (id: number, action: string, reason?: string) => {
    if (action === 'reject' && !reason && !window.confirm(t('Reject this request?'))) return;
    try { await apiPost(`/transactions/requests/${id}/action`, { action, reason: reason || '' }); setDepositCase(null); loadReqs(); load(); } catch {}
  };
  // case-file popup for a pending deposit proof (opened from the yellow request rows)
  const [depositCase, setDepositCase] = useState<any>(null);   // holds the _req row
  // Sales-agent filter dropdown (same as Leads/Clients)
  const [agentList, setAgentList] = useState<any[]>([]);
  useEffect(() => { apiGet('/agents/names').then((d:any) => setAgentList(d.agents || [])).catch(() => {}); }, []);
  // Country / IB filter options come from the rows already loaded (there is no dedicated
  // options endpoint) — same approach as the Clients list. They ACCUMULATE across loads:
  // deriving them from the current page alone would collapse each dropdown to its single
  // active value once filtered, leaving no way to switch straight to another one.
  const [uniqueCountries, setUniqueCountries] = useState<string[]>([]);
  const [uniqueIBs, setUniqueIBs]             = useState<string[]>([]);
  useEffect(() => {
    // returning `prev` unchanged when nothing new appeared avoids a pointless re-render
    const merge = (prev: string[], vals: any[]) => {
      const next = Array.from(new Set([...prev, ...vals.filter(Boolean).map(String)])).sort();
      return next.length === prev.length ? prev : next;
    };
    setUniqueCountries(prev => merge(prev, txs.map((t:any) => t.country)));
    setUniqueIBs(prev => merge(prev, txs.map((t:any) => t.ib_name)));
  }, [txs]);
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
        agent: filterAgent, ib: filterIB, country: filterCountry, client: filterClient,
        date_from: dateFrom, date_to: dateTo, period,
      });
      const data = await apiGet(`/transactions?${p}`);
      const txList = data.transactions || [];
      setTxs(txList);
      if (txList.length > 0 && txList[0].tx_date) {
        setLastUpdated(fmtIqDate(txList[0].tx_date));
      }
      setTotal(data.total || 0);
      setKpis(data.kpis || {});
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [page, pageSize, txType, sort, sortDir, search, filterMethod, filterStatus, filterAgent, filterIB, filterCountry, filterClient, dateFrom, dateTo, period]);

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
    } catch (e) { alert(t('Action failed')); }
  };

  const filterBy = (field: string, val: string) => {
    if (!val || val === '—') return;
    if (field === 'method') setFilterMethod(val);
    if (field === 'agent')  setFilterAgent(val);
    if (field === 'ib')     setFilterIB(val);
    setPage(1);
  };

  const clearFilters = () => {
    setFilterMethod(''); setFilterStatus(''); setFilterAgent(''); setFilterIB(''); setFilterCountry(''); setFilterClient('');
    setDateFrom(''); setDateTo(''); setSearch(''); setSearchInput(''); setPage(1);
  };

  const hasFilters = filterMethod || filterStatus || filterAgent || filterIB || filterCountry || filterClient || dateFrom || dateTo || search;

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
        agent: filterAgent, ib: filterIB, country: filterCountry, client: filterClient,
        date_from: dateFrom, date_to: dateTo, period, export: 'csv',
      });
      const token = localStorage.getItem('token') || '';
      const res = await fetch(`/api/transactions?${p}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) { alert(res.status === 403 ? t('You are not allowed to export.') : t('Export failed.')); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `transactions_${txType}.csv`; document.body.appendChild(a); a.click();
      a.remove(); URL.revokeObjectURL(url);
    } catch { alert(t('Export failed.')); }
    finally { setExporting(false); }
  };

  const thSort = (col: string, label: string) => (
    <th style={{ ...CT.th(sort === col), cursor: 'pointer' }} onClick={() => handleSort(col)}>
      {label}{sort === col ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
    </th>
  );

  const TABS: { key: TxType; label: string; count: number }[] = [
    { key: 'deposit',           label: t('Deposits'),           count: dashKpis?.deposit_count || 0 },
    { key: 'withdrawal',        label: t('Withdrawals'),         count: dashKpis?.withdrawal_count || 0 },
    { key: 'internal_transfer', label: t('Internal transfers'),  count: dashKpis?.transfer_count || 0 },
    { key: 'bonus',             label: t('Bonus'),               count: dashKpis?.bonus_count || 0 },
    { key: 'mt_adjustment',     label: t('MT5/MT4 fixes'),       count: dashKpis?.mt_adjustment_count || 0 },
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

      {/* Period selector + custom date range (one row) */}
      <div style={{ display:'flex', alignItems:'center', gap:4, padding:'8px 0 4px', overflowX:'auto' }}>
        {[['all_time','All time'],['today','Today'],['this_week','This week'],['last_week','Last week'],['this_month','This month'],['last_month','Last month'],['this_year','This year'],['last_year','Last year']].map(([k,l]) => (
          <button key={k} onClick={() => setPeriod(k)}
            style={{ padding:'4px 12px', borderRadius:6, border:`1px solid ${period===k?'#00e5a0':'#626d80'}`, background:period===k?'rgba(0,229,160,0.1)':'transparent', color:period===k?'#00e5a0':'#555', cursor:'pointer', fontSize:11, whiteSpace:'nowrap', fontFamily:'inherit' }}>
            {t(l)}
          </button>
        ))}
        {/* Custom range — sits with the presets it overrides (a date range wins over `period`) */}
        <span style={{ width:1, height:18, background:'var(--border,#4f596b)', margin:'0 6px', flexShrink:0 }} />
        <input type="date" title={t('Custom range — from')} max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1); }}
          style={{ padding:'4px 8px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:6, color:'var(--text,#e0e0e0)', fontSize:11, width:125, flexShrink:0, fontFamily:'inherit' }} />
        <span style={{ color:'var(--text3,#555)', flexShrink:0 }}>—</span>
        <input type="date" title={t('Custom range — to')} max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1); }}
          style={{ padding:'4px 8px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:6, color:'var(--text,#e0e0e0)', fontSize:11, width:125, flexShrink:0, fontFamily:'inherit' }} />
        {(dateFrom || dateTo) && (
          <button onClick={() => { setDateFrom(''); setDateTo(''); setPage(1); }} title={t('Clear the custom date range')}
            style={{ padding:'4px 8px', borderRadius:6, border:'1px solid var(--border2,#626d80)', background:'transparent', color:'var(--text3,#888)', cursor:'pointer', fontSize:11, flexShrink:0, fontFamily:'inherit' }}>✕</button>
        )}
      </div>

      {/* Search + filters bar — ONE row, no wrapping (controls are sized to fit) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', marginBottom: 14, background: '#2c333e', borderBottom: '1px solid #373f4d', flexShrink: 0, flexWrap: 'nowrap', overflowX: 'auto' }}>
        <div style={{ fontWeight: 600, fontSize: 13, whiteSpace: 'nowrap', flexShrink: 0 }}>{t('Transactions')}</div>
        <div style={{ fontSize: 11, color: '#555', whiteSpace: 'nowrap', flexShrink: 0 }}>{total.toLocaleString('en-GB')} {t('records')}</div>
        <input value={searchInput} onChange={e => setSearchInput(e.target.value)} placeholder={t('Search name, login, wallet ID...')}
          style={{ flex: '0 0 220px', width: 220, minWidth: 0, padding: '6px 10px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 7, color: 'var(--text,#e0e0e0)', fontSize: 12, outline: 'none', fontFamily: 'inherit' }} />
        <select value={filterMethod} onChange={e => { setFilterMethod(e.target.value); setPage(1); }}
          title={t('Filter by payment method')}
          style={{ flex: '0 0 auto', minWidth: 0, maxWidth: 120, padding: '6px 8px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 7, color: 'var(--text,#e0e0e0)', fontSize: 11, fontFamily: 'inherit' }}>
          <option value="">{t('All methods')}</option>
          {['Qi card','ZainCash','AsiaPay','USDT','Ovadraft','Visa/Master','Bank wire'].map(m => <option key={m}>{m}</option>)}
        </select>
        <select value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setPage(1); }}
          title={t('Filter by status')}
          style={{ flex: '0 0 auto', minWidth: 0, maxWidth: 115, padding: '6px 8px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 7, color: 'var(--text,#e0e0e0)', fontSize: 11, fontFamily: 'inherit' }}>
          <option value="">{t('All statuses')}</option>
          {['pending','processing','approved','rejected'].map(s => <option key={s}>{s}</option>)}
        </select>
        {/* Country / IB — options derived from the loaded rows (same pattern as the Clients list) */}
        <select value={filterCountry} onChange={e => { setFilterCountry(e.target.value); setPage(1); }}
          title={t('Filter by country')}
          style={{ flex: '0 0 auto', minWidth: 0, maxWidth: 120, padding: '6px 8px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 7, color: 'var(--text,#e0e0e0)', fontSize: 11, fontFamily: 'inherit' }}>
          <option value="">{t('All countries')}</option>
          {uniqueCountries.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filterIB} onChange={e => { setFilterIB(e.target.value); setPage(1); }}
          title={t('Filter by IB')}
          style={{ flex: '0 0 auto', minWidth: 0, maxWidth: 120, padding: '6px 8px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 7, color: 'var(--text,#e0e0e0)', fontSize: 11, fontFamily: 'inherit' }}>
          <option value="">{t('All IBs')}</option>
          {uniqueIBs.map(i => <option key={i} value={i}>{i}</option>)}
        </select>
        <input list="tx-agent-list" value={filterAgent} onChange={e => { setFilterAgent(e.target.value); setPage(1); }}
          placeholder={t('All sales agents')} title={t('Filter by sales agent — type to search')}
          style={{ flex: '0 0 130px', width: 130, minWidth: 0, padding: '6px 8px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 7, color: 'var(--text,#e0e0e0)', fontSize: 11, outline: 'none', fontFamily: 'inherit' }} />
        <datalist id="tx-agent-list">
          {agentList.map((a:any) => <option key={a.id} value={a.name} />)}
        </datalist>
        {canExport && (
          <button onClick={doExport} disabled={exporting}
            title={t('Export the filtered transactions to CSV')}
            style={{ flex: '0 0 auto', whiteSpace: 'nowrap', padding: '6px 12px', background: exporting ? '#2c333e' : '#00e5a0', border: '1px solid ' + (exporting ? '#626d80' : '#00e5a0'), borderRadius: 8, color: exporting ? '#888' : '#0a1a14', fontWeight: 700, fontSize: 12, cursor: exporting ? 'default' : 'pointer', fontFamily: 'inherit' }}>
            {exporting ? t('Exporting…') : '⬇ ' + t('Export')}
          </button>
        )}
      </div>

      {/* Active filters */}
      {hasFilters && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: '#555' }}>{t('Filtered by:')}</span>
          {filterMethod && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterMethod('')}>{t('Method')}: {filterMethod} ✕</span>}
          {filterStatus && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterStatus('')}>{t('Status')}: {filterStatus} ✕</span>}
          {filterClient && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterClient('')}>{t('Client')}: {filterClient} ✕</span>}
          {filterAgent  && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterAgent('')}>{t('Agent')}: {filterAgent} ✕</span>}
          {filterIB     && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterIB('')}>{t('IB')}: {filterIB} ✕</span>}
          {filterCountry && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', cursor: 'pointer' }} onClick={() => setFilterCountry('')}>{t('Country')}: {filterCountry} ✕</span>}
          <span style={{ fontSize: 11, color: '#ff4d4d', cursor: 'pointer' }} onClick={clearFilters}>{t('Clear all')}</span>
        </div>
      )}

      {/* Tabs — the ACTIVE one is accent-green with a 2px underline; the rest stay muted */}
      <div style={{ display: 'flex', gap: 4, background: 'var(--bg-input,#373f4d)', borderRadius: 10, padding: 4, marginBottom: 14 }}>
        {TABS.map(t => {
          const on = txType === t.key;
          return (
            <button key={t.key} onClick={() => { setTxType(t.key); setPage(1); }}
              style={{
                padding: '6px 16px', borderRadius: 7, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
                border: 'none', borderBottom: `2px solid ${on ? 'var(--accent,#00e5a0)' : 'transparent'}`,
                background: on ? 'var(--bg-card,#2c333e)' : 'transparent',
                color: on ? 'var(--accent,#00e5a0)' : 'var(--text2,#888)',
                fontWeight: on ? 700 : 500,
              }}>
              {t.label}{' '}
              <span style={{ fontSize: 10, fontWeight: 600, color: on ? 'var(--accent,#00e5a0)' : 'var(--text3,#667)' }}>
                {t.count.toLocaleString('en-GB')}
              </span>
            </button>
          );
        })}
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8, marginBottom: 14 }}>
        {txType === 'deposit' && <>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00e5a0' }}>{fmtUSD(dashKpis?.deposits || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Total deposited')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#ffaa00' }}>{dashKpis?.pending_w || 0}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Pending review')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00aaff' }}>{(dashKpis?.deposit_count || 0).toLocaleString('en-GB')}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Total deposits')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00e5a0' }}>{fmtUSD(dashKpis?.deposit_3d || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Last 3 days')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00e5a0' }}>{fmtUSD(dashKpis?.today_amount || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Today')}</div></div>
        </>}
        {txType === 'withdrawal' && <>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#ff4d4d' }}>{fmtUSD(dashKpis?.withdrawals || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Total withdrawn')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#ffaa00' }}>{dashKpis?.pending_w || 0}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Pending review')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00aaff' }}>{(dashKpis?.withdrawal_count || 0).toLocaleString('en-GB')}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Total withdrawals')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#ff4d4d' }}>{fmtUSD(dashKpis?.withdrawal_3d || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Last 3 days')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#ff4d4d' }}>{dashKpis?.flagged_count || 0} {t('flagged')}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Network risk ≥6/10')}</div></div>
        </>}
        {(txType === 'internal_transfer' || txType === 'bonus') && <>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00aaff' }}>{fmtUSD(kpis.total_amount || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Total amount')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00aaff' }}>{(kpis.total_count || 0).toLocaleString('en-GB')}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Total records')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#9966ff' }}>{fmtUSD(dashKpis?.bonus_3d || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Last 3 days')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#00e5a0' }}>{fmtUSD(dashKpis?.today_amount || 0)}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Today')}</div></div>
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}><div style={{ fontSize: 18, fontWeight: 600, color: '#555' }}>{(kpis.pending_count || 0).toLocaleString('en-GB')}</div><div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{t('Pending')}</div></div>
        </>}
      </div>

      {/* Table */}
      <div style={{ flex: 1, overflowX: 'auto', overflowY: 'auto', minHeight: 0 }}>
      <div style={{ background: 'transparent', overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ ...CT.table, minWidth: 1200 }}>
            <thead>
              <tr style={CT.theadTr}>
                {thSort('date',   t('Date & time'))}
                <th style={CT.th()}>{t('Client')}</th>
                <th style={CT.th()}>{t('Login')}</th>
                {thSort('amount', t('Amount'))}
                {txType === 'internal_transfer' ? (<>
                  <th style={CT.th()}>{t('From')}</th>
                  <th style={CT.th()}>{t('To')}</th>
                </>) : (<>
                  <th style={CT.th()}>{t('Card / Method')}</th>
                  <th style={CT.th()}>{t('Card name / Wallet')}</th>
                  <th style={CT.th()}>{t('Wallet ID')}</th>
                </>)}
                <th style={CT.th(false, 'center')}>{t('# Txns')}</th>
                <th style={CT.th()}>{t('Sales agent')}</th>
                <th style={CT.th()}>{t('IB')}</th>
                <th style={CT.th()}>{t('Network')}</th>
                {txType === 'withdrawal' && <th style={CT.th()}>{t('Abuse flag')}</th>}
                {txType === 'bonus' && <th style={CT.th()}>{t('Type')}</th>}
                <th style={CT.th()}>{t('Status')}</th>
                <th style={CT.th()}>{t('Action')}</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={14} style={{ textAlign: 'center', color: '#555', padding: 40 }}>{t('Loading...')}</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={14} style={{ textAlign: 'center', color: '#555', padding: 40 }}>{t('No records found')}</td></tr>
              ) : rows.map((tx, i) => {
                const isManual = !METHODS_AUTO.includes(tx.method);
                const isPending = tx.status === 'pending' || tx.status === 'processing';
                const isReq = !!tx._req;
                // ZainCash / Fastpay: the "Card name / Wallet" column shows the RECEIVER NUMBER (no card
                // name on those receipts). Qi Card: it shows the receiver's card NAME. Sender always in Wallet ID.
                const zcFp = /zc|zain|fast\s*pay|fastpay/i.test(String(tx.method || ''));
                return (
                  <tr key={i} style={{ ...CT.row(), cursor: 'default', background: isReq ? 'rgba(255,170,0,0.07)' : 'transparent' }}
                    onMouseEnter={e => (e.currentTarget.style.background = isReq ? 'rgba(255,170,0,0.12)' : 'var(--bg-card,#2c333e)')}
                    onMouseLeave={e => (e.currentTarget.style.background = isReq ? 'rgba(255,170,0,0.07)' : 'transparent')}>
                    <td style={CT.td}>
                      <div>{fmtIqDate(tx.tx_date)}</div>
                      <div style={{ fontSize: 10, color: '#555' }}>{fmtIqTime(tx.tx_date)}</div>
                    </td>
                    <td style={CT.td}>
                      <span onClick={() => { const nm = tx.client_name || String(tx.login); if (filterClient === nm) { setClientModal(tx); } else { setFilterClient(nm); setPage(1); } }}
                        title={filterClient === (tx.client_name || String(tx.login)) ? t('Open client profile') : t('Filter by this client (click again to open profile)')}
                        style={{ color: '#e0e0e0', cursor: 'pointer', fontWeight: 500 }} className="hover-underline">
                        {tx.client_name || `#${tx.login}`}
                      </span>
                    </td>
                    <td style={CT.td}>
                      <span onClick={() => setAccountModal(tx)} style={{ color: '#00aaff', cursor: 'pointer', fontFamily: 'monospace' }}>
                        {tx.login}
                      </span>
                    </td>
                    <td style={{ ...CT.td, color: txType === 'withdrawal' ? '#ff4d4d' : txType === 'bonus' ? '#ffaa00' : '#00e5a0', fontWeight: 600 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        {fmtUSD(tx.amount || 0)}
                        {tx.has_receipt && (
                          <span onClick={e => { e.stopPropagation(); setDetailsModal(tx); }}
                            title={t('View the uploaded payment receipt')}
                            style={{ cursor: 'pointer', color: '#0E9E97', display: 'inline-flex' }}>
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                          </span>
                        )}
                      </span>
                    </td>
                    {txType === 'internal_transfer' ? (<>
                      <td style={CT.td}>
                        {tx.from_account
                          ? <span onClick={() => { setSearch(String(tx.from_account)); setPage(1); }}
                              title={String(tx.from_account) === String(tx.login) ? t('This account') : t('Show this account')}
                              style={{ color: String(tx.from_account) === String(tx.login) ? '#e0e0e0' : '#00aaff', cursor: 'pointer', fontFamily: 'monospace', fontWeight: String(tx.from_account) === String(tx.login) ? 600 : 400 }}>
                              {tx.from_account}</span>
                          : <span style={{ color: '#555' }}>—</span>}
                      </td>
                      <td style={CT.td}>
                        {tx.to_account
                          ? <span onClick={() => { setSearch(String(tx.to_account)); setPage(1); }}
                              title={String(tx.to_account) === String(tx.login) ? t('This account') : t('Show this account')}
                              style={{ color: String(tx.to_account) === String(tx.login) ? '#e0e0e0' : '#00aaff', cursor: 'pointer', fontFamily: 'monospace', fontWeight: String(tx.to_account) === String(tx.login) ? 600 : 400 }}>
                              {tx.to_account}</span>
                          : <span style={{ color: '#555' }}>—</span>}
                      </td>
                    </>) : (<>
                      <td style={CT.td}>
                        <MethodBadge method={methodLabel(tx)} mtype={isManual ? 'manual' : 'auto'} onClick={() => filterBy('method', tx.method)} />
                      </td>
                      <td style={{ ...CT.td, color: '#666' }}
                          title={tx.receiver_acct ? `${t('Receiver account:')} ${tx.receiver_acct}${tx.card_name ? ` · ${tx.card_name}` : ''}` : undefined}>
                        {zcFp
                          ? (tx.receiver_acct
                              ? <span style={{ fontFamily: 'monospace', color: '#0E6E6B', fontWeight: 600 }}>{tx.receiver_acct}</span>
                              : tx.card_name
                                ? <span style={{ color: '#0E6E6B', fontWeight: 600 }}>{tx.card_name}</span>
                                : (tx.wallet_type || '—'))
                          : (tx.card_name
                              ? <span style={{ color: '#0E6E6B', fontWeight: 600 }}>{tx.card_name}</span>
                              : tx.receiver_acct
                                ? <span style={{ fontFamily: 'monospace' }}>{tx.receiver_acct}</span>
                                : (tx.wallet_type || '—'))}
                      </td>
                      <td style={{ ...CT.td, color: '#555', fontSize: 11, maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis' }}
                          title={tx.sender_acct ? `${t('Sender:')} ${tx.sender_acct}` : (tx.wallet_id || (tx.sender_block ? `${t('Qi sender block')} ${tx.sender_block} ${t('(4 digits — full account not read)')}` : ''))}>
                        {tx.sender_acct
                          ? (<span>
                              <span style={{ fontFamily: 'monospace', color: '#0E6E6B', fontWeight: 600 }}>{tx.sender_acct}</span>
                              {tx.sender_src === 'inferred' && <span title={t("Receipt shows the sender name only — account inferred from this client's previous deposit with the same sender block")} style={{ color: '#7c8db5', marginLeft: 4 }}>≈</span>}
                              {tx.wallet_confidence === 'ambiguous' && <span title={t('Multiple candidate transactions — verify')} style={{ color: '#d97706', marginLeft: 4 }}>~</span>}
                            </span>)
                          : tx.sender_block
                            ? <span style={{ fontFamily: 'monospace', color: '#888' }} title={t('Qi sender wallet id (4-digit block) — full account not yet read')}>{tx.sender_block}<span style={{ fontSize: 10 }}> ·{t('block')}</span></span>
                            : '—'}
                      </td>
                    </>)}
                    <td style={{ ...CT.td, textAlign: 'center' }} onClick={e=>e.stopPropagation()}>
                      <span
                        onMouseEnter={e=>setTxPopup({tx, x:e.clientX, y:e.clientY})}
                        onMouseLeave={()=>setTxPopup(null)}
                        style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', fontWeight: 500, cursor:'default' }}>
                        {tx.tx_count || 0}
                      </span>
                    </td>
                    <td style={CT.td}>
                      <span onClick={() => filterBy('agent', tx.agent_name)} style={{ color: '#888', cursor: tx.agent_name ? 'pointer' : 'default' }}>
                        {tx.agent_name || '—'}
                      </span>
                    </td>
                    <td style={CT.td}>
                      <span onClick={() => { if(!tx.ib_name) return; if(filterIB===tx.ib_name){ openIbProfile(tx.ib_name); } else { filterBy('ib', tx.ib_name); } }}
                        title={tx.ib_name ? (filterIB===tx.ib_name ? 'Open IB page' : 'Filter by this IB (click again to open IB page)') : ''}
                        style={{ color: '#00aaff', cursor: tx.ib_name ? 'pointer' : 'default' }}>
                        {tx.ib_name || '—'}
                      </span>
                    </td>
                    <td style={CT.td} onClick={e=>e.stopPropagation()}>
                      <NetworkBadge score={tx.network_score} login={tx.login} />
                    </td>
                    {txType === 'withdrawal' && (
                      <td style={CT.td}>
                        {tx.abuse_flag
                          ? (() => {
                              const sc: any = { critical:'#ff4d4d', high:'#ff8800', medium:'#ffaa00' };
                              const col = sc[tx.abuse_severity] || '#ff4d4d';
                              return <span onClick={()=>setAbuseTx(tx)}
                                onMouseEnter={e=>setAbuseHover({tx, x:e.clientX, y:e.clientY})}
                                onMouseLeave={()=>setAbuseHover(null)}
                                title={t('This account is in an open abuse case — hold the withdrawal and review')}
                                style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${col}22`, color: col, fontWeight: 700, cursor:'pointer', border:`1px solid ${col}66`, whiteSpace:'nowrap' }}>
                                {tx.abuse_hot ? '🔥 ' : ''}⛔ {t('HOLD')} · {tx.abuse_flag}</span>;
                            })()
                          : <span style={{ color: '#626d80' }}>—</span>}
                      </td>
                    )}
                    {txType === 'bonus' && (
                      <td style={CT.td}>
                        <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: tx.tx_type === 'bonus_deposit' ? '#3a2a0e' : '#3a0e0e', color: tx.tx_type === 'bonus_deposit' ? '#ffaa00' : '#ff4d4d', fontWeight: 500 }}>
                          {tx.tx_type === 'bonus_deposit' ? t('Bonus in') : t('Bonus out')}
                        </span>
                      </td>
                    )}
                    <td style={CT.td}><StatusBadge status={tx.status || 'approved'} /></td>
                    <td style={CT.td}>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        {isReq ? (
                          // one "Details" button for every pending/rejected request — approve/reject happens
                          // inside the popup. Yellow while pending, red once rejected.
                          (() => {
                            const isRej = (tx._req.status || '').toLowerCase() === 'rejected';
                            return <button onClick={() => setDepositCase(tx._req)}
                              title={isRej ? t('View this rejected request') : t('Review & approve/reject this request')}
                              style={{ padding: '4px 12px', background: isRej ? 'rgba(240,85,106,0.12)' : '#3a2a0e', border: `1px solid ${isRej ? '#f0556a' : '#ffaa00'}`, borderRadius: 6, color: isRej ? '#f0556a' : '#ffc04d', cursor: 'pointer', fontSize: 11, fontWeight: 700, fontFamily: 'inherit' }}>{t('Details')}</button>;
                          })()
                        ) : (<>
                          <button onClick={() => setDetailsModal(tx)} title={t('View full transaction details')}
                            style={{ padding: '4px 10px', background: '#0a1a3a', border: '1px solid #00aaff', borderRadius: 6, color: '#00aaff', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>{t('Details')}</button>
                          {isPending && !readOnly &&
                            <button onClick={() => setReviewModal(tx)} style={{ padding: '4px 10px', background: '#3a2a0e', border: '1px solid #ffaa00', borderRadius: 6, color: '#ffaa00', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>{t('Review')}</button>}
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
          <span style={{ color: '#555', fontSize: 11 }}>{t('Page')} {page} · {total.toLocaleString('en-GB')} {t('records')}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
              style={{ padding: '3px 6px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 5, color: '#888', fontSize: 11 }}>
              {[20, 50, 100, 200].map(s => <option key={s} value={s}>{s}/{t('page')}</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: page === 1 ? '#626d80' : '#888', cursor: page === 1 ? 'default' : 'pointer', fontSize: 12 }}>← {t('Prev')}</button>
            <button onClick={() => setPage(p => p + 1)} disabled={txs.length < pageSize}
              style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: txs.length < pageSize ? '#626d80' : '#00e5a0', cursor: txs.length < pageSize ? 'default' : 'pointer', fontSize: 12, borderColor: txs.length < pageSize ? '#626d80' : '#00e5a0' }}>{t('Next')} →</button>
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
        const atx = abuseHover.tx;
        const left = Math.min(abuseHover.x+10, window.innerWidth-300);
        const top  = Math.min(abuseHover.y+14, window.innerHeight-180);
        return (
          <div style={{ position:'fixed', left, top, zIndex:99999, background:'#2c333e', border:'1px solid #ff4d4d44', borderRadius:10, padding:13, width:280, boxShadow:'0 8px 32px rgba(0,0,0,0.6)', pointerEvents:'none' }}>
            <div style={{ fontSize:12, fontWeight:600, color:'#ff4d4d', marginBottom:6 }}>⚠️ {atx.abuse_flag}</div>
            <div style={{ fontSize:10, color:'#999', lineHeight:1.6 }}>
              <div><b style={{color:'#ccc'}}>{t('Why:')}</b> {t('flagged by the trading-behaviour detectors (bonus hedging, swap arbitrage, latency abuse, …) — based on how this account')} <i>{t('traded')}</i>{t(', not its network links.')}</div>
              <div style={{marginTop:5}}><b style={{color:'#ccc'}}>{t('What:')}</b> #{atx.login} · {atx.client_name} · {t('withdrawing')} ${(atx.amount||0).toLocaleString('en-GB')}.</div>
              <div style={{marginTop:6, color:'#666'}}>{t('Click for the full abuse-case detail.')}</div>
            </div>
          </div>
        );
      })()}
      {txDetail && (
        <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.7)', zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center' }} onClick={()=>setTxDetail(null)}>
          <div style={{ background:'#2c333e', border:'1px solid #626d80', borderRadius:12, padding:22, width:420 }} onClick={e=>e.stopPropagation()}>
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:16 }}>
              <div style={{ fontSize:14, fontWeight:600 }}>{t('Transaction detail')}</div>
              <div onClick={()=>setTxDetail(null)} style={{ cursor:'pointer', color:'#555' }}>✕</div>
            </div>
            {[['Client', txDetail.client_name],['Login', '#'+txDetail.login],['Type', txDetail.tx_type],['Amount', '$'+(txDetail.amount||0).toLocaleString('en-GB')],['Method', methodLabel(txDetail)],['Date', fmtIqDT(txDetail.tx_date)],['Status', txDetail.status||'—'],['Agent', txDetail.agent_name||'—'],['IB', txDetail.ib_name||'—'],['Notes', txDetail.notes||'—']].map(([k,v])=>(
              <div key={k as string} style={{ display:'flex', justifyContent:'space-between', padding:'7px 0', borderBottom:'1px solid #373f4d', fontSize:12 }}>
                <span style={{ color:'#555' }}>{t(k as string)}</span>
                <span style={{ color:'#e0e0e0', maxWidth:250, textAlign:'right' as any }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
