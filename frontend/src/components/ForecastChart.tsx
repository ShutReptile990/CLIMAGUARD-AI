import { CloudRain } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useClimate } from '../context'
import { useEnvironment } from '../lib/hooks'
import { demoForecast } from '../lib/demo'
import { EmptyState, LoadingSkeleton } from './Shared'

export default function ForecastChart() {
  const { demo, localityId } = useClimate()
  const query = useEnvironment(localityId, !demo)
  const data = demo ? demoForecast : query.data?.weather && 'daily' in query.data.weather
    ? query.data.weather.daily.map(item => ({ day: new Date(`${item.date}T00:00:00+05:30`).toLocaleDateString('en-IN', { weekday: 'short', timeZone: 'Asia/Kolkata' }), rain: item.precipitation_sum_mm, temp: item.temperature_max_c }))
    : []
  if (!demo && query.isLoading) return <LoadingSkeleton/>
  if (!data.length) return <EmptyState title="Forecast unavailable" description="Open-Meteo did not supply a validated daily forecast for this locality." icon={CloudRain}/>
  return <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data} margin={{ top: 10, right: 10, left: -30, bottom: 0 }}><defs><linearGradient id="rainFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4e83b9" stopOpacity={0.24}/><stop offset="100%" stopColor="#4e83b9" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#e9eef2" strokeDasharray="4 4"/><XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fill: '#8592a2', fontSize: 12 }}/><YAxis tickLine={false} axisLine={false} tick={{ fill: '#8592a2', fontSize: 12 }}/><Tooltip contentStyle={{ borderRadius: 12, borderColor: '#e5ebf0' }} formatter={(v, n) => [`${v}${n === 'rain' ? ' mm' : '°C'}`, n === 'rain' ? 'Rainfall' : 'Temperature']} /><Area type="monotone" dataKey="rain" stroke="#3777ad" strokeWidth={2.5} fill="url(#rainFill)" /></AreaChart></ResponsiveContainer></div>
}
