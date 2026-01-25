import { Routes, Route } from 'react-router-dom'
import RunList from './components/RunList'
import RunDetail from './components/RunDetail'

function App() {
  return (
    <div className="container">
      <Routes>
        <Route path="/" element={<RunList />} />
        <Route path="/runs/:runId" element={<RunDetail />} />
      </Routes>
    </div>
  )
}

export default App
