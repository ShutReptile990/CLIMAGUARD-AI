import type { Locality, RiskAssessment, Snapshot } from '../types'
export const localities: Locality[] = [
  { id: 'pune', name: 'Pune', city: 'Pune, Maharashtra', center: [18.5204, 73.8567] },
  { id: 'shivajinagar', name: 'Shivajinagar', city: 'Pune, Maharashtra', center: [18.5308, 73.8475] },
  { id: 'kothrud', name: 'Kothrud', city: 'Pune, Maharashtra', center: [18.5074, 73.8077] },
  { id: 'hadapsar', name: 'Hadapsar', city: 'Pune, Maharashtra', center: [18.4967, 73.9414] },
]
export const demoRisks: RiskAssessment[] = [
  { hazard: 'flood', level: 'moderate', score: 48, factors: ['Illustrative heavy rainfall', 'Illustrative low-lying terrain'], assessedAt: null, source: 'Illustrative scenario', status: 'demo' },
  { hazard: 'heat', level: 'low', score: 24, factors: ['Illustrative air temperature', 'Illustrative humidity'], assessedAt: null, source: 'Illustrative scenario', status: 'demo' },
  { hazard: 'air_quality', level: 'high', score: 72, factors: ['Illustrative particulate concentration', 'Illustrative wind conditions'], assessedAt: null, source: 'Illustrative scenario', status: 'demo' },
]
export const demoForecast = [
  { day: 'Mon', rain: 24, temp: 31 }, { day: 'Tue', rain: 38, temp: 32 },
  { day: 'Wed', rain: 29, temp: 30 }, { day: 'Thu', rain: 54, temp: 29 },
  { day: 'Fri', rain: 43, temp: 30 }, { day: 'Sat', rain: 67, temp: 28 },
  { day: 'Sun', rain: 46, temp: 29 },
]
export function demoSnapshot(locality: Locality): Snapshot {
  return { locality, weather: { temperatureC: 31, humidityPercent: 68, rainfallMm: 12, aqi: 152, observedAt: null, source: 'Illustrative scenario', status: 'demo' }, risks: demoRisks, alerts: [], facilities: [], updatedAt: null, status: 'demo' }
}
