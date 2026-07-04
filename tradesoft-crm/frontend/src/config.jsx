import React from 'react'
import { fmtMoney, fmtNum, fmtDate, fmtDay } from './api'

const initials = (name) => (name || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()

export const Avatar = ({ name }) => <span className="avatar">{initials(name)}</span>
export const NameCell = ({ name, sub }) => (
  <span className="cellname"><Avatar name={name} /><span>{name || '—'}{sub && <div className="muted" style={{ fontSize: 11 }}>{sub}</div>}</span></span>
)

const tag = (cls, text) => <span className={`tag ${cls}`}>{text}</span>

export const ratingBadge = (r) => {
  const m = { hot: 'red', warm: 'amber', cold: 'blue' }
  return r ? tag(m[r] || 'grey', r) : tag('grey', '—')
}
export const statusBadge = (s) => {
  const m = { completed: 'green', approved: 'green', rejected: 'red', pending: 'amber', processing: 'amber', updating: 'amber' }
  return s ? tag(m[String(s).toLowerCase()] || 'grey', s) : tag('grey', '—')
}
export const typeBadge = (t) => {
  const m = { deposit: 'green', withdrawal: 'red', transfer: 'blue' }
  return t ? tag(m[String(t).toLowerCase()] || 'grey', t) : tag('grey', '—')
}
export const acctTypeBadge = (t) => (String(t).toLowerCase() === 'demo' ? tag('grey', 'Demo') : tag('purple', t || '—'))
export const kycBadge = (v) => (String(v) === '1' ? tag('green', 'Verified') : tag('grey', 'No'))
export const roleBadge = (t) => tag('purple', t || '—')

// Each entity: list columns + which type filter chips (optional) + title/singular.
export const ENTITY = {
  clients: {
    title: 'Clients', singular: 'Client', detail: 'clients',
    columns: [
      { key: 'name', label: 'Name', render: (r) => <NameCell name={r.name} sub={r.email} /> },
      { key: 'phone', label: 'Phone', sort: false, render: (r) => r.phone || '—' },
      { key: 'owner_name', label: 'Sales Rep', sort: false, render: (r) => r.owner_name || '—' },
      { key: 'country', label: 'Country' },
      { key: 'currency', label: 'Ccy', sort: false },
      { key: 'balance', label: 'Balance', align: 'num', render: (r) => fmtMoney(r.balance, r.currency) },
      { key: 'created_at', label: 'Registered', render: (r) => fmtDay(r.created_at) },
    ],
  },
  leads: {
    title: 'Leads', singular: 'Lead', detail: 'leads',
    filters: { field: 'rating_status', options: ['hot', 'warm', 'cold'] },
    columns: [
      { key: 'name', label: 'Name', render: (r) => <NameCell name={r.name} sub={r.email} /> },
      { key: 'phone', label: 'Phone', sort: false, render: (r) => r.phone || '—' },
      { key: 'rating_status', label: 'Rating', render: (r) => ratingBadge(r.rating_status) },
      { key: 'lead_value', label: 'Value', align: 'num', render: (r) => fmtMoney(r.lead_value) },
      { key: 'sales_rep_name', label: 'Sales Rep', sort: false, render: (r) => r.sales_rep_name || '—' },
      { key: 'country', label: 'Country' },
      { key: 'created_at', label: 'Created', render: (r) => fmtDay(r.created_at) },
    ],
  },
  accounts: {
    title: 'Trading Accounts', singular: 'Account', detail: 'accounts',
    columns: [
      { key: 'account_number', label: 'Account #', render: (r) => <b>{r.account_number}</b> },
      { key: 'account_type', label: 'Type', render: (r) => acctTypeBadge(r.account_type) },
      { key: 'account_group', label: 'Group', sort: false },
      { key: 'account_currency', label: 'Ccy', sort: false },
      { key: 'leverage', label: 'Leverage', align: 'num', render: (r) => '1:' + fmtNum(r.leverage) },
      { key: 'account_balance', label: 'Balance', align: 'num', render: (r) => fmtMoney(r.account_balance, r.account_currency) },
      { key: 'equity', label: 'Equity', align: 'num', render: (r) => fmtMoney(r.equity, r.account_currency) },
      { key: 'agent_name', label: 'IB / Agent', sort: false, render: (r) => r.agent_name || '—' },
      { key: 'created_at', label: 'Opened', render: (r) => fmtDay(r.created_at) },
    ],
  },
  transactions: {
    title: 'Transactions', singular: 'Transaction', detail: 'transactions',
    filters: { field: 'type', options: ['deposit', 'withdrawal', 'transfer'] },
    columns: [
      { key: 'created_at', label: 'Date', render: (r) => fmtDate(r.created_at) },
      { key: 'account_number', label: 'Account #' },
      { key: 'type', label: 'Type', render: (r) => typeBadge(r.type) },
      { key: 'amount', label: 'Amount', align: 'num', render: (r) => fmtMoney(r.amount, r.currency) },
      { key: 'payment_method', label: 'Method', sort: false },
      { key: 'status', label: 'Status', render: (r) => statusBadge(r.status) },
    ],
  },
  users: {
    title: 'Users & Staff', singular: 'User', detail: 'users',
    columns: [
      { key: 'name', label: 'Name', render: (r) => <NameCell name={[r.name, r.surname].filter(Boolean).join(' ')} sub={r.email} /> },
      { key: 'phone', label: 'Phone', sort: false, render: (r) => r.phone || '—' },
      { key: 'type', label: 'Role', render: (r) => roleBadge(r.type) },
      { key: 'ib_code', label: 'IB Code', sort: false, render: (r) => r.ib_code || '—' },
      { key: 'is_kyc_verified', label: 'KYC', sort: false, render: (r) => kycBadge(r.is_kyc_verified) },
      { key: 'last_login', label: 'Last Login', render: (r) => fmtDate(r.last_login) },
      { key: 'created_at', label: 'Joined', render: (r) => fmtDay(r.created_at) },
    ],
  },
}

export const NAV = [
  { to: '/', label: 'Dashboard', ico: '▦', exact: true },
  { section: 'CRM' },
  { to: '/clients', label: 'Clients', ico: '◴' },
  { to: '/leads', label: 'Leads', ico: '⚑' },
  { section: 'Trading' },
  { to: '/accounts', label: 'Accounts', ico: '▤' },
  { to: '/transactions', label: 'Transactions', ico: '⇄' },
  { section: 'People' },
  { to: '/users', label: 'Users & Staff', ico: '☺' },
]
