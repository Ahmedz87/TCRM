import React from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { NAV } from '../config.jsx'

export default function Layout({ title, children }) {
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">FX</div>
          <div>
            <div className="name">TradeSoft</div>
            <div className="tag">Best Forex Broker</div>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((n, i) =>
            n.section ? (
              <div className="nav-label" key={i}>{n.section}</div>
            ) : (
              <NavLink key={i} to={n.to} end={n.exact}
                className={({ isActive }) => (isActive ? 'active' : '')}>
                <span className="ico">{n.ico}</span> {n.label}
              </NavLink>
            )
          )}
        </nav>
        <div className="foot">Legacy CRM copy · read-only<br />Powered by archived data</div>
      </aside>
      <div className="main">
        <header className="topbar">
          <h1>{title}</h1>
          <div className="spacer" />
          <span className="badge-ro">READ-ONLY ARCHIVE</span>
        </header>
        <div className="content">{children}</div>
      </div>
    </div>
  )
}
