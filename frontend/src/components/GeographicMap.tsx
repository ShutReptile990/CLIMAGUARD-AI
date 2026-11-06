import { useEffect, useState } from 'react'
import { CircleMarker, GeoJSON, MapContainer, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import type { FeatureCollection } from 'geojson'
import type { Layer } from 'leaflet'
import type { Locality, ScreeningBand, ZoneFeature } from '../types'
import { useClimate } from '../context'
import { useComparison, useMappedInfrastructure, useMappedRoads, useMapScreening, useZonesGeojson } from '../lib/hooks'

type LayerKind = 'rainfall' | 'temperature' | 'us_aqi' | 'flood_index'
const bandColors: Record<ScreeningBand, string> = { low: '#9acbbf', moderate: '#efd398', high: '#eba56e', severe: '#db7777', unavailable: '#d8e0e4' }
const labels: Record<LayerKind, string> = { rainfall: '24h rain', temperature: '2-day heat', us_aqi: 'US AQI', flood_index: 'Flood index' }
function MapFlyTo({ center }: { center: [number, number] }) { const map = useMap(); useEffect(() => { map.flyTo(center, map.getZoom(), { duration: 0.45 }) }, [center[0], center[1], map]); return null }
function MapBounds({ onChange }: { onChange: (bbox: string) => void }) { const map = useMapEvents({ moveend: update, zoomend: update }); function update() { const b = map.getBounds(); const west = Math.max(73.5, b.getWest()); const south = Math.max(18.2, b.getSouth()); const east = Math.min(74.2, b.getEast()); const north = Math.min(18.9, b.getNorth()); if (west < east && south < north) onChange([west, south, east, north].map(value => value.toFixed(6)).join(',')) } useEffect(() => { update() }, [map]); return null }
function valueLabel(layer: LayerKind, value?: number | null) { return value == null ? 'Unavailable' : `${value}${layer === 'rainfall' ? ' mm' : layer === 'temperature' ? '°C' : layer === 'us_aqi' ? ' US AQI' : '/100 heuristic index'}` }

export function RiskMap({ locality, compact = false }: { locality: Locality; compact?: boolean }) {
  const { demo, demoFlood, demoScenarioId, setLocalityId } = useClimate()
  const zones = useZonesGeojson()
  const screening = useMapScreening(!demo)
  const comparison = useComparison(!demo)
  const [bbox, setBbox] = useState<string>()
  const facilities = useMappedInfrastructure(bbox, !demo && !!bbox)
  const [layer, setLayer] = useState<LayerKind>(demo ? 'flood_index' : 'rainfall')
  useEffect(() => { if (demo) setLayer('flood_index') }, [demo])
  const [showHospitals, setShowHospitals] = useState(true)
  const [showSchools, setShowSchools] = useState(false)
  const [showEmergency, setShowEmergency] = useState(false)
  const [showRoads, setShowRoads] = useState(false)
  const roads = useMappedRoads(!demo && showRoads && !!bbox, bbox)
  const visibleFacilities = facilities.data?.features.filter(item => item.kind === 'hospital' && showHospitals || item.kind === 'school' && showSchools || !['hospital', 'school'].includes(item.kind) && showEmergency) ?? []
  const roadFeatures = roads.data?.features.map(road => ({ type: 'Feature' as const, geometry: road.geometry, properties: { name: road.name, highway_class: road.highway_class, source_url: road.source_url } })) ?? []
  const counts = facilities.data?.counts
  const screeningValue = (feature: ZoneFeature) => screening.data?.zones[feature.properties.slug]
  const onEachFeature = (feature: { properties?: { slug?: string; name?: string } }, leafletLayer: Layer) => {
    const slug = feature.properties?.slug ?? ''
    const name = feature.properties?.name ?? 'Pune analysis cell'
    const data = screening.data?.zones[slug]
    const flood = demo ? demoFlood?.zones[slug]?.assessments.find(item => item.hazard === 'flood') : comparison.data?.zones.find(item => item.zone_id === slug)?.hazards.flood
    const slope = demoFlood?.zones[slug]?.metrics?.slope_mean_degrees
    const value = layer === 'rainfall' ? demo ? demoFlood ? demoFlood.rainfall_intensity_mm_h * demoFlood.rainfall_duration_hours : null : data?.rainfall_24h_mm : layer === 'temperature' ? demo ? null : data?.temperature_max_2d_c : layer === 'us_aqi' ? demo ? null : data?.us_aqi : flood?.score
    const popup = document.createElement('div')
    const heading = document.createElement('strong')
    heading.textContent = name
    const detail = document.createElement('p')
    detail.textContent = `${demo ? 'SIMULATED — NOT CURRENT CONDITIONS. ' : ''}${labels[layer]}: ${valueLabel(layer, value)}. ${demo && layer === 'flood_index' && demoFlood ? `Hypothetical ${demoFlood.rainfall_intensity_mm_h} mm/h for ${demoFlood.rainfall_duration_hours} hours. ${slope != null ? `Sourced mean slope ${slope}°. ` : 'Slope unavailable. '}` : ''}${layer === 'flood_index' ? 'Rainfall-led heuristic, not a flood probability. ' : ''}Analysis grid only, not a ward or inundation boundary.`
    popup.append(heading, detail)
    leafletLayer.bindPopup(popup)
    leafletLayer.on('click', () => setLocalityId(slug))
  }
  const onEachRoad = (feature: { properties?: { name?: string | null; highway_class?: string; source_url?: string } }, leafletLayer: Layer) => { const popup = document.createElement('div'); const title = document.createElement('strong'); title.textContent = feature.properties?.name || 'Unnamed mapped road'; const detail = document.createElement('p'); detail.textContent = `${feature.properties?.highway_class ?? 'Road'} · OpenStreetMap mapped`; popup.append(title, detail); if (feature.properties?.source_url) { const link = document.createElement('a'); link.href = feature.properties.source_url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = 'View OSM record'; popup.append(link) } leafletLayer.bindPopup(popup) }
  return <div className={`map-shell ${compact ? 'map-shell-compact' : ''}`}><div className={`map-wrap ${compact ? 'map-compact' : ''}`}>
    <MapContainer center={locality.center} zoom={compact ? 12 : 12} scrollWheelZoom={!compact} className="leaflet-map">
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <MapFlyTo center={locality.center}/>
      <MapBounds onChange={setBbox}/>
      {zones.data && <GeoJSON key={`${layer}-${demo}-${demoFlood?.zones['pune-grid-r2-c2']?.assessed_at}-${screening.dataUpdatedAt}-${comparison.dataUpdatedAt}-${locality.id}`} data={zones.data as unknown as FeatureCollection} style={feature => { const data = screeningValue(feature as unknown as ZoneFeature); const slug = feature?.properties?.slug as string; const floodLevel = demo ? demoFlood?.zones[slug]?.assessments.find(item => item.hazard === 'flood')?.level : comparison.data?.zones.find(item => item.zone_id === slug)?.hazards.flood?.level; const band: ScreeningBand = layer === 'flood_index' ? floodLevel ?? 'unavailable' : demo ? 'unavailable' : data?.bands[layer] ?? 'unavailable'; const selected = slug === locality.id; return { color: selected ? '#183e58' : '#577a85', weight: selected ? 3 : 1.2, fillColor: bandColors[band], fillOpacity: selected ? 0.55 : 0.38 } }} onEachFeature={onEachFeature}/ >}
      {showRoads && roadFeatures.length > 0 && <GeoJSON key={`roads-${bbox}-${roads.dataUpdatedAt}`} data={{ type: 'FeatureCollection', features: roadFeatures } as FeatureCollection} style={{ color: '#55758a', weight: 2.5, opacity: 0.7 }} onEachFeature={onEachRoad}/ >}
      {visibleFacilities.map((item, index) => <CircleMarker key={`${item.osm_type ?? 'mapped'}-${item.osm_id ?? index}`} center={[item.lat, item.lng]} radius={6} pathOptions={{ color: '#fff', weight: 1.5, fillColor: item.kind === 'hospital' ? '#347f97' : item.kind === 'school' ? '#c38d4d' : '#568b73', fillOpacity: 0.95 }}><Popup><strong>{item.name}</strong><br/>{item.kind.replace('_', ' ')} · OpenStreetMap mapped<br/>Not independently verified{item.source_url && <><br/><a href={item.source_url} target="_blank" rel="noreferrer">View OSM record</a></>}</Popup></CircleMarker>)}
    </MapContainer>
    {compact && <div className="map-note"><span className="map-note-dot"/>{zones.isLoading ? 'Loading analysis grid…' : zones.error ? 'Grid unavailable' : demo ? demoScenarioId === 'extreme_rainfall' ? `SIMULATED extreme rainfall · ${demoFlood ? `${demoFlood.rainfall_intensity_mm_h} mm/h for ${demoFlood.rainfall_duration_hours} h` : 'loading screening…'}` : 'No flood map screening for selected scenario' : screening.isLoading ? 'Loading model screening…' : screening.error ? 'Screening unavailable' : locality.id.startsWith('pune-grid-') ? `Selected ${locality.name} · analysis cell, not an official ward` : 'Pune overview · select a grid cell for local evidence'}</div>}
    </div>
    {!compact && <aside className="map-side-panel" aria-label="Map controls and legend">
      <div className="map-controls" aria-label="Map layers"><div className="map-control-title">SCREENING LAYER</div><div className="map-control-row">{(['rainfall', 'temperature', 'us_aqi', 'flood_index'] as const).map(item => <button key={item} type="button" className={layer === item ? 'selected' : ''} aria-pressed={layer === item} onClick={() => setLayer(item)}>{labels[item]}</button>)}</div><div className="map-control-title">MAPPED FEATURES IN VIEW</div><div className="map-control-checks"><label><input type="checkbox" checked={showHospitals} onChange={e => setShowHospitals(e.target.checked)}/>Hospitals {counts?.hospital ?? '—'}</label><label><input type="checkbox" checked={showSchools} onChange={e => setShowSchools(e.target.checked)}/>Schools {counts?.school ?? '—'}</label><label><input type="checkbox" checked={showEmergency} onChange={e => setShowEmergency(e.target.checked)}/>Fire stations {counts?.fire_station ?? '—'}</label><label><input type="checkbox" checked={showRoads} onChange={e => setShowRoads(e.target.checked)}/>Roads {showRoads ? roads.isLoading ? 'loading…' : roads.data?.returned_count ?? '—' : 'off'}</label></div>
        <div className="map-legend"><strong>{demo ? 'SIMULATED · ' : ''}{labels[layer]} display bins</strong><div>{(['low', 'moderate', 'high', 'severe', 'unavailable'] as const).map(band => <span key={band}><i style={{ background: bandColors[band] }}/>{band}</span>)}</div><small>{demo && demoFlood ? `Hypothetical ${demoFlood.rainfall_intensity_mm_h} mm/h × ${demoFlood.rainfall_duration_hours} h. ` : ''}{layer === 'flood_index' ? 'Heuristic rainfall index · not flood probability' : demo ? 'Unavailable in this scenario' : 'Model-derived screening · not flood boundaries'}</small></div>
      </div>
      <div className="map-source-status" role="status"><strong>{demo ? 'SIMULATION — NOT CURRENT CONDITIONS' : 'Map data'}</strong><p>{zones.isLoading ? 'Loading analysis grid…' : zones.error ? 'Grid unavailable' : demo ? demoFlood ? `Extreme rainfall · ${demoFlood.rainfall_intensity_mm_h} mm/h for ${demoFlood.rainfall_duration_hours} hours. Select a cell for its computed index.` : demoScenarioId === 'extreme_rainfall' ? 'Loading hypothetical screening…' : 'Flood screening unavailable for this scenario.' : screening.isLoading ? 'Loading model screening…' : screening.error ? 'Screening unavailable' : locality.id.startsWith('pune-grid-') ? `Selected ${locality.name} · analysis cell, not an official ward` : 'Pune overview · select a grid cell for local evidence'}</p><p>{demo ? 'Switch to live mode for sourced OSM layers.' : facilities.isLoading ? 'Loading mapped facilities…' : facilities.error || facilities.data?.status === 'unavailable' ? 'Facility data temporarily unavailable.' : facilities.data?.storage === 'postgis' ? 'OSM facilities · Supabase PostGIS' : facilities.data?.storage === 'local_geojson_preview' ? 'OSM source preview · Database import pending' : 'Facility data unavailable.'}</p>{!demo && showRoads && <p>{roads.isLoading ? 'Loading mapped roads…' : roads.error || roads.data?.status === 'unavailable' ? 'Road data temporarily unavailable.' : roads.data?.storage === 'postgis' ? 'OSM roads · Supabase PostGIS' : roads.data?.storage === 'local_geojson_preview' ? 'OSM roads · local source preview' : 'Road data unavailable.'}</p>}{!demo && facilities.data?.truncated && <p>Showing {facilities.data.returned_count} of {facilities.data.total_count} mapped facilities; zoom in for more.</p>}{!demo && showRoads && roads.data?.truncated && <p>Showing {roads.data.returned_count} of {roads.data.total_count} mapped roads; zoom in for more.</p>}</div>
    </aside>}
  </div>
}
