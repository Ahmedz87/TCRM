import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import ListPage from './components/ListPage.jsx'
import Detail from './pages/Detail.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/clients" element={<ListPage entity="clients" />} />
      <Route path="/clients/:id" element={<Detail entity="clients" />} />
      <Route path="/leads" element={<ListPage entity="leads" />} />
      <Route path="/leads/:id" element={<Detail entity="leads" />} />
      <Route path="/accounts" element={<ListPage entity="accounts" />} />
      <Route path="/accounts/:id" element={<Detail entity="accounts" />} />
      <Route path="/transactions" element={<ListPage entity="transactions" />} />
      <Route path="/transactions/:id" element={<Detail entity="transactions" />} />
      <Route path="/users" element={<ListPage entity="users" />} />
      <Route path="/users/:id" element={<Detail entity="users" />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
