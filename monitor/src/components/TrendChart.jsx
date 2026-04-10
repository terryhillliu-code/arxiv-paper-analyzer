import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts'
import { format } from 'date-fns'

export default function TrendChart({ data, title, dataKey = 'value', color = '#00d4ff', type = 'line' }) {
  const formattedData = data.map(d => ({
    ...d,
    time: d.timestamp ? format(new Date(d.timestamp), 'HH:mm') : d.time,
  }))

  return (
    <div className="card">
      <h3 className="text-sm text-gray-400 uppercase mb-2">{title}</h3>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          {type === 'area' ? (
            <AreaChart data={formattedData}>
              <XAxis dataKey="time" stroke="#666" tick={{ fill: '#666', fontSize: 10 }} />
              <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 10 }} width={40} />
              <Tooltip
                contentStyle={{ background: '#16213e', border: '1px solid #333', borderRadius: '8px' }}
                labelStyle={{ color: '#eee' }}
              />
              <Area type="monotone" dataKey={dataKey} stroke={color} fill={color} fillOpacity={0.2} />
            </AreaChart>
          ) : (
            <LineChart data={formattedData}>
              <XAxis dataKey="time" stroke="#666" tick={{ fill: '#666', fontSize: 10 }} />
              <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 10 }} width={40} />
              <Tooltip
                contentStyle={{ background: '#16213e', border: '1px solid #333', borderRadius: '8px' }}
                labelStyle={{ color: '#eee' }}
              />
              <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  )
}