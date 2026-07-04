import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, fmtNum, fmtMoney, fmtDate } from '../api'
import { typeBadge, statusBadge } from '../config.jsx'
import Layout from '../components/Layout.jsx'

const Kpi = ({ ico, color, val, lbl, onClick }) => (
  <div className="kpi" style={{ cursor: onClick ? 'pointer' : 'default' }} onClick={onClick}>
    <div className="k-top"><div className="k-ico" style={{ background: color }}>{ico}</div></div>
    <div className="k-val">{val}</div>
    <div className="k-lbl">{lbl}</div>
  </div>
)

const BarList = ({ items, max }) => (
  <div>
    {items.map((it, i) => (
      <div className="barrow" key={i}>
        <div className="bl">{it.label || '—'}</div>
        <div className="bt"><div className="bf" style={{ width: `${Math.max(2, (it.n / max) * 100)}%` }} /></div>
        <div className="bn">{fmtNum(it.n)}</div>
      </div>
    ))}
  </div>
)

export default function Dashboard() {
  const [s, setS] = useState(null)
  const nav = useNavigate()
  useEffect(() => { api.stats().then(setS).catch(() => setS(false)) }, [])

  if (s === null) return <Layout title="Dashboard"><div className="loading">Loading dashboard…</div></Layout>
  if (s === false) return <Layout title="Dashboard"><div className="empty">Could not load stats. Is the backend running?</div></Layout>

  const c = s.counts
  const maxMonthly = Math.max(1, ...s.monthly_deposits.map((m) => Number(m.deposits)))
  const maxCountry = Math.max(1, ...s.top_countries.map((m) => m.n))
  const maxRating = Math.max(1, ...s.lead_rating.map((m) => m.n))

  return (
    <Layout title="Dashboard">
      <div className="kpis">
        <Kpi ico="◴" color="#907eec" val={fmtNum(c.clients)} lbl="Clients" onClick={() => nav('/clients')} />
        <Kpi ico="⚑" color="#2f76e1" val={fmtNum(c.leads)} lbl="Leads" onClick={() => nav('/leads')} />
        <Kpi ico="▤" color="#16ae9f" val={fmtNum(c.accounts)} lbl="Trading Accounts" onClick={() => nav('/accounts')} />
        <Kpi ico="⇄" color="#fdab29" val={fmtNum(c.transactions)} lbl="Transactions" onClick={() => nav('/transactions')} />
        <Kpi ico="☺" color="#fb6b5b" val={fmtNum(c.staff)} lbl="Staff Users" onClick={() => nav('/users')} />
      </div>

      <div className="grid3">
        {s.txn_types.map((t) => (
          <div className="kpi" key={t.label}>
            <div className="k-lbl" style={{ textTransform: 'capitalize' }}>{t.label}s (completed)</div>
            <div className="k-val" style={{ fontSize: 22 }}>{fmtMoney(t.total)}</div>
            <div className="k-lbl">{fmtNum(t.n)} transactions</div>
          </div>
        ))}
      </div>

      <div className="grid2">
        <div className="card">
          <div className="card-h">Monthly Deposits (completed)</div>
          <div className="card-b">
            {s.monthly_deposits.length === 0 ? <div className="empty">No data</div> : (
              <div className="spark">
                {s.monthly_deposits.map((m) => (
                  <div className="col" key={m.month} title={`${m.month}: ${fmtMoney(m.deposits)}`}>
                    <div className="bar" style={{ height: `${(Number(m.deposits) / maxMonthly) * 110}px` }} />
                    <div className="lbl">{m.month.slice(2)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="card">
          <div className="card-h">Accounts</div>
          <div className="card-b">
            <BarList items={s.account_types} max={Math.max(1, ...s.account_types.map((a) => a.n))} />
            <div className="card-h" style={{ border: 0, padding: '14px 0 6px' }}>Transaction status</div>
            <BarList items={s.txn_status} max={Math.max(1, ...s.txn_status.map((a) => a.n))} />
          </div>
        </div>
      </div>

      <div className="grid2">
        <div className="card">
          <div className="card-h">Recent Transactions <span className="muted" style={{ fontWeight: 400, cursor: 'pointer' }} onClick={() => nav('/transactions')}>View all →</span></div>
          <table className="tbl">
            <thead><tr><th>Date</th><th>Account</th><th>Type</th><th style={{ textAlign: 'right' }}>Amount</th><th>Status</th></tr></thead>
            <tbody>
              {s.recent_txns.map((t) => (
                <tr key={t.id} onClick={() => nav(`/transactions/${t.id}`)}>
                  <td>{fmtDate(t.created_at)}</td>
                  <td>{t.account_number}</td>
                  <td>{typeBadge(t.type)}</td>
                  <td className="num">{fmtMoney(t.amount, t.currency)}</td>
                  <td>{statusBadge(t.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <div className="card-h">Top Lead Countries</div>
          <div className="card-b">
            <BarList items={s.top_countries} max={maxCountry} />
            <div className="card-h" style={{ border: 0, padding: '14px 0 6px' }}>Lead rating</div>
            <BarList items={s.lead_rating} max={maxRating} />
          </div>
        </div>
      </div>
    </Layout>
  )
}
