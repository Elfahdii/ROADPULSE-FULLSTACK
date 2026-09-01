import { Fragment, useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Popup, useMap } from 'react-leaflet'
import { BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Camera,
  Clock,
  CloudUpload,
  Download,
  FileText,
  FileVideo,
  Gauge,
  History,
  Info,
  LayoutDashboard,
  Map as MapIcon,
  MapPin,
  Play,
  Search,
  RotateCcw,
  Route,
  ShieldCheck,
  Smartphone,
  Upload,
  Video,
  Wifi,
  XCircle,
} from 'lucide-react'
import { API_URL, createAnalysisJob, getHealth, getJob, getSurvey, listSurveys } from './api'

const CLASS_LABELS = {
  pothole: 'Pothole',
  longitudinal_crack: 'Longitudinal Crack',
  transverse_crack: 'Transverse Crack',
  fatigue_crack: 'Fatigue Crack',
}

const CLASS_COLORS = {
  pothole: '#ff4f5e',
  longitudinal_crack: '#ff8a2a',
  transverse_crack: '#ffc12d',
  fatigue_crack: '#7c4ee8',
}

const STATUS_COLORS = {
  Good: '#55d867',
  Fair: '#ffc83d',
  Poor: '#ff8a2a',
  Critical: '#ff4f5e',
}

function sourceLabel(source) {
  if (source === 'phone_gps_track') return 'Phone GPS track'
  if (source === 'video_metadata') return 'Embedded in video'
  return 'Unavailable'
}

function roughnessSourceLabel(source) {
  if (source === 'phone_motion_sensors') return 'Phone motion sensors'
  if (source === 'video_motion_proxy') return 'Video motion estimate'
  return 'Unavailable'
}

function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return '—'
  const total = Math.max(0, Math.round(Number(seconds)))
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins} min ${String(secs).padStart(2, '0')} sec`
}

function StatusPill({ value }) {
  const key = (value || 'Unknown').toLowerCase()
  return <span className={`status-pill status-${key}`}>{value || 'Unknown'}</span>
}

function MetricCard({ icon: Icon, label, value, helper, tone = 'blue' }) {
  return (
    <div className="metric-card">
      <div className={`metric-icon tone-${tone}`}><Icon size={22} /></div>
      <div className="metric-copy">
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value}</div>
        {helper && <div className="metric-helper">{helper}</div>}
      </div>
    </div>
  )
}

function FitMap({ points, center }) {
  const map = useMap()
  useEffect(() => {
    if (points?.length > 1) {
      map.fitBounds(points.map(p => [p.latitude, p.longitude]), { padding: [24, 24] })
    } else if (center?.[0] != null && center?.[1] != null) {
      map.setView(center, 16)
    }
  }, [map, points, center])
  return null
}

function RoadMap({ result }) {
  const location = result?.location
  const defects = result?.defects || []
  const route = location?.route_points || []
  const hasLocation = location?.center_lat != null && location?.center_lon != null
  const center = hasLocation
    ? [location.center_lat, location.center_lon]
    : route.length ? [route[0].latitude, route[0].longitude] : null
  const routeColor = STATUS_COLORS[result?.summary?.status] || '#4cc9f0'

  if (!center) {
    return (
      <div className="map-card map-unavailable">
        <MapPin size={34} />
        <strong>Location unavailable</strong>
        <span>No embedded video GPS or synchronized phone GPS was found.</span>
      </div>
    )
  }

  return (
    <div className="map-card">
      <MapContainer center={center} zoom={location?.center_lat != null ? 16 : 11} scrollWheelZoom className="map-view">
        <FitMap points={route} center={center} />
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {route.length > 1 && (
          <Polyline positions={route.map(p => [p.latitude, p.longitude])} pathOptions={{ color: routeColor, weight: 5, opacity: 0.9 }} />
        )}
        {defects.filter(d => d.latitude != null && d.longitude != null).map((d) => (
          <CircleMarker
            key={d.id}
            center={[d.latitude, d.longitude]}
            radius={7}
            pathOptions={{ color: CLASS_COLORS[d.class_name] || '#ff5d73', fillColor: CLASS_COLORS[d.class_name] || '#ff5d73', fillOpacity: 0.95 }}
          >
            <Popup>
              <strong>{CLASS_LABELS[d.class_name] || d.class_name}</strong><br />
              Confidence: {(d.confidence * 100).toFixed(1)}%<br />
              {d.road_name || ''}
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
function PersistentRoadMap({ surveys }) {
  const roadLayers = (surveys || [])
    .filter(item => item?.result?.location)
    .map(item => ({
      surveyId: item.survey_id,
      route: item.result.location?.route_points || [],
      center: item.result.location?.center_lat != null && item.result.location?.center_lon != null
        ? { latitude: item.result.location.center_lat, longitude: item.result.location.center_lon }
        : null,
      result: item.result,
    }))
    .filter(item => item.route.length > 0 || item.center)

  const allPoints = roadLayers.flatMap(item => item.route.length ? item.route : [item.center])
  const defaultCenter = [26.0667, 50.5577]
  const center = allPoints.length
    ? [allPoints[0].latitude, allPoints[0].longitude]
    : defaultCenter

  return (
    <div className="map-card">
      <MapContainer center={center} zoom={allPoints.length ? 13 : 10} scrollWheelZoom className="map-view">
        <FitMap points={allPoints} center={center} />
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

        {roadLayers.map(({ surveyId, route, center: roadCenter, result }) => {
          const color = STATUS_COLORS[result.summary?.status] || '#4cc9f0'
          const markerPoint = roadCenter || route[0]
          const popup = (
            <Popup>
              <strong>{result.location?.road_name || 'Road analysis'}</strong><br />
              Health: {result.summary?.health_score ?? '—'}<br />
              Status: {result.summary?.status || 'Unknown'}
            </Popup>
          )

          return (
            <Fragment key={surveyId}>
              {route.length > 1 ? (
                <Polyline positions={route.map(p => [p.latitude, p.longitude])} pathOptions={{ color, weight: 7, opacity: 0.9 }}>
                  {popup}
                </Polyline>
              ) : markerPoint ? (
                <CircleMarker center={[markerPoint.latitude, markerPoint.longitude]} radius={9} pathOptions={{ color, fillColor: color, fillOpacity: 0.9 }}>
                  {popup}
                </CircleMarker>
              ) : null}

              {(result.defects || []).filter(d => d.latitude != null && d.longitude != null).map(defect => (
                <CircleMarker
                  key={`${surveyId}-${defect.id}`}
                  center={[defect.latitude, defect.longitude]}
                  radius={5}
                  pathOptions={{ color: CLASS_COLORS[defect.class_name] || '#ff5d73', fillColor: CLASS_COLORS[defect.class_name] || '#ff5d73', fillOpacity: 0.95 }}
                >
                  <Popup>
                    <strong>{CLASS_LABELS[defect.class_name] || defect.class_name}</strong><br />
                    {result.location?.road_name || 'Road location'}
                  </Popup>
                </CircleMarker>
              ))}
            </Fragment>
          )
        })}
      </MapContainer>
    </div>
  )
}

function downloadReport(result) {
  if (!result) return
  const rows = [
    ['RoadPulse Road Analysis Report'],
    ['Road', result.location?.road_name || 'Unavailable'],
    ['Address', result.location?.formatted_address || 'Unavailable'],
    ['Latitude', result.location?.center_lat ?? ''],
    ['Longitude', result.location?.center_lon ?? ''],
    ['GPS Source', sourceLabel(result.location?.source)],
    ['Health Score', result.summary?.health_score ?? ''],
    ['Condition', result.summary?.status || ''],
    ['Roughness Index', result.summary?.roughness_index ?? ''],
    ['Roughness Label', result.summary?.roughness_label || ''],
    ['Roughness Source', roughnessSourceLabel(result.summary?.roughness_source)],
    ['Unique Defects', result.summary?.total_defects ?? 0],
    ['Video File', result.video?.filename || ''],
    ['Duration (sec)', result.video?.duration_sec ?? ''],
    ['Analysis Sampling (fps)', result.video?.analysis_sampling_fps ?? ''],
    ['Frame Stride', result.video?.analysis_frame_stride ?? ''],
    [],
    ['Type', 'Confidence', 'Road', 'Latitude', 'Longitude'],
    ...(result.defects || []).map(d => [
      CLASS_LABELS[d.class_name] || d.class_name,
      d.confidence,
      d.road_name || '',
      d.latitude ?? '',
      d.longitude ?? '',
    ]),
  ]
  const csv = rows.map(row => row.map(v => `"${String(v ?? '').replaceAll('"', '""')}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'roadpulse-analysis-report.csv'
  a.click()
  URL.revokeObjectURL(url)
}

function UploadSurvey({ onStarted }) {
  const [video, setVideo] = useState(null)
  const [gpsFile, setGpsFile] = useState(null)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const uploadLockRef = useRef(false)

  async function submit() {
    if (!video) return setError('Choose a road video first.')
    if (uploadLockRef.current) return
    uploadLockRef.current = true
    setUploading(true)
    setUploadProgress(0)
    setError('')
    try {
      const job = await createAnalysisJob({
        videoFile: video,
        gpsFile,
        onUploadProgress: progress => {
          if (progress != null) setUploadProgress(progress)
        },
      })
      onStarted(job.job_id)
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Could not start analysis.')
    } finally {
      uploadLockRef.current = false
      setUploading(false)
    }
  }

  return (
    <section className="panel upload-panel">
      <div className="panel-heading-row">
        <div>
          <div className="panel-title"><CloudUpload size={18} /> Upload road video</div>
          <p className="muted">RoadPulse automatically checks the video for GPS metadata, identifies the road, detects damage and estimates roughness.</p>
        </div>
      </div>
      <label className="file-drop">
        <FileVideo size={34} />
        <strong>{video ? video.name : 'Choose road video'}</strong>
        <span>MP4, MOV, WEBM, AVI or MKV</span>
        <input type="file" accept="video/*" disabled={uploading} onChange={e => setVideo(e.target.files?.[0] || null)} hidden />
      </label>
      <div className="auto-analysis-strip">
        <div><MapPin size={18} /><span><strong>Automatic location</strong><small>Uses embedded video GPS when available</small></span></div>
        <div><Activity size={18} /><span><strong>Automatic roughness</strong><small>Uses video motion as a fallback estimate</small></span></div>
        <div><ShieldCheck size={18} /><span><strong>Automatic AI settings</strong><small>No thresholds or frame settings required</small></span></div>
      </div>
      <details className="gps-fallback">
        <summary>Optional GPS track fallback</summary>
        <p>If the video was exported through WhatsApp, social media or an editor, its GPS metadata may have been removed. You can attach a synchronized RoadPulse GPS JSON track instead. Road/street name is still resolved automatically.</p>
        <label className="gps-file-row">
          <MapPin size={16} />
          <span><strong>{gpsFile ? gpsFile.name : 'Choose GPS JSON track'}</strong><small>Optional · synchronized latitude/longitude points</small></span>
          <input type="file" accept="application/json,.json" disabled={uploading} onChange={e => setGpsFile(e.target.files?.[0] || null)} hidden />
        </label>
      </details>
      {error && <div className="error-box">{error}</div>}
      {uploading && (
        <div className="upload-status" role="status" aria-live="polite">
          <div className="progress-head">
            <span>{uploadProgress >= 100 ? 'Starting analysis…' : 'Uploading video…'}</span>
            <strong>{uploadProgress}%</strong>
          </div>
          <div className="progress-track"><div className="progress-fill" style={{ width: `${uploadProgress}%` }} /></div>
          <small>Keep this page open. Analysis begins automatically after the upload.</small>
        </div>
      )}
      <button className="primary-button" disabled={uploading} aria-busy={uploading} onClick={submit}>
        {uploading ? <><Upload size={18} /> {uploadProgress >= 100 ? 'Starting analysis…' : `Uploading ${uploadProgress}%`}</> : <><Play size={18} /> Analyze road video</>}
      </button>
      <p className="micro-note">If an exported video no longer contains GPS metadata, RoadPulse will say location unavailable rather than guessing. Use “Record with Phone” for synchronized GPS and motion capture.</p>
    </section>
  )
}

function pickMimeType() {
  const candidates = ['video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm']
  return candidates.find(t => window.MediaRecorder?.isTypeSupported?.(t)) || ''
}

function RecordSurvey({ onStarted }) {
  const previewRef = useRef(null)
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const gpsRef = useRef([])
  const motionRef = useRef([])
  const watchRef = useRef(null)
  const motionHandlerRef = useRef(null)
  const startPerfRef = useRef(0)
  const [recording, setRecording] = useState(false)
  const [permissionMessage, setPermissionMessage] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState('')
  const timerRef = useRef(null)

  async function requestMotionPermission() {
    if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') {
      const state = await DeviceMotionEvent.requestPermission()
      if (state !== 'granted') throw new Error('Motion sensor permission was denied.')
    }
  }

  async function start() {
    setError('')
    setPermissionMessage('')
    try {
      if (!window.isSecureContext && location.hostname !== 'localhost') throw new Error('Phone recording requires HTTPS.')
      if (!('geolocation' in navigator)) throw new Error('This browser does not provide geolocation. RoadPulse phone video analysis requires GPS.')

      await requestMotionPermission()

      // Get one GPS fix before recording starts. This avoids saving a phone
      // road video with an empty GPS track while the permission dialog is pending.
      const initialPosition = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
          resolve,
          err => reject(new Error(`GPS is required for a phone road video: ${err.message}`)),
          { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 },
        )
      })

      // Keep phone recordings uploadable and within the backend's memory
      // budget. Unrestricted mobile cameras commonly default to 4K.
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280, max: 1280 },
          height: { ideal: 720, max: 720 },
          frameRate: { ideal: 30, max: 30 },
        },
        audio: false,
      })
      streamRef.current = stream
      if (previewRef.current) previewRef.current.srcObject = stream

      const mimeType = pickMimeType()
      const recorderOptions = {
        ...(mimeType ? { mimeType } : {}),
        videoBitsPerSecond: 2_500_000,
      }
      let recorder
      try {
        recorder = new MediaRecorder(stream, recorderOptions)
      } catch {
        // Older mobile browsers may reject the bitrate option even though
        // MediaRecorder itself is supported.
        recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      }
      recorderRef.current = recorder
      chunksRef.current = []
      motionRef.current = []
      startPerfRef.current = performance.now()
      gpsRef.current = [{
        t_ms: 0,
        latitude: initialPosition.coords.latitude,
        longitude: initialPosition.coords.longitude,
        accuracy: initialPosition.coords.accuracy,
        speed: initialPosition.coords.speed,
        heading: initialPosition.coords.heading,
      }]

      recorder.ondataavailable = e => { if (e.data?.size) chunksRef.current.push(e.data) }
      recorder.start(1000)

      watchRef.current = navigator.geolocation.watchPosition(
        pos => gpsRef.current.push({
          t_ms: performance.now() - startPerfRef.current,
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          speed: pos.coords.speed,
          heading: pos.coords.heading,
        }),
        err => setPermissionMessage(`GPS warning: ${err.message}`),
        { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 },
      )

      const motionHandler = e => motionRef.current.push({
        t_ms: performance.now() - startPerfRef.current,
        acceleration: e.acceleration ? { x: e.acceleration.x, y: e.acceleration.y, z: e.acceleration.z } : null,
        accelerationIncludingGravity: e.accelerationIncludingGravity ? { x: e.accelerationIncludingGravity.x, y: e.accelerationIncludingGravity.y, z: e.accelerationIncludingGravity.z } : null,
        rotationRate: e.rotationRate ? { alpha: e.rotationRate.alpha, beta: e.rotationRate.beta, gamma: e.rotationRate.gamma } : null,
        interval: e.interval,
      })
      motionHandlerRef.current = motionHandler
      window.addEventListener('devicemotion', motionHandler)

      setRecording(true)
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed(Math.floor((performance.now() - startPerfRef.current) / 1000)), 500)
    } catch (e) {
      setError(e.message || 'Could not start recording.')
    }
  }

  async function stop() {
    if (!recorderRef.current) return
    setRecording(false)
    clearInterval(timerRef.current)
    if (watchRef.current != null) navigator.geolocation.clearWatch(watchRef.current)
    if (motionHandlerRef.current) window.removeEventListener('devicemotion', motionHandlerRef.current)

    const recorder = recorderRef.current
    const stopped = new Promise(resolve => { recorder.onstop = resolve })
    recorder.stop()
    await stopped
    streamRef.current?.getTracks().forEach(t => t.stop())

    try {
      const type = recorder.mimeType || 'video/webm'
      const ext = type.includes('mp4') ? 'mp4' : 'webm'
      const blob = new Blob(chunksRef.current, { type })
      const videoFile = new File([blob], `roadpulse-phone-video.${ext}`, { type })
      const gpsFile = new File([JSON.stringify(gpsRef.current)], 'gps.json', { type: 'application/json' })
      const motionFile = new File([JSON.stringify(motionRef.current)], 'motion.json', { type: 'application/json' })
      const job = await createAnalysisJob({ videoFile, gpsFile, motionFile })
      onStarted(job.job_id)
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Could not upload the recorded road video.')
    }
  }

  useEffect(() => () => {
    clearInterval(timerRef.current)
    if (watchRef.current != null) navigator.geolocation.clearWatch(watchRef.current)
    if (motionHandlerRef.current) window.removeEventListener('devicemotion', motionHandlerRef.current)
    streamRef.current?.getTracks().forEach(t => t.stop())
  }, [])

  return (
    <section className="panel phone-panel">
      <div className="panel-title"><Smartphone size={18} /> Record with phone</div>
      <p className="muted">RoadPulse records the camera, GPS track and motion sensors on the same clock. Road name, defect coordinates and roughness are calculated automatically.</p>
      <div className="camera-shell">
        <video ref={previewRef} autoPlay muted playsInline />
        {!recording && <div className="camera-placeholder"><Video size={34} /><span>Camera preview</span></div>}
        {recording && <div className="recording-badge"><span className="record-dot" /> REC {elapsed}s</div>}
      </div>
      {permissionMessage && <div className="warning-box"><AlertTriangle size={18} />{permissionMessage}</div>}
      {error && <div className="error-box">{error}</div>}
      <div className="record-actions">
        {!recording
          ? <button className="primary-button" onClick={start}><Camera size={18} /> Start road video</button>
          : <button className="danger-button" onClick={stop}><span className="stop-square" /> Stop & analyze</button>}
      </div>
      <div className="auto-analysis-strip phone-strip">
        <div><MapPin size={18} /><span><strong>GPS track</strong><small>Captured continuously</small></span></div>
        <div><Activity size={18} /><span><strong>Motion sensors</strong><small>Used for roughness</small></span></div>
        <div><Route size={18} /><span><strong>Road identification</strong><small>Resolved automatically</small></span></div>
      </div>
      <p className="micro-note">Phone recording requires HTTPS and permission for Camera, Location and Motion sensors.</p>
    </section>
  )
}

function AnalysisProgress({ job, jobId, onReset }) {
  const progress = job?.progress ?? 0
  return (
    <div className="analysis-progress-page">
      <section className="panel analysis-header">
        <div>
          <div className="panel-title">Road analysis in progress</div>
          <div className="job-id">{jobId}</div>
        </div>
        <button className="ghost-button" onClick={onReset}><RotateCcw size={16} /> Cancel / new video</button>
      </section>
      <section className="panel progress-panel">
        <div className="progress-head"><span>{job?.message || 'Preparing analysis…'}</span><strong>{Math.round(progress)}%</strong></div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${progress}%` }} /></div>
        <div className="processing-steps">
          <span className={progress >= 10 ? 'done' : ''}>Video decoding</span>
          <span className={progress >= 35 ? 'done' : ''}>YOLO detection</span>
          <span className={progress >= 88 ? 'done' : ''}>Roughness</span>
          <span className={progress >= 94 ? 'done' : ''}>GPS & road lookup</span>
        </div>
      </section>
    </div>
  )
}

function AnalysisResults({ result }) {
  const summary = result.summary || {}
  const counts = summary.counts || {}
  const chartData = Object.entries(CLASS_LABELS).map(([key, label]) => ({ key, name: label, count: counts[key] || 0 }))
  const sortedDefects = [...(result.defects || [])].sort((a, b) => b.confidence - a.confidence)
  const evidence = sortedDefects.filter(d => d.evidence_url)
  const preview = evidence[0]
  const location = result.location || {}
  const annotatedVideoUrl =
      result.video?.annotated_video_url
  const analysisSamplingFps = result.video?.analysis_sampling_fps
    ?? (result.video?.fps && result.video?.analysis_frame_stride
      ? result.video.fps / result.video.analysis_frame_stride
      : null)
  const samplingLabel = analysisSamplingFps == null
    ? 'YOLO bounding boxes'
    : `${Number(analysisSamplingFps).toFixed(analysisSamplingFps < 10 ? 1 : 0)} analyzed frame${Math.abs(analysisSamplingFps - 1) < 0.01 ? '' : 's'}/second · YOLO bounding boxes`

  return (
    <div className="results-stack">
      {result.warnings?.length > 0 && (
        <div className="warning-box compact-warning">
          <AlertTriangle size={18} />
          <div>{result.warnings.map((w, i) => <div key={i}>{w}</div>)}</div>
        </div>
      )}

      <div className="metrics-grid">
        <MetricCard icon={Gauge} label="Road Health Score" value={`${summary.health_score ?? '—'} / 100`} helper={<StatusPill value={summary.status} />} tone="green" />
        <MetricCard icon={AlertTriangle} label="Unique Defects" value={summary.total_defects ?? 0} helper="Deduplicated events" tone="yellow" />
        <MetricCard icon={Activity} label="Roughness Index" value={summary.roughness_index == null ? 'Unavailable' : `${summary.roughness_index} / 100`} helper={`${summary.roughness_label || 'Unavailable'} · ${roughnessSourceLabel(summary.roughness_source)}`} tone="red" />
        <MetricCard icon={MapPin} label="Road" value={location.road_name || 'Location unavailable'} helper={location.formatted_address || sourceLabel(location.source)} tone="blue" />
      </div>

      <div className="overview-grid">
        <section className="panel map-panel" id="map-section">
          <div className="panel-title">Road Location</div>
          <RoadMap result={result} />
        </section>

        <section className="panel recent-panel">
          <div className="panel-heading-row">
            <div className="panel-title">Selected Road Analysis</div>
            <StatusPill value="Completed" />
          </div>
          <div className="recent-content">
            <div className="recent-preview">
              {preview
                ? <img src={`${API_URL}${preview.evidence_url}`} alt={preview.class_name} />
                : <div className="recent-placeholder"><FileVideo size={42} /><span>No defect evidence image</span></div>}
            </div>
            <div className="recent-details">
              <h3>{location.road_name || 'Road location unavailable'}</h3>
              <div className="detail-line"><MapPin size={16} /><span>{location.formatted_address || 'No road address available'}</span></div>
              <div className="detail-line"><Clock size={16} /><span>{formatDuration(result.video?.duration_sec)}</span></div>
              <div className="detail-line"><Route size={16} /><span>{location.center_lat != null ? `${location.center_lat.toFixed(6)}, ${location.center_lon.toFixed(6)}` : 'Coordinates unavailable'}</span></div>
              <div className="detail-line"><FileVideo size={16} /><span>{result.video?.filename || 'Uploaded road video'}</span></div>
            </div>
          </div>
          <div className="recent-stats">
            <div><span>Potholes</span><strong>{counts.pothole || 0}</strong></div>
            <div><span>Cracks</span><strong>{(counts.longitudinal_crack || 0) + (counts.transverse_crack || 0) + (counts.fatigue_crack || 0)}</strong></div>
            <div><span>Roughness</span><strong className="danger-text">{summary.roughness_label || 'Unavailable'}</strong></div>
            <div><span>Health Score</span><strong className="danger-text">{summary.health_score ?? '—'} / 100</strong></div>
          </div>
          <div className="recent-actions">
            <button className="primary-button compact" onClick={() => document.getElementById('defects-section')?.scrollIntoView({ behavior: 'smooth' })}>View Details</button>
            <button className="ghost-button compact" onClick={() => downloadReport(result)}><Download size={16} /> Download Report</button>
          </div>
        </section>
      </div>
      {annotatedVideoUrl && (
          <section className="panel analyzed-video-panel">

            <div className="panel-heading-row">
              <div className="panel-title">
                Analyzed Video
              </div>

              <span className="muted small">
        {samplingLabel}
      </span>
            </div>

            <video
                className="analyzed-video-player"
                controls
                playsInline
                preload="metadata"
                src={`${API_URL}${annotatedVideoUrl}`}
            >
              Your browser does not support video playback.
            </video>

          </section>
      )}

      <div className="analytics-grid">
        <section className="panel chart-panel">
          <div className="panel-title">Defect Distribution</div>
          <div className="chart-wrap compact-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ left: -15, right: 8, top: 10, bottom: 26 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#213047" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: '#9fb0c6', fontSize: 10 }} interval={0} angle={-8} textAnchor="end" height={52} />
                <YAxis allowDecimals={false} tick={{ fill: '#93a7c3', fontSize: 10 }} />
                <Tooltip contentStyle={{ background: '#111c2c', border: '1px solid #29405e', borderRadius: 10 }} />
                <Bar dataKey="count" radius={[5, 5, 0, 0]}>
                  {chartData.map(item => <Cell key={item.key} fill={CLASS_COLORS[item.key]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-total">Total: <strong>{summary.total_defects ?? 0}</strong></div>
        </section>

        <section className="panel defects-panel" id="defects-section">
          <div className="panel-heading-row">
            <div className="panel-title">Detected Defects (Top 10)</div>
            <span className="muted small">{result.defects?.length || 0} total</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Type</th><th>Confidence</th><th>Road</th></tr></thead>
              <tbody>
                {sortedDefects.length === 0 && <tr><td colSpan="4" className="empty-cell">No defects detected.</td></tr>}
                {sortedDefects.slice(0, 10).map((d, i) => (
                  <tr key={d.id}>
                    <td>{i + 1}</td>
                    <td>{CLASS_LABELS[d.class_name] || d.class_name}</td>
                    <td>{(d.confidence * 100).toFixed(1)}%</td>
                    <td>{d.road_name || location.road_name || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel evidence-panel">
          <div className="panel-heading-row">
            <div className="panel-title">Top Evidence</div>
            <span className="muted small">Highest confidence</span>
          </div>
          {evidence.length ? (
            <div className="evidence-grid compact-evidence">
              {evidence.slice(0, 4).map(d => (
                <div className="evidence-card" key={`e-${d.id}`}>
                  <img src={`${API_URL}${d.evidence_url}`} alt={d.class_name} />
                  <div className="evidence-overlay">
                    <span style={{ background: CLASS_COLORS[d.class_name] || '#ff5d73' }}>{CLASS_LABELS[d.class_name] || d.class_name}</span>
                    <strong>{d.confidence.toFixed(2)}</strong>
                  </div>
                </div>
              ))}
            </div>
          ) : <div className="empty-state">No evidence frames were generated.</div>}
        </section>
      </div>

      <section className="metadata-strip" id="report-section">
        <div><MapPin size={18} /><span><small>GPS Source</small><strong className={location.source === 'none' ? 'danger-text' : 'success-text'}>{sourceLabel(location.source)}</strong><em>{location.accuracy_m != null ? `Accuracy: ±${Math.round(location.accuracy_m)} m` : 'Accuracy not reported'}</em></span></div>
        <div><Route size={18} /><span><small>Coordinates</small><strong>{location.center_lat != null ? `${location.center_lat.toFixed(6)}, ${location.center_lon.toFixed(6)}` : 'Unavailable'}</strong></span></div>
        <div><Clock size={18} /><span><small>Video Duration</small><strong>{formatDuration(result.video?.duration_sec)}</strong></span></div>
        <div><FileVideo size={18} /><span><small>Video File</small><strong>{result.video?.filename || 'Unknown'}</strong></span></div>
      </section>
    </div>
  )
}


function formatSurveyDate(value) {
  if (!value) return 'Unknown date'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString()
}

function conditionFromScore(score) {
  if (score == null) return 'Unknown'
  if (score >= 80) return 'Good'
  if (score >= 60) return 'Fair'
  if (score >= 40) return 'Poor'
  return 'Critical'
}

function RoadRankings({ surveys, onOpenAnalysis }) {
  const grouped = new Map()

  ;(surveys || []).forEach((analysis) => {
    const road = analysis.road_name || analysis.formatted_address || analysis.filename || 'Unidentified road'
    const key = `${analysis.road_name || ''}|${analysis.formatted_address || road}`.toLowerCase()
    const current = grouped.get(key) || {
      road,
      address: analysis.formatted_address || analysis.filename || 'Location unavailable',
      latestId: analysis.survey_id,
      analysisCount: 0,
      healthTotal: 0,
      healthCount: 0,
      totalDefects: 0,
    }
    const health = analysis.health_score == null ? null : Number(analysis.health_score)
    current.analysisCount += 1
    current.totalDefects += Number(analysis.total_defects || 0)
    if (Number.isFinite(health)) {
      current.healthTotal += health
      current.healthCount += 1
    }
    grouped.set(key, current)
  })

  const rankings = [...grouped.values()]
    .map(item => ({
      ...item,
      averageHealth: item.healthCount ? Math.round(item.healthTotal / item.healthCount) : null,
    }))
    .sort((a, b) => {
      if (a.averageHealth == null) return 1
      if (b.averageHealth == null) return -1
      return b.averageHealth - a.averageHealth || a.totalDefects - b.totalDefects
    })

  return (
    <section className="panel road-rankings-panel">
      <div className="panel-heading-row rankings-heading">
        <div>
          <div className="panel-title"><BarChart3 size={18} /> Road Rankings</div>
          <p className="muted">Roads are ranked by average health score, from best condition to most urgent attention.</p>
        </div>
        <span className="muted small">{rankings.length} roads</span>
      </div>

      {rankings.length === 0 ? (
        <div className="ranking-empty">Analyze a road video to create the first ranking.</div>
      ) : (
        <div className="ranking-list">
          <div className="ranking-header"><span>Rank</span><span>Road</span><span>Analyses</span><span>Health</span><span>Defects</span><span>Condition</span></div>
          {rankings.map((road, index) => {
            const condition = conditionFromScore(road.averageHealth)
            const rankingNote = rankings.length === 1 ? 'Only ranked road' : index === 0 ? 'Best condition' : index === rankings.length - 1 ? 'Needs attention' : ''
            return (
              <button className="ranking-row" key={`${road.road}-${road.latestId}`} onClick={() => onOpenAnalysis(road.latestId)}>
                <span className={`rank-number rank-${index + 1}`}>#{index + 1}</span>
                <span className="ranking-road"><strong>{road.road}</strong><small>{rankingNote || road.address}</small></span>
                <strong>{road.analysisCount}</strong>
                <strong>{road.averageHealth == null ? '—' : `${road.averageHealth} / 100`}</strong>
                <strong>{road.totalDefects}</strong>
                <StatusPill value={condition} />
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}

function AnalysisHistoryPage({ surveys, selectedAnalysisId, onOpenAnalysis, onNewAnalysis }) {
  return (
    <section className="panel history-page">
      <div className="panel-heading-row history-heading">
        <div>
          <div className="panel-title"><History size={18} /> Analysis History</div>
          <p className="muted">Completed road-video analyses stay available after you start a new analysis or restart the dashboard.</p>
        </div>
        <button className="primary-button compact" onClick={onNewAnalysis}><Upload size={17} /> Analyze new video</button>
      </div>

      {surveys.length === 0 ? (
        <div className="history-empty">
          <History size={36} />
          <strong>No saved analyses yet</strong>
          <span>Your first completed analysis will appear here automatically.</span>
        </div>
      ) : (
        <div className="history-list">
          {surveys.map((survey) => (
            <button className={`history-row ${selectedAnalysisId === survey.survey_id ? 'selected' : ''}`} key={survey.survey_id} onClick={() => onOpenAnalysis(survey.survey_id)}>
              <div className="history-road">
                <div className="history-icon"><Route size={17} /></div>
                <span>
                  <strong>{survey.road_name || survey.filename || 'Road location unavailable'}</strong>
                  <small>{survey.formatted_address || survey.filename || survey.survey_id}</small>
                </span>
              </div>
              <div><small>Date</small><strong>{formatSurveyDate(survey.processed_at)}</strong></div>
              <div><small>Health</small><strong>{survey.health_score ?? '—'} / 100</strong></div>
              <div><small>Defects</small><strong>{survey.total_defects ?? 0}</strong></div>
              <div><small>Roughness</small><strong>{survey.roughness_label || 'Unavailable'}</strong></div>
              <span className="history-open">{selectedAnalysisId === survey.survey_id ? 'Selected' : 'Select'}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

function HistoryReportsPage({ surveys, result, selectedAnalysisId, onOpenAnalysis, onNewAnalysis }) {
  return (
    <div className="history-report-stack">
      <section className="panel report-page combined-report-page">
        <div className="panel-heading-row">
          <div>
            <div className="panel-title"><FileText size={18} /> Selected Analysis Report</div>
            <p className="muted">Select any saved analysis below, then download its CSV report.</p>
          </div>
          {result && <StatusPill value={result.summary?.status} />}
        </div>
        {result ? (
          <>
            <div className="report-summary">
              <div><small>Road</small><strong>{result.location?.road_name || 'Unavailable'}</strong></div>
              <div><small>Health Score</small><strong>{result.summary?.health_score ?? '—'} / 100</strong></div>
              <div><small>Defects</small><strong>{result.summary?.total_defects ?? 0}</strong></div>
              <div><small>Roughness</small><strong>{result.summary?.roughness_label || 'Unavailable'}</strong></div>
            </div>
            <div className="report-actions">
              <button className="primary-button compact" onClick={() => downloadReport(result)}><Download size={17} /> Download CSV report</button>
            </div>
          </>
        ) : (
          <div className="report-empty">Select a saved analysis below to prepare its report.</div>
        )}
      </section>
      <AnalysisHistoryPage
        surveys={surveys}
        selectedAnalysisId={selectedAnalysisId}
        onOpenAnalysis={onOpenAnalysis}
        onNewAnalysis={onNewAnalysis}
      />
      {result && (
        <div className="unified-dashboard">
          <AnalysisResults result={result} />
          <DefectsPage result={result} />
        </div>
      )}
    </div>
  )
}

function DefectsPage({ result }) {
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')

  if (!result) {
    return (
      <section className="panel defects-page-empty">
        <AlertTriangle size={38} />
        <h2>No analysis selected</h2>
        <p>Select a saved road analysis from History & Reports or analyze a new road video first.</p>
      </section>
    )
  }

  const defects = [...(result.defects || [])].sort((a, b) => b.confidence - a.confidence)
  const location = result.location || {}
  const counts = result.summary?.counts || {}
  const normalizedQuery = query.trim().toLowerCase()
  const filtered = defects.filter((d) => {
    if (filter !== 'all' && d.class_name !== filter) return false
    if (!normalizedQuery) return true
    return [
      CLASS_LABELS[d.class_name] || d.class_name,
      d.road_name,
      location.road_name,
    ].filter(Boolean).join(' ').toLowerCase().includes(normalizedQuery)
  })

  return (
    <div className="defects-page-stack">
      <section className="panel defects-hero">
        <div>
          <div className="panel-title"><AlertTriangle size={18} /> Defect Intelligence</div>
          <p className="muted">Every deduplicated defect from the selected road video, with filters and evidence.</p>
        </div>
        <div className="defect-analysis-context">
          <small>Selected road</small>
          <strong>{location.road_name || 'Location unavailable'}</strong>
          <span>{result.video?.filename || 'Road video'}</span>
        </div>
      </section>

      <div className="defect-summary-grid">
        {Object.entries(CLASS_LABELS).map(([key, label]) => (
          <button
            key={key}
            className={`defect-type-card ${filter === key ? 'selected' : ''}`}
            onClick={() => setFilter(filter === key ? 'all' : key)}
          >
            <span className="defect-type-dot" style={{ background: CLASS_COLORS[key] }} />
            <span><small>{label}</small><strong>{counts[key] || 0}</strong></span>
          </button>
        ))}
      </div>

      <section className="panel defects-workspace">
        <div className="defects-toolbar">
          <div className="search-box"><Search size={16} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search defect type or road" /></div>
          <div className="filter-chips">
            <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>All ({defects.length})</button>
            {Object.entries(CLASS_LABELS).map(([key, label]) => (
              <button key={key} className={filter === key ? 'active' : ''} onClick={() => setFilter(key)}>{label}</button>
            ))}
          </div>
        </div>

        <div className="defects-dedicated-grid">
          <div className="defects-full-table">
            <table>
              <thead><tr><th>#</th><th>Type</th><th>Confidence</th><th>Road</th><th>GPS</th></tr></thead>
              <tbody>
                {filtered.length === 0 && <tr><td colSpan="5" className="empty-cell">No defects match this filter.</td></tr>}
                {filtered.map((d, i) => (
                  <tr key={d.id}>
                    <td>{i + 1}</td>
                    <td><span className="defect-label"><i style={{ background: CLASS_COLORS[d.class_name] }} />{CLASS_LABELS[d.class_name] || d.class_name}</span></td>
                    <td>{(d.confidence * 100).toFixed(1)}%</td>
                    <td>{d.road_name || location.road_name || '—'}</td>
                    <td>{d.latitude != null ? `${d.latitude.toFixed(5)}, ${d.longitude.toFixed(5)}` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="defects-evidence-column">
            <div className="panel-heading-row"><div className="panel-title">Evidence</div><span className="muted small">{filtered.filter(d => d.evidence_url).length} frames</span></div>
            <div className="defects-evidence-list">
              {filtered.filter(d => d.evidence_url).slice(0, 8).map(d => (
                <div className="defect-evidence-row" key={`dedicated-${d.id}`}>
                  <img src={`${API_URL}${d.evidence_url}`} alt={d.class_name} />
                  <span>
                    <strong>{CLASS_LABELS[d.class_name] || d.class_name}</strong>
                    <small>{(d.confidence * 100).toFixed(1)}% confidence</small>
                  </span>
                </div>
              ))}
              {filtered.filter(d => d.evidence_url).length === 0 && <div className="empty-state">No evidence images for this filter.</div>}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

function UnifiedDashboard({ surveys, mapResults, onOpenAnalysis }) {
  return (
    <div className="unified-dashboard">
      <RoadRankings surveys={surveys} onOpenAnalysis={onOpenAnalysis} />

      <section className="panel network-map-panel">
        <div className="panel-heading-row">
          <div>
            <div className="panel-title"><MapIcon size={18} /> All Roads Map</div>
            <p className="muted">Saved road routes are colored by condition so the full network can be compared in one view.</p>
          </div>
          <span className="muted small">{mapResults.length} saved analyses</span>
        </div>
        <PersistentRoadMap surveys={mapResults} />
      </section>
    </div>
  )
}

function VideoAnalysisPage({ result, mode, onNewAnalysis }) {
  const uploaded = mode === 'upload'
  return (
    <div className="unified-dashboard">
      <section className="panel analysis-header">
        <div>
          <div className="panel-title">{uploaded ? 'Uploaded Video Analysis' : 'Recorded Video Analysis'}</div>
          <p className="muted">The latest result stays with the video workflow where it was created.</p>
        </div>
        <button className="primary-button compact" onClick={onNewAnalysis}>
          <RotateCcw size={16} /> {uploaded ? 'Upload another video' : 'Record another video'}
        </button>
      </section>
      <AnalysisResults result={result} />
      <DefectsPage result={result} />
    </div>
  )
}

function Sidebar({ activePage, setActivePage, result, backendHealth }) {
  const items = [
    ['dashboard', LayoutDashboard, 'Dashboard'],
    ['upload', CloudUpload, 'Analyze Road Video'],
    ['record', Smartphone, 'Record Road Video'],
    ['history', FileText, 'History & Reports'],
    ['about', Info, 'About'],
  ]

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark">RP</div>
        <div><strong>RoadPulse</strong><span>AI Road Health Monitor</span></div>
      </div>
      <nav className="sidebar-nav">
        {items.map(([key, Icon, label]) => (
          <button key={key} className={activePage === key ? 'active' : ''} onClick={() => setActivePage(key)}>
            <Icon size={18} /><span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-spacer" />
      <div className="system-card">
        <div className="system-title">System Status</div>
        <div className="system-line"><span className={`status-dot ${backendHealth?.ok ? 'online' : 'offline'}`} />{backendHealth?.ok ? 'Backend online' : 'Backend unavailable'}</div>
        <div className="system-meta"><small>AI Model</small><strong className={backendHealth?.model_loaded ? 'success-text' : 'danger-text'}>{backendHealth?.model_loaded ? 'best.pt loaded' : 'Not loaded'}</strong></div>
        <div className="system-meta"><small>Road</small><strong>{result?.location?.road_name || 'Awaiting analysis'}</strong></div>
      </div>
      <div className="sidebar-footer"><strong>RoadPulse v2</strong><span>Road Condition Intelligence</span></div>
    </aside>
  )
}

function AboutPage() {
  return (
    <section className="panel about-panel">
      <div className="panel-title"><Info size={18} /> About RoadPulse</div>
      <p>RoadPulse combines a trained YOLO road-damage detector, GPS road identification, motion-based roughness estimation and a prototype Road Health Score.</p>
      <div className="about-grid">
        <div><strong>Visible damage</strong><span>Longitudinal cracks, transverse cracks, fatigue cracks and potholes.</span></div>
        <div><strong>Location</strong><span>Embedded video GPS or synchronized phone GPS. Road name is resolved automatically.</span></div>
        <div><strong>Roughness</strong><span>Phone motion sensors when available, otherwise a video-motion proxy. It is not IRI.</span></div>
        <div><strong>Video sampling</strong><span>YOLO analyzes one frame per video second; at 30 FPS it skips 29 frames between detections.</span></div>
      </div>
    </section>
  )
}

function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const [jobId, setJobId] = useState(null)
  const [job, setJob] = useState(null)
  const [pollError, setPollError] = useState('')
  const [backendHealth, setBackendHealth] = useState(null)
  const [surveys, setSurveys] = useState([])
  const [mapResults, setMapResults] = useState([])
  const [selectedResult, setSelectedResult] = useState(null)
  const [selectedSurveyId, setSelectedSurveyId] = useState(null)
  const [historyError, setHistoryError] = useState('')
  const [analysisOrigin, setAnalysisOrigin] = useState(null)


  async function refreshMapResults(rows = null) {
    try {
      const surveyRows = rows || await listSurveys()

      const details = await Promise.all(
          surveyRows.map(async (survey) => {
            try {
              const detail = await getSurvey(survey.survey_id)
              return {
                survey_id: survey.survey_id,
                result: detail.result
              }
            } catch {
              return null
            }
          })
      )

      setMapResults(details.filter(Boolean))
    } catch (e) {
      console.error('Could not load saved road analyses for the map:', e)
    }
  }



  async function refreshSurveys() {
    try {
      const rows = await listSurveys()
      setSurveys(rows)
      await refreshMapResults(rows)
      setHistoryError('')
    } catch (e) {
      setHistoryError(e.message || 'Could not load analysis history.')
    }
  }

  useEffect(() => {
    getHealth().then(setBackendHealth).catch(() => setBackendHealth({ ok: false, model_loaded: false }))
    refreshSurveys()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    const tick = async () => {
      try {
        const data = await getJob(jobId)
        if (!cancelled) {
          setJob(data)
          if (data.status === 'completed') {
            setSelectedResult(null)
            setSelectedSurveyId(data.job_id)
            refreshSurveys().catch(() => {})
          }
          if (!['completed', 'failed'].includes(data.status)) setTimeout(tick, 1000)
        }
      } catch (e) {
        if (!cancelled) setPollError(e.message)
      }
    }
    tick()
    return () => { cancelled = true }
  }, [jobId])

  function newSurvey(page = 'upload') {
    setJobId(null)
    setJob(null)
    setSelectedResult(null)
    setSelectedSurveyId(null)
    setPollError('')
    setAnalysisOrigin(page)
    setActivePage(page)
  }

  function reset() {
    newSurvey('upload')
  }

  function startJob(id, page) {
    setSelectedResult(null)
    setSelectedSurveyId(null)
    setJobId(id)
    setJob(null)
    setPollError('')
    setAnalysisOrigin(page)
    setActivePage(page)
  }

  async function openSurvey(id, page = 'history') {
    try {
      const detail = await getSurvey(id)
      setJobId(null)
      setJob(null)
      setSelectedSurveyId(id)
      setSelectedResult(detail.result)
      setPollError('')
      setAnalysisOrigin('history')
      setActivePage(page)
    } catch (e) {
      setHistoryError(e.message || 'Could not open the saved analysis.')
    }
  }

  const result = selectedResult || (job?.status === 'completed' ? job.result : null)
  const analyzing = jobId && job?.status !== 'completed' && job?.status !== 'failed'

  function renderMain() {
    if (analyzing && activePage === analysisOrigin) return <AnalysisProgress job={job} jobId={jobId} onReset={reset} />
    if (job?.status === 'failed' && activePage === analysisOrigin) {
      return (
        <section className="panel failed-panel">
          <XCircle size={36} />
          <h2>Analysis failed</h2>
          <p>{job.error || 'Unknown error'}</p>
          <button className="primary-button compact" onClick={reset}>Analyze another video</button>
        </section>
      )
    }

    if (activePage === 'upload') {
      return result && analysisOrigin === 'upload'
        ? <VideoAnalysisPage result={result} mode="upload" onNewAnalysis={() => newSurvey('upload')} />
        : <UploadSurvey onStarted={(id) => startJob(id, 'upload')} />
    }
    if (activePage === 'record') {
      return result && analysisOrigin === 'record'
        ? <VideoAnalysisPage result={result} mode="record" onNewAnalysis={() => newSurvey('record')} />
        : <RecordSurvey onStarted={(id) => startJob(id, 'record')} />
    }
    if (activePage === 'about') return <AboutPage />

    if (activePage === 'history') {
      return (
        <HistoryReportsPage
          surveys={surveys}
          result={analysisOrigin === 'history' ? result : null}
          selectedAnalysisId={selectedSurveyId}
          onOpenAnalysis={(id) => openSurvey(id, 'history')}
          onNewAnalysis={() => newSurvey('upload')}
        />
      )
    }

    return (
      <UnifiedDashboard
        surveys={surveys}
        mapResults={mapResults}
        onOpenAnalysis={(id) => openSurvey(id, 'history')}
      />
    )
  }

  const pageTitle = activePage === 'dashboard'
    ? 'Dashboard'
    : activePage === 'upload'
      ? 'Analyze Road Video'
      : activePage === 'record'
        ? 'Record Road Video'
        : activePage === 'history'
          ? 'History & Reports'
          : 'About'

  return (
    <div className="app-shell">
      <Sidebar activePage={activePage} setActivePage={setActivePage} result={result} backendHealth={backendHealth} />
      <div className="app-main">
        <header className="topbar">
          <div>
            <h1>{pageTitle}</h1>
            <p>Monitor, detect and improve road conditions</p>
          </div>
          <div className="top-actions">
            <div className="live-chip"><span /> {backendHealth?.ok ? 'System online' : 'Checking system'}</div>
            {result && activePage === 'history' && analysisOrigin === 'history' && (
              <button className="ghost-button compact" onClick={() => newSurvey('upload')}><RotateCcw size={15} /> New Video Analysis</button>
            )}
          </div>
        </header>
        <main className="main-content">
          {pollError && <div className="error-box">{pollError}</div>}
          {historyError && <div className="error-box">{historyError}</div>}
          {renderMain()}
        </main>
      </div>
    </div>
  )
}

export default App
