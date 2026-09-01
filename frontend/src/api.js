import axios from 'axios'

// The deployment marker means "use this page's origin". Codespaces then sends
// /api and /evidence through Vite's proxy instead of trying to reach localhost
// on the visitor's computer.
const configuredApiUrl = import.meta.env.VITE_API_URL
export const API_URL = configuredApiUrl === 'same-origin' ? '' : (configuredApiUrl ?? '')

export async function createAnalysisJob({ videoFile, gpsFile, motionFile, onUploadProgress }) {
  const form = new FormData()
  form.append('video', videoFile)
  if (gpsFile) form.append('gps_json', gpsFile)
  if (motionFile) form.append('motion_json', motionFile)

  const response = await axios.post(`${API_URL}/api/jobs/analysis`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: event => {
      if (!onUploadProgress) return
      if (!event.total) return onUploadProgress(null)
      onUploadProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
    },
  })
  return response.data
}

export async function getJob(jobId) {
  const response = await axios.get(`${API_URL}/api/jobs/${jobId}`)
  return response.data
}

export async function getHealth() {
  const response = await axios.get(`${API_URL}/api/health`)
  return response.data
}

export async function listSurveys(limit = 100) {
  const response = await axios.get(`${API_URL}/api/surveys`, { params: { limit } })
  return response.data.surveys || []
}

export async function getSurvey(surveyId) {
  const response = await axios.get(`${API_URL}/api/surveys/${surveyId}`)
  return response.data
}
