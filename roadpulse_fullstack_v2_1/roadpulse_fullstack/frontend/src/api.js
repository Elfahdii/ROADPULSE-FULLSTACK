import axios from 'axios'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function createAnalysisJob({ videoFile, gpsFile, motionFile }) {
  const form = new FormData()
  form.append('video', videoFile)
  if (gpsFile) form.append('gps_json', gpsFile)
  if (motionFile) form.append('motion_json', motionFile)

  const response = await axios.post(`${API_URL}/api/jobs/analysis`, form, {
    headers: { 'Content-Type': 'multipart/form-data' }
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
