import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet, apiPost } from './api';

const API = '/api';

const LAYER_COLORS = ['#00e5a0', '#00aaff', '#ffaa00', '#ff4d4d', '#cc88ff'];
const LAYER_BG     = ['rgba(0,229,160,0.12)', 'rgba(0,170,255,0.12)', 'rgba(255,170,0,0.12)', 'rgba(255,77,77,0.12)', 'rgba(204,136,255,0.12)'];
const LAYER_NAMES  = ['Root', 'Layer 1', 'Layer 2', 'Layer 3'];
const EDGE_COLORS: Record<string,string> = { ip:'#00aaff', cid:'#ff4d4d', family:'#ffaa00', ib:'#cc88ff' };
const EDGE_ICONS:  Record<string,string> = { ip:'🌐', cid:'📱', family:'👨‍👩‍👧', ib:'🤝' };

// ─── KPI card ────────────────────────────────────────────────────────────────
const KPI = ({ icon, label, value, color }: any) => (
  <div style={{ background:'#2c333e', border:'1px solid #4f596b', borderRadius:10, padding:'12px 16px', display:'flex', alignItems:'center', gap:12 }}>
    <div style={{ width:40, height:40, borderRadius:8, background:color+'22', display:'flex', alignItems:'center', justifyContent:'center', fontSize:20 }}>{icon}</div>
    <div>
      <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:1 }}>{label}</div>
      <div style={{ fontSize:22, fontWeight:700, color, marginTop:2 }}>{value}</div>
    </div>
  </div>
);

// ─── Network Canvas Graph ────────────────────────────────────────────────────
function GraphCanvas({ nodes, edges, onSelect, selected }: any) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const posRef    = useRef<Record<number,{x:number,y:number}>>({});
  const animRef   = useRef<number>(0);
  const [hovered, setHovered] = useState<number|null>(null);

  const W = 700, H = 480;

  const buildLayout = useCallback(() => {
    if (!nodes?.length) return;
    const cx = W/2, cy = H/2;
    const radii = [0, 110, 200, 285, 360];
    const layerGroups: Record<number,any[]> = {};
    nodes.forEach((n:any) => { const l=n.layer||0; (layerGroups[l]=layerGroups[l]||[]).push(n); });

    Object.entries(layerGroups).forEach(([layer, ns]) => {
      const l = parseInt(layer);
      const r = radii[l] || l*100;
      ns.forEach((n:any, i:number) => {
        const angle = l===0 ? 0 : (2*Math.PI*i/ns.length) - Math.PI/2;
        posRef.current[n.login] = { x: cx + r*Math.cos(angle), y: cy + r*Math.sin(angle) };
      });
    });
  }, [nodes]);

  useEffect(() => { buildLayout(); }, [buildLayout]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !nodes?.length) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    cancelAnimationFrame(animRef.current);
    const draw = () => {
      ctx.clearRect(0,0,W,H);

      // Draw layer rings
      [0,110,200,285].forEach((r,i) => {
        if (r===0) return;
        ctx.beginPath();
        ctx.arc(W/2, H/2, r, 0, 2*Math.PI);
        ctx.strokeStyle = LAYER_COLORS[i]+'18';
        ctx.lineWidth = 1;
        ctx.setLineDash([4,8]);
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // Draw edges
      edges?.forEach((e:any) => {
        const f = posRef.current[e.from], t = posRef.current[e.to];
        if (!f||!t) return;
        const isSel = selected?.login === e.from || selected?.login === e.to;
        ctx.beginPath();
        ctx.moveTo(f.x, f.y);
        ctx.lineTo(t.x, t.y);
        ctx.strokeStyle = EDGE_COLORS[e.type] || '#626d80';
        ctx.lineWidth = isSel ? 2.5 : e.type==='cid' ? 1.8 : 1;
        ctx.globalAlpha = isSel ? 0.9 : e.type==='cid' ? 0.5 : 0.2;
        ctx.stroke();
        ctx.globalAlpha = 1;
      });

      // Draw nodes
      nodes.forEach((n:any) => {
        const pos = posRef.current[n.login];
        if (!pos) return;
        const color = LAYER_COLORS[n.layer] || '#888';
        const isSel = selected?.login === n.login;
        const isHov = hovered === n.login;
        const r = n.layer===0 ? 20 : isHov||isSel ? 14 : 10;

        // Glow for selected
        if (isSel) {
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, r+6, 0, 2*Math.PI);
          ctx.fillStyle = color+'30';
          ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(pos.x, pos.y, r, 0, 2*Math.PI);
        ctx.fillStyle = LAYER_BG[n.layer] || '#1a1d2420';
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.lineWidth = isSel ? 3 : n.layer===0 ? 2.5 : 1.5;
        ctx.stroke();

        // Node label
        ctx.fillStyle = n.layer===0 ? color : '#aaa';
        ctx.font = n.layer===0 ? 'bold 8px sans-serif' : '7px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(n.label || `#${n.login}`, pos.x, pos.y + r + 10);
        if (isHov || isSel) {
          const nm = n.name?.split(' ').slice(0,2).join(' ') || '';
          ctx.fillStyle = '#fff';
          ctx.font = '8px sans-serif';
          ctx.fillText(nm, pos.x, pos.y - r - 4);
        }
      });
    };
    draw();
  }, [nodes, edges, selected, hovered]);

  const getNodeAt = (mx:number, my:number) => {
    for (const n of (nodes||[])) {
      const pos = posRef.current[n.login];
      if (!pos) continue;
      const r = n.layer===0 ? 20 : 12;
      if (Math.hypot(mx-pos.x, my-pos.y) < r+4) return n;
    }
    return null;
  };

  const handleMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const sx = W / rect.width, sy = H / rect.height;
    const n = getNodeAt((e.clientX-rect.left)*sx, (e.clientY-rect.top)*sy);
    setHovered(n?.login || null);
  };

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const sx = W / rect.width, sy = H / rect.height;
    const n = getNodeAt((e.clientX-rect.left)*sx, (e.clientY-rect.top)*sy);
    onSelect && onSelect(n || null);
  };

  return (
    <canvas ref={canvasRef} width={W} height={H}
      onMouseMove={handleMove} onMouseLeave={() => setHovered(null)} onClick={handleClick}
      style={{ width:'100%', cursor:hovered?'pointer':'crosshair', borderRadius:12, background:'#080a0f', border:'1px solid #373f4d', display:'block' }} />
  );
}

// ─── Account pill ────────────────────────────────────────────────────────────
function AccountPill({ node, isSelected, onClick }: any) {
  const color = LAYER_COLORS[node.layer] || '#888';
  return (
    <div onClick={onClick}
      style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 10px', borderRadius:8, background:isSelected?LAYER_BG[node.layer]:'transparent', cursor:'pointer', borderLeft:`3px solid ${color}`, marginBottom:3, transition:'background .15s' }}>
      <div style={{ width:26, height:26, borderRadius:6, background:color+'22', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
        <span style={{ fontSize:8, color, fontFamily:'monospace', fontWeight:700 }}>{node.layer===0?'ROOT':`L${node.layer}`}</span>
      </div>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontSize:12, fontWeight:500, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', color:'#e0e0e0' }}>{node.name || `#${node.login}`}</div>
        <div style={{ fontSize:10, color:'#555', display:'flex', gap:6 }}>
          <span>#{node.login}</span>
          {node.country && <span>{node.country}</span>}
          {node.ib && <span style={{ color:'#cc88ff' }}>IB</span>}
          {node.connect_via && <span style={{ color:EDGE_COLORS[node.type]||'#555' }}>{EDGE_ICONS[node.type]||''} {node.type?.toUpperCase()}</span>}
        </div>
      </div>
      <div style={{ fontSize:11, color:'#00e5a0', fontWeight:600, flexShrink:0 }}>${(node.balance||0).toLocaleString()}</div>
    </div>
  );
}

// ─── Cluster card ─────────────────────────────────────────────────────────────
function ClusterCard({ cluster, type }: any) {
  const [open, setOpen] = useState(false);
  const key = type==='cid' ? cluster.cid : cluster.ip;
  const count = cluster.account_count;
  const color = count>=10?'#ff4d4d':count>=5?'#ffaa00':'#00aaff';

  return (
    <div style={{ background:'#2c333e', border:`1px solid ${open?color:'#373f4d'}`, borderRadius:10, marginBottom:6, overflow:'hidden', transition:'border-color .2s' }}>
      <div onClick={() => setOpen(!open)} style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 14px', cursor:'pointer' }}>
        <div style={{ width:34, height:34, borderRadius:8, background:color+'22', display:'flex', alignItems:'center', justifyContent:'center', fontSize:16, flexShrink:0 }}>
          {type==='cid' ? '📱' : '🌐'}
        </div>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:11, fontFamily:'monospace', color:'#888', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{key}</div>
          <div style={{ fontSize:10, color:'#444', marginTop:2 }}>{type==='cid'?'Device ID':'IP Address'}</div>
        </div>
        <span style={{ fontSize:12, fontWeight:700, color, padding:'3px 10px', borderRadius:99, background:color+'18', flexShrink:0 }}>{count} accts</span>
        <span style={{ color:'#444', fontSize:11 }}>{open?'▲':'▼'}</span>
      </div>
      {open && (
        <div style={{ borderTop:'1px solid #373f4d', padding:'8px 14px' }}>
          {/* visual graph of this cluster: shared key in the centre, accounts around it */}
          {cluster.accounts?.length > 0 && (() => {
            const hub = { login: -1, name: key, layer: 0, label: type === 'cid' ? 'DEVICE' : 'IP' };
            const nodes = [hub, ...cluster.accounts.map((a:any) => ({ login: a.login, name: a.name, country: a.country, balance: a.balance, layer: 1 }))];
            const edges = cluster.accounts.map((a:any) => ({ from: -1, to: a.login, type }));
            return (
              <div style={{ marginBottom: 10 }}>
                <GraphCanvas nodes={nodes} edges={edges} />
                <div style={{ fontSize: 10, color: '#555', textAlign: 'center', marginTop: 4 }}>
                  Centre = shared {type === 'cid' ? 'device' : 'IP'} · {count} linked account{count === 1 ? '' : 's'}
                </div>
              </div>
            );
          })()}
          {/* Ring summary — the back-office "why" at a glance */}
          {cluster.totals && (() => {
            const t = cluster.totals;
            const money = (n:number) => '$' + Math.round(n||0).toLocaleString();
            const netBad = (t.net_to_clients||0) > 0 && (t.bonus||0) > 0;   // extracted more than deposited, on bonus
            return (
              <div style={{ background:'#20252f', border:`1px solid ${netBad?'#ff4d4d55':'#373f4d'}`, borderRadius:8, padding:'8px 10px', marginBottom:10 }}>
                <div style={{ display:'flex', flexWrap:'wrap', gap:14 }}>
                  {[['Deposits', money(t.deposits), '#00aaff'],
                    ['Withdrawals', money(t.withdrawals), '#ff8888'],
                    ['Bonus given', money(t.bonus), '#cc88ff'],
                    ['Net to clients', (t.net_to_clients>0?'+':'')+money(t.net_to_clients), t.net_to_clients>0?'#ff4d4d':'#00e5a0'],
                    ['Trading P&L', (t.pnl>0?'+':'')+money(t.pnl), t.pnl>=0?'#00e5a0':'#ff8888']].map(([l,v,c]:any) => (
                    <div key={l}><div style={{ fontSize:9, color:'#667', textTransform:'uppercase' }}>{l}</div>
                      <div style={{ fontSize:14, fontWeight:800, color:c }}>{v}</div></div>
                  ))}
                </div>
                {(t.ib_names||[]).length > 0 && (
                  <div style={{ fontSize:10.5, color:'#8a93a3', marginTop:6 }}>IB: <b style={{ color:'#ffd479' }}>{(t.ib_names||[]).join(', ')}</b></div>
                )}
                {netBad && <div style={{ fontSize:10.5, color:'#ff7a7a', marginTop:4 }}>⚠ Clients withdrew more than they deposited while holding bonus — possible bonus extraction.</div>}
              </div>
            );
          })()}

          {/* per-account detail table */}
          <div style={{ display:'grid', gridTemplateColumns:'1.6fr 1fr 1.2fr 0.85fr 0.85fr 0.85fr 0.95fr 0.95fr', gap:6, fontSize:9.5, color:'#667', textTransform:'uppercase', padding:'2px 0 4px', borderBottom:'1px solid #373f4d' }}>
            <span>Account</span><span>City</span><span>IB</span><span style={{textAlign:'right'}}>Dep</span><span style={{textAlign:'right'}}>W/D</span><span style={{textAlign:'right'}}>Bonus</span><span style={{textAlign:'right'}}>P&L</span><span style={{textAlign:'right'}}>Last dep</span>
          </div>
          {cluster.accounts.map((a:any,i:number) => {
            const money = (n:number) => '$' + Math.round(n||0).toLocaleString();
            const lastDep = a.last_deposit ? new Date(a.last_deposit.replace(' ','T')).toLocaleDateString() : '—';
            return (
              <div key={i} style={{ display:'grid', gridTemplateColumns:'1.6fr 1fr 1.2fr 0.85fr 0.85fr 0.85fr 0.95fr 0.95fr', gap:6, alignItems:'center', padding:'6px 0', borderBottom:i<cluster.accounts.length-1?'1px solid #2c333e':'none', fontSize:11 }}>
                <span style={{ minWidth:0, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                  <span style={{ fontFamily:'monospace', color:'#00aaff' }}>#{a.login}</span> <span style={{ color:'#ccc' }}>{a.name}</span>
                  {a.win_rate != null && <span style={{ color:a.win_rate>=85?'#ffaa00':'#667', marginLeft:4 }}>· {a.win_rate}% win</span>}
                </span>
                <span style={{ color:'#8a93a3', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }} title={a.country}>{a.city || a.country || '—'}</span>
                <span style={{ color:a.ib_name?'#ffd479':'#556', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }} title={a.ib_name}>{a.ib_name || '—'}</span>
                <span style={{ textAlign:'right', color:'#00aaff' }}>{money(a.deposits)}</span>
                <span style={{ textAlign:'right', color:'#ff8888' }}>{money(a.withdrawals)}</span>
                <span style={{ textAlign:'right', color:a.bonus>0?'#cc88ff':'#556' }}>{money(a.bonus)}</span>
                <span style={{ textAlign:'right', color:a.pnl>=0?'#00e5a0':'#ff8888', fontWeight:600 }}>{a.pnl>0?'+':''}{money(a.pnl)}</span>
                <span style={{ textAlign:'right', color:'#8a93a3' }}>{lastDep}</span>
              </div>
            );
          })}
          {count > 10 && <div style={{ fontSize:11, color:'#555', textAlign:'center', marginTop:6 }}>+{count-10} more (showing first 10)</div>}
        </div>
      )}
    </div>
  );
}

// ─── Connection-group card (the "Connections" tab) ─────────────────────────────
const SEVC: any = { critical:'#ff4d4d', high:'#ffaa00', medium:'#ffd400', low:'#00aaff' };
const VERDICT_ICON: any = { ib_farming:'🤝', bonus_abuse:'🎁', toxic:'☢️', swap_free:'💱', offsetting:'🔄', linked:'🔗' };
const REASON_ICON: any = { cid:'📱', mqid:'📱', email:'✉️', similar_email:'📧', phone:'📞', family:'👪', ip:'🌐', payment:'💳', ib:'🤝', city:'📍', name:'👤' };
const LINK_LABEL: any = { cid:'Device (CID)', mqid:'Device (MQID)', ip:'IP address', email:'Email', similar_email:'Similar email', phone:'Phone', name:'Same name', family:'Family', city:'City', payment:'Payment', ib:'Same IB' };
const m0 = (n:number) => '$' + Math.round(n||0).toLocaleString();

function ConnGroupCard({ g }: any) {
  const [open, setOpen] = useState(false);
  const [ai, setAi] = useState<any>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const c = SEVC[g.severity] || '#00aaff';
  const T = g.totals || {};
  const v0 = g.verdicts?.[0];

  const askClaude = async () => {
    setAiBusy(true);
    try {
      const r = await apiPost('/network/connection-groups/analyze', { logins: g.members.map((m:any)=>m.login) });
      setAi(r);
    } catch { setAi({ narrative: 'Could not reach the analyzer.' }); }
    setAiBusy(false);
  };

  return (
    <div style={{ background:'#262c36', border:`1px solid ${open?c:'#373f4d'}`, borderLeft:`3px solid ${c}`, borderRadius:10, marginBottom:8, overflow:'hidden' }}>
      <div onClick={()=>setOpen(!open)} style={{ display:'flex', alignItems:'center', gap:12, padding:'11px 14px', cursor:'pointer' }}>
        <div style={{ width:34, height:34, borderRadius:8, background:c+'22', display:'flex', alignItems:'center', justifyContent:'center', fontSize:17, flexShrink:0 }}>{VERDICT_ICON[v0?.tag]||'🔗'}</div>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:13, fontWeight:700, color:'#e6e9ef', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{g.top_verdict}</div>
          <div style={{ display:'flex', alignItems:'center', gap:6, marginTop:3, flexWrap:'wrap' }}>
            <span style={{ fontSize:10, color:'#8a93a3' }}>{g.size} accounts</span>
            {(g.link_reasons||[]).map((r:string)=>(
              <span key={r} style={{ fontSize:10, color:'#8a93a3' }} title={r}>{REASON_ICON[r]||'·'} {r}</span>
            ))}
            {g.dominant_ib && <span style={{ fontSize:10, color:'#ffd479' }}>🤝 {g.dominant_ib}</span>}
          </div>
        </div>
        <div style={{ textAlign:'right', flexShrink:0 }}>
          <div style={{ fontSize:9, color:'#667', textTransform:'uppercase' }}>Bonus / Net out</div>
          <div style={{ fontSize:13, fontWeight:800, color:'#cc88ff' }}>{m0(T.bonus)} <span style={{ color: (T.net_to_clients>0)?'#ff4d4d':'#00e5a0' }}>/ {(T.net_to_clients>0?'+':'')}{m0(T.net_to_clients)}</span></div>
        </div>
        <span style={{ fontSize:10, fontWeight:800, padding:'2px 9px', borderRadius:99, background:c+'18', color:c, flexShrink:0 }}>{String(g.severity).toUpperCase()}</span>
        <span style={{ color:'#444', fontSize:11 }}>{open?'▲':'▼'}</span>
      </div>

      {open && (
        <div style={{ borderTop:'1px solid #373f4d', padding:'10px 14px' }}>
          {/* ring totals */}
          <div style={{ display:'flex', flexWrap:'wrap', gap:14, marginBottom:10 }}>
            {[['Deposits',m0(T.deposits),'#00aaff'],['Withdrawals',m0(T.withdrawals),'#ff8888'],['Bonus',m0(T.bonus),'#cc88ff'],
              ['Net to clients',(T.net_to_clients>0?'+':'')+m0(T.net_to_clients),T.net_to_clients>0?'#ff4d4d':'#00e5a0'],
              ['IB commission',m0(T.ib_commission),'#ffd479'],['Trading P&L',(T.pnl>0?'+':'')+m0(T.pnl),T.pnl>=0?'#00e5a0':'#ff8888']].map(([l,v,col]:any)=>(
              <div key={l}><div style={{ fontSize:9, color:'#667', textTransform:'uppercase' }}>{l}</div>
                <div style={{ fontSize:14, fontWeight:800, color:col }}>{v}</div></div>
            ))}
          </div>

          {/* CONNECTIONS — how these accounts are linked (shown FIRST, before the abuse verdict) */}
          {(g.links && g.links.length>0) ? (
            <div style={{ marginBottom:12 }}>
              <div style={{ fontSize:10, color:'#8a93a3', textTransform:'uppercase', letterSpacing:0.5, marginBottom:6 }}>🔗 How these accounts are connected</div>
              {g.links.map((lk:any,li:number)=>(
                <div key={li} style={{ display:'flex', alignItems:'flex-start', gap:8, padding:'5px 0', fontSize:11.5, borderBottom: li<g.links.length-1?'1px solid #2c333e':'none' }}>
                  <span style={{ width:16, textAlign:'center', flexShrink:0 }}>{REASON_ICON[lk.type]||'🔗'}</span>
                  <span style={{ color:'#9aa3b2', width:96, flexShrink:0 }}>{LINK_LABEL[lk.type]||lk.type}</span>
                  <span style={{ color:'#e6e9ef', fontFamily:'monospace', flexShrink:0, maxWidth:170, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }} title={lk.value}>{lk.value}</span>
                  <span style={{ color:'#667', flexShrink:0 }}>→ shared by</span>
                  <span style={{ display:'flex', gap:3, flexWrap:'wrap', flex:1 }}>
                    {(lk.logins||[]).map((lg:number)=>(<span key={lg} style={{ fontFamily:'monospace', fontSize:10, color:'#00aaff', background:'#0a1a2a', borderRadius:4, padding:'1px 5px' }}>#{lg}</span>))}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize:11, color:'#667', marginBottom:10 }}>Linked via {(g.link_reasons||[]).join(', ')||'shared identifiers'} (per-value detail unavailable).</div>
          )}

          {/* abuse verdicts — the DOUBT, shown after the connections */}
          {((g.verdicts||[]).length>0) && <div style={{ fontSize:10, color:'#8a93a3', textTransform:'uppercase', letterSpacing:0.5, marginBottom:6 }}>⚠ Any doubt of abuse</div>}
          {(g.verdicts||[]).map((v:any,i:number)=>(
            <div key={i} style={{ display:'flex', gap:8, padding:'7px 10px', background:'#20252f', border:`1px solid ${SEVC[v.severity]||'#373f4d'}44`, borderRadius:8, marginBottom:6 }}>
              <span style={{ fontSize:15 }}>{VERDICT_ICON[v.tag]||'•'}</span>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:12, fontWeight:700, color:SEVC[v.severity]||'#ccc' }}>{v.title}</div>
                <div style={{ fontSize:11, color:'#bcc3cf', lineHeight:1.5, marginTop:2 }}>{v.detail}</div>
              </div>
            </div>
          ))}

          {/* Claude deep-dive */}
          <div style={{ margin:'8px 0' }}>
            {!ai ? (
              <button onClick={askClaude} disabled={aiBusy} style={{ padding:'7px 14px', borderRadius:8, border:'1px solid #8a5cf6', background:'rgba(138,92,246,0.12)', color:'#b794ff', fontSize:12, fontWeight:700, cursor:'pointer', fontFamily:'inherit' }}>
                {aiBusy ? '🧠 Claude analysing…' : '🧠 Ask Claude 4.8 to investigate'}
              </button>
            ) : (
              <div style={{ background:'rgba(138,92,246,0.08)', border:'1px solid rgba(138,92,246,0.35)', borderRadius:8, padding:'10px 12px' }}>
                <div style={{ fontSize:10, color:'#b794ff', fontWeight:700, marginBottom:4 }}>🧠 Claude {ai.model||'4.8'} {ai.ai===false?'(rule-based fallback)':''}</div>
                <div style={{ fontSize:12, color:'#dfe3ea', lineHeight:1.6, whiteSpace:'pre-wrap' }}>{ai.narrative}</div>
              </div>
            )}
          </div>

          {/* member table */}
          <div style={{ display:'grid', gridTemplateColumns:'1.5fr 0.9fr 1.1fr 0.8fr 0.8fr 0.8fr 0.9fr 0.7fr', gap:6, fontSize:9.5, color:'#667', textTransform:'uppercase', padding:'4px 0', borderBottom:'1px solid #373f4d' }}>
            <span>Account</span><span>City</span><span>IB</span><span style={{textAlign:'right'}}>Dep</span><span style={{textAlign:'right'}}>W/D</span><span style={{textAlign:'right'}}>Bonus</span><span style={{textAlign:'right'}}>P&L</span><span style={{textAlign:'right'}}>Win</span>
          </div>
          {(g.members||[]).map((mm:any,i:number)=>(
            <div key={i} style={{ display:'grid', gridTemplateColumns:'1.5fr 0.9fr 1.1fr 0.8fr 0.8fr 0.8fr 0.9fr 0.7fr', gap:6, alignItems:'center', padding:'6px 0', borderBottom:i<g.members.length-1?'1px solid #2c333e':'none', fontSize:11 }}>
              <span style={{ minWidth:0, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                <span style={{ fontFamily:'monospace', color:'#00aaff' }}>#{mm.login}</span> <span style={{ color:'#ccc' }}>{(mm.name||'').split(/\s+/).slice(0,2).join(' ')}</span>
                {mm.is_islamic && <span style={{ color:'#9b8cff', marginLeft:4 }} title="Swap-free / Islamic">IS</span>}
              </span>
              <span style={{ color:'#8a93a3', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{mm.city||'—'}</span>
              <span style={{ color:mm.ib_name?'#ffd479':'#556', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }} title={mm.ib_name}>{mm.ib_name||'—'}</span>
              <span style={{ textAlign:'right', color:'#00aaff' }}>{m0(mm.deposits)}</span>
              <span style={{ textAlign:'right', color:'#ff8888' }}>{m0(mm.withdrawals)}</span>
              <span style={{ textAlign:'right', color:mm.bonus>0?'#cc88ff':'#556' }}>{m0(mm.bonus)}</span>
              <span style={{ textAlign:'right', color:mm.pnl>=0?'#00e5a0':'#ff8888', fontWeight:600 }}>{mm.pnl>0?'+':''}{m0(mm.pnl)}</span>
              <span style={{ textAlign:'right', color:(mm.win_rate>=85)?'#ffaa00':'#8a93a3' }}>{mm.win_rate!=null?mm.win_rate+'%':'—'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function NetworkPage() {
  const [tab, setTab]                 = useState<'connections'|'ip'|'cid'|'search'>('connections');
  const [groups, setGroups]           = useState<any[]>([]);
  const [linkFilter, setLinkFilter]   = useState<string>('all');
  const [loadingG, setLoadingG]       = useState(false);
  const [stats, setStats]             = useState<any>(null);
  const [clusters, setClusters]       = useState<any[]>([]);
  const [total, setTotal]             = useState(0);
  const [page, setPage]               = useState(1);
  const [search, setSearch]           = useState('');
  const [minAcc, setMinAcc]           = useState(2);
  const [loadingC, setLoadingC]       = useState(false);
  const [loginInput, setLoginInput]   = useState('');
  const [layers, setLayers]           = useState(3);
  const [traversal, setTraversal]     = useState<any>(null);
  const [traversalLoading, setTL]     = useState(false);
  const [selected, setSelected]       = useState<any>(null);
  const [filterLayer, setFilterLayer] = useState<number|null>(null);

  useEffect(() => { apiGet('/network/stats').then(setStats).catch(()=>{}); }, []);

  // Deep-link: another page (e.g. Transactions network popup) asked us to focus an account
  useEffect(() => {
    const h = (e: any) => {
      const lg = String(e.detail?.login || '').trim();
      if (!lg) return;
      setTab('search'); setLoginInput(lg);
      setTL(true); setTraversal(null); setSelected(null);
      apiGet(`/network/traverse/${lg}?layers=3`).then(setTraversal).catch(()=>{}).finally(()=>setTL(false));
    };
    window.addEventListener('network_focus', h);
    return () => window.removeEventListener('network_focus', h);
  }, []);

  const loadClusters = useCallback(async () => {
    if (tab==='search') return;
    setLoadingC(true);
    try {
      const p = new URLSearchParams({ page:String(page), page_size:'20', search, min_accounts:String(minAcc) });
      const data = await apiGet(tab==='cid' ? `/network/cid-clusters?${p}` : `/network/ip-clusters?${p}`);
      setClusters(data.clusters||[]); setTotal(data.total||0);
    } catch(e) { console.error(e); }
    setLoadingC(false);
  }, [tab,page,search,minAcc]);

  useEffect(() => { loadClusters(); }, [loadClusters]);

  // Connections tab — linked-account groups with verdicts
  useEffect(() => {
    if (tab!=='connections') return;
    setLoadingG(true);
    apiGet('/network/connection-groups?limit=60').then(d=>setGroups(d.groups||[])).catch(()=>{}).finally(()=>setLoadingG(false));
  }, [tab]);

  const runTraversal = async () => {
    if (!loginInput.trim()) return;
    setTL(true); setTraversal(null); setSelected(null);
    try {
      const data = await apiGet(`/network/traverse/${loginInput.trim()}?layers=${layers}`);
      setTraversal(data);
    } catch(e) { alert('Account not found'); }
    setTL(false);
  };

  const layerGroups: Record<number,any[]> = {};
  traversal?.nodes?.forEach((n:any) => { const l=n.layer||0; (layerGroups[l]=layerGroups[l]||[]).push(n); });

  const displayedNodes = traversal?.nodes?.filter((n:any) => filterLayer===null || n.layer===filterLayer) || [];

  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', overflow:'hidden', minHeight:0, background:'#20252f' }}>

      {/* KPIs */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:8, padding:'10px 14px', borderBottom:'1px solid #373f4d', flexShrink:0 }}>
        <KPI icon="🕸️" label="Total edges"      value={(stats?.total_edges||0).toLocaleString()}      color="#00aaff" />
        <KPI icon="🌐" label="IP clusters"       value={(stats?.ip_clusters||0).toLocaleString()}      color="#ffaa00" />
        <KPI icon="📱" label="Device clusters"   value={(stats?.cid_clusters||0).toLocaleString()}     color="#ff4d4d" />
        <KPI icon="⚠️" label="CID-linked accts"  value={(stats?.flagged_accounts||0).toLocaleString()} color="#ff4d4d" />
      </div>

      {/* Tab bar */}
      <div style={{ display:'flex', alignItems:'center', gap:6, padding:'8px 14px', borderBottom:'1px solid #373f4d', flexShrink:0, background:'#262c36' }}>
        {[['connections','🎯  Connections'],['ip','🌐  IP Clusters'],['cid','📱  Device Clusters'],['search','🔍  Account Network']].map(([k,l])=>(
          <button key={k} onClick={()=>{ setTab(k as any); setPage(1); setSearch(''); }}
            style={{ padding:'5px 14px', borderRadius:7, border:`1px solid ${tab===k?'#00e5a0':'#626d80'}`, background:tab===k?'rgba(0,229,160,0.08)':'transparent', color:tab===k?'#00e5a0':'#555', cursor:'pointer', fontSize:12, fontFamily:'inherit', fontWeight:tab===k?700:400 }}>
            {l}
          </button>
        ))}
        {(tab==='ip'||tab==='cid') && <>
          <input value={search} onChange={e=>{ setSearch(e.target.value); setPage(1); }}
            placeholder={tab==='ip'?'Search IP address...':'Search device ID...'}
            style={{ padding:'5px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:11, width:200, outline:'none', marginLeft:8 }} />
          {tab==='ip' && (
            <select value={minAcc} onChange={e=>{ setMinAcc(Number(e.target.value)); setPage(1); }}
              style={{ padding:'5px 8px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#888', fontSize:11 }}>
              {[2,3,5,10].map(n=><option key={n} value={n}>{n}+ accounts</option>)}
            </select>
          )}
          <span style={{ marginLeft:'auto', fontSize:11, color:'#444' }}>{total.toLocaleString()} clusters</span>
        </>}
      </div>

      {/* Content */}
      <div style={{ flex:1, overflow:'hidden', display:'flex', minHeight:0 }}>

        {/* ── Connections (grouped + verdicts) ── */}
        {tab==='connections' && (() => {
          // filter chips by link type — CID first, as requested. A group matches a filter if any of
          // its link types fall in that bucket (cid+mqid → Device; family+phone → Family; email+similar_email → Email).
          const BUCKET: any = { cid:['cid','mqid'], ib:['ib'], city:['city'], family:['family','phone'], email:['email','similar_email'], ip:['ip'], payment:['payment'] };
          const CHIPS = [['all','All'],['cid','📱 Device (CID)'],['ib','🤝 IB'],['city','📍 City'],['family','👪 Family'],['email','📧 Email'],['ip','🌐 IP'],['payment','💳 Payment']];
          const shown = linkFilter==='all' ? groups
            : groups.filter(g => (g.link_reasons||[]).some((r:string)=> (BUCKET[linkFilter]||[]).includes(r)));
          return (
          <div style={{ flex:1, overflowY:'auto', padding:'10px 14px' }}>
            <div style={{ fontSize:11, color:'#8a93a3', marginBottom:8, lineHeight:1.5 }}>
              Rings of <b style={{color:'#ccc'}}>different clients/leads</b> linked by <b style={{color:'#ccc'}}>device(CID) · IB · city · family · email · IP · payment</b> — a single trader's own accounts are excluded. Ordered device-first. Click a group → it shows exactly what links them, then any abuse doubt.
            </div>
            <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:10 }}>
              {CHIPS.map(([k,l]:any)=>(
                <button key={k} onClick={()=>setLinkFilter(k)}
                  style={{ padding:'4px 11px', borderRadius:99, border:`1px solid ${linkFilter===k?'#00e5a0':'#3a4250'}`, background:linkFilter===k?'rgba(0,229,160,0.10)':'transparent', color:linkFilter===k?'#00e5a0':'#8a93a3', cursor:'pointer', fontSize:11, fontFamily:'inherit', fontWeight:linkFilter===k?700:400 }}>
                  {l}{k!=='all' && <span style={{ marginLeft:5, color:'#556' }}>{groups.filter(g=>(g.link_reasons||[]).some((r:string)=>(BUCKET[k]||[]).includes(r))).length}</span>}
                </button>
              ))}
            </div>
            {loadingG
              ? <div style={{ textAlign:'center', color:'#444', padding:40 }}>Analysing connections…</div>
              : shown.length===0
                ? <div style={{ textAlign:'center', color:'#444', padding:40 }}>No connection groups for this filter</div>
                : shown.map((g,i)=><ConnGroupCard key={i} g={g} />)
            }
          </div>
          );
        })()}

        {/* ── Cluster list ── */}
        {(tab==='ip'||tab==='cid') && (
          <div style={{ flex:1, overflowY:'auto', padding:'10px 14px' }}>
            {loadingC
              ? <div style={{ textAlign:'center', color:'#444', padding:40 }}>Loading...</div>
              : clusters.length===0
                ? <div style={{ textAlign:'center', color:'#444', padding:40 }}>No clusters found</div>
                : clusters.map((c,i)=><ClusterCard key={i} cluster={c} type={tab} />)
            }
            {total>20 && (
              <div style={{ display:'flex', justifyContent:'center', gap:8, marginTop:12, paddingBottom:16 }}>
                <button onClick={()=>setPage(p=>Math.max(1,p-1))} disabled={page===1}
                  style={{ padding:'5px 14px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:page===1?'#626d80':'#888', cursor:page===1?'default':'pointer', fontSize:12 }}>← Prev</button>
                <span style={{ padding:'5px 10px', color:'#444', fontSize:12 }}>Page {page} · {total.toLocaleString()}</span>
                <button onClick={()=>setPage(p=>p+1)} disabled={clusters.length<20}
                  style={{ padding:'5px 14px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:clusters.length<20?'#626d80':'#00e5a0', cursor:clusters.length<20?'default':'pointer', fontSize:12, borderColor:clusters.length<20?'#626d80':'#00e5a0' }}>Next →</button>
              </div>
            )}
          </div>
        )}

        {/* ── Account Network Search ── */}
        {tab==='search' && (
          <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>

            {/* Search bar */}
            <div style={{ padding:'10px 14px', borderBottom:'1px solid #373f4d', display:'flex', gap:8, alignItems:'center', flexShrink:0, background:'#262c36' }}>
              <input value={loginInput} onChange={e=>setLoginInput(e.target.value)}
                onKeyDown={e=>e.key==='Enter'&&runTraversal()}
                placeholder="Enter account login (e.g. 537715)..."
                style={{ flex:1, padding:'8px 14px', background:'#2c333e', border:'1px solid #626d80', borderRadius:8, color:'#e0e0e0', fontSize:13, outline:'none' }} />
              <select value={layers} onChange={e=>setLayers(Number(e.target.value))}
                style={{ padding:'8px 10px', background:'#2c333e', border:'1px solid #626d80', borderRadius:8, color:'#888', fontSize:12 }}>
                <option value={1}>1 layer</option>
                <option value={2}>2 layers</option>
                <option value={3}>3 layers</option>
              </select>
              <button onClick={runTraversal} disabled={traversalLoading||!loginInput.trim()}
                style={{ padding:'8px 20px', background:loginInput.trim()?'#00e5a0':'#373f4d', border:'none', borderRadius:8, color:loginInput.trim()?'#000':'#555', fontWeight:700, cursor:loginInput.trim()?'pointer':'default', fontSize:13, fontFamily:'inherit' }}>
                {traversalLoading ? '⏳ Searching...' : '🔍 Search'}
              </button>
            </div>

            {/* Empty state */}
            {!traversal && !traversalLoading && (
              <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', flexDirection:'column', gap:14 }}>
                <div style={{ fontSize:64 }}>🕸️</div>
                <div style={{ fontSize:16, color:'#555', fontWeight:500 }}>Network traversal</div>
                <div style={{ fontSize:12, color:'#626d80', textAlign:'center', maxWidth:380, lineHeight:1.8 }}>
                  Enter any account login to map its full network.<br/>
                  Shows IP sharing, device (CID) sharing, family, and IB connections — up to 3 layers deep.
                </div>
                <div style={{ display:'flex', gap:10, marginTop:8 }}>
                  {[['🌐','IP shared','#00aaff'],['📱','Same device','#ff4d4d'],['👨‍👩‍👧','Family','#ffaa00'],['🤝','Same IB','#cc88ff']].map(([icon,label,color])=>(
                    <div key={label} style={{ display:'flex', alignItems:'center', gap:6, padding:'5px 12px', borderRadius:99, background:(color as string)+'18', border:`1px solid ${color}33` }}>
                      <span style={{ fontSize:13 }}>{icon}</span>
                      <span style={{ fontSize:11, color: color as string }}>{label}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Results */}
            {traversal && !traversalLoading && (
              <div style={{ flex:1, display:'flex', flexDirection:'column', overflowY:'auto', overflowX:'hidden' }}>

                {/* Stats + layer filter bar */}
                <div style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 14px', borderBottom:'1px solid #373f4d', flexShrink:0, background:'#262c36', flexWrap:'wrap' }}>
                  <span style={{ fontSize:11, color:'#555' }}>
                    {traversal.stats?.total_accounts || 0} accounts · {traversal.stats?.total_edges || 0} connections
                  </span>
                  <button onClick={()=>setFilterLayer(null)}
                    style={{ padding:'3px 10px', borderRadius:6, border:`1px solid ${filterLayer===null?'#00e5a0':'#626d80'}`, background:filterLayer===null?'rgba(0,229,160,0.08)':'transparent', color:filterLayer===null?'#00e5a0':'#555', cursor:'pointer', fontSize:10, fontFamily:'inherit' }}>
                    All
                  </button>
                  {Object.entries(layerGroups).map(([l,ns]:any)=>(
                    <button key={l} onClick={()=>setFilterLayer(filterLayer===parseInt(l)?null:parseInt(l))}
                      style={{ padding:'3px 8px', borderRadius:6, border:`1px solid ${filterLayer===parseInt(l)?LAYER_COLORS[parseInt(l)]:'#626d80'}`, background:filterLayer===parseInt(l)?LAYER_BG[parseInt(l)]:'transparent', color:filterLayer===parseInt(l)?LAYER_COLORS[parseInt(l)]:'#555', cursor:'pointer', fontSize:10, fontFamily:'inherit' }}>
                      {LAYER_NAMES[parseInt(l)]}: {ns.length}
                    </button>
                  ))}
                  <div style={{ marginLeft:'auto', display:'flex', gap:8 }}>
                    {Object.entries(EDGE_COLORS).map(([k,v])=>(
                      <div key={k} style={{ display:'flex', alignItems:'center', gap:4, fontSize:10, color:'#555' }}>
                        <div style={{ width:16, height:2, background:v as string, opacity:0.7 }} />
                        {k.toUpperCase()}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Main content: 1/3 list + 2/3 details */}
                <div style={{ flex:'0 0 420px', display:'flex', overflow:'hidden' }}>

                  {/* Account list - 1/3 */}
                  <div style={{ flex:'0 0 33%', overflowY:'auto', padding:'8px 10px', borderRight:'1px solid #373f4d' }}>
                    {displayedNodes.map((n:any)=>(
                      <AccountPill key={n.login} node={n} isSelected={selected?.login===n.login} onClick={()=>setSelected(n)} />
                    ))}
                  </div>

                  {/* Detail panel - 2/3 */}
                  <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', background:'#262c36' }}>
                    {selected ? (
                      <div style={{ padding:'12px', flex:1, overflowY:'auto' }}>
                        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                          <span style={{ fontSize:11, color:LAYER_COLORS[selected.layer], fontWeight:600 }}>{LAYER_NAMES[selected.layer]}</span>
                          <button onClick={()=>setSelected(null)} style={{ background:'none', border:'none', color:'#555', cursor:'pointer', fontSize:16 }}>✕</button>
                        </div>
                        <div style={{ width:48, height:48, borderRadius:10, background:LAYER_COLORS[selected.layer]+'22', display:'flex', alignItems:'center', justifyContent:'center', fontSize:18, marginBottom:10 }}>
                          {selected.layer===0?'⭐':selected.type==='ip'?'🌐':selected.type==='cid'?'📱':'👤'}
                        </div>
                        <div style={{ fontSize:14, fontWeight:600, color:'#e0e0e0', marginBottom:4 }}>{selected.name || `#${selected.login}`}</div>
                        <div style={{ fontSize:20, fontWeight:700, color:'#00e5a0', marginBottom:12 }}>${(selected.balance||0).toLocaleString()}</div>
                        {[
                          ['Login',    `#${selected.login}`,   '#00aaff'],
                          ['Country',  selected.country,        null],
                          ['City',     selected.city,           null],
                          ['IB',       selected.ib||'—',        '#cc88ff'],
                          ['Layer',    LAYER_NAMES[selected.layer], LAYER_COLORS[selected.layer]],
                          ['Via',      selected.connect_via ? `${(selected.type||'').toUpperCase()}: ${selected.connect_via?.substring(0,18)}` : 'Root account', EDGE_COLORS[selected.type]||'#555'],
                        ].filter(([,v])=>v).map(([k,v,c])=>(
                          <div key={k as string} style={{ display:'flex', justifyContent:'space-between', padding:'6px 0', fontSize:11, borderBottom:'1px solid #373f4d' }}>
                            <span style={{ color:'#555' }}>{k}</span>
                            <span style={{ color:(c as string)||'#aaa', maxWidth:160, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{v as string}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', flexDirection:'column', gap:8, color:'#444', padding:20, textAlign:'center' }}>
                        <div style={{ fontSize:32 }}>👆</div>
                        <div style={{ fontSize:12 }}>Click any account to see details</div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Graph at bottom - scrollable */}
                <div style={{ borderTop:'1px solid #373f4d', padding:'10px 14px', flexShrink:0, background:'#080a0f' }}>
                  <div style={{ fontSize:11, color:'#444', marginBottom:6 }}>Network graph — click nodes to select</div>
                  <GraphCanvas nodes={traversal.nodes} edges={traversal.edges} onSelect={setSelected} selected={selected} />
                </div>

              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

