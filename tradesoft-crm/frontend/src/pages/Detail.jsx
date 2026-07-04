import React, { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api, fmtMoney, fmtNum, fmtDate, fmtDay } from '../api'
import { Avatar, acctTypeBadge, statusBadge, typeBadge, ratingBadge, roleBadge, kycBadge } from '../config.jsx'
import Layout from '../components/Layout.jsx'

const KV = ({ rows }) => (
  <div className="kv">
    {rows.filter(([, v]) => v !== undefined).map(([k, v], i) => (
      <React.Fragment key={i}><div className="k">{k}</div><div>{v ?? '—'}</div></React.Fragment>
    ))}
  </div>
)

const SummaryCards = ({ summary }) => summary && (
  <div className="grid3" style={{ marginTop: 0, marginBottom: 16 }}>
    <div className="kpi"><div className="k-lbl">Deposits</div><div className="k-val" style={{ fontSize: 22 }}>{fmtMoney(summary.deposits)}</div></div>
    <div className="kpi"><div className="k-lbl">Withdrawals</div><div className="k-val" style={{ fontSize: 22 }}>{fmtMoney(summary.withdrawals)}</div></div>
    <div className="kpi"><div className="k-lbl">Completed Txns</div><div className="k-val" style={{ fontSize: 22 }}>{fmtNum(summary.completed_txns)}</div></div>
  </div>
)

const AccountsTable = ({ accounts, nav }) => (
  <div className="card" style={{ marginTop: 16 }}>
    <div className="card-h">Trading Accounts ({accounts.length})</div>
    <table className="tbl">
      <thead><tr><th>Account #</th><th>Type</th><th>Group</th><th>Ccy</th><th style={{ textAlign: 'right' }}>Balance</th><th style={{ textAlign: 'right' }}>Equity</th><th>Status</th><th>Opened</th></tr></thead>
      <tbody>
        {accounts.length === 0 ? <tr><td colSpan={8} className="empty">No accounts</td></tr> :
          accounts.map((a, i) => (
            <tr key={i}>
              <td><b>{a.account_number}</b></td><td>{acctTypeBadge(a.account_type)}</td>
              <td>{a.account_group || '—'}</td><td>{a.account_currency}</td>
              <td className="num">{fmtMoney(a.account_balance, a.account_currency)}</td>
              <td className="num">{fmtMoney(a.equity, a.account_currency)}</td>
              <td>{statusBadge(a.status)}</td><td>{fmtDay(a.created_at)}</td>
            </tr>
          ))}
      </tbody>
    </table>
  </div>
)

const TxnsTable = ({ txns, nav }) => (
  <div className="card" style={{ marginTop: 16 }}>
    <div className="card-h">Transactions ({txns.length})</div>
    <table className="tbl">
      <thead><tr><th>Date</th><th>Account</th><th>Type</th><th style={{ textAlign: 'right' }}>Amount</th><th>Method</th><th>Status</th></tr></thead>
      <tbody>
        {txns.length === 0 ? <tr><td colSpan={6} className="empty">No transactions</td></tr> :
          txns.map((t) => (
            <tr key={t.id} onClick={() => nav(`/transactions/${t.id}`)}>
              <td>{fmtDate(t.created_at)}</td><td>{t.account_number || '—'}</td>
              <td>{typeBadge(t.type)}</td><td className="num">{fmtMoney(t.amount, t.currency)}</td>
              <td>{t.payment_method || '—'}</td><td>{statusBadge(t.status)}</td>
            </tr>
          ))}
      </tbody>
    </table>
  </div>
)

const TITLES = { clients: 'Client', leads: 'Lead', accounts: 'Account', transactions: 'Transaction', users: 'User' }

export default function Detail({ entity }) {
  const { id } = useParams()
  const nav = useNavigate()
  const [d, setD] = useState(null)
  useEffect(() => { setD(null); api.detail(entity, id).then(setD).catch(() => setD(false)) }, [entity, id])

  if (d === null) return <Layout title={TITLES[entity]}><div className="loading">Loading…</div></Layout>
  if (d === false) return <Layout title={TITLES[entity]}><div className="empty">Not found.</div></Layout>

  const back = (to, label) => <Link className="back" to={to}>‹ Back to {label}</Link>

  // ---------------- person-like (client / lead / user) ----------------
  if (entity === 'clients' || entity === 'leads' || entity === 'users') {
    const main = d.client || d.lead || d.user
    const u = d.user
    const name = entity === 'users' ? [u?.name, u?.surname].filter(Boolean).join(' ') : main.name
    return (
      <Layout title={TITLES[entity]}>
        {back(`/${entity}`, ENTITY_LABEL[entity])}
        <div className="detail-head">
          <span className="avatar avatar-lg">{(name || '?').replace(/\s+/g, ' ').trim().split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase()}</span>
          <div>
            <h2>{name || '—'}</h2>
            <div className="sub">
              {entity === 'leads' && <>{ratingBadge(main.rating_status)} &nbsp;</>}
              {entity === 'users' && <>{roleBadge(u?.type)} &nbsp;</>}
              {main.country ? `${main.country}` : ''}{main.city ? ` · ${main.city}` : ''} · ID {id}
            </div>
          </div>
        </div>

        <SummaryCards summary={d.summary} />

        <div className="grid2" style={{ marginTop: 0 }}>
          <div className="card">
            <div className="card-h">Profile</div>
            <div className="card-b">
              {entity === 'clients' && <KV rows={[
                ['Email', main.email], ['Phone', main.phone],
                ['Code', main.code], ['Sales Rep', main.owner_name], ['Country', main.country],
                ['City', main.city], ['State', main.state], ['Currency', main.currency],
                ['Balance', fmtMoney(main.balance, main.currency)], ['Registered', fmtDate(main.created_at)],
                ['Archived', main.archived_at ? fmtDate(main.archived_at) : '—'],
              ]} />}
              {entity === 'leads' && <KV rows={[
                ['Email', main.email], ['Phone', main.phone],
                ['Company', main.company], ['Rating', main.rating_status], ['Stage ID', main.stage_id],
                ['Sales Rep', main.sales_rep_name], ['Lead Value', fmtMoney(main.lead_value)],
                ['Lead Score', fmtNum(main.lead_score)], ['Source', main.lead_source],
                ['Country', main.country], ['City', main.city],
                ['Next Follow-up', fmtDate(main.next_followup)], ['Converted', main.converted_at ? fmtDate(main.converted_at) : '—'],
                ['Created', fmtDate(main.created_at)],
              ]} />}
              {entity === 'users' && <KV rows={[
                ['Email', u?.email], ['Phone', u?.phone],
                ['Role', u?.type], ['Language', u?.language], ['IB Code', u?.ib_code], ['IB Number', u?.ib_number],
                ['KYC', kycBadge(u?.is_kyc_verified)], ['Banned', u?.banned === '1' ? 'Yes' : 'No'],
                ['Total Deposit', fmtMoney(u?.total_deposit)], ['Loyalty Points', fmtNum(u?.loyalty_points)],
                ['Last Login', fmtDate(u?.last_login)], ['Last IP', u?.last_ip], ['Joined', fmtDate(u?.created_at)],
              ]} />}
            </div>
          </div>
          {entity !== 'users' && u && (
            <div className="card">
              <div className="card-h">User Account</div>
              <div className="card-b">
                <KV rows={[
                  ['User ID', u.id], ['Email', u.email], ['Phone', u.phone],
                  ['Type', roleBadge(u.type)], ['KYC', kycBadge(u.is_kyc_verified)],
                  ['Language', u.language], ['Last Login', fmtDate(u.last_login)], ['Last IP', u.last_ip],
                  ['Total Deposit', fmtMoney(u.total_deposit)], ['Created', fmtDate(u.created_at)],
                ]} />
              </div>
            </div>
          )}
        </div>

        <AccountsTable accounts={d.accounts || []} nav={nav} />
        <TxnsTable txns={d.transactions || []} nav={nav} />
      </Layout>
    )
  }

  // ---------------- account ----------------
  if (entity === 'accounts') {
    const a = d.account, o = d.owner
    return (
      <Layout title="Account">
        {back('/accounts', 'Accounts')}
        <div className="detail-head">
          <span className="avatar avatar-lg">#</span>
          <div><h2>Account {a.account_number}</h2>
            <div className="sub">{acctTypeBadge(a.account_type)} · {a.account_group} · {a.account_currency}</div></div>
        </div>
        <div className="grid2" style={{ marginTop: 0 }}>
          <div className="card"><div className="card-h">Account Details</div><div className="card-b">
            <KV rows={[
              ['Account #', a.account_number], ['Type', a.account_type], ['Group', a.account_group],
              ['Currency', a.account_currency], ['Leverage', '1:' + fmtNum(a.leverage)],
              ['Balance', fmtMoney(a.account_balance, a.account_currency)], ['Equity', fmtMoney(a.equity, a.account_currency)],
              ['Credit', fmtMoney(a.credit, a.account_currency)], ['Free Margin', fmtMoney(a.margin_free, a.account_currency)],
              ['Islamic', a.is_islamic === '1' ? 'Yes' : 'No'], ['Status', statusBadge(a.status)],
              ['IB / Agent', a.agent_name || '—'], ['Opened', fmtDate(a.created_at)],
            ]} />
          </div></div>
          <div className="card"><div className="card-h">Owner</div><div className="card-b">
            {o ? <KV rows={[
              ['Name', <Link to={`/users/${o.id}`} style={{ color: 'var(--primary)' }}>{[o.name, o.surname].filter(Boolean).join(' ')}</Link>],
              ['User ID', o.id], ['Email', o.email], ['Phone', o.phone],
              ['Type', roleBadge(o.type)], ['KYC', kycBadge(o.is_kyc_verified)],
              ['Last Login', fmtDate(o.last_login)],
            ]} /> : <div className="muted">No owner linked</div>}
          </div></div>
        </div>
        <TxnsTable txns={d.transactions || []} nav={nav} />
      </Layout>
    )
  }

  // ---------------- transaction ----------------
  const t = d.transaction
  return (
    <Layout title="Transaction">
      {back('/transactions', 'Transactions')}
      <div className="detail-head">
        <span className="avatar avatar-lg">⇄</span>
        <div><h2>{fmtMoney(t.amount, t.currency)} <span style={{ fontSize: 15 }}>{typeBadge(t.type)}</span></h2>
          <div className="sub">Account {t.account_number} · {fmtDate(t.created_at)}</div></div>
      </div>
      <div className="card" style={{ maxWidth: 640 }}><div className="card-h">Transaction Details</div><div className="card-b">
        <KV rows={[
          ['Transaction ID', t.id], ['Type', typeBadge(t.type)], ['Status', statusBadge(t.status)],
          ['Amount', fmtMoney(t.amount, t.currency)], ['Currency', t.currency],
          ['Account #', t.account_number], ['To Account', t.to_account], ['Payment Method', t.payment_method],
          ['Order / Trade', t.order_trade], ['Note', t.note], ['Open Time', fmtDate(t.open_time)],
          ['Created', fmtDate(t.created_at)], ['Updated', fmtDate(t.updated_at)],
        ]} />
      </div></div>
    </Layout>
  )
}

const ENTITY_LABEL = { clients: 'Clients', leads: 'Leads', users: 'Users & Staff' }
