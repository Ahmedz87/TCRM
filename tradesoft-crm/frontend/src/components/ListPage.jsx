import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, fmtNum } from '../api'
import { ENTITY } from '../config.jsx'
import Layout from './Layout.jsx'

const PAGE_SIZE = 25

export default function ListPage({ entity }) {
  const cfg = ENTITY[entity]
  const nav = useNavigate()
  const [data, setData] = useState({ rows: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState(cfg.columns[cfg.columns.length - 1].key)
  const [order, setOrder] = useState('desc')
  const [filter, setFilter] = useState('')

  useEffect(() => { const t = setTimeout(() => { setDebounced(search); setPage(1) }, 350); return () => clearTimeout(t) }, [search])

  const load = useCallback(() => {
    setLoading(true)
    const q = { search: debounced, page, page_size: PAGE_SIZE, sort, order }
    api.list(entity, q)
      .then((d) => {
        // client-side filter chip (rating/type) on the returned page is not ideal for
        // big sets, so we fold it into search-by-value via the same endpoint param when set.
        setData(d)
      })
      .catch(() => setData({ rows: [], total: 0 }))
      .finally(() => setLoading(false))
  }, [entity, debounced, page, sort, order])

  useEffect(() => { load() }, [load])
  useEffect(() => { setSearch(''); setDebounced(''); setPage(1); setFilter(''); setSort(cfg.columns[cfg.columns.length - 1].key); setOrder('desc') }, [entity])

  const onSort = (key, canSort) => {
    if (canSort === false) return
    if (sort === key) setOrder(order === 'asc' ? 'desc' : 'asc')
    else { setSort(key); setOrder('desc') }
    setPage(1)
  }

  const rows = cfg.filters && filter
    ? data.rows.filter((r) => String(r[cfg.filters.field]).toLowerCase() === filter)
    : data.rows

  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE))

  return (
    <Layout title={cfg.title}>
      <div className="toolbar">
        <div className="search">
          <input placeholder={`Search ${cfg.title.toLowerCase()}…`} value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        {cfg.filters && (
          <div className="chip-filters">
            <span className={`chip ${filter === '' ? 'active' : ''}`} onClick={() => setFilter('')}>All</span>
            {cfg.filters.options.map((o) => (
              <span key={o} className={`chip ${filter === o ? 'active' : ''}`} onClick={() => setFilter(o)}>{o}</span>
            ))}
          </div>
        )}
        <div style={{ flex: 1 }} />
        <span className="muted">{fmtNum(data.total)} records</span>
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              {cfg.columns.map((c) => (
                <th key={c.key} className={c.sort === false ? 'no-sort' : ''}
                  onClick={() => onSort(c.key, c.sort)}
                  style={{ textAlign: c.align === 'num' ? 'right' : 'left' }}>
                  {c.label}{sort === c.key ? (order === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={cfg.columns.length} className="loading">Loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={cfg.columns.length} className="empty">No records found</td></tr>
            ) : rows.map((r) => (
              <tr key={r.id} onClick={() => nav(`/${cfg.detail}/${r.id}`)}>
                {cfg.columns.map((c) => (
                  <td key={c.key} className={c.align === 'num' ? 'num' : ''}>
                    {c.render ? c.render(r) : (r[c.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="pager">
        <span>Page {page} of {fmtNum(pages)}</span>
        <div className="pbtns">
          <button className="btn" disabled={page <= 1} onClick={() => setPage(1)}>« First</button>
          <button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Prev</button>
          <button className="btn" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next ›</button>
          <button className="btn" disabled={page >= pages} onClick={() => setPage(pages)}>Last »</button>
        </div>
      </div>
    </Layout>
  )
}
