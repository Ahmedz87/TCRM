import React, { useState, useEffect } from 'react';
import { apiGet, apiPost } from './api';
import ClientChat from './ClientChat';

export default function ClientDashboard({ user }: any) {
  const [kpis, setKpis]             = useState<any>(null);
  const [bonus, setBonus]           = useState<any>(null);
  const [loading, setLoading]       = useState(true);
  const [bonusLoading, setBonusLoading] = useState(false);
  const [cid, setCid]               = useState('');

  const login = user?.login || user?.id;

  useEffect(() => {
    if (!login) return;
    setLoading(true);
    apiGet(`/client-dashboard/kpis/${login}`)
      .then(setKpis).catch(()=>{})
      .finally(()=>setLoading(false));
  }, [login]);

  const checkBonus = async () => {
    setBonusLoading(true);
    try {
      const ip = ''; // captured from browser
      const result = await apiPost(`/client-dashboard/bonus-check/${login}`, { cid, ip });
      setBonus(result);
    } catch(e) {}
    setBonusLoading(false);
  };

  if (loading) return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100%', color:'#555' }}>
      Loading your dashboard...
    </div>
  );

  return (
    <div style={{ padding:'20px', maxWidth:900, margin:'0 auto' }}>
      {/* Welcome */}
      <div style={{ marginBottom:20 }}>
        <div style={{ fontSize:22, fontWeight:700 }}>Welcome back, {kpis?.name || 'Trader'} 👋</div>
        <div style={{ fontSize:12, color:'#555', marginTop:4 }}>Account #{login}</div>
      </div>

      {/* KPI grid */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, marginBottom:24 }}>
        {[
          { icon:'💰', label:'Balance',      value:`$${(kpis?.balance||0).toLocaleString('en-GB')}`,        color:'#00e5a0' },
          { icon:'📊', label:'Equity',       value:`$${(kpis?.equity||0).toLocaleString('en-GB')}`,         color:'#00aaff' },
          { icon:'📥', label:'Total Deposit',value:`$${(kpis?.total_deposits||0).toLocaleString('en-GB')}`, color:'#ffaa00' },
          { icon:'📤', label:'Withdrawn',    value:`$${(kpis?.total_withdrawals||0).toLocaleString('en-GB')}`, color:'#ff8888' },
          { icon:'📈', label:'Open Positions',value:(kpis?.open_positions||0).toString(),            color:'#00e5a0' },
          { icon:'🔄', label:'Monthly Trades',value:(kpis?.monthly_trades||0).toString(),            color:'#cc88ff' },
        ].map((k,i)=>(
          <div key={i} style={{ background:'#2c333e', border:'1px solid #373f4d', borderRadius:12, padding:'16px 18px', display:'flex', alignItems:'center', gap:12 }}>
            <div style={{ width:44, height:44, borderRadius:10, background:k.color+'22', display:'flex', alignItems:'center', justifyContent:'center', fontSize:22 }}>{k.icon}</div>
            <div>
              <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:4 }}>{k.label}</div>
              <div style={{ fontSize:20, fontWeight:700, color:k.color }}>{k.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Welcome Bonus Section */}
      <div style={{ background:'#2c333e', border:'1px solid #373f4d', borderRadius:12, padding:20, marginBottom:24 }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:16 }}>
          <span style={{ fontSize:28 }}>🎁</span>
          <div>
            <div style={{ fontSize:16, fontWeight:700 }}>Welcome Bonus</div>
            <div style={{ fontSize:12, color:'#555' }}>Check if you are eligible for your welcome bonus</div>
          </div>
        </div>

        {!bonus && (
          <div>
            <div style={{ fontSize:12, color:'#888', marginBottom:12 }}>
              To check your eligibility, please log into your trading account first. Your device will be verified automatically.
            </div>
            <button onClick={checkBonus} disabled={bonusLoading}
              style={{ padding:'10px 24px', background:'#00e5a0', border:'none', borderRadius:8, color:'#000', fontWeight:700, cursor:'pointer', fontSize:14, fontFamily:'inherit' }}>
              {bonusLoading ? '⏳ Checking...' : '🎁 Check Welcome Bonus'}
            </button>
          </div>
        )}

        {bonus && bonus.eligible && (
          <div style={{ background:'rgba(0,229,160,0.08)', border:'1px solid rgba(0,229,160,0.3)', borderRadius:10, padding:16 }}>
            <div style={{ fontSize:16, fontWeight:700, color:'#00e5a0', marginBottom:8 }}>
              🎉 Congratulations! You are eligible!
            </div>
            <div style={{ fontSize:24, fontWeight:700, color:'#00e5a0', marginBottom:8 }}>
              ${bonus.bonus_amount} Welcome Bonus
            </div>
            <div style={{ fontSize:12, color:'#888', marginBottom:14 }}>{bonus.reason}</div>
            <div style={{ fontSize:11, color:'#ffaa00', background:'rgba(255,170,0,0.1)', padding:'8px 12px', borderRadius:7, marginBottom:14 }}>
              📋 Next step: {bonus.next_step}
            </div>
            <button style={{ padding:'10px 24px', background:'#00e5a0', border:'none', borderRadius:8, color:'#000', fontWeight:700, cursor:'pointer', fontSize:14, fontFamily:'inherit' }}>
              ✅ Claim Bonus
            </button>
          </div>
        )}

        {bonus && !bonus.eligible && (
          <div style={{ background:'rgba(255,77,77,0.08)', border:'1px solid rgba(255,77,77,0.3)', borderRadius:10, padding:16 }}>
            <div style={{ fontSize:14, fontWeight:600, color:'#ff4d4d', marginBottom:8 }}>
              ❌ Not eligible for welcome bonus
            </div>
            <div style={{ fontSize:12, color:'#888', marginBottom:14 }}>{bonus.reason}</div>
            {bonus.show_deposit_bonus && (
              <div>
                <div style={{ fontSize:13, color:'#ffaa00', fontWeight:600, marginBottom:8 }}>
                  🎁 But you can get our Deposit Bonus!
                </div>
                <div style={{ fontSize:12, color:'#888', marginBottom:12 }}>
                  Deposit now and receive up to 50% bonus on your first deposit.
                </div>
                <button style={{ padding:'10px 24px', background:'#ffaa00', border:'none', borderRadius:8, color:'#000', fontWeight:700, cursor:'pointer', fontSize:14, fontFamily:'inherit' }}>
                  💰 Deposit & Get Bonus
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Monthly P&L */}
      <div style={{ background:'#2c333e', border:'1px solid #373f4d', borderRadius:12, padding:20 }}>
        <div style={{ fontSize:14, fontWeight:600, marginBottom:12 }}>Monthly Performance</div>
        <div style={{ display:'flex', gap:20 }}>
          <div>
            <div style={{ fontSize:10, color:'#555', marginBottom:4 }}>TRADES THIS MONTH</div>
            <div style={{ fontSize:24, fontWeight:700, color:'#00aaff' }}>{kpis?.monthly_trades||0}</div>
          </div>
          <div>
            <div style={{ fontSize:10, color:'#555', marginBottom:4 }}>MONTHLY P&L</div>
            <div style={{ fontSize:24, fontWeight:700, color:(kpis?.monthly_pnl||0)>=0?'#00e5a0':'#ff4d4d' }}>
              {(kpis?.monthly_pnl||0)>=0?'+':''}${(kpis?.monthly_pnl||0).toLocaleString('en-GB')}
            </div>
          </div>
        </div>
      </div>

      {/* AI live chat assistant (floating) */}
      <ClientChat login={login} />
    </div>
  );
}
